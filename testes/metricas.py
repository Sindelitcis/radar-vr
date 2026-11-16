"""Medicao de latencia e taxa de sucesso do Radar VR.

Cada execucao roda o fluxo completo pelo n8n, como no agendamento diario, e
grava uma linha em evidencias/metricas_execucoes.jsonl com:

    - o resultado e a duracao que o n8n registrou, do fluxo e de cada no;
    - o tempo de cada etapa da edicao, medido pelo microsservico;
    - o resultado de cada envio (canal, status, tentativas, latencia);
    - o contexto da maquina: carga do processador, uso e consumo da placa de
      video, e se o modelo ja estava carregado no Ollama.

Nenhum contato de assinante entra no registro.

    python testes/metricas.py campanha 30   30 execucoes seguidas, em ensaio
    python testes/metricas.py uma           uma execucao em ensaio (agendador)
    python testes/metricas.py real 5        envio real, com historico fixo

Em ensaio (RADAR_DRY_RUN=1) nenhuma mensagem sai da maquina. No modo real o
historico nao e gravado (RADAR_HISTORICO_FIXO=1): as novidades do dia se
repetem a cada execucao, para medir o envio sem consumi-las.

O microsservico sobe em porta e banco proprios, copiados do banco real a cada
execucao: a medicao parte sempre da mesma leitura anterior e nao altera o
historico do boletim.
"""
import ctypes
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
PORTA = 8798
URL = f"http://127.0.0.1:{PORTA}"
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODELO = "llama3.1:8b"
FLUXO = "radarVRetapa2001"
BANCO = "metricas.db"
SAIDA = RAIZ / "evidencias" / "metricas_execucoes.jsonl"
TRAVA = RAIZ / "data" / "metricas.lock"
TIPOS_REDIGIDOS = {"PATCH_GRANDE"}
# Pelo agendador o script roda sem janela (pythonw); os processos filhos tambem.
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
if sys.stdout is None:
    sys.stdout = sys.stderr = open(os.devnull, "w")
# Folga entre execucoes seguidas, para nao pressionar a Steam.
PAUSA_CAMPANHA_S = 15
NOS_ENVIO = ("Enviar boletim por e-mail", "Enviar alerta instantâneo")


# ------------------------------------------------------------- contexto

def _tempos_cpu():
    """(ocioso, total) do sistema inteiro, em unidades de 100 ns."""
    ocioso, nucleo, usuario = ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong()
    ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(ocioso), ctypes.byref(nucleo), ctypes.byref(usuario))
    return ocioso.value, nucleo.value + usuario.value  # o tempo de nucleo inclui o ocioso


def _gpu():
    """(uso %, potencia W) da placa de video, ou None sem nvidia-smi."""
    try:
        saida = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, creationflags=SEM_JANELA,
        ).stdout.strip().splitlines()[0]
        uso, potencia = (float(v) for v in saida.split(","))
        return uso, potencia
    except Exception:
        return None


class AmostraGPU(threading.Thread):
    """Le uso e consumo da placa a cada 2 s enquanto a execucao roda."""

    def __init__(self):
        super().__init__(daemon=True)
        self.parar = threading.Event()
        self.leituras = []

    def run(self):
        while not self.parar.is_set():
            leitura = _gpu()
            if leitura:
                self.leituras.append(leitura)
            self.parar.wait(2)

    def resumo(self):
        self.parar.set()
        if not self.leituras:
            return {}
        usos = [u for u, _ in self.leituras]
        potencias = [p for _, p in self.leituras]
        return {
            "gpu_uso_medio_pct": round(sum(usos) / len(usos), 1),
            "gpu_w_medio": round(sum(potencias) / len(potencias), 1),
            "gpu_w_max": round(max(potencias), 1),
        }


def _ollama():
    """Estado do Ollama antes da execucao."""
    estado = {"ollama_no_ar": False, "modelo_instalado": False, "modelo_carregado": False}
    try:
        modelos = requests.get(f"{OLLAMA}/api/tags", timeout=3).json().get("models", [])
        estado["ollama_no_ar"] = True
        estado["modelo_instalado"] = any(m["name"] == MODELO for m in modelos)
        ativos = requests.get(f"{OLLAMA}/api/ps", timeout=3).json().get("models", [])
        estado["modelo_carregado"] = any(m["name"] == MODELO for m in ativos)
    except Exception:
        pass
    return estado


# ------------------------------------------------------------- execucao

def _copiar_banco():
    """Copia consistente do banco real (que fica em modo WAL)."""
    destino = RAIZ / "data" / BANCO
    # O microsservico da execucao anterior pode levar alguns segundos para
    # soltar o arquivo depois de encerrado.
    for tentativa in range(40):
        try:
            for sufixo in ("", "-wal", "-shm"):
                Path(str(destino) + sufixo).unlink(missing_ok=True)
            break
        except PermissionError:
            if tentativa == 39:
                raise
            time.sleep(0.5)
    origem = RAIZ / "data" / "jornal_vr.db"
    if not origem.exists():
        return
    de, para = sqlite3.connect(origem), sqlite3.connect(destino)
    try:
        de.backup(para)
    finally:
        de.close()
        para.close()


class Servico:
    def __init__(self, real):
        self.env = {**os.environ, "RADAR_PORTA": str(PORTA), "RADAR_DB": BANCO,
                    "RADAR_FALHAR_CANAIS": ""}
        if real:
            self.env.update(RADAR_DRY_RUN="0", RADAR_HISTORICO_FIXO="1")
        else:
            self.env.update(RADAR_DRY_RUN="1")

    def __enter__(self):
        self.processo = subprocess.Popen(
            [PYTHON, str(RAIZ / "src" / "servico.py")], env=self.env, cwd=RAIZ,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=SEM_JANELA,
        )
        for _ in range(150):
            try:
                requests.get(f"{URL}/saude", timeout=5)
                return self
            except requests.ConnectionError:
                time.sleep(0.2)
        self.processo.terminate()
        raise RuntimeError("microsserviço não subiu")

    def __exit__(self, *_):
        # O python.exe do ambiente virtual e um lancador: o interpretador de
        # verdade e um processo filho. O taskkill encerra os dois.
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.processo.pid)],
                       capture_output=True, creationflags=SEM_JANELA)
        self.processo.wait(timeout=15)


def _rodar_n8n():
    """Executa o fluxo pela linha de comando e devolve o registro do n8n."""
    env = {
        **os.environ,
        "N8N_ENCRYPTION_KEY": "radar-vr-pucpr-etapa1",
        "NODES_EXCLUDE": "[]",
        "N8N_RESTRICT_FILE_ACCESS_TO": str(RAIZ) + os.sep,
        "N8N_BLOCK_FILE_ACCESS_TO_N8N_FILES": "false",
        "N8N_BLOCK_ENV_ACCESS_IN_NODE": "false",
        "N8N_DIAGNOSTICS_ENABLED": "false",
        "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
        "N8N_SECURE_COOKIE": "false",
        "RADAR_DIR_LOGS": str(RAIZ / "logs"),
        "RADAR_SERVICO_URL": URL,
        "RADAR_REAPROVEITAR_EDICAO": "",
    }
    processo = subprocess.run(
        f"n8n execute --id={FLUXO} --rawOutput",
        shell=True, env=env, cwd=RAIZ, capture_output=True, timeout=900,
        creationflags=SEM_JANELA,
    )
    texto = processo.stdout.decode("utf-8", "replace")
    # Antes do JSON o n8n pode imprimir avisos de inicializacao.
    inicio = texto.find("{")
    while inicio >= 0:
        try:
            return json.loads(texto[inicio:texto.rfind("}") + 1])
        except ValueError:
            inicio = texto.find("\n{", inicio + 1)
            inicio = inicio + 1 if inicio >= 0 else -1
    erro = processo.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
    raise RuntimeError("n8n sem registro de execução: " + " | ".join(erro)[:300])


def _ms(inicio_iso, fim_iso):
    formato = "%Y-%m-%dT%H:%M:%S.%f%z"
    inicio = datetime.strptime(inicio_iso.replace("Z", "+0000"), formato)
    fim = datetime.strptime(fim_iso.replace("Z", "+0000"), formato)
    return round((fim - inicio).total_seconds() * 1000)


def _itens(no_execucoes):
    """(ramo, json) de cada item que saiu do no, em todas as passagens."""
    for passagem in no_execucoes:
        for ramo, itens in enumerate((passagem.get("data") or {}).get("main") or []):
            for item in itens or []:
                yield ramo, item.get("json", {})


def _com_avaliacao(edicao_id):
    """Titulos da edicao que vieram com os dados de avaliacoes da Steam.

    A resposta de /edicao nao traz o catalogo; ele fica no arquivo da edicao.
    """
    try:
        edicao = json.loads((RAIZ / "data" / "edicao_atual.json").read_text(encoding="utf-8"))
        if edicao.get("id") != edicao_id:
            return None
        return sum(j.get("aprovacao_pct") is not None for j in edicao["catalogo"])
    except Exception:
        return None


def _resumir(registro):
    """Extrai do registro do n8n o que a analise usa. Nada de contato."""
    nos = registro["data"]["resultData"]["runData"]
    resumo = {
        "status": registro.get("status"),
        "fluxo_ms": _ms(registro["startedAt"], registro["stoppedAt"]),
        "nos": {
            nome: {
                "ms": sum(p.get("executionTime", 0) for p in passagens),
                "status": passagens[-1].get("executionStatus"),
            }
            for nome, passagens in nos.items()
        },
        "envios": [],
    }

    edicao = next((dados for ramo, dados in _itens(nos.get("Gerar edição", []))
                   if ramo == 0 and "tempos" in dados), None)
    if edicao:
        redigidas = [m for m in edicao["manchetes"] if m["tipo"] in TIPOS_REDIGIDOS]
        resumo.update(
            edicao_id=edicao["id"],
            etapas_s=edicao["tempos"],
            titulos=edicao["titulos_observados"],
            manchetes=len(edicao["manchetes"]),
            audio=bool(edicao.get("audio")),
            anuncios=len(redigidas),
            anuncios_pelo_llm=sum(m.get("origem_linha") == "llm" for m in redigidas),
        )
        resumo["titulos_com_avaliacao"] = _com_avaliacao(edicao["id"])
        # Completa: o fluxo terminou sem erro e nenhuma parte saiu pela metade
        # (sem audio, sem o resumo do modelo ou sem os dados de avaliacoes).
        resumo["completa"] = (
            resumo["status"] == "success" and resumo["audio"]
            and resumo["anuncios_pelo_llm"] == resumo["anuncios"]
            and resumo["titulos_com_avaliacao"] == resumo["titulos"]
        )
    else:
        resumo["completa"] = False

    for no in NOS_ENVIO:
        for ramo, dados in _itens(nos.get(no, [])):
            if ramo == 0 and "status" in dados:
                resumo["envios"].append({
                    "canal": dados.get("canal"), "status": dados["status"],
                    "tentativas": dados.get("tentativas"),
                    "latencia_ms": dados.get("latencia_ms"),
                })
            else:  # saida de erro do no: o envio falhou depois das tentativas
                resumo["envios"].append({
                    "canal": "email" if no == NOS_ENVIO[0] else "instantaneo",
                    "status": "falhou",
                    "erro": str((dados.get("error") or {}).get("message", ""))[:120]
                    if isinstance(dados.get("error"), dict)
                    else str(dados.get("error", ""))[:120],
                })
    return resumo


def executar(origem, real=False):
    linha = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "origem": origem,
        "modo": "real" if real else "ensaio",
        **_ollama(),
    }
    antes_gpu = _gpu()
    if antes_gpu:
        linha["gpu_uso_antes_pct"] = antes_gpu[0]
    ocioso0, total0 = _tempos_cpu()
    amostra = AmostraGPU()
    amostra.start()
    inicio = time.perf_counter()
    try:
        _copiar_banco()
        with Servico(real):
            linha.update(_resumir(_rodar_n8n()))
    except Exception as erro:
        linha.update(status="error", completa=False,
                     erro=f"{type(erro).__name__}: {erro}"[:300])
    linha["relogio_s"] = round(time.perf_counter() - inicio, 1)
    ocioso1, total1 = _tempos_cpu()
    if total1 > total0:
        linha["cpu_ocupada_pct"] = round(
            100 * (1 - (ocioso1 - ocioso0) / (total1 - total0)), 1)
    linha.update(amostra.resumo())

    SAIDA.parent.mkdir(exist_ok=True)
    with open(SAIDA, "a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
    etapas = linha.get("etapas_s", {})
    print(f"{linha['ts']}  {linha['status']:<8} fluxo {linha.get('fluxo_ms', 0) / 1000:5.1f} s"
          f"  edição {etapas.get('total', 0):5.1f} s"
          f"  completa={linha['completa']}  envios={len(linha.get('envios', []))}",
          flush=True)
    return linha


def _n8n_aberto():
    try:
        socket.create_connection(("127.0.0.1", 5678), timeout=1).close()
        return True
    except OSError:
        return False


def _com_trava(funcao):
    """Uma medicao por vez: a agendada nao roda por cima da campanha."""
    if _n8n_aberto():
        # O editor do n8n e o `n8n execute` disputam a mesma porta interna. Com
        # o editor aberto a execucao falharia por causa da medicao, nao do fluxo.
        print("editor do n8n aberto; medição adiada")
        return
    if TRAVA.exists() and time.time() - TRAVA.stat().st_mtime < 20 * 60:
        print("outra medição em curso; nada feito")
        return
    TRAVA.write_text(str(os.getpid()))
    try:
        funcao()
    finally:
        TRAVA.unlink(missing_ok=True)


def main():
    comando = sys.argv[1] if len(sys.argv) > 1 else "uma"
    vezes = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    if comando == "uma":
        _com_trava(lambda: executar("agendada"))
    elif comando == "campanha":
        def campanha():
            for _ in range(vezes):
                executar("campanha")
                TRAVA.touch()
                time.sleep(PAUSA_CAMPANHA_S)
        _com_trava(campanha)
    elif comando == "real":
        def reais():
            for _ in range(vezes):
                executar("real", real=True)
                TRAVA.touch()
        _com_trava(reais)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
