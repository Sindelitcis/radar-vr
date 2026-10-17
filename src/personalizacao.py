"""Edicao personalizada por assinante.

Para cada perfil, tres decisoes em sequencia:

    1. selecao   que fatos da edicao interessam a esta pessoa
    2. canal     e-mail sempre que houver fato relevante; alerta instantaneo
                 so quando ha urgencia (oferta acabando, menor preco)
    3. texto     assunto, abertura e alerta montados a partir dos fatos

Tudo aqui e regra. O LLM fica na edicao, onde resume o texto livre dos
anuncios; os cartoes reaproveitam esse resumo. Uma versao anterior usava o
modelo para escrever o assunto de cada assinante, e saiu por dois motivos
medidos: era o gargalo da personalizacao e inventava detalhes que nao
estavam nos fatos (docs/07_testes.md).

As mensagens sao feitas para leitura de relance: so o que mudou, um rotulo
colorido por fato, preco com o corte em destaque e uma linha curta.
"""
import html
import json
import logging
import time
from datetime import datetime

import boletim_html
import config
import itad

log = logging.getLogger("perfil")

PRAZO_URGENTE_DIAS = 2
MAX_ITENS_EMAIL = 6
MAX_ITENS_ALERTA = 3

TIPOS_DE_PRECO = {"PRECO_MINIMO", "PROMOCAO_ACABANDO", "PROMOCAO_NOVA", "PROMOCAO_ENCERRADA"}
ICONES = {"PRECO_MINIMO": "🔥", "PROMOCAO_ACABANDO": "⏳"}


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


def _urgente(evento):
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
        dentro_do_orcamento = (
            orcamento is None or (jogo.get("preco_num") or 0) <= orcamento
        )
        if _urgente(evento) and dentro_do_orcamento:
            urgentes.append(evento)
        else:
            itens.append(evento)
    # O que nao cabe no e-mail fica de fora tambem da contagem e do assunto.
    return {"urgentes": urgentes, "itens": itens[:MAX_ITENS_EMAIL]}


def _fato(evento):
    return evento.get("linha") or f"{evento['nome']} {evento['resumo']}"


def destaque(evento):
    """O fato em poucas palavras, para ler de relance."""
    dados = evento.get("dados", {})
    tipo = evento["tipo"]
    if tipo == "PRECO_MINIMO":
        visto = dados.get("visto_em")
        return "Menor preço histórico" + (f" · visto pela última vez em {visto}" if visto else "")
    if tipo == "PROMOCAO_ACABANDO":
        faltam = dados.get("faltam", 0)
        return {0: "Promoção acaba hoje", 1: "Promoção acaba amanhã"}.get(
            faltam, f"Promoção acaba em {faltam} dias")
    if tipo == "PROMOCAO_NOVA":
        return "Entrou em promoção" if evento["resumo"].startswith("entrou") else "Em promoção"
    if tipo == "PROMOCAO_ENCERRADA":
        return "Saiu de promoção"
    if tipo in ("PICO_JOGADORES", "QUEDA_JOGADORES") and dados.get("variacao") is not None:
        return f"{dados['variacao']:+.0f}% jogadores online"
    if tipo == "ONDA_AVALIACOES" and dados.get("novas"):
        return f"+{dados['novas']} avaliações"
    texto = _fato(evento)
    if texto.startswith(evento["nome"]):
        texto = texto[len(evento["nome"]):].strip(" ,.:")
    texto = texto[:1].upper() + texto[1:]
    return texto if len(texto) <= 90 else texto[:87].rstrip() + "…"


# ------------------------------------------------------------------- texto

def _assunto_de(evento):
    nome, tipo = evento["nome"], evento["tipo"]
    if tipo == "PRECO_MINIMO":
        return f"{nome} no menor preço histórico"
    if tipo == "PROMOCAO_ACABANDO":
        return f"{destaque(evento).replace('Promoção', f'Promoção de {nome}', 1)}"
    if tipo == "PROMOCAO_NOVA":
        return f"{nome} entrou em promoção"
    if tipo == "PATCH_GRANDE":
        return f"{nome} recebeu atualização"
    return f"Novidade em {nome}"


def textos(selecao):
    """Assunto e abertura do e-mail, a partir do fato mais importante."""
    eventos = selecao["urgentes"] + selecao["itens"]
    urgentes, demais = len(selecao["urgentes"]), len(selecao["itens"])
    assunto = _assunto_de(eventos[0])
    if len(eventos) > 1:
        assunto += f" e mais {len(eventos) - 1}"

    partes = []
    if urgentes:
        partes.append("Uma oferta pede atenção hoje." if urgentes == 1
                      else f"{urgentes} ofertas pedem atenção hoje.")
    if demais:
        partes.append("Uma novidade nos seus jogos." if demais == 1
                      else f"{demais} novidades nos seus jogos.")
    return {"assunto": assunto, "abertura": " ".join(partes)}


# ------------------------------------------------------------------ e-mail

FONTE_EMAIL = "-apple-system,'Segoe UI',Roboto,Arial,sans-serif"
LARANJA, LARANJA_CLARO = "#ea580c", "#fff7ed"
VERDE = "#059669"


def _preco_html(evento):
    if evento["tipo"] not in TIPOS_DE_PRECO or not evento.get("preco"):
        return ""
    partes = []
    if evento.get("desconto"):
        partes.append(
            f'<span style="background:{VERDE};color:#fff;font-weight:700;font-size:12px;'
            f'padding:2px 6px;border-radius:4px">-{evento["desconto"]}%</span> '
        )
    if evento.get("preco_cheio") and evento.get("desconto"):
        partes.append(f'<span style="color:#888;text-decoration:line-through;font-size:13px">'
                      f'{html.escape(evento["preco_cheio"])}</span> ')
    partes.append(f'<b style="font-size:15px">{html.escape(evento["preco"])}</b>')
    return f'<div style="margin:6px 0 2px">{"".join(partes)}</div>'


def _cartao(evento, urgente=False):
    rotulo, cor = boletim_html.ROTULOS.get(evento["tipo"], ("Novidade", "#64748b"))
    fundo = "#ffffff"
    borda = LARANJA if urgente else cor
    return (
        f'<div style="background:{fundo};border:1px solid #e5e7eb;border-left:4px solid {borda};'
        f'border-radius:8px;padding:12px 14px;margin:0 0 10px">'
        f'<span style="background:{cor};color:#fff;font-size:11px;font-weight:700;'
        f'letter-spacing:.4px;text-transform:uppercase;padding:2px 8px;border-radius:99px">'
        f'{html.escape(rotulo)}</span>'
        f'<div style="font-size:17px;font-weight:700;margin:8px 0 0">'
        f'<a href="{html.escape(evento["url"])}" style="color:#111;text-decoration:none">'
        f'{html.escape(evento["nome"])}</a></div>'
        f'{_preco_html(evento)}'
        f'<div style="color:#555;font-size:13px;margin-top:4px">{html.escape(destaque(evento))}</div>'
        f"</div>"
    )


def _secao(titulo, conteudo, cor="#6b7280", fundo=None):
    caixa = (f"background:{fundo};border-radius:10px;padding:12px 12px 2px;margin:0 0 16px"
             if fundo else "margin:0 0 16px")
    return (
        f'<div style="{caixa}">'
        f'<div style="color:{cor};font-size:12px;font-weight:800;letter-spacing:.8px;'
        f'text-transform:uppercase;margin:0 0 8px">{titulo}</div>{conteudo}</div>'
    )


def montar_email(perfil, selecao, mensagem, edicao):
    data = datetime.fromisoformat(edicao["publicada_em"]).strftime("%d/%m")
    inscrito = datetime.fromisoformat(perfil["consentimento"]).strftime("%d/%m/%Y")
    partes = [
        f'<div style="font-family:{FONTE_EMAIL};color:#111;line-height:1.45;'
        f'max-width:560px;margin:0 auto;padding:20px 16px">',
        f'<div style="font-size:12px;font-weight:800;letter-spacing:1.5px;color:{LARANJA}">'
        f'RADAR VR <span style="color:#9ca3af;font-weight:400;letter-spacing:0">· {data}</span></div>',
        f'<div style="font-size:22px;font-weight:800;margin:6px 0 2px">Olá, {html.escape(perfil["nome"])}</div>',
        f'<div style="color:#555;margin:0 0 18px">{html.escape(mensagem["abertura"])}</div>',
    ]
    if selecao["urgentes"]:
        partes.append(_secao(
            "Atenção hoje",
            "".join(_cartao(e, urgente=True) for e in selecao["urgentes"]),
            cor=LARANJA, fundo=LARANJA_CLARO,
        ))
    if selecao["itens"]:
        partes.append(_secao(
            "Novidades nos seus jogos",
            "".join(_cartao(e) for e in selecao["itens"]),
        ))
    if edicao.get("audio"):
        partes.append('<div style="color:#555;font-size:13px">Narração da edição em anexo.</div>')
    partes.append(
        '<div style="border-top:1px solid #e5e7eb;margin:18px 0 0;padding-top:10px;'
        'color:#9ca3af;font-size:11px">'
        f'Preço histórico: <a href="{itad.URL_FONTE}" style="color:#9ca3af">{itad.FONTE}</a> · '
        f"dados da Steam · inscrito em {inscrito} · responda SAIR para cancelar</div></div>"
    )
    return "".join(partes)


def montar_texto(perfil, selecao, mensagem):
    """Versao em texto puro do e-mail, para leitores sem HTML e filtros de spam."""
    linhas = [f"Olá, {perfil['nome']}", mensagem["abertura"], ""]
    for titulo, eventos in (("ATENÇÃO HOJE", selecao["urgentes"]),
                            ("NOVIDADES NOS SEUS JOGOS", selecao["itens"])):
        if not eventos:
            continue
        linhas.append(titulo)
        for evento in eventos:
            preco = f" · {evento['preco']}" if evento["tipo"] in TIPOS_DE_PRECO and evento.get("preco") else ""
            linhas.append(f"- {evento['nome']}{preco}: {destaque(evento)}")
            linhas.append(f"  {evento['url']}")
        linhas.append("")
    linhas.append(f"Preço histórico: {itad.FONTE} · responda SAIR para cancelar")
    return "\n".join(linhas)


# ---------------------------------------------------------------- alerta

def _linha_alerta(evento):
    icone = ICONES.get(evento["tipo"], "•")
    titulo = f'{icone} <a href="{html.escape(evento["url"])}"><b>{html.escape(evento["nome"])}</b></a>'
    if evento.get("desconto"):
        titulo += f"  −{evento['desconto']}%"
    preco = ""
    if evento.get("preco"):
        cheio = evento.get("preco_cheio") if evento.get("desconto") else ""
        preco = (f"<s>{html.escape(cheio)}</s> " if cheio else "") + f"<b>{html.escape(evento['preco'])}</b> · "
    resumo = destaque(evento).split(" · ")[0]  # no chat, so o essencial; a data fica no e-mail
    return f"{titulo}\n{preco}{resumo[:1].lower() + resumo[1:]}"


def montar_alerta(selecao):
    return "\n\n".join(_linha_alerta(e) for e in selecao["urgentes"][:MAX_ITENS_ALERTA])


def montar_complemento(selecao):
    """Demais novidades em uma linha cada, para quando o e-mail nao chega."""
    if not selecao["itens"]:
        return ""
    linhas = []
    for evento in selecao["itens"]:
        fato = destaque(evento).split(" · ")[0]
        linhas.append(f'• <a href="{html.escape(evento["url"])}">{html.escape(evento["nome"])}</a>: '
                      f'{html.escape(fato[:1].lower() + fato[1:])}')
    return "Também hoje:\n" + "\n".join(linhas)


# ------------------------------------------------------------ orquestracao

def _envelope(perfil, edicao):
    inicio = time.perf_counter()
    selecao = selecionar(perfil, edicao)

    envelope = {
        "edicao_id": edicao["id"],
        "perfil_id": perfil["id"],
        "itens": len(selecao["itens"]) + len(selecao["urgentes"]),
        "urgentes": len(selecao["urgentes"]),
        "email": None,
        "instantaneo": None,
    }
    if not envelope["itens"]:
        envelope["motivo"] = "sem novidade nos interesses do assinante"
        envelope["latencia_ms"] = round((time.perf_counter() - inicio) * 1000)
        return envelope

    mensagem = textos(selecao)
    envelope["email"] = {
        "para": perfil["email"],
        "assunto": mensagem["assunto"],
        "html": montar_email(perfil, selecao, mensagem, edicao),
        "texto": montar_texto(perfil, selecao, mensagem),
        "anexo": edicao.get("audio") or "",
    }
    canal = perfil.get("instantaneo") or {}
    if selecao["urgentes"] and canal.get("canal"):
        envelope["instantaneo"] = {
            "canal": canal["canal"],
            "destino": canal["destino"],
            "texto": montar_alerta(selecao),
            # So entra se o e-mail falhar: o alerta passa a carregar o resto
            # do dia, que de outro modo se perderia.
            "complemento": montar_complemento(selecao),
        }
        envelope["motivo"] = "urgência: alerta instantâneo e boletim por e-mail"
    else:
        envelope["motivo"] = "boletim por e-mail"
    envelope["latencia_ms"] = round((time.perf_counter() - inicio) * 1000)
    return envelope


def personalizar(edicao, perfis):
    return [_envelope(perfil, edicao) for perfil in perfis]
