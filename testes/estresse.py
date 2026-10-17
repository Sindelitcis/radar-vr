"""Testes de carga e de falha do Radar VR.

Cada cenario sobe o microsservico em um processo proprio, com DRY_RUN ligado:
nenhuma mensagem real sai da maquina durante os testes.

    python testes/estresse.py                 todos os cenarios
    python testes/estresse.py personalizacao  so um cenario

Resultados em evidencias/estresse.json; a leitura esta em docs/07_testes.md.
"""
import itertools
import json
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
PYTHON = sys.executable
PORTA = 8799
URL = f"http://127.0.0.1:{PORTA}"
SAIDA = RAIZ / "evidencias" / "estresse.json"

GENEROS = ["Ação", "Aventura", "Casual", "Simulação", "Indie", "Esportes"]


def percentil(valores, p):
    if not valores:
        return None
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p / 100
    baixo, alto = int(k), min(int(k) + 1, len(ordenados) - 1)
    return round(ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (k - baixo), 1)


def estatisticas(latencias_ms):
    return {
        "n": len(latencias_ms),
        "p50_ms": percentil(latencias_ms, 50),
        "p95_ms": percentil(latencias_ms, 95),
        "p99_ms": percentil(latencias_ms, 99),
        "max_ms": round(max(latencias_ms), 1) if latencias_ms else None,
    }


class Servico:
    """Microsservico em processo separado, com variaveis de ambiente proprias."""

    def __init__(self, **env):
        self.env = {**os.environ, "RADAR_DRY_RUN": "1", "RADAR_PORTA": str(PORTA),
                    "RADAR_DB": "estresse.db",
                    **{k: str(v) for k, v in env.items()}}

    def __enter__(self):
        self.processo = subprocess.Popen(
            [PYTHON, str(RAIZ / "src" / "servico.py")], env=self.env, cwd=RAIZ,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                requests.get(f"{URL}/saude", timeout=5)
                return self
            except requests.ConnectionError:
                time.sleep(0.2)
        raise RuntimeError("serviço não subiu")

    def __exit__(self, *_):
        self.processo.terminate()
        self.processo.wait(timeout=10)


def perfis_sinteticos(quantidade, edicao):
    """Assinantes ficticios com interesses combinados a partir do catalogo real.

    Os interesses se repetem como numa base real: muita gente segue os
    mesmos jogos populares.
    """
    appids = [j["appid"] for j in edicao["catalogo"]]
    combinacoes = list(itertools.product(
        [GENEROS[i:i + 2] for i in range(0, len(GENEROS), 2)],
        [appids[i:i + 3] for i in range(0, 9, 3)],
    ))
    perfis = []
    for i in range(quantidade):
        generos, jogos = combinacoes[i % len(combinacoes)]
        perfis.append({
            "id": f"carga{i:04d}", "nome": f"Assinante {i}",
            "email": f"carga{i:04d}@exemplo.invalid",
            "instantaneo": {"canal": "telegram", "destino": str(100000 + i)},
            "jogos": jogos, "generos": generos, "orcamento": 100,
            "consentimento": "2026-10-17",
        })
    return perfis


# --------------------------------------------------------------- cenarios

def cenario_coleta():
    """Coleta sequencial (Etapa 1) contra coleta paralela com ritmo compartilhado."""
    import coleta
    import jornal

    jornal.configurar_log()
    resultado = {}
    for paralelo in (1, 4):
        tempos = []
        for _ in range(3):
            inicio = time.perf_counter()
            catalogo = coleta.coletar(15, paralelo=paralelo)
            tempos.append(round(time.perf_counter() - inicio, 1))
        resultado[f"paralelo_{paralelo}"] = {
            "execucoes_s": tempos,
            "mediana_s": statistics.median(tempos),
            "titulos": len(catalogo),
        }
        print(f"  coleta paralelo={paralelo}: {resultado[f'paralelo_{paralelo}']}")
    return resultado


def cenario_personalizacao():
    """Assinantes por segundo, antes e depois do cache de redacao."""
    edicao = json.loads((RAIZ / "data" / "edicao_atual.json").read_text(encoding="utf-8"))
    configuracoes = {
        "antes": {"RADAR_CACHE_REDACAO": "0", "RADAR_PERSONALIZACAO_PARALELA": "1"},
        "depois": {"RADAR_CACHE_REDACAO": "1", "RADAR_PERSONALIZACAO_PARALELA": "4"},
    }
    resultado = {}
    for rotulo, env in configuracoes.items():
        resultado[rotulo] = {}
        for quantidade in (10, 50, 100):
            with Servico(**env):
                perfis = perfis_sinteticos(quantidade, edicao)
                inicio = time.perf_counter()
                resposta = requests.post(f"{URL}/personalizar",
                                         json={"perfis": ["-"], "perfis_extras": perfis,
                                               "todos": True}, timeout=3600)
                segundos = time.perf_counter() - inicio
                envelopes = resposta.json()
                metricas = requests.get(f"{URL}/metricas", timeout=10).json()
            linha = {
                "assinantes": quantidade,
                "segundos": round(segundos, 1),
                "assinantes_por_s": round(quantidade / segundos, 2),
                "chamadas_llm": metricas["llm"],
                "acertos_cache": metricas["cache"],
                "pela_regra": metricas["regra"],
                "com_email": sum(1 for e in envelopes if e["email"]),
                "com_alerta": sum(1 for e in envelopes if e["instantaneo"]),
            }
            resultado[rotulo][quantidade] = linha
            print(f"  {rotulo:6} {linha}")
    return resultado


def _disparar(rota, corpos, concorrencia):
    sessao = requests.Session()

    def um(corpo):
        inicio = time.perf_counter()
        try:
            resposta = sessao.post(f"{URL}{rota}", json=corpo, timeout=60)
            return (time.perf_counter() - inicio) * 1000, resposta.status_code, resposta.json()
        except Exception as erro:
            return (time.perf_counter() - inicio) * 1000, 0, {"erro": str(erro)}

    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concorrencia) as executor:
        respostas = list(executor.map(um, corpos))
    total = time.perf_counter() - inicio
    return respostas, total


def cenario_envio():
    """Vazao do endpoint de envio sob concorrencia crescente."""
    resultado = {}
    with Servico():
        for concorrencia in (1, 10, 50):
            corpos = [{
                "edicao_id": f"carga-c{concorrencia}", "perfil_id": f"p{i}",
                "para": f"p{i}@exemplo.invalid", "assunto": "teste", "html": "<p>teste</p>",
            } for i in range(500)]
            respostas, total = _disparar("/enviar/email", corpos, concorrencia)
            latencias = [r[0] for r in respostas]
            erros = sum(1 for r in respostas if r[1] != 200)
            linha = {
                "requisicoes": len(corpos),
                "concorrencia": concorrencia,
                "req_por_s": round(len(corpos) / total, 1),
                "erros": erros,
                **estatisticas(latencias),
            }
            resultado[concorrencia] = linha
            print(f"  envio c={concorrencia}: {linha}")
    return resultado


def cenario_idempotencia():
    """50 requisicoes simultaneas identicas devem gerar um unico envio."""
    with Servico():
        corpo = {"edicao_id": "carga-idem", "perfil_id": "unico",
                 "para": "unico@exemplo.invalid", "assunto": "teste", "html": "<p>x</p>"}
        respostas, _ = _disparar("/enviar/email", [corpo] * 50, 50)
    contagem = {}
    for _, _, corpo_resposta in respostas:
        contagem[corpo_resposta.get("status")] = contagem.get(corpo_resposta.get("status"), 0) + 1
    print(f"  idempotência: {contagem}")
    return contagem


def cenario_falhas():
    """Comportamento com dependencias fora do ar."""
    edicao = json.loads((RAIZ / "data" / "edicao_atual.json").read_text(encoding="utf-8"))
    perfis = perfis_sinteticos(20, edicao)
    resultado = {}

    with Servico(OLLAMA_URL="http://127.0.0.1:9", RADAR_CACHE_REDACAO="0"):
        inicio = time.perf_counter()
        envelopes = requests.post(f"{URL}/personalizar", timeout=600, json={
            "perfis": ["-"], "perfis_extras": perfis, "todos": True}).json()
        resultado["llm_fora_do_ar"] = {
            "assinantes": len(perfis),
            "segundos": round(time.perf_counter() - inicio, 1),
            "envelopes_validos": sum(1 for e in envelopes if e["email"]),
            "origem": sorted({e["origem_texto"] for e in envelopes}),
        }

    with Servico(RADAR_FALHAR_CANAIS="telegram"):
        resposta = requests.post(f"{URL}/enviar/instantaneo", timeout=60, json={
            "edicao_id": "carga-falha", "perfil_id": "x", "canal": "telegram",
            "destino": "1", "texto": "teste"})
        resultado["canal_fora_do_ar"] = {"http": resposta.status_code, **resposta.json()}

    with Servico():
        resposta = requests.post(f"{URL}/enviar/email", timeout=60, json={"perfil_id": "x"})
        resultado["corpo_invalido"] = {"http": resposta.status_code, **resposta.json()}
        resposta = requests.post(f"{URL}/enviar/email", timeout=60, json={
            "edicao_id": "e", "perfil_id": "x", "para": "a@b", "assunto": "s",
            "html": "h", "anexo": "../../.env"})
        resultado["anexo_fora_da_pasta"] = {"http": resposta.status_code, **resposta.json()}

    for chave, valor in resultado.items():
        print(f"  {chave}: {valor}")
    return resultado


def cenario_ipv6():
    """Latencia de conexao nova ate a API do Telegram, com e sem IPv6."""
    codigo = "\n".join([
        "import sys, time, requests",
        "import urllib3.util.connection as conexao",
        "conexao.HAS_IPV6 = sys.argv[1] == '1'",
        "tempos = []",
        "for _ in range(3):",
        "    inicio = time.perf_counter()",
        "    requests.get('https://api.telegram.org', timeout=60)",
        "    tempos.append(round((time.perf_counter() - inicio) * 1000))",
        "print(tempos)",
    ])
    resultado = {}
    for rotulo, ipv6 in (("com_ipv6", "1"), ("somente_ipv4", "0")):
        saida = subprocess.run([PYTHON, "-c", codigo, ipv6], capture_output=True, text=True)
        resultado[rotulo] = json.loads(saida.stdout.strip() or "[]")
        print(f"  telegram {rotulo}: {resultado[rotulo]} ms")
    return resultado


CENARIOS = {
    "coleta": cenario_coleta,
    "personalizacao": cenario_personalizacao,
    "envio": cenario_envio,
    "idempotencia": cenario_idempotencia,
    "falhas": cenario_falhas,
    "ipv6": cenario_ipv6,
}


def main():
    escolhidos = sys.argv[1:] or list(CENARIOS)
    resultados = json.loads(SAIDA.read_text(encoding="utf-8")) if SAIDA.exists() else {}
    for nome in escolhidos:
        print(f"[{nome}]")
        resultados[nome] = {"executado_em": time.strftime("%Y-%m-%d %H:%M"),
                            **CENARIOS[nome]()}
        SAIDA.parent.mkdir(exist_ok=True)
        SAIDA.write_text(json.dumps(resultados, ensure_ascii=False, indent=2),
                         encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
