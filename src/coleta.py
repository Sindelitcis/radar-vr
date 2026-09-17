"""Coleta de dados do catalogo VR na Steam.

Cinco rotas publicas, nenhuma exige chave de autenticacao:

    /search/results              descoberta de titulos com suporte a VR
    /api/appdetails              ficha da loja: preco, generos, descricao
    GetNumberOfCurrentPlayers    jogadores simultaneos
    /appreviews/<appid>          resumo das avaliacoes da comunidade
    /app/<appid>                 pagina da loja, para o fim da promocao
"""
import logging
import re
import time
from datetime import datetime

import requests

import config

log = logging.getLogger("coleta")

CABECALHO = {"User-Agent": "RadarVR/1.0 (projeto academico PUCPR)"}

# O appid nao vem em campo proprio na busca; aparece na URL da imagem.
RE_APPID = re.compile(r"/apps/(\d+)/")

# A pagina da loja exibe o fim da promocao como "Termina em 21 de Setembro".
RE_FIM_PROMOCAO = re.compile(
    r'discount_countdown"[^>]*>[^<]*?Termina em (\d{1,2}) de (\w+)', re.IGNORECASE
)

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _get(url, params=None):
    resposta = requests.get(
        url, params=params, headers=CABECALHO, timeout=config.TIMEOUT
    )
    resposta.raise_for_status()
    return resposta.json()


def _limpar_html(texto):
    sem_marcacao = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", sem_marcacao).strip()


def _formatar_preco(bloco, eh_gratis):
    """Devolve (texto, valor, desconto, texto do preco cheio)."""
    if eh_gratis:
        return "Gratuito", 0.0, 0, ""
    if not bloco:
        return "Indisponível", None, 0, ""

    desconto = bloco.get("discount_percent", 0)
    return (
        bloco.get("final_formatted", "Indisponível"),
        bloco.get("final", 0) / 100,
        desconto,
        bloco.get("initial_formatted", "") if desconto else "",
    )


def descobrir_jogos_vr(quantidade):
    """Lista [(appid, nome)] de titulos com suporte a VR."""
    parametros = {
        "query": "",
        "sort_by": config.ORDENACAO,
        "cc": config.PAIS,
        "l": config.IDIOMA,
        "json": 1,
        **config.FILTRO_VR,
    }
    itens = _get(config.STEAM_BUSCA, parametros).get("items", [])
    jogos, vistos = [], set()
    for item in itens:
        achado = RE_APPID.search(item.get("logo", ""))
        if not achado:
            continue
        appid = int(achado.group(1))
        if appid in vistos:
            continue
        vistos.add(appid)
        jogos.append((appid, item.get("name", "")))
        if len(jogos) >= quantidade:
            break
    return jogos


def detalhar_jogo(appid):
    dados = _get(
        config.STEAM_DETALHES,
        {"appids": appid, "cc": config.PAIS, "l": config.IDIOMA},
    )
    bloco = dados.get(str(appid), {})
    if not bloco.get("success"):
        raise ValueError(f"appdetails sem sucesso para {appid}")
    return bloco["data"]


def contar_jogadores(appid):
    """Jogadores simultaneos. Nem todo titulo expoe esse dado."""
    try:
        dados = _get(config.STEAM_JOGADORES, {"appid": appid})
        return dados.get("response", {}).get("player_count")
    except Exception as erro:
        log.warning("Sem contagem de jogadores para %s: %s", appid, erro)
        return None


def buscar_avaliacoes(appid):
    """Percentual de aprovacao e volume de avaliacoes da comunidade."""
    vazio = {"aprovacao_pct": None, "total_reviews": 0, "review_desc": "sem dados"}
    try:
        dados = _get(
            f"{config.STEAM_AVALIACOES}{appid}",
            {"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0},
        )
    except Exception as erro:
        log.warning("Sem avaliações para %s: %s", appid, erro)
        return vazio

    resumo = dados.get("query_summary", {})
    total = resumo.get("total_reviews", 0)
    positivas = resumo.get("total_positive", 0)
    return {
        "aprovacao_pct": round(positivas / total * 100, 1) if total else None,
        "total_reviews": total,
        "review_desc": resumo.get("review_score_desc", "sem dados"),
    }


def buscar_noticias(appid, quantidade=None):
    """Anuncios recentes do titulo.

    O feed mistura publicacoes do desenvolvedor com materias de imprensa.
    Apenas as primeiras indicam alteracao no jogo, e sao marcadas em `oficial`.
    """
    quantidade = quantidade or config.NOTICIAS_POR_JOGO
    try:
        dados = _get(
            config.STEAM_NOTICIAS,
            {"appid": appid, "count": quantidade * 3, "maxlength": 400},
        )
    except Exception as erro:
        log.warning("Sem notícias para %s: %s", appid, erro)
        return []

    agora = datetime.now()
    itens = []
    for bruto in dados.get("appnews", {}).get("newsitems", []):
        publicado = datetime.fromtimestamp(bruto.get("date", 0))
        itens.append({
            "gid": str(bruto.get("gid", "")),
            "titulo": bruto.get("title", "").strip(),
            "resumo": _limpar_html(bruto.get("contents", ""))[:400],
            "idade_dias": (agora - publicado).days,
            "oficial": (
                bruto.get("feed_type") == 1
                or "announcement" in (bruto.get("feedname") or "").lower()
            ),
        })
        if len(itens) >= quantidade:
            break
    return itens


def buscar_fim_promocao(appid):
    """Data de termino da promocao, ou None.

    Nenhuma rota JSON publica expoe esse dado por appid: `discount_expiration`
    existe apenas em /api/featuredcategories, restrito a dez titulos em
    destaque. A alternativa e o contador na pagina da loja, o que implica
    leitura de HTML.

    A funcao falha em silencio. Sem a data, o boletim nao anuncia o fim da
    promocao e nenhuma outra etapa e afetada.
    """
    try:
        resposta = requests.get(
            f"https://store.steampowered.com/app/{appid}/",
            params={"cc": config.PAIS, "l": config.IDIOMA},
            headers={**CABECALHO, "Cookie": "birthtime=0; wants_mature_content=1"},
            timeout=config.TIMEOUT,
        )
        resposta.raise_for_status()
    except Exception:
        return None

    achado = RE_FIM_PROMOCAO.search(resposta.text)
    if not achado:
        return None

    mes = MESES_PT.get(achado.group(2).lower())
    if not mes:
        return None

    hoje = datetime.now()
    ano = hoje.year + 1 if mes < hoje.month else hoje.year
    try:
        return datetime(ano, mes, int(achado.group(1)))
    except ValueError:
        return None


def montar_watchlist(tamanho=None):
    """Conjunto observado, ordenado por volume de avaliacoes.

    Nao filtra por promocao: a lista precisa ser a mesma amanha para que a
    comparacao entre edicoes tenha significado.
    """
    tamanho = tamanho or config.TAM_WATCHLIST
    log.info("Montando watchlist de %d títulos", tamanho)
    return descobrir_jogos_vr(tamanho)


def coletar(tamanho=None):
    """Executa a etapa de coleta e devolve o catalogo normalizado."""
    log.info("=== ETAPA 1/4 | Coleta do catálogo VR ===")
    try:
        watchlist = montar_watchlist(tamanho)
    except Exception as erro:
        log.error("Falha ao montar a watchlist: %s", erro)
        return []

    catalogo = []
    for appid, nome in watchlist:
        time.sleep(config.PAUSA_REQ)
        try:
            ficha = detalhar_jogo(appid)
        except Exception as erro:
            log.warning("Ignorando %s (%s): %s", nome, appid, erro)
            continue

        preco, valor, desconto, preco_cheio = _formatar_preco(
            ficha.get("price_overview"), ficha.get("is_free", False)
        )
        jogo = {
            "appid": appid,
            "nome": ficha.get("name", nome),
            "preco": preco,
            "preco_cheio": preco_cheio,
            "preco_num": valor,
            "desconto": desconto,
            "descricao": _limpar_html(ficha.get("short_description", ""))[:400],
            "generos": ", ".join(g["description"] for g in ficha.get("genres", [])),
            "jogadores_online": contar_jogadores(appid),
            "url": f"https://store.steampowered.com/app/{appid}",
            "noticias": buscar_noticias(appid),
            # consultar o fim da promocao so faz sentido para quem esta em oferta
            "fim_promocao": buscar_fim_promocao(appid) if desconto else None,
            **buscar_avaliacoes(appid),
        }
        catalogo.append(jogo)
        log.info(
            "  + %-30s %-10s online:%-7s %d avisos",
            jogo["nome"][:30], jogo["preco"], jogo["jogadores_online"],
            sum(1 for n in jogo["noticias"] if n["oficial"]),
        )

    log.info("Etapa 1 concluída: %d títulos observados", len(catalogo))
    return catalogo
