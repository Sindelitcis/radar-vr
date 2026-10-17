"""Deteccao de eventos e ordenacao por relevancia editorial.

Um evento representa algo que mudou desde a edicao anterior, ou que e recente
o bastante para ainda nao ter sido noticiado. Caracteristicas permanentes do
titulo - preco alto, nota boa, popularidade - nao geram evento.

Todo evento de variacao exige base minima alem do percentual: uma alta de
200% sobre tres jogadores e ruido, nao noticia.
"""
import logging
from datetime import datetime

import config
import historico
import pronuncia

log = logging.getLogger("noticias")

PESOS = {
    "PROMOCAO_ACABANDO": 90,
    "PRECO_MINIMO": 85,
    "PATCH_GRANDE": 70,
    "PROMOCAO_NOVA": 55,
    "PROMOCAO_ENCERRADA": 50,
    "PICO_JOGADORES": 45,
    "QUEDA_JOGADORES": 35,
    "ONDA_AVALIACOES": 30,
}

SECOES = {
    "PROMOCAO_ACABANDO": "promocoes",
    "PRECO_MINIMO": "promocoes",
    "PROMOCAO_NOVA": "promocoes",
    "PROMOCAO_ENCERRADA": "promocoes",
    "PATCH_GRANDE": "destaques",
    "PICO_JOGADORES": "destaques",
    "QUEDA_JOGADORES": "radar",
    "ONDA_AVALIACOES": "radar",
}

# Tipos cujo fato e compartilhado por varios titulos e portanto agrupavel.
TIPOS_AGRUPAVEIS = ("PROMOCAO_ACABANDO", "PROMOCAO_ENCERRADA")

MAX_EVENTOS_POR_JOGO = 2
MIN_PARA_AGRUPAR = 3


def _reais(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


def _evento(tipo, jogo, resumo, score, dados=None):
    return {
        "tipo": tipo,
        "secao": SECOES[tipo],
        "appid": jogo["appid"],
        "nome": jogo["nome"],
        "preco": jogo["preco"],
        "preco_cheio": jogo.get("preco_cheio", ""),
        "desconto": jogo.get("desconto") or 0,
        "url": jogo["url"],
        "resumo": resumo,
        "score": round(score, 1),
        "dados": dados or {},
    }


def _prazo_mudou(fim, faltam, antes):
    """Promocao acabando vira noticia duas vezes: ao entrar na janela de aviso
    e ao entrar no prazo urgente. Nos outros dias o fato e o mesmo de ontem."""
    if not antes or not (antes.get("desconto") or 0):
        return True
    faltavam = (fim.date() - datetime.fromisoformat(antes["coletado_em"]).date()).days
    return any(faltam <= limite < faltavam
               for limite in (config.AVISO_FIM_PROMOCAO_DIAS, config.PRAZO_URGENTE_DIAS))


def _eventos_de_preco(conexao, jogo, antes):
    eventos = []
    preco = jogo.get("preco_num")
    desconto = jogo.get("desconto") or 0
    if preco is None or preco <= 0:
        return eventos

    # Sem leitura anterior nao ha como afirmar que a promocao comecou agora;
    # o texto muda de "entrou em" para "esta em".
    if antes is None:
        if desconto:
            eventos.append(_evento(
                "PROMOCAO_NOVA", jogo,
                f"está em promoção com {desconto}% de desconto, saindo por {jogo['preco']}",
                PESOS["PROMOCAO_NOVA"] + desconto / 2 - 10,
                {"desconto": desconto},
            ))
    elif desconto and not (antes.get("desconto") or 0):
        eventos.append(_evento(
            "PROMOCAO_NOVA", jogo,
            f"entrou em promoção com {desconto}% de desconto, saindo por {jogo['preco']}",
            PESOS["PROMOCAO_NOVA"] + desconto / 2,
            {"desconto": desconto},
        ))
    elif not desconto and (antes.get("desconto") or 0):
        # A janela fechou: o preco voltou ao cheio. E o unico evento que
        # reporta perda de oportunidade, e por isso o peso cresce com o
        # tamanho do desconto que deixou de existir.
        antigo = antes.get("preco_num")
        volta = f", ante {_reais(antigo)}" if antigo else ""
        eventos.append(_evento(
            "PROMOCAO_ENCERRADA", jogo,
            f"saiu de promoção e voltou a {jogo['preco']}{volta}",
            PESOS["PROMOCAO_ENCERRADA"] + (antes.get("desconto") or 0) / 4,
            {
                "desconto_anterior": antes.get("desconto") or 0,
                "preco_anterior": _reais(antigo) if antigo else "",
            },
        ))

    fim = jogo.get("fim_promocao")
    if fim:
        faltam = (fim.date() - datetime.now().date()).days
        if 0 <= faltam <= config.AVISO_FIM_PROMOCAO_DIAS and _prazo_mudou(fim, faltam, antes):
            prazo = {
                0: "termina hoje",
                1: "termina amanhã",
            }.get(faltam, f"termina em {faltam} dias, no dia "
                          f"{pronuncia.data_por_extenso(fim)}")
            eventos.append(_evento(
                "PROMOCAO_ACABANDO", jogo,
                f"está a {desconto}% de desconto por {jogo['preco']}, "
                f"mas a oferta {prazo}",
                PESOS["PROMOCAO_ACABANDO"]
                + (config.AVISO_FIM_PROMOCAO_DIAS - faltam) * 5,
                {
                    "desconto": desconto,
                    "fim": fim.strftime("%d/%m/%Y"),
                    "fim_extenso": pronuncia.data_por_extenso(fim),
                    "faltam": faltam,
                },
            ))

    # O historico do ITAD cobre anos de precos e vale desde a primeira edicao.
    # A serie propria fica como alternativa quando o jogo nao esta no ITAD.
    itad = jogo.get("itad")
    if itad and desconto and preco <= itad["menor_preco"] * config.ITAD_MARGEM_MINIMO:
        # O recorde continua valendo enquanto a oferta durar. So e fato novo
        # se o preco caiu desde a leitura anterior.
        ja_noticiado = (antes and (antes.get("desconto") or 0)
                        and antes.get("preco_num") and preco >= antes["preco_num"])
        if ja_noticiado:
            return eventos
        quando = itad["data_menor"]
        # O ITAD atualiza o recorde quando a promocao atual o bate; nesse caso
        # a data do recorde e a desta propria oferta e nao vale cita-la.
        recente = bool(quando) and (
            datetime.now() - datetime.fromisoformat(quando)
        ).days <= 14
        resumo = f"está por {jogo['preco']}, menor preço histórico"
        if quando and not recente:
            data = datetime.fromisoformat(quando)
            resumo += (f", visto pela última vez em "
                       f"{pronuncia.MESES[data.month - 1]} de {data.year}")
        eventos.append(_evento(
            "PRECO_MINIMO", jogo, resumo,
            PESOS["PRECO_MINIMO"] + desconto / 4,
            {
                "menor_historico": itad["menor_preco"],
                "visto_em": f"{quando[5:7]}/{quando[:4]}" if quando and not recente else "",
                "fonte": "IsThereAnyDeal",
            },
        ))
        return eventos

    # Comparacao estrita: preco igual ao minimo ja visto nao e fato novo.
    minimo = historico.preco_minimo_visto(conexao, jogo["appid"])
    if minimo is not None and preco < minimo and desconto:
        queda = round((minimo - preco) / minimo * 100, 1)
        eventos.append(_evento(
            "PRECO_MINIMO", jogo,
            f"caiu para {jogo['preco']}, {queda}% abaixo do menor valor já registrado",
            PESOS["PRECO_MINIMO"] + desconto / 4,
            {"minimo_anterior": minimo, "queda_pct": queda},
        ))
    return eventos


def _eventos_de_jogadores(jogo, antes):
    agora = jogo.get("jogadores_online")
    if agora is None or not antes:
        return []

    base = antes.get("jogadores")
    variacao = historico.calcular_variacao(agora, base)
    if variacao is None or base is None or base < config.PICO_BASE_MINIMA:
        return []

    if variacao >= config.PICO_VARIACAO_MINIMA:
        return [_evento(
            "PICO_JOGADORES", jogo,
            f"saltou {variacao}% em jogadores simultâneos, de {base} para {agora}",
            PESOS["PICO_JOGADORES"] + min(variacao, 150) / 3,
            {"antes": base, "agora": agora, "variacao": variacao},
        )]
    if variacao <= -config.QUEDA_VARIACAO_MINIMA:
        return [_evento(
            "QUEDA_JOGADORES", jogo,
            f"perdeu {abs(variacao)}% de jogadores, de {base} para {agora}",
            PESOS["QUEDA_JOGADORES"] + min(abs(variacao), 150) / 4,
            {"antes": base, "agora": agora, "variacao": variacao},
        )]
    return []


def _eventos_de_noticias(jogo, ja_publicados):
    """Anuncio mais recente do desenvolvedor ainda nao noticiado.

    Um por titulo: a janela de deteccao cobre sete dias, e sem esse limite um
    jogo com varios patch notes ocuparia o boletim inteiro.
    """
    candidatos = [
        n for n in jogo.get("noticias", [])
        if n["oficial"]
        and n["idade_dias"] <= config.NOTICIA_RECENTE_DIAS
        and n.get("gid") not in ja_publicados
    ]
    if not candidatos:
        return []

    noticia = min(candidatos, key=lambda n: n["idade_dias"])
    extras = len(candidatos) - 1
    sufixo = (
        f" (mais {extras} anúncio{'s' if extras > 1 else ''} na semana)"
        if extras else ""
    )
    quando = pronuncia.data_relativa(noticia["idade_dias"])

    return [_evento(
        "PATCH_GRANDE", jogo,
        f"recebeu um anúncio do desenvolvedor {quando}: "
        f"{noticia['titulo']}{sufixo}",
        PESOS["PATCH_GRANDE"]
        + (config.NOTICIA_RECENTE_DIAS - noticia["idade_dias"]) * 3
        + extras * 4,
        {
            "gid": noticia.get("gid", ""),
            "titulo": noticia["titulo"],
            "texto": noticia["resumo"],
            "idade_dias": noticia["idade_dias"],
        },
    )]


def _eventos_de_avaliacoes(jogo, antes):
    if not antes:
        return []
    novas = (jogo.get("total_reviews") or 0) - (antes.get("total_reviews") or 0)
    if novas < config.ONDA_REVIEWS_MINIMA:
        return []
    return [_evento(
        "ONDA_AVALIACOES", jogo,
        f"recebeu {novas} avaliações novas desde a última edição",
        PESOS["ONDA_AVALIACOES"] + min(novas, 300) / 10,
        {"novas": novas},
    )]


def _agrupar_promocoes(eventos):
    """Reune num unico evento as promocoes que compartilham o mesmo fato.

    Liquidacoes sazonais movem o catalogo inteiro de uma vez: todos os titulos
    passam a ter a mesma data de termino, e depois todos saem de promocao no
    mesmo dia. Emitir um evento por titulo produziria varias chamadas com o
    mesmo conteudo.

    O evento agrupado mantem os individuais em `dados.membros`: o audio usa a
    chamada resumida, a pagina expande a lista completa.
    """
    def chave(evento):
        # promocoes que acabam sao agrupadas pela data; as ja encerradas
        # compartilham um unico fato - a janela fechou desde a edicao anterior
        if evento["tipo"] == "PROMOCAO_ACABANDO":
            return ("PROMOCAO_ACABANDO", evento["dados"]["fim"])
        return ("PROMOCAO_ENCERRADA", "")

    grupos, outros = {}, []
    for evento in eventos:
        if evento["tipo"] in TIPOS_AGRUPAVEIS:
            grupos.setdefault(chave(evento), []).append(evento)
        else:
            outros.append(evento)

    resultado = list(outros)
    for (tipo, _), grupo in grupos.items():
        if len(grupo) < MIN_PARA_AGRUPAR:
            resultado += grupo
            continue

        grupo.sort(
            key=lambda e: e["dados"].get("desconto")
            or e["dados"].get("desconto_anterior", 0),
            reverse=True,
        )
        citados = [e["nome"] for e in grupo[:3]]
        restantes = len(grupo) - 3
        sobra = f", além de outros {restantes}" if restantes > 0 else ""
        lista = f"{', '.join(citados[:-1])} e {citados[-1]}{sobra}"

        if tipo == "PROMOCAO_ACABANDO":
            faltam = grupo[0]["dados"]["faltam"]
            quando = {0: "hoje", 1: "amanhã"}.get(
                faltam, f"em {faltam} dias, no dia {grupo[0]['dados']['fim_extenso']}"
            )
            resumo = f"da lista estão com promoção terminando {quando}: {lista}"
            extras = {
                "fim": grupo[0]["dados"]["fim"],
                "faltam": faltam,
            }
        else:
            resumo = f"da lista saíram de promoção desde a última edição: {lista}"
            extras = {}

        resultado.append({
            "tipo": tipo,
            "secao": "promocoes",
            "appid": grupo[0]["appid"],
            "nome": f"{len(grupo)} títulos",
            "preco": "",
            "preco_cheio": "",
            "desconto": 0,
            "url": (
                "https://store.steampowered.com/search/?category1=998"
                "&vrsupport=401&specials=1"
            ),
            "resumo": resumo,
            "score": max(e["score"] for e in grupo) + 5,
            "dados": {**extras, "quantidade": len(grupo), "membros": grupo},
        })
    return resultado


def detectar(conexao, catalogo, anterior):
    """Devolve (eventos do boletim, todos os eventos detectados)."""
    log.info("=== ETAPA 2/4 | Detecção de eventos ===")

    ja_publicados = historico.noticias_ja_publicadas(conexao)
    if ja_publicados:
        log.info("  %d anúncios já noticiados serão ignorados", len(ja_publicados))

    eventos = []
    for jogo in catalogo:
        antes = anterior.get(jogo["appid"]) if anterior else None
        eventos += _eventos_de_preco(conexao, jogo, antes)
        eventos += _eventos_de_noticias(jogo, ja_publicados)
        eventos += _eventos_de_jogadores(jogo, antes)
        eventos += _eventos_de_avaliacoes(jogo, antes)

    eventos = _agrupar_promocoes(eventos)
    eventos.sort(key=lambda e: e["score"], reverse=True)

    # Teto por titulo, para que um unico jogo nao domine a edicao.
    por_jogo, diversos = {}, []
    for evento in eventos:
        usados = por_jogo.get(evento["appid"], 0)
        if usados >= MAX_EVENTOS_POR_JOGO:
            continue
        por_jogo[evento["appid"]] = usados + 1
        diversos.append(evento)

    contagem = {}
    for evento in eventos:
        contagem[evento["tipo"]] = contagem.get(evento["tipo"], 0) + 1
    log.info("  %d eventos detectados%s", len(eventos),
             "" if anterior else " (primeira edição: sem base de comparação)")
    for tipo, quantidade in sorted(contagem.items(), key=lambda x: -x[1]):
        log.info("    %-18s %d", tipo, quantidade)

    selecionados = diversos[: config.MANCHETES_NO_BOLETIM]
    log.info("Etapa 2 concluída: %d eventos no boletim", len(selecionados))
    return selecionados, eventos
