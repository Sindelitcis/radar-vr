"""Edicao em pagina, para leitura.

Complementa o audio: a narracao serve para varrer o boletim sem tirar o
headset, a pagina resolve o nome escrito e leva a loja por link. Arquivo
autocontido, sem dependencia externa.
"""
import html
import logging
from datetime import datetime

import config

log = logging.getLogger("html")

ROTULOS = {
    "PROMOCAO_ACABANDO": ("Acaba em breve", "#dc2626"),
    "PRECO_MINIMO": ("Menor preço", "#7c3aed"),
    "PATCH_GRANDE": ("Atualização", "#2563eb"),
    "PROMOCAO_NOVA": ("Promoção", "#059669"),
    "PICO_JOGADORES": ("Em alta", "#ea580c"),
    "QUEDA_JOGADORES": ("Em queda", "#64748b"),
    "ONDA_AVALIACOES": ("Movimento", "#64748b"),
}

SECOES = [
    ("destaques", "Destaques do dia"),
    ("promocoes", "Promoções"),
    ("radar", "No radar"),
]

ESTILO = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 20px 16px 40px;
  font: 15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif;
  background: #f7f7f5; color: #1a1a1a;
}
.folha { max-width: 1080px; margin: 0 auto; }
header {
  border-bottom: 3px solid #1a1a1a; padding-bottom: 10px; margin-bottom: 16px;
  display: flex; align-items: baseline; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
}
h1 { font-size: 26px; margin: 0; letter-spacing: -0.5px; }
.data { color: #666; font-size: 13px; }
.aviso {
  background: #fff8e1; border-left: 4px solid #f59e0b;
  padding: 10px 14px; margin: 0 0 16px; font-size: 13.5px; border-radius: 0 6px 6px 0;
}
.grade {
  display: grid; gap: 12px; align-items: start;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
}
.grade > h2, .grade > .manchete, .grade > .bloco { grid-column: 1 / -1; }
h2 {
  font-size: 12px; text-transform: uppercase; letter-spacing: 1.2px;
  color: #666; margin: 14px 0 0; font-weight: 600;
}
.manchete { background: #1a1a1a; color: #fff; padding: 18px 20px; border-radius: 10px; }
.manchete .etiqueta { background: rgba(255,255,255,.18); }
.manchete h3 { font-size: 19px; }
.manchete a { color: #fff; }
.manchete .dados { color: #b8b8b8; }
.item {
  background: #fff; border: 1px solid #e5e5e2; border-radius: 10px;
  padding: 14px 16px; height: 100%;
}
.etiqueta {
  display: inline-block; font-size: 10.5px; font-weight: 600; color: #fff;
  padding: 2px 8px; border-radius: 20px; text-transform: uppercase;
  letter-spacing: .6px; margin-bottom: 7px;
}
h3 { font-size: 16px; margin: 0 0 5px; line-height: 1.3; }
h3 a { color: inherit; text-decoration: none; border-bottom: 2px solid #d4d4d0; }
h3 a:hover { border-color: currentColor; }
.linha { margin: 0 0 9px; font-size: 14px; }
.dados { font-size: 12.5px; color: #666; display: flex; flex-wrap: wrap; gap: 4px 12px; }
.dados b { color: #1a1a1a; font-weight: 600; }
.preco { display: inline-flex; align-items: center; gap: 7px; }
.corte { background: #059669; color: #fff; font-weight: 600; padding: 1px 6px; border-radius: 3px; }
.cheio { text-decoration: line-through; opacity: .55; }
.final { font-weight: 600; color: #1a1a1a; }
.bloco { background: #fff; border: 1px solid #e5e5e2; border-radius: 10px; padding: 14px 16px; }
.bloco > .titulo { font-size: 14px; margin: 0 0 10px; }
.bloco.manchete { background: #1a1a1a; color: #fff; border: none; padding: 18px 20px; }
.bloco.manchete > .titulo { font-size: 17px; }
.bloco.manchete .jogo { background: rgba(255,255,255,.08); }
.bloco.manchete .jogo a { color: #fff; }
.bloco.manchete .cheio { color: #b8b8b8; }
.bloco.manchete .final { color: #fff; }
.lista { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); }
.lista .jogo {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 10px; padding: 7px 10px; background: #f7f7f5; border-radius: 6px; font-size: 13.5px;
}
.lista .jogo a { color: inherit; text-decoration: none; font-weight: 500; }
.lista .jogo a:hover { text-decoration: underline; }
footer {
  margin-top: 28px; padding-top: 14px; border-top: 1px solid #ddd;
  font-size: 12.5px; color: #777; line-height: 1.6;
}
footer a { color: inherit; }
footer strong { color: #1a1a1a; font-weight: 600; }
footer .meta { display: inline-block; margin-top: 6px; font-size: 11.5px; opacity: .75; }
@media (prefers-color-scheme: dark) {
  body { background: #17171a; color: #e8e8e6; }
  header { border-bottom-color: #e8e8e6; }
  .item, .bloco { background: #202024; border-color: #303036; }
  .manchete { background: #2563eb; }
  h2, .data, .dados, footer { color: #9a9aa0; }
  .dados b, .final, footer strong { color: #e8e8e6; }
  h3 a { border-color: #45454d; }
  .aviso { background: #2a2418; border-left-color: #f59e0b; }
  .lista .jogo { background: #17171a; }
}
"""


def _preco(evento):
    """Preco no formato da loja: corte, valor cheio riscado e valor final."""
    final = evento.get("preco")
    if not final:
        return ""
    cheio = evento.get("preco_cheio")
    desconto = evento.get("desconto") or 0
    if not cheio or not desconto:
        return f'<span class="preco"><span class="final">{html.escape(final)}</span></span>'
    return (
        '<span class="preco">'
        f'<span class="corte">-{desconto}%</span>'
        f'<span class="cheio">{html.escape(cheio)}</span>'
        f'<span class="final">{html.escape(final)}</span>'
        "</span>"
    )


def _dados(evento):
    partes = []
    preco = _preco(evento)
    if preco:
        partes.append(preco)

    dados = evento.get("dados", {})
    if dados.get("faltam") is not None and not dados.get("membros"):
        faltam = dados["faltam"]
        prazo = {0: "termina hoje", 1: "termina amanhã"}.get(
            faltam, f"termina em {faltam} dias"
        )
        partes.append(f"<span><b>{prazo}</b></span>")

    variacao = dados.get("variacao")
    if variacao is not None:
        seta = "▲" if variacao > 0 else "▼"
        partes.append(
            f'<span>{seta} <b>{abs(variacao)}%</b> · '
            f'{dados["antes"]} → {dados["agora"]} jogadores</span>'
        )

    if dados.get("novas"):
        partes.append(f'<span><b>+{dados["novas"]}</b> avaliações</span>')

    return "".join(partes)


def _cartao(evento, destaque=False):
    rotulo, cor = ROTULOS.get(evento["tipo"], ("Movimento", "#64748b"))
    estilo = "" if destaque else f' style="background:{cor}"'
    return f"""<article class="{'manchete' if destaque else 'item'}">
  <span class="etiqueta"{estilo}>{rotulo}</span>
  <h3><a href="{html.escape(evento['url'])}" target="_blank" rel="noopener">{html.escape(evento['nome'])}</a></h3>
  <p class="linha">{html.escape(evento.get('linha') or evento['resumo'])}</p>
  <div class="dados">{_dados(evento)}</div>
</article>"""


def _bloco_agrupado(evento, destaque=False):
    """Expande um evento agrupado na lista completa de titulos.

    O agrupamento existe para o audio, onde repetir a mesma data seria
    redundante. Na pagina ha espaco para mostrar todos os titulos envolvidos.
    """
    membros = evento["dados"]["membros"]
    linhas = "".join(
        f'<div class="jogo">'
        f'<a href="{html.escape(m["url"])}" target="_blank" rel="noopener">'
        f'{html.escape(m["nome"])}</a>{_preco(m)}</div>'
        for m in membros
    )
    faltam = evento["dados"]["faltam"]
    prazo = {0: "termina hoje", 1: "termina amanhã"}.get(
        faltam, f"termina em {faltam} dias, dia {evento['dados']['fim'][:5]}"
    )
    cor = ROTULOS["PROMOCAO_ACABANDO"][1]
    estilo = "" if destaque else f' style="background:{cor}"'
    return f"""<div class="bloco{' manchete' if destaque else ''}">
  <span class="etiqueta"{estilo}>Acaba em breve</span>
  <p class="titulo"><b>{len(membros)} títulos</b> com promoção que {prazo}</p>
  <div class="lista">{linhas}</div>
</div>"""


def _renderizar(evento, destaque=False):
    if evento["dados"].get("membros"):
        return _bloco_agrupado(evento, destaque)
    return _cartao(evento, destaque)


def gerar(eventos, titulos_observados, primeira_edicao, arquivo_audio=""):
    agora = datetime.now()
    partes = [
        "<!doctype html>",
        '<html lang="pt-BR"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>Radar VR — {agora:%d/%m/%Y}</title>",
        f"<style>{ESTILO}</style></head><body><div class='folha'>",
        "<header><h1>Radar VR</h1>",
        f'<div class="data">{agora:%d/%m/%Y} · {agora:%H:%M} · '
        f"{titulos_observados} títulos monitorados</div></header>",
    ]

    if primeira_edicao:
        partes.append(
            '<div class="aviso"><b>Primeira edição.</b> Esta execução estabelece a '
            "linha de base. Variações de preço e de jogadores passam a ser "
            "comparadas a partir da próxima edição.</div>"
        )

    if not eventos:
        partes.append(
            '<div class="aviso">Nenhuma movimentação relevante entre os títulos '
            "monitorados. Catálogo estável.</div>"
        )
    else:
        partes.append('<div class="grade">')
        partes.append(_renderizar(eventos[0], destaque=True))
        agrupados = {}
        for evento in eventos[1:]:
            agrupados.setdefault(evento["secao"], []).append(evento)
        for chave, titulo in SECOES:
            bloco = agrupados.get(chave)
            if not bloco:
                continue
            partes.append(f"<h2>{titulo}</h2>")
            partes += [_renderizar(e) for e in bloco]
        partes.append("</div>")

    ouvir = (
        f' · <a href="../audio/{html.escape(arquivo_audio)}">ouvir a narração</a>'
        if arquivo_audio else ""
    )
    movimentos = (
        "1 movimento relevante" if len(eventos) == 1
        else f"{len(eventos)} movimentos relevantes"
    )
    partes.append(
        "<footer><strong>Seu jornal diário de realidade virtual.</strong> "
        "Preços, jogadores ativos, avaliações e anúncios direto da Steam — "
        "processado 100% na sua máquina.<br>"
        f"<span class='meta'>{titulos_observados} títulos monitorados · "
        f"{movimentos} nesta edição{ouvir}</span>"
        "</footer></div></body></html>"
    )

    pagina = "\n".join(partes)
    destino = config.DIR_DADOS / f"boletim_{agora:%Y-%m-%d_%H-%M}.html"
    destino.write_text(pagina, encoding="utf-8")
    (config.DIR_DADOS / "boletim_atual.html").write_text(pagina, encoding="utf-8")

    log.info("  HTML   -> %s (+ boletim_atual.html)", destino.name)
    return destino
