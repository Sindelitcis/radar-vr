"""Edicao personalizada por assinante.

Para cada perfil, tres decisoes em sequencia:

    1. selecao   que fatos da edicao interessam a esta pessoa
    2. canal     e-mail sempre que houver fato relevante; alerta instantaneo
                 so quando ha urgencia (oferta acabando, menor preco)
    3. redacao   o LLM escreve assunto, abertura e alerta a partir dos fatos

A regra decide e o modelo redige, mesmo principio da edicao geral. Canal e
urgencia precisam ser explicaveis e reproduziveis; tom e fluidez nao.

O texto do modelo passa por uma verificacao: todo numero citado precisa
existir nos fatos de entrada. Se o modelo inventar um preco, o texto e
descartado e entra o modelo de frase fixo.
"""
import hashlib
import html
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import config
import itad
import redacao

log = logging.getLogger("perfil")

TIPOS_URGENTES = {"PROMOCAO_ACABANDO", "PRECO_MINIMO"}
PRAZO_URGENTE_DIAS = 2

SISTEMA = (
    "Voce escreve mensagens curtas para assinantes de um boletim de jogos de "
    "realidade virtual, em portugues do Brasil. Tom proximo e direto, sem "
    "exagero de marketing. Voce nunca inventa, arredonda ou altera numeros: "
    "usa apenas os que aparecem nos fatos. Evita frases feitas como 'nao "
    "perca' ou 'corra'."
)

GABARITO = """Escreva os textos do boletim pessoal a partir dos fatos abaixo.
Responda APENAS com JSON valido:

{{"assunto": "assunto do e-mail, ate 70 caracteres",
  "abertura": "duas frases que resumem o que importa hoje para esta pessoa",
  "alerta": "{instrucao_alerta}"}}

Regras:
- Use somente os fatos listados. Nao acrescente jogos, precos ou datas.
- Nao cumprimente pelo nome; a saudacao e inserida depois.
- Sem emoji, sem exclamacao em excesso.

INTERESSES: {interesses}
FATOS:
{fatos}
URGENTES:
{urgentes}"""

_cache = {}
_cache_trava = threading.Lock()
_metricas = {"llm": 0, "cache": 0, "regra": 0}


def _contar(origem):
    with _cache_trava:
        _metricas[origem] += 1


# ------------------------------------------------------------------ perfis

def carregar_perfis(caminho=None):
    caminho = caminho or config.ARQ_PERFIS
    if not caminho.exists():
        raise FileNotFoundError(
            f"{caminho.name} não encontrado. Copie perfis.exemplo.json e preencha."
        )
    perfis = json.loads(caminho.read_text(encoding="utf-8"))
    validos = []
    for perfil in perfis:
        if not perfil.get("consentimento"):
            log.warning("Perfil %s ignorado: sem registro de consentimento", perfil.get("id"))
            continue
        validos.append(perfil)
    return validos


def jogos_seguidos(perfis):
    return sorted({a for p in perfis for a in p.get("jogos", [])})


# ----------------------------------------------------------------- selecao

def _reais(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


def _expandir(eventos):
    """Desfaz os agrupamentos: o interesse e avaliado jogo a jogo."""
    for evento in eventos:
        membros = evento.get("dados", {}).get("membros")
        if membros:
            yield from membros
        else:
            yield evento


def _interessa(perfil, jogo):
    if not jogo:
        return False
    if jogo["appid"] in perfil.get("jogos", []):
        return True
    generos = {g.strip().lower() for g in (jogo.get("generos") or "").split(",")}
    return bool(generos & {g.lower() for g in perfil.get("generos", [])})


def _urgente(perfil, evento):
    if evento["tipo"] == "PRECO_MINIMO":
        return True
    if evento["tipo"] == "PROMOCAO_ACABANDO":
        return evento.get("dados", {}).get("faltam", 99) <= PRAZO_URGENTE_DIAS
    return False


def selecionar(perfil, edicao):
    catalogo = {j["appid"]: j for j in edicao["catalogo"]}
    orcamento = perfil.get("orcamento")

    itens, urgentes, vistos = [], [], set()
    for evento in _expandir(edicao["eventos"]):
        jogo = catalogo.get(evento["appid"])
        chave = (evento["tipo"], evento["appid"])
        if chave in vistos or not _interessa(perfil, jogo):
            continue
        vistos.add(chave)
        itens.append(evento)
        dentro_do_orcamento = (
            orcamento is None or (jogo.get("preco_num") or 0) <= orcamento
        )
        if _urgente(perfil, evento) and dentro_do_orcamento:
            urgentes.append(evento)

    seguidos = [catalogo[a] for a in perfil.get("jogos", []) if a in catalogo]
    return {"itens": itens, "urgentes": urgentes, "seguidos": seguidos}


def _fato(evento):
    return evento.get("linha") or f"{evento['nome']} {evento['resumo']}"


def _fato_seguido(jogo):
    partes = [f"{jogo['nome']}: {jogo['preco']}"]
    if jogo.get("desconto"):
        partes.append(f"com {jogo['desconto']}% de desconto")
    historico = jogo.get("itad")
    if historico:
        partes.append(f"menor preço da história {_reais(historico['menor_preco'])}"
                      f" ({historico['loja_menor']})")
    return ", ".join(partes)


# ----------------------------------------------------------------- redacao

def _numeros(texto):
    return set(re.findall(r"\d+(?:[.,]\d+)?", texto))


def _confere(gerado, fontes):
    """Todo numero do texto gerado precisa constar nos fatos."""
    permitidos = _numeros(fontes)
    return all(n in permitidos for n in _numeros(gerado))


def _texto_padrao(perfil, selecao):
    itens, urgentes = selecao["itens"], selecao["urgentes"]
    if urgentes:
        assunto = f"Radar VR: {urgentes[0]['nome']} pede atenção hoje"
    elif itens:
        assunto = f"Radar VR: {len(itens)} novidades nos seus jogos"
    else:
        assunto = "Radar VR: seus jogos hoje"
    abertura = (
        f"Separei {len(itens)} movimentos que combinam com o que você acompanha."
        if itens else "Nenhum movimento novo nos seus jogos desde a última edição."
    )
    alerta = _fato(urgentes[0]) if urgentes else ""
    return {"assunto": assunto, "abertura": abertura, "alerta": alerta}


def _assinatura(perfil, fatos, urgentes):
    """Chave do cache: o conteudo que o modelo recebe, sem dado pessoal.

    Assinantes com os mesmos interesses recebem os mesmos fatos; o texto
    gerado para um serve para todos.
    """
    base = json.dumps([sorted(perfil.get("generos", [])), fatos, urgentes],
                      ensure_ascii=False)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def redigir(perfil, selecao):
    """Devolve (textos, origem). Origem: llm, cache ou regra."""
    fatos = [_fato(e) for e in selecao["itens"][:8]]
    fatos += [_fato_seguido(j) for j in selecao["seguidos"]]
    urgentes = [_fato(e) for e in selecao["urgentes"]]
    padrao = _texto_padrao(perfil, selecao)
    if not fatos:
        _contar("regra")
        return padrao, "regra"

    chave = _assinatura(perfil, fatos, urgentes)
    if config.CACHE_REDACAO:
        with _cache_trava:
            if chave in _cache:
                _metricas["cache"] += 1
                return dict(_cache[chave]), "cache"

    instrucao = (
        "uma mensagem de ate 280 caracteres sobre o fato urgente, para chat"
        if urgentes else "deixe vazio"
    )
    prompt = GABARITO.format(
        instrucao_alerta=instrucao,
        interesses=", ".join(perfil.get("generos", [])) or "jogos seguidos",
        fatos="\n".join(f"- {f}" for f in fatos),
        urgentes="\n".join(f"- {u}" for u in urgentes) or "- nenhum",
    )
    fontes = "\n".join(fatos + urgentes)
    try:
        bruto = redacao.chamar(prompt, SISTEMA)
        gerado = redacao.extrair_json(bruto) or {}
        textos = {
            "assunto": str(gerado.get("assunto", "")).strip()[:90],
            "abertura": str(gerado.get("abertura", "")).strip()[:600],
            "alerta": str(gerado.get("alerta", "")).strip()[:400] if urgentes else "",
        }
        if not textos["assunto"] or not textos["abertura"]:
            raise ValueError("resposta incompleta")
        if not _confere(" ".join(textos.values()), fontes):
            raise ValueError("número ausente dos fatos")
    except Exception as erro:
        log.warning("Redação do perfil %s pela regra: %s", perfil["id"], erro)
        _contar("regra")
        return padrao, "regra"

    if urgentes and not textos["alerta"]:
        textos["alerta"] = padrao["alerta"]
    with _cache_trava:
        _cache[chave] = dict(textos)
        _metricas["llm"] += 1
    return textos, "llm"


# ------------------------------------------------------------------ e-mail

ESTILO_EMAIL = (
    "font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;"
    "color:#1a1a1a;line-height:1.5;max-width:600px;margin:0 auto;padding:24px"
)


def _linha_item(evento):
    return (
        f'<li style="margin:0 0 10px">'
        f'<a href="{html.escape(evento["url"])}" style="color:#1a1a1a;font-weight:600">'
        f'{html.escape(evento["nome"])}</a><br>'
        f'<span style="color:#444">{html.escape(_fato(evento))}</span></li>'
    )


def _linha_seguido(jogo):
    historico = jogo.get("itad")
    detalhe = ""
    if historico:
        url = historico.get("url_itad") or itad.URL_FONTE
        detalhe = (
            f'<br><span style="color:#666;font-size:13px">Menor preço da história: '
            f'{_reais(historico["menor_preco"])} na {html.escape(historico["loja_menor"])}'
            f' · <a href="{html.escape(url)}" style="color:#666">histórico</a></span>'
        )
    desconto = f' <b style="color:#059669">-{jogo["desconto"]}%</b>' if jogo.get("desconto") else ""
    return (
        f'<li style="margin:0 0 10px"><a href="{html.escape(jogo["url"])}" '
        f'style="color:#1a1a1a;font-weight:600">{html.escape(jogo["nome"])}</a>'
        f' — {html.escape(jogo["preco"] or "")}{desconto}{detalhe}</li>'
    )


def montar_email(perfil, selecao, textos, edicao):
    data = datetime.fromisoformat(edicao["publicada_em"]).strftime("%d/%m/%Y")
    partes = [
        f'<div style="{ESTILO_EMAIL}">',
        '<p style="font-size:13px;color:#666;margin:0">Radar VR · ' + data + "</p>",
        f'<h1 style="font-size:22px;margin:4px 0 16px">Olá, {html.escape(perfil["nome"])}</h1>',
        f'<p>{html.escape(textos["abertura"])}</p>',
    ]
    if selecao["urgentes"]:
        partes.append(
            '<div style="background:#fff4e5;border-left:4px solid #ea580c;'
            'padding:10px 14px;margin:16px 0">'
            "<b>Atenção hoje</b><ul style='padding-left:18px;margin:8px 0 0'>"
            + "".join(_linha_item(e) for e in selecao["urgentes"])
            + "</ul></div>"
        )
    demais = [e for e in selecao["itens"] if e not in selecao["urgentes"]]
    if demais:
        partes.append('<h2 style="font-size:16px;margin:20px 0 8px">Movimentos que combinam com você</h2>')
        partes.append("<ul style='padding-left:18px'>"
                      + "".join(_linha_item(e) for e in demais[:8]) + "</ul>")
    if selecao["seguidos"]:
        partes.append('<h2 style="font-size:16px;margin:20px 0 8px">Seus jogos</h2>')
        partes.append("<ul style='padding-left:18px'>"
                      + "".join(_linha_seguido(j) for j in selecao["seguidos"]) + "</ul>")
    if edicao.get("audio"):
        partes.append("<p>A narração completa da edição está em anexo.</p>")
    partes.append(
        '<hr style="border:none;border-top:1px solid #ddd;margin:24px 0 12px">'
        '<p style="font-size:12px;color:#777">'
        f'Histórico de preços: <a href="{itad.URL_FONTE}" style="color:#777">{itad.FONTE}</a>. '
        "Preços, jogadores e anúncios: Steam.<br>"
        f"Você recebe este boletim porque se inscreveu em {html.escape(perfil['consentimento'])}. "
        "Para sair, responda este e-mail com SAIR.</p></div>"
    )
    return "".join(partes)


def montar_alerta(perfil, textos, assunto_email):
    return (
        f"<b>Radar VR · {html.escape(perfil['nome'])}</b>\n{html.escape(textos['alerta'])}\n\n"
        f"Boletim completo no seu e-mail: <i>{html.escape(assunto_email)}</i>"
    )


# ------------------------------------------------------------ orquestracao

def _envelope(perfil, edicao):
    inicio = time.perf_counter()
    selecao = selecionar(perfil, edicao)
    relevante = selecao["itens"] or any(j.get("desconto") for j in selecao["seguidos"])

    envelope = {
        "edicao_id": edicao["id"],
        "perfil_id": perfil["id"],
        "itens": len(selecao["itens"]),
        "urgentes": len(selecao["urgentes"]),
        "email": None,
        "instantaneo": None,
    }
    if not relevante:
        envelope["motivo"] = "sem movimento nos interesses do assinante"
        envelope["origem_texto"] = "-"
        envelope["latencia_ms"] = round((time.perf_counter() - inicio) * 1000)
        return envelope

    textos, origem = redigir(perfil, selecao)
    envelope["origem_texto"] = origem
    envelope["email"] = {
        "para": perfil["email"],
        "assunto": textos["assunto"],
        "html": montar_email(perfil, selecao, textos, edicao),
        "anexo": edicao.get("audio") or "",
    }
    canal = perfil.get("instantaneo") or {}
    if selecao["urgentes"] and canal.get("canal") and textos.get("alerta"):
        envelope["instantaneo"] = {
            "canal": canal["canal"],
            "destino": canal["destino"],
            "texto": montar_alerta(perfil, textos, textos["assunto"]),
        }
        envelope["motivo"] = "urgência: alerta instantâneo e boletim por e-mail"
    else:
        envelope["motivo"] = "boletim por e-mail"
    envelope["latencia_ms"] = round((time.perf_counter() - inicio) * 1000)
    return envelope


def personalizar(edicao, perfis, paralelo=None):
    paralelo = paralelo or config.PERSONALIZACAO_PARALELA
    with ThreadPoolExecutor(max_workers=paralelo) as executor:
        return list(executor.map(lambda p: _envelope(p, edicao), perfis))


def metricas():
    return dict(_metricas, entradas_cache=len(_cache))


def limpar_cache():
    with _cache_trava:
        _cache.clear()
    for chave in _metricas:
        _metricas[chave] = 0
