"""Serie temporal do catalogo e memoria de publicacao.

A Steam expoe apenas o estado atual de cada titulo. A variacao entre leituras
precisa ser construida por acumulacao, uma execucao por vez - por isso a
primeira edicao nao tem base de comparacao e apenas registra o ponto de
partida.
"""
import logging
import sqlite3
from datetime import datetime, timedelta

import config

log = logging.getLogger("historico")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coletado_em TEXT NOT NULL,
    appid INTEGER NOT NULL,
    nome TEXT NOT NULL,
    jogadores INTEGER,
    preco_num REAL,
    desconto INTEGER,
    total_reviews INTEGER,
    aprovacao_pct REAL
);
CREATE INDEX IF NOT EXISTS idx_snap_appid ON snapshots(appid, coletado_em);

CREATE TABLE IF NOT EXISTS edicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publicada_em TEXT NOT NULL,
    titulos_observados INTEGER,
    eventos_detectados INTEGER,
    arquivo_audio TEXT,
    arquivo_pagina TEXT
);

CREATE TABLE IF NOT EXISTS noticias_publicadas (
    gid TEXT PRIMARY KEY,
    appid INTEGER NOT NULL,
    publicada_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pub_data ON noticias_publicadas(publicada_em);
"""


def conectar():
    conexao = sqlite3.connect(config.ARQ_DB)
    conexao.row_factory = sqlite3.Row
    conexao.executescript(ESQUEMA)
    return conexao


def contar_execucoes(conexao):
    return conexao.execute(
        "SELECT COUNT(DISTINCT coletado_em) FROM snapshots"
    ).fetchone()[0]


def snapshot_anterior(conexao):
    """Leituras da execucao anterior por appid, e seu carimbo de tempo."""
    linha = conexao.execute(
        "SELECT MAX(coletado_em) AS ultimo FROM snapshots"
    ).fetchone()
    if not linha or not linha["ultimo"]:
        return {}, None

    momento = linha["ultimo"]
    registros = conexao.execute(
        "SELECT * FROM snapshots WHERE coletado_em = ?", (momento,)
    ).fetchall()
    return {r["appid"]: dict(r) for r in registros}, momento


def preco_minimo_visto(conexao, appid):
    """Menor preco registrado, ou None enquanto o historico for raso."""
    if contar_execucoes(conexao) < config.EDICOES_PARA_MINIMA_HISTORICA:
        return None
    linha = conexao.execute(
        "SELECT MIN(preco_num) AS minimo FROM snapshots "
        "WHERE appid = ? AND preco_num IS NOT NULL AND preco_num > 0",
        (appid,),
    ).fetchone()
    return linha["minimo"] if linha else None


def calcular_variacao(atual, anterior):
    if anterior in (None, 0) or atual is None:
        return None
    return round((atual - anterior) / anterior * 100, 1)


def gravar_snapshot(conexao, catalogo):
    momento = datetime.now().isoformat(timespec="seconds")
    conexao.executemany(
        "INSERT INTO snapshots (coletado_em, appid, nome, jogadores, preco_num, "
        "desconto, total_reviews, aprovacao_pct) VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                momento, j["appid"], j["nome"], j.get("jogadores_online"),
                j.get("preco_num"), j.get("desconto") or 0,
                j.get("total_reviews") or 0, j.get("aprovacao_pct"),
            )
            for j in catalogo
        ],
    )
    conexao.commit()
    return momento


def registrar_edicao(conexao, titulos, eventos, arquivo_audio="", arquivo_pagina=""):
    """Registra a edicao com os arquivos que a representam.

    Audio e pagina sao gravados juntos para que o painel abra sempre o par da
    mesma edicao: os .wav acumulam com carimbo de data, enquanto a pagina tem
    um nome fixo que e sobrescrito a cada execucao.
    """
    conexao.execute(
        "INSERT INTO edicoes (publicada_em, titulos_observados, "
        "eventos_detectados, arquivo_audio, arquivo_pagina) VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), titulos, eventos,
         arquivo_audio, arquivo_pagina),
    )
    conexao.commit()


def noticias_ja_publicadas(conexao):
    return {
        linha["gid"]
        for linha in conexao.execute("SELECT gid FROM noticias_publicadas")
    }


def registrar_noticias(conexao, eventos):
    """Marca os anuncios desta edicao como publicados."""
    agora = datetime.now().isoformat(timespec="seconds")
    novos = [
        (e["dados"]["gid"], e["appid"], agora)
        for e in eventos
        if e["tipo"] == "PATCH_GRANDE" and e.get("dados", {}).get("gid")
    ]
    if not novos:
        return 0
    conexao.executemany(
        "INSERT OR IGNORE INTO noticias_publicadas (gid, appid, publicada_em) "
        "VALUES (?,?,?)",
        novos,
    )
    conexao.commit()
    return len(novos)


def podar_noticias(conexao):
    """Remove registros que nao influenciam mais nenhuma edicao."""
    limite = (
        datetime.now() - timedelta(days=config.RETENCAO_NOTICIAS_DIAS)
    ).isoformat(timespec="seconds")
    cursor = conexao.execute(
        "DELETE FROM noticias_publicadas WHERE publicada_em < ?", (limite,)
    )
    conexao.commit()
    return cursor.rowcount
