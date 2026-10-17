"""Historico de precos pela API do IsThereAnyDeal.

A Steam so informa o preco de agora. O ITAD guarda o historico de varias
lojas, o que permite dizer se uma promocao e de fato a menor da historia do
jogo sem esperar meses de leituras proprias.

Termos de uso da API: os dados sao exibidos sem alteracao, os links da loja
sao repassados como vieram e a fonte e creditada no boletim.

Duas chamadas por edicao, independente do tamanho da watchlist:
    /lookup/id/shop/61/v1   appid da Steam -> id do ITAD (cache permanente)
    /games/overview/v2      preco atual e menor historico (cache de 6 h)
"""
import json
import logging
import sqlite3
from datetime import datetime, timedelta

import requests

import config

log = logging.getLogger("itad")

FONTE = "IsThereAnyDeal"
URL_FONTE = "https://isthereanydeal.com"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS itad_ids (
    appid INTEGER PRIMARY KEY,
    itad_id TEXT
);
CREATE TABLE IF NOT EXISTS itad_precos (
    itad_id TEXT PRIMARY KEY,
    lido_em TEXT NOT NULL,
    dados TEXT NOT NULL
);
"""


def _conectar():
    conexao = sqlite3.connect(config.ARQ_DB, timeout=30)
    conexao.executescript(ESQUEMA)
    return conexao


def _resolver_ids(conexao, appids):
    conhecidos = dict(conexao.execute(
        f"SELECT appid, itad_id FROM itad_ids WHERE appid IN "
        f"({','.join('?' * len(appids))})", appids,
    ).fetchall())
    faltam = [a for a in appids if a not in conhecidos]
    if faltam:
        resposta = requests.post(
            f"{config.ITAD_URL}/lookup/id/shop/{config.ITAD_LOJA_STEAM}/v1",
            params={"key": config.ITAD_API_KEY},
            json=[f"app/{a}" for a in faltam],
            timeout=config.TIMEOUT,
        )
        resposta.raise_for_status()
        novos = {int(k.split("/")[1]): v for k, v in resposta.json().items()}
        # jogos sem cadastro no ITAD ficam com None e nao sao consultados de novo
        conexao.executemany(
            "INSERT OR REPLACE INTO itad_ids (appid, itad_id) VALUES (?, ?)",
            list(novos.items()),
        )
        conexao.commit()
        conhecidos.update(novos)
    return {a: i for a, i in conhecidos.items() if i}


def _precos(conexao, itad_ids):
    limite = (
        datetime.now() - timedelta(hours=config.ITAD_CACHE_HORAS)
    ).isoformat(timespec="seconds")
    em_cache = {
        i: json.loads(d) for i, d in conexao.execute(
            f"SELECT itad_id, dados FROM itad_precos WHERE lido_em >= ? AND "
            f"itad_id IN ({','.join('?' * len(itad_ids))})",
            [limite, *itad_ids],
        ).fetchall()
    }
    faltam = [i for i in itad_ids if i not in em_cache]
    if faltam:
        resposta = requests.post(
            f"{config.ITAD_URL}/games/overview/v2",
            params={"key": config.ITAD_API_KEY, "country": config.PAIS.upper()},
            json=faltam,
            timeout=config.TIMEOUT,
        )
        resposta.raise_for_status()
        agora = datetime.now().isoformat(timespec="seconds")
        for item in resposta.json().get("prices", []):
            em_cache[item["id"]] = item
            conexao.execute(
                "INSERT OR REPLACE INTO itad_precos VALUES (?, ?, ?)",
                (item["id"], agora, json.dumps(item)),
            )
        conexao.commit()
    return em_cache, len(itad_ids) - len(faltam)


def _resumir(item):
    atual, menor = item.get("current"), item.get("lowest")
    if not atual or not menor:
        return None
    preco_atual = atual["price"]["amount"]
    preco_minimo = menor["price"]["amount"]
    return {
        "loja_atual": atual["shop"]["name"],
        "preco_atual": preco_atual,
        "desconto_atual": atual.get("cut", 0),
        "url_oferta": atual.get("url", ""),
        "menor_preco": preco_minimo,
        "loja_menor": menor["shop"]["name"],
        "data_menor": (menor.get("timestamp") or "")[:10],
        "no_minimo": preco_atual <= preco_minimo * config.ITAD_MARGEM_MINIMO,
        "url_itad": item.get("urls", {}).get("game", ""),
    }


def enriquecer(catalogo):
    """Acrescenta `itad` a cada jogo do catalogo. Falha sem interromper a edicao."""
    if not config.ITAD_API_KEY:
        log.info("ITAD_API_KEY ausente: historico de precos desativado")
        return catalogo
    appids = [j["appid"] for j in catalogo]
    try:
        conexao = _conectar()
        ids = _resolver_ids(conexao, appids)
        precos, do_cache = _precos(conexao, list(set(ids.values()))) if ids else ({}, 0)
        conexao.close()
    except Exception as erro:
        log.warning("Histórico de preços indisponível: %s", erro)
        return catalogo

    no_minimo = 0
    for jogo in catalogo:
        item = precos.get(ids.get(jogo["appid"]))
        jogo["itad"] = _resumir(item) if item else None
        if jogo["itad"] and jogo["itad"]["no_minimo"] and jogo.get("desconto"):
            no_minimo += 1
    log.info("  ITAD: %d de %d títulos com histórico (%d do cache), %d no menor preço",
             len(ids), len(appids), do_cache, no_minimo)
    return catalogo
