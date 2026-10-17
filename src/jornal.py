"""Radar VR - boletim diario do catalogo de realidade virtual da Steam.

    coleta  ->  deteccao de eventos  ->  redacao e voz  ->  publicacao
                + serie historica

Uso:
    python src/jornal.py
    python src/jornal.py --titulos 8
    python src/jornal.py --sem-audio
"""
import argparse
import csv
import json
import logging
import sys
import time
from datetime import datetime

import boletim_html
import coleta
import config
import historico
import itad
import noticias
import redacao
import voz

COLUNAS = [
    "publicada_em", "posicao", "secao", "tipo", "score", "appid", "nome",
    "preco", "preco_cheio", "desconto", "linha", "url",
]


def configurar_log():
    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-10s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formato)
    arquivo = logging.FileHandler(config.ARQ_LOG, encoding="utf-8")
    arquivo.setFormatter(formato)

    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.handlers.clear()
    raiz.addHandler(console)
    raiz.addHandler(arquivo)
    return logging.getLogger("jornal")


def gravar_csv(eventos):
    carimbo = datetime.now().isoformat(timespec="seconds")
    novo = not config.ARQ_CSV.exists()
    with open(config.ARQ_CSV, "a", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS, delimiter=";")
        if novo:
            escritor.writeheader()
        for posicao, evento in enumerate(eventos, 1):
            escritor.writerow({
                "publicada_em": carimbo,
                "posicao": posicao,
                **{c: evento.get(c, "") for c in COLUNAS
                   if c not in ("publicada_em", "posicao")},
            })


def _resumo_jogo(jogo):
    campos = ("appid", "nome", "preco", "preco_cheio", "preco_num", "desconto",
              "generos", "jogadores_online", "aprovacao_pct", "url", "itad")
    return {c: jogo.get(c) for c in campos}


def publicar(titulos=None, gerar_audio=True, extras=()):
    """Gera uma edicao completa e devolve seu conteudo estruturado.

    O dicionario devolvido e o contrato com o microsservico e o n8n; a mesma
    estrutura fica gravada em data/edicao_atual.json.
    """
    log = logging.getLogger("jornal")
    inicio = time.perf_counter()
    tempos = {}

    def marcar(etapa, desde):
        tempos[etapa] = round(time.perf_counter() - desde, 2)
        return time.perf_counter()

    log.info("=" * 72)
    log.info("RADAR VR | %s", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    log.info("=" * 72)

    conexao = historico.conectar()
    anterior, momento = historico.snapshot_anterior(conexao)
    primeira_edicao = historico.contar_execucoes(conexao) == 0

    if primeira_edicao:
        log.info("Primeira edição: estabelecendo a linha de base.")
    else:
        log.info("Comparando com a leitura de %s", momento)

    passo = time.perf_counter()
    catalogo = coleta.coletar(titulos, extras)
    passo = marcar("coleta", passo)
    if not catalogo:
        conexao.close()
        raise RuntimeError("Nenhum título coletado. Edição abortada.")

    itad.enriquecer(catalogo)
    passo = marcar("historico_precos", passo)

    selecionados, todos = noticias.detectar(conexao, catalogo, anterior)
    historico.gravar_snapshot(conexao, catalogo)
    passo = marcar("deteccao", passo)

    if selecionados:
        redacao.redigir(selecionados)
    else:
        log.info("=== ETAPA 3/4 | Sem eventos para redigir ===")
    for evento in todos:
        evento.setdefault("linha", f"{evento['nome']} {evento['resumo']}")
    passo = marcar("redacao", passo)

    roteiro = voz.montar_roteiro(selecionados, len(catalogo), primeira_edicao)
    (config.DIR_AUDIO / "ultimo_boletim.txt").write_text(roteiro, encoding="utf-8")

    caminho_audio, duracao, voz_usada = "", 0, "-"
    if gerar_audio:
        try:
            destino, duracao, voz_usada = voz.sintetizar(roteiro)
            caminho_audio = destino.name
        except Exception as erro:
            log.error("Síntese de voz falhou: %s", erro)
    else:
        log.info("=== Síntese de voz ignorada ===")
    passo = marcar("voz", passo)

    log.info("=== ETAPA 4/4 | Publicação ===")
    gravar_csv(selecionados)
    log.info("  CSV    -> %s (%d manchetes)", config.ARQ_CSV.name, len(selecionados))
    pagina = boletim_html.gerar(
        selecionados, len(catalogo), primeira_edicao, caminho_audio
    )

    historico.registrar_edicao(
        conexao, len(catalogo), len(todos), caminho_audio, pagina.name
    )
    marcados = historico.registrar_noticias(conexao, selecionados)
    podados = historico.podar_noticias(conexao)
    memoria = conexao.execute(
        "SELECT COUNT(*) FROM noticias_publicadas"
    ).fetchone()[0]
    leituras = conexao.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    conexao.close()
    marcar("publicacao", passo)
    tempos["total"] = round(time.perf_counter() - inicio, 2)

    log.info("  SQLite -> %s (%d leituras acumuladas)", config.ARQ_DB.name, leituras)
    log.info("  Memória-> %d anúncios marcados, %d expirados, %d retidos",
             marcados, podados, memoria)

    agora = datetime.now()
    edicao = {
        "id": agora.strftime("%Y-%m-%dT%H-%M-%S"),
        "publicada_em": agora.isoformat(timespec="seconds"),
        "primeira_edicao": primeira_edicao,
        "titulos_observados": len(catalogo),
        "manchetes": selecionados,
        "eventos": todos,
        "catalogo": [_resumo_jogo(j) for j in catalogo],
        "audio": caminho_audio,
        "pagina": pagina.name,
        "tempos": tempos,
    }
    config.ARQ_EDICAO.write_text(
        json.dumps(edicao, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )

    log.info("=" * 72)
    log.info("EDIÇÃO PUBLICADA em %.1f s", tempos["total"])
    log.info("  Coleta ..... %d títulos observados (%.1f s)", len(catalogo), tempos["coleta"])
    log.info("  Eventos .... %d detectados, %d no boletim", len(todos),
             len(selecionados))
    log.info("  Voz ........ %s (%.1f s, voz %s)",
             caminho_audio or "não gerado", duracao, voz_usada)
    log.info("  Publicação . %s + %s + %s",
             config.ARQ_CSV.name, config.ARQ_DB.name, pagina.name)
    log.info("=" * 72)
    return edicao


def executar(titulos=None, gerar_audio=True):
    log = configurar_log()
    try:
        edicao = publicar(titulos, gerar_audio)
    except RuntimeError as erro:
        log.error("%s", erro)
        return 1

    print("\nEDIÇÃO DE HOJE")
    print("-" * 72)
    if not edicao["manchetes"]:
        print("  Catálogo estável: nenhuma movimentação relevante.")
    for posicao, evento in enumerate(edicao["manchetes"], 1):
        marca = "MANCHETE" if posicao == 1 else evento["secao"].upper()
        print(f"  [{marca:<9}] {evento.get('linha', evento['resumo'])[:78]}")
    print("-" * 72)
    if edicao["audio"]:
        print(f"  Áudio ...: audio/{edicao['audio']}")
    print(f"  Leitura .: data/{config.ARQ_HTML.name}")
    print(f"  Planilha : data/{config.ARQ_CSV.name}")
    return 0


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(
        description="Radar VR - boletim diário de realidade virtual na Steam"
    )
    argumentos.add_argument("--titulos", type=int, help="tamanho da watchlist")
    argumentos.add_argument("--sem-audio", action="store_true",
                            help="pula a síntese de voz")
    opcoes = argumentos.parse_args()
    sys.exit(executar(opcoes.titulos, not opcoes.sem_audio))
