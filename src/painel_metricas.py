"""Painel de desempenho do Radar VR.

Le as medicoes de testes/metricas.py e gera:

    evidencias/painel_metricas.html   painel com a historia dos dados
    evidencias/metricas_resumo.json   os mesmos numeros, para a documentacao

    python src/painel_metricas.py

As premissas do retorno (tempo manual, horas de desenvolvimento, valor da
hora, tarifa de energia) ficam em evidencias/premissas_roi.json, separadas
do que foi medido.
"""
import html
import json
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EVID = RAIZ / "evidencias"
ARQ_EXECUCOES = EVID / "metricas_execucoes.jsonl"
ARQ_ENVIOS_ANTIGOS = EVID / "envios_reais_2026-10-17.json"
ARQ_PREMISSAS = EVID / "premissas_roi.json"
ARQ_PAINEL = EVID / "painel_metricas.html"
ARQ_RESUMO = EVID / "metricas_resumo.json"

ETAPAS = [  # (chave no registro, nome no painel)
    ("coleta", "Coleta na Steam"),
    ("historico_precos", "Histórico de preços"),
    ("redacao", "Redação pelo modelo"),
    ("voz", "Narração"),
]


# ------------------------------------------------------------- numeros

def percentil(valores, p):
    if not valores:
        return None
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p / 100
    baixo, alto = int(k), min(int(k) + 1, len(ordenados) - 1)
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (k - baixo)


def num(valor, casas=1):
    """Numero no formato brasileiro."""
    texto = f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return texto


def duracao(segundos):
    if segundos is None:
        return "–"
    if segundos < 10:
        return f"{num(segundos)} s"
    if segundos < 60:
        return f"{round(segundos)} s"
    minutos, resto = divmod(round(segundos), 60)
    return f"{minutos} min" + (f" {resto} s" if resto else "")


def pct(parte, todo):
    return 100 * parte / todo if todo else 0.0


def carregar():
    linhas = []
    if ARQ_EXECUCOES.exists():
        for texto in ARQ_EXECUCOES.read_text(encoding="utf-8").splitlines():
            if texto.strip():
                linhas.append(json.loads(texto))
    linhas.sort(key=lambda l: l["ts"])
    return linhas


def resumir(execucoes, premissas, antigos):
    ok = [e for e in execucoes if e.get("status") == "success"]
    # A latencia do fluxo e calculada so em ensaio: com envio real o fluxo
    # inclui o tempo de transmitir os e-mails, que e outra medida.
    ensaio = [e for e in ok if e.get("modo") != "real"]
    reais = [e for e in ok if e.get("modo") == "real"]
    quentes = [e for e in ensaio if e.get("modelo_carregado")]
    frias = [e for e in ensaio if not e.get("modelo_carregado")]

    def etapas(grupo):
        return {chave: percentil([e["etapas_s"][chave] for e in grupo], 50)
                for chave, _ in ETAPAS} if grupo else {}

    def bloco(grupo):
        tempos = [e["fluxo_ms"] / 1000 for e in grupo]
        return {"n": len(grupo), "p50_s": percentil(tempos, 50),
                "p95_s": percentil(tempos, 95), "etapas_p50_s": etapas(grupo)}

    # A Steam desligou a rota antiga de avaliacoes em outubro de 2026. Ate a
    # correcao, toda edicao saia sem esses dados.
    antes = [e for e in ok if not e.get("titulos_com_avaliacao")]
    depois = [e for e in ok if e.get("titulos_com_avaliacao")]

    envios_reais = [envio for e in execucoes if e.get("modo") == "real"
                    for envio in e.get("envios", [])]
    email_novo = [v for v in envios_reais if v.get("canal") == "email"]
    canais = {}
    for canal, novos in (("email", email_novo),
                         ("telegram", [v for v in envios_reais if v.get("canal") == "telegram"])):
        velho = antigos.get("canais", {}).get(canal, {})
        latencias = [v["latencia_ms"] / 1000 for v in novos if v.get("status") == "enviado"]
        latencias += [ms / 1000 for ms in velho.get("latencias_ms", [])]
        enviados = sum(v.get("status") == "enviado" for v in novos) + velho.get("enviados", 0)
        falhas = sum(v.get("status") == "falhou" for v in novos) + velho.get("falhas", 0)
        canais[canal] = {
            "enviados": enviados, "falhas": falhas,
            "novembro": len(novos), "outubro": velho.get("enviados", 0) + velho.get("falhas", 0),
            "p50_s": percentil(latencias, 50), "p95_s": percentil(latencias, 95),
        }

    potencias = [e["gpu_w_medio"] for e in ok if e.get("gpu_w_medio")]
    geral = bloco(ensaio)
    resumo = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "periodo": [execucoes[0]["ts"], execucoes[-1]["ts"]] if execucoes else [],
        "execucoes": len(execucoes),
        "concluidas": len(ok),
        "falhas": len(execucoes) - len(ok),
        "taxa_sucesso_pct": pct(len(ok), len(execucoes)),
        "por_origem": {origem: sum(e["origem"] == origem for e in execucoes)
                       for origem in sorted({e["origem"] for e in execucoes})},
        "fluxo": geral,
        "fluxo_real": bloco(reais),
        "modelo_carregado": bloco(quentes),
        "modelo_frio": bloco(frias),
        "completas_antes_correcao": {"n": len(antes), "completas": sum(bool(e.get("completa")) for e in antes)},
        "completas_depois_correcao": {"n": len(depois), "completas": sum(bool(e.get("completa")) for e in depois)},
        "envio": canais,
        "gpu_w_medio": sum(potencias) / len(potencias) if potencias else None,
        "cpu_ocupada_p50_pct": percentil([e["cpu_ocupada_pct"] for e in ok
                                          if e.get("cpu_ocupada_pct") is not None], 50),
    }
    resumo["roi"] = retorno(resumo, premissas)
    return resumo


def retorno(resumo, p):
    """Retorno no primeiro ano. Tudo aqui depende das premissas do arquivo."""
    edicao_s = resumo["fluxo"]["p50_s"] or p["etapa2_total_s"]
    watts = (resumo["gpu_w_medio"] or 0) + p["watts_resto_do_computador"]
    energia_ano = watts * edicao_s / 3600 / 1000 * 365 * p["tarifa_reais_por_kwh"]
    manutencao_h = p["minutos_manutencao_por_mes"] * 12 / 60

    leitura = p.get("minutos_leitura_boletim", 0)

    def cenario(manuais, assinantes, fator_dev=1):
        minutos = manuais - leitura  # o boletim ainda precisa ser lido
        ganho_h = minutos * 365 / 60 * assinantes
        custo_h = p["horas_desenvolvimento"] * fator_dev + manutencao_h
        ganho = ganho_h * p["valor_hora_reais"]
        custo = custo_h * p["valor_hora_reais"] + energia_ano
        ganho_dia_h = minutos / 60 * assinantes - manutencao_h / 365
        return {
            "minutos_manuais": manuais, "minutos_por_dia": minutos, "assinantes": assinantes,
            "ganho_h": ganho_h, "custo_h": custo_h,
            "ganho_reais": ganho, "custo_reais": custo,
            "roi_pct": 100 * (ganho - custo) / custo,
            "payback_dias": p["horas_desenvolvimento"] * fator_dev / ganho_dia_h
            if ganho_dia_h > 0 else None,
        }

    base, pessimista = p["minutos_manuais_por_dia"], p["minutos_manuais_pessimista"]
    return {
        "energia_reais_ano": energia_ano,
        "watts_considerados": watts,
        "manutencao_h_ano": manutencao_h,
        "cenarios": [
            {"nome": "Hoje: só o autor usa", **cenario(base, 1)},
            {"nome": "Conferência manual mais rápida", **cenario(pessimista, 1)},
            {"nome": f"Hora de desenvolvimento valendo {p['fator_hora_desenvolvimento_pessimista']} vezes mais",
             **cenario(base, 1, p["fator_hora_desenvolvimento_pessimista"])},
            {"nome": "Dez assinantes (hipótese)", **cenario(base, 10)},
            {"nome": "Dez assinantes, conferência mais rápida (hipótese)", **cenario(pessimista, 10)},
        ],
        "base": cenario(base, 1),
        "pessimista": cenario(pessimista, 1),
        "dev_mais_caro": cenario(base, 1, p["fator_hora_desenvolvimento_pessimista"]),
    }


# ------------------------------------------------------------- graficos

def _e(texto):
    return html.escape(str(texto), quote=True)


def barras_antes_depois(itens, largura=720, x0=250):
    """Barras horizontais; `itens` = (nome, segundos, destaque)."""
    altura_linha = 44
    maximo = max(s for _, s, _ in itens)
    util = largura - x0 - 110
    partes = [f'<svg viewBox="0 0 {largura} {altura_linha * len(itens) + 8}" role="img" '
              f'aria-label="Tempo para saber o que mudou, antes e depois">']
    partes.append(f'<line x1="{x0}" y1="0" x2="{x0}" y2="{altura_linha * len(itens)}" class="eixo"/>')
    for i, (nome, segundos, destaque) in enumerate(itens):
        y = i * altura_linha + 10
        w = max(3, util * segundos / maximo)
        classe = "s1" if destaque else "apagado"
        partes.append(f'<text x="{x0 - 12}" y="{y + 16}" text-anchor="end" class="rotulo">{_e(nome)}</text>')
        partes.append(
            f'<path d="M{x0},{y} h{w - 4} a4,4 0 0 1 4,4 v16 a4,4 0 0 1 -4,4 h-{w - 4} z" '
            f'class="marca {classe}" tabindex="0" data-dica="{_e(nome)}: {_e(duracao(segundos))}"/>')
        partes.append(f'<text x="{x0 + w + 8}" y="{y + 16}" class="valor">{_e(duracao(segundos))}</text>')
    partes.append("</svg>")
    return "".join(partes)


def linha_execucoes(execucoes, p50, p95):
    """Tempo do fluxo em cada execucao, na ordem em que aconteceram."""
    largura, altura, x0, x1, y0, y1 = 540, 290, 44, 440, 16, 240
    n = len(execucoes)
    if not n:
        return "<p>Sem execuções registradas.</p>"
    tempos = [e.get("fluxo_ms", 0) / 1000 for e in execucoes]
    teto = max(tempos + [p95 or 0]) * 1.12 or 1
    passo_y = next(p for p in (5, 10, 20, 30, 60, 120, 300) if teto / p <= 6)

    def px(i):
        return x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0.5)

    def py(valor):
        return y1 - (y1 - y0) * valor / teto

    partes = [f'<svg viewBox="0 0 {largura} {altura}" role="img" '
              f'aria-label="Tempo do fluxo em cada execução">']
    marca = 0
    while marca <= teto:
        partes.append(f'<line x1="{x0}" y1="{py(marca):.1f}" x2="{x1}" y2="{py(marca):.1f}" class="grade"/>')
        partes.append(f'<text x="{x0 - 8}" y="{py(marca) + 4:.1f}" text-anchor="end" class="tique">{marca} s</text>')
        marca += passo_y
    for valor, nome in ((p50, "mediana"), (p95, "p95")):
        if valor:
            partes.append(f'<line x1="{x0}" y1="{py(valor):.1f}" x2="{x1}" y2="{py(valor):.1f}" class="referencia"/>')
            partes.append(f'<text x="{x1 + 6}" y="{py(valor) + 4:.1f}" class="tique">{nome} {_e(duracao(valor))}</text>')
    boas = [(i, t) for i, (e, t) in enumerate(zip(execucoes, tempos)) if e.get("status") == "success"]
    if len(boas) > 1:
        pontos = " ".join(f"{px(i):.1f},{py(t):.1f}" for i, t in boas)
        partes.append(f'<polyline points="{pontos}" class="fio"/>')
    for i, (e, t) in enumerate(zip(execucoes, tempos)):
        quando = datetime.fromisoformat(e["ts"]).strftime("%d/%m %H:%M")
        if e.get("status") != "success":
            x = px(i)
            partes.append(
                f'<g class="falha" tabindex="0" data-dica="{quando}: execução com erro">'
                f'<circle cx="{x:.1f}" cy="{y1}" r="12" class="alvo"/>'
                f'<path d="M{x - 5:.1f},{y1 - 5} l10,10 M{x + 5:.1f},{y1 - 5} l-10,10"/></g>')
            continue
        classe = "s1" if e.get("modelo_carregado") else "s2"
        estado = "modelo já na memória" if e.get("modelo_carregado") else "modelo frio"
        partes.append(
            f'<g tabindex="0" data-dica="{quando}: {_e(duracao(t))} ({estado})">'
            f'<circle cx="{px(i):.1f}" cy="{py(t):.1f}" r="12" class="alvo"/>'
            f'<circle cx="{px(i):.1f}" cy="{py(t):.1f}" r="4.5" class="ponto {classe}"/></g>')
    partes.append(f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" class="eixo"/>')
    primeiro = datetime.fromisoformat(execucoes[0]["ts"]).strftime("%d/%m %H:%M")
    ultimo = datetime.fromisoformat(execucoes[-1]["ts"]).strftime("%d/%m %H:%M")
    partes.append(f'<text x="{x0}" y="{y1 + 20}" class="tique">{primeiro}</text>')
    partes.append(f'<text x="{x1}" y="{y1 + 20}" text-anchor="end" class="tique">{ultimo}</text>')
    partes.append(f'<text x="{(x0 + x1) / 2}" y="{y1 + 38}" text-anchor="middle" class="tique">'
                  f'{n} execuções, na ordem em que rodaram</text>')
    partes.append("</svg>")
    return "".join(partes)


def barras_etapas(linhas):
    """Barras empilhadas; `linhas` = (nome, {etapa: segundos})."""
    linhas = [(nome, etapas) for nome, etapas in linhas if etapas]
    if not linhas:
        return "<p>Sem dados de etapas.</p>"
    largura, x0, altura_linha = 540, 150, 52
    util = largura - x0 - 86
    maximo = max(sum(etapas.values()) for _, etapas in linhas)
    partes = [f'<svg viewBox="0 0 {largura} {altura_linha * len(linhas) + 6}" role="img" '
              f'aria-label="Tempo de cada etapa da edição">']
    for i, (nome, etapas) in enumerate(linhas):
        y = i * altura_linha + 12
        partes.append(f'<text x="{x0 - 12}" y="{y + 16}" text-anchor="end" class="rotulo">{_e(nome)}</text>')
        x = x0
        for indice, (chave, rotulo) in enumerate(ETAPAS, 1):
            segundos = etapas.get(chave) or 0
            w = util * segundos / maximo
            if w < 1:
                continue
            partes.append(
                f'<rect x="{x:.1f}" y="{y}" width="{max(1, w - 2):.1f}" height="24" rx="2" '
                f'class="marca s{indice}" tabindex="0" '
                f'data-dica="{_e(nome)} · {_e(rotulo)}: {_e(duracao(segundos))}"/>')
            if w > 46:
                tinta = "escura" if indice == 4 else "clara"
                partes.append(f'<text x="{x + 6:.1f}" y="{y + 16}" class="dentro {tinta}">{_e(duracao(segundos))}</text>')
            x += w
        partes.append(f'<text x="{x + 6:.1f}" y="{y + 16}" class="valor">{_e(duracao(sum(etapas.values())))}</text>')
    partes.append("</svg>")
    legenda = "".join(f'<span><i class="s{i}"></i>{_e(rotulo)}</span>'
                      for i, (_, rotulo) in enumerate(ETAPAS, 1))
    return "".join(partes) + f'<div class="legenda">{legenda}</div>'


def medidores(linhas):
    """Lista de medidores; `linhas` = (nome, parte, todo, observacao)."""
    partes = ['<div class="medidores">']
    for nome, parte, todo, observacao in linhas:
        if not todo:
            continue
        valor = pct(parte, todo)
        partes.append(
            f'<div class="medidor" tabindex="0" data-dica="{_e(nome)}: {parte} de {todo}">'
            f'<div class="nome">{_e(nome)}<small>{_e(observacao)}</small></div>'
            f'<div class="figura">{num(valor, 0)}%<small>{parte} de {todo}</small></div>'
            f'<div class="trilho"><div class="cheio" style="width:{valor:.1f}%"></div></div></div>')
    partes.append("</div>")
    return "".join(partes)


# --------------------------------------------------------------- pagina

CSS = """
:root{--pagina:#f9f9f7;--superficie:#fcfcfb;--tinta:#0b0b0b;--tinta2:#52514e;--apagada:#898781;
--grade:#e1e0d9;--eixo:#c3c2b7;--borda:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;
--s4:#eda100;--neutro:#c3c2b7;--trilho:#cde2fb;--critico:#d03b3b;--bom:#006300}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){--pagina:#0d0d0d;
--superficie:#1a1a19;--tinta:#f0efec;--tinta2:#c3c2b7;--grade:#2c2c2a;--eixo:#383835;
--borda:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--neutro:#52514e;
--trilho:#104281;--critico:#e66767;--bom:#0ca30c}}
*{box-sizing:border-box}
body{margin:0;background:var(--pagina);color:var(--tinta);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1120px;margin:0 auto;padding:28px 16px 40px}
h1{font-size:28px;line-height:1.2;margin:0 0 6px;letter-spacing:-.3px}
.sub{color:var(--tinta2);margin:0 0 22px;max-width:760px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.8px;color:var(--tinta2);margin:30px 0 4px}
.tese{font-size:19px;line-height:1.35;margin:0 0 14px;max-width:820px;font-weight:600}
.cartao{background:var(--superficie);border:1px solid var(--borda);border-radius:10px;padding:16px 18px}
.cartao h3{font-size:15px;margin:0 0 2px}
.cartao .nota{color:var(--tinta2);font-size:13px;margin:0 0 10px}
.grade2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.indicadores{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.indicador .rotulo{color:var(--tinta2);font-size:13px}
.indicador .numero{font-size:34px;font-weight:600;line-height:1.15;margin:4px 0 2px}
.indicador .apoio{color:var(--tinta2);font-size:13px}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{fill:var(--tinta2);font-size:12.5px}
svg .rotulo{fill:var(--tinta);font-size:13.5px}
svg .valor{fill:var(--tinta);font-size:13.5px;font-weight:600}
svg .tique{fill:var(--apagada);font-size:11.5px;font-variant-numeric:tabular-nums}
svg .dentro{font-size:12px;font-weight:600}
svg .dentro.clara{fill:#fff} svg .dentro.escura{fill:#0b0b0b}
.grade{stroke:var(--grade);stroke-width:1} .eixo{stroke:var(--eixo);stroke-width:1}
.referencia{stroke:var(--apagada);stroke-width:1}
.fio{fill:none;stroke:var(--neutro);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.ponto{stroke:var(--superficie);stroke-width:2} .alvo{fill:transparent}
.s1{fill:var(--s1)} .s2{fill:var(--s2)} .s3{fill:var(--s3)} .s4{fill:var(--s4)}
.apagado{fill:var(--neutro)}
.falha path{stroke:var(--critico);stroke-width:2.5;stroke-linecap:round;fill:none}
[data-dica]{outline:none} [data-dica]:hover .ponto,[data-dica]:focus .ponto{r:6.5}
.marca:hover,.marca:focus{filter:brightness(1.12)}
.legenda{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:8px;color:var(--tinta2);font-size:13px}
.legenda i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
.legenda i.s1{background:var(--s1)} .legenda i.s2{background:var(--s2)}
.legenda i.s3{background:var(--s3)} .legenda i.s4{background:var(--s4)}
.legenda i.redondo{border-radius:50%} .legenda b{color:var(--critico);margin-right:6px}
.medidor{display:grid;grid-template-columns:1fr auto;gap:4px 14px;align-items:end;
padding:9px 0;border-top:1px solid var(--grade)}
.medidor .trilho{grid-column:1/-1}
.medidor:first-child{border-top:0}
.medidor small{display:block;color:var(--tinta2);font-size:12px;font-weight:400}
.trilho{height:8px;border-radius:4px;background:var(--trilho);overflow:hidden}
.cheio{height:100%;background:var(--s1);border-radius:4px}
.figura{text-align:right;font-weight:600;font-size:17px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:6px 8px;border-top:1px solid var(--grade)}
th{color:var(--tinta2);font-weight:600;border-top:0}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr.base td{font-weight:600}
ul.achados{margin:0;padding-left:20px} ul.achados li{margin:6px 0}
details{margin-top:10px;font-size:13px;color:var(--tinta2)} details table{margin-top:8px}
footer{color:var(--tinta2);font-size:12.5px;margin-top:26px;border-top:1px solid var(--grade);padding-top:12px}
#dica{position:fixed;pointer-events:none;background:var(--tinta);color:var(--superficie);
padding:5px 9px;border-radius:6px;font-size:12.5px;opacity:0;transition:opacity .08s;z-index:9;max-width:320px}
@media (max-width:760px){.grade2,.indicadores{grid-template-columns:1fr}}
"""

JS = """
// ?claro fixa o tema claro; ?parte1 e ?parte2 mostram metade do painel (imagens da documentacao).
if(location.search.includes('claro'))document.documentElement.dataset.theme='light';
for(const [parte,some] of [['parte1','.p2,details,footer'],['parte2','.p1,details,footer']])
if(location.search.includes(parte)){document.querySelectorAll(some).forEach(e=>e.hidden=true);
document.querySelector('main').style.padding='16px 16px 20px';
if(parte==='parte2')document.querySelector('.p2 h2').style.marginTop='0'}
const dica=document.getElementById('dica');
function mostrar(alvo,x,y){dica.textContent=alvo.dataset.dica;dica.style.opacity=1;
const l=Math.min(x+14,innerWidth-dica.offsetWidth-8);dica.style.left=l+'px';dica.style.top=(y+16)+'px'}
document.querySelectorAll('[data-dica]').forEach(el=>{
el.addEventListener('pointermove',e=>mostrar(el,e.clientX,e.clientY));
el.addEventListener('pointerleave',()=>dica.style.opacity=0);
el.addEventListener('focus',()=>{const r=el.getBoundingClientRect();mostrar(el,r.left+r.width/2,r.top+r.height/2)});
el.addEventListener('blur',()=>dica.style.opacity=0)});
"""


def montar(execucoes, r, p):
    fluxo, quente, frio = r["fluxo"], r["modelo_carregado"], r["modelo_frio"]
    manual_s = p["minutos_manuais_por_dia"] * 60
    mediana = fluxo["p50_s"]
    vezes = manual_s / mediana if mediana else 0
    base = r["roi"]["base"]
    antes, depois = r["completas_antes_correcao"], r["completas_depois_correcao"]
    email, telegram = r["envio"]["email"], r["envio"]["telegram"]
    dia = lambda iso: datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    periodo = (f"{dia(r['periodo'][0])} a {dia(r['periodo'][1])}"
               if r["periodo"] and dia(r["periodo"][0]) != dia(r["periodo"][1])
               else dia(r["periodo"][0]) if r["periodo"] else "")

    antes_depois = barras_antes_depois([
        (f"Conferir {15} jogos à mão (estimativa)", manual_s, False),
        ("Etapa 1: uma coisa de cada vez", p["etapa1_total_s"], True),
        ("Etapa 2: coleta em paralelo", p["etapa2_total_s"], True),
        ("Etapa final: mediana medida", mediana or 0, True),
    ])
    em_ensaio = [e for e in execucoes if e.get("modo") != "real"]
    serie = linha_execucoes(em_ensaio, fluxo["p50_s"], fluxo["p95_s"])
    concluidas = [e for e in em_ensaio if e.get("status") == "success" and e.get("etapas_s")]
    mais_lenta = max(concluidas, key=lambda e: e["fluxo_ms"], default=None)
    etapas = barras_etapas([
        ("Execução típica", fluxo["etapas_p50_s"]),
        ("Execução mais lenta", {chave: mais_lenta["etapas_s"].get(chave, 0) for chave, _ in ETAPAS}
         if mais_lenta else {}),
    ])
    confianca = medidores([
        ("Fluxo concluído sem erro", r["concluidas"], r["execucoes"], "execuções pelo n8n, em ensaio e reais"),
        ("Edição completa, antes da correção", antes["completas"], antes["n"],
         "a Steam tinha desligado a rota de avaliações em outubro"),
        ("Edição completa, depois da correção", depois["completas"], depois["n"],
         "com a rota nova de avaliações"),
        ("E-mails entregues", email["enviados"], email["enviados"] + email["falhas"],
         f"envios reais: {email['outubro']} em 17/10 e {email['novembro']} em novembro"),
        ("Alertas no Telegram entregues", telegram["enviados"], telegram["enviados"] + telegram["falhas"],
         f"envios reais: {telegram['outubro']} em 17/10 e {telegram['novembro']} em novembro"),
    ])
    envio = barras_antes_depois([
        ("E-mail, com o áudio anexo", email["p50_s"] or 0, True),
        ("Alerta no Telegram", telegram["p50_s"] or 0, True),
    ], largura=540, x0=200)

    linhas_roi = "".join(
        f'<tr class="{"base" if i == 0 else ""}"><td>{_e(c["nome"])}</td>'
        f'<td class="n">{c["assinantes"]}</td><td class="n">{c["minutos_por_dia"]} min</td>'
        f'<td class="n">{num(c["ganho_h"], 0)} h</td><td class="n">{num(c["custo_h"], 0)} h</td>'
        f'<td class="n">{num(c["roi_pct"], 0)}%</td>'
        f'<td class="n">{num(c["payback_dias"], 0) + " dias" if c["payback_dias"] else "não se paga"}</td></tr>'
        for i, c in enumerate(r["roi"]["cenarios"]))

    tabela_execucoes = "".join(
        f'<tr><td>{datetime.fromisoformat(e["ts"]).strftime("%d/%m %H:%M")}</td><td>{_e(e["origem"])}</td>'
        f'<td>{"ok" if e.get("status") == "success" else "erro"}</td>'
        f'<td class="n">{num(e.get("fluxo_ms", 0) / 1000)}</td>'
        + "".join(f'<td class="n">{num(e.get("etapas_s", {}).get(chave, 0))}</td>' for chave, _ in ETAPAS)
        + f'<td>{"sim" if e.get("modelo_carregado") else "não"}</td>'
        f'<td>{"sim" if e.get("completa") else "não"}</td></tr>'
        for e in execucoes)

    penalidade = (frio["p50_s"] - quente["p50_s"]) if frio["n"] and quente["n"] else None
    achados = [
        f"A coleta na Steam ocupa a maior parte da edição ({duracao(quente['etapas_p50_s'].get('coleta') or frio['etapas_p50_s'].get('coleta'))}). "
        "O ritmo é lento de propósito, para respeitar o limite da loja.",
    ]
    if penalidade is not None:
        achados.append(
            f"Na mediana, manter o modelo na memória poupa só {duracao(max(penalidade, 0))} por execução "
            f"({duracao(quente['p50_s'])} contra {duracao(frio['p50_s'])}). Não compensa ocupar a placa de vídeo o dia todo.")
    cargas_lentas = [e for e in em_ensaio if e.get("etapas_s", {}).get("redacao", 0) > 10]
    if cargas_lentas:
        achados.append(
            f"Os picos do gráfico vêm da carga do modelo: em {len(cargas_lentas)} execuções a redação passou de 10 s, "
            f"todas com o modelo frio. É isso que leva o p95 a {duracao(fluxo['p95_s'])}.")
    achados += [
        f"Cada e-mail leva {duracao(email['p50_s'])}; a causa ainda não foi isolada (o anexo é suspeito, mas em 17/10 e-mails com áudio saíram em 9 s). "
        f"O alerta no Telegram leva {duracao(telegram['p50_s'])}. O envio só foi medido com dois destinatários.",
        "O fluxo terminou sem erro mesmo quando faltava uma parte: a rota de avaliações desligada pela Steam "
        "não derrubou a edição, mas ela saiu incompleta sem avisar ninguém.",
    ]
    proximos = [
        "Avisar o operador quando a edição sair incompleta, e acompanhar a taxa de edições completas, não só a de fluxos sem erro.",
        "Trocar o áudio anexo por um arquivo menor ou por um link, e testar o envio com mais destinatários.",
        "Testar todo dia as rotas externas, para perceber no mesmo dia quando uma API muda.",
        "Carregar o modelo no início da edição, em paralelo com a coleta, para aproximar o p95 da mediana sem ocupar a placa o dia todo.",
        "Publicar o serviço fora do computador do operador e automatizar o cancelamento da inscrição.",
    ]

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radar VR · painel de desempenho</title><style>{CSS}</style></head>
<body><main>
<section class="p1">
<h1>Radar VR: do que mudou na Steam ao aviso certo, em menos de um minuto</h1>
<p class="sub">Painel de desempenho da automação. {r['execucoes']} execuções do fluxo completo pelo n8n,
{periodo}, no computador do operador em uso normal. Projeto da disciplina AI Factory (PUCPR), por Rafael Probst.</p>

<h2>1 · O problema</h2>
<p class="tese">A Steam mostra o preço e os jogadores de agora, mas não o que mudou desde ontem.
Quem acompanha 15 jogos de realidade virtual precisa abrir 15 páginas todo dia e lembrar como estavam.</p>

<div class="indicadores">
 <div class="cartao indicador"><div class="rotulo">Tempo para saber o que mudou</div>
  <div class="numero">{p['minutos_manuais_por_dia']} min → {p.get('minutos_leitura_boletim', 0)} min</div>
  <div class="apoio">do seu tempo por dia: a conferência à mão (estimativa) vira a leitura do boletim; a máquina faz o resto em {duracao(mediana)} (mediana)</div></div>
 <div class="cartao indicador"><div class="rotulo">Taxa de sucesso do fluxo</div>
  <div class="numero">{num(r['taxa_sucesso_pct'], 0)}%</div>
  <div class="apoio">{r['concluidas']} de {r['execucoes']} execuções terminaram sem erro</div></div>
 <div class="cartao indicador"><div class="rotulo">Retorno no primeiro ano, um assinante</div>
  <div class="numero">{num(base['roi_pct'], 0)}%</div>
  <div class="apoio">{num(base['ganho_h'], 0)} horas poupadas contra {num(base['custo_h'], 0)} investidas; o projeto se paga em {num(base['payback_dias'], 0)} dias</div></div>
</div>

<h2>2 · A solução, antes e depois</h2>
<p class="tese">O fluxo coleta os dados, compara com a leitura anterior, redige, narra e envia só o que mudou
para cada assinante.</p>
<div class="cartao"><h3>Tempo para saber o que mudou em 15 jogos</h3>
<p class="nota">A conferência manual é uma estimativa de 1 minuto por jogo. As três etapas do projeto foram medidas. A etapa final ficou um pouco mais lenta que a Etapa 2 porque as edições de novembro têm 5 ou 6 manchetes, contra 2 em 17/10, e a narração ficou mais longa.</p>
{antes_depois}</div>

<h2>3 · O que medimos</h2>
<p class="tese">Em ensaio, metade das execuções termina em até {duracao(fluxo['p50_s'])}, e 95% em até {duracao(fluxo['p95_s'])}.</p>
<div class="grade2">
 <div class="cartao"><h3>Latência do fluxo em cada execução</h3>
 <p class="nota">Do primeiro ao último nó do n8n, nas execuções em ensaio.</p>{serie}
 <div class="legenda"><span><i class="s1 redondo"></i>modelo já na memória</span>
 <span><i class="s2 redondo"></i>modelo frio</span><span><b>×</b>execução com erro</span></div></div>
 <div class="cartao"><h3>Para onde vai o tempo da edição</h3>
 <p class="nota">Tempo de cada etapa da edição, medido pelo microsserviço: a mediana e a execução mais demorada.</p>{etapas}</div>
</div>
</section>

<section class="p2">
<h2>4 · O que os dados revelaram</h2>
<p class="tese">O fluxo não falhou, mas a medição mostrou edições que saíam incompletas sem ninguém perceber.</p>
<div class="grade2">
 <div class="cartao"><h3>Confiabilidade</h3>
 <p class="nota">Edição completa: com áudio, com os resumos do modelo e com os dados de avaliações.</p>{confianca}</div>
 <div class="cartao"><h3>Tempo de cada envio real</h3>
 <p class="nota">Mediana por mensagem entregue.</p>{envio}
 <ul class="achados">{''.join(f'<li>{_e(a)}</li>' for a in achados)}</ul></div>
</div>

<h2>5 · Quanto vale</h2>
<p class="tese">O custo é quase fixo e o ganho cresce com cada assinante: o valor do projeto depende de abrir o serviço a mais gente.</p>
<div class="cartao"><h3>Retorno no primeiro ano, em horas</h3>
<p class="nota">Ganho: minutos de conferência manual poupados por dia, já descontado {p.get('minutos_leitura_boletim', 0)} min para ler o boletim. Custo: {p['horas_desenvolvimento']} horas de desenvolvimento
mais {num(r['roi']['manutencao_h_ano'], 0)} horas de manutenção por ano. A energia soma R$ {num(r['roi']['energia_reais_ano'], 2)} por ano.
Com mais de um assinante, o ganho por pessoa é uma hipótese a validar.</p>
<table><tr><th>Cenário</th><th class="n">Assinantes</th><th class="n">Tempo poupado por dia</th><th class="n">Ganho no ano</th>
<th class="n">Custo no ano</th><th class="n">Retorno</th><th class="n">Paga-se em</th></tr>{linhas_roi}</table></div>

<h2>6 · Próximos passos</h2>
<div class="cartao"><ul class="achados">{''.join(f'<li>{_e(x)}</li>' for x in proximos)}</ul></div>
</section>

<details><summary>Ver as execuções em tabela</summary>
<table><tr><th>Quando</th><th>Origem</th><th>Resultado</th><th class="n">Fluxo (s)</th>
{''.join(f'<th class="n">{_e(nome)} (s)</th>' for _, nome in ETAPAS)}<th>Modelo na memória</th><th>Completa</th></tr>
{tabela_execucoes}</table></details>

<footer>Fonte: evidencias/metricas_execucoes.jsonl (execuções), evidencias/envios_reais_2026-10-17.json (envios da Etapa 2)
e evidencias/premissas_roi.json (premissas do retorno). Em ensaio, nenhuma mensagem sai da máquina.
Nenhum dado de assinante aparece neste painel. Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}.</footer>
</main><div id="dica" role="status"></div><script>{JS}</script></body></html>"""


def main():
    execucoes = carregar()
    if not execucoes:
        print("Sem medições. Rode: python testes/metricas.py campanha 30")
        return
    premissas = json.loads(ARQ_PREMISSAS.read_text(encoding="utf-8"))
    antigos = json.loads(ARQ_ENVIOS_ANTIGOS.read_text(encoding="utf-8")) if ARQ_ENVIOS_ANTIGOS.exists() else {}
    resumo = resumir(execucoes, premissas, antigos)
    ARQ_RESUMO.write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    ARQ_PAINEL.write_text(montar(execucoes, resumo, premissas), encoding="utf-8")
    print(f"{resumo['execucoes']} execuções, {num(resumo['taxa_sucesso_pct'], 1)}% sem erro, "
          f"mediana {duracao(resumo['fluxo']['p50_s'])}, p95 {duracao(resumo['fluxo']['p95_s'])}")
    print(f"Painel: {ARQ_PAINEL}")


if __name__ == "__main__":
    main()
