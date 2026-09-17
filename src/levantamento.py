"""Levantamento do catalogo VR para o diagnostico.

Usa apenas a biblioteca padrao: os numeros citados no diagnostico precisam ser
reproduziveis sem instalar dependencias.

    python src/levantamento.py
"""
import json
import re
import statistics
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

UA = {"User-Agent": "RadarVR-Levantamento/1.0 (projeto academico PUCPR)"}
BUSCA = "https://store.steampowered.com/search/results/"
DETALHES = "https://store.steampowered.com/api/appdetails"
RE_APPID = re.compile(r"/apps/(\d+)/")
AMOSTRA = 25


def pegar(url, params):
    alvo = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(alvo, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def contar(**extra):
    dados = pegar(BUSCA, {
        "query": "", "category1": 998, "vrsupport": 401,
        "cc": "br", "l": "portuguese", "json": 1, "infinite": 1, **extra,
    })
    return dados.get("total_count", 0)


def amostrar_precos(n=AMOSTRA):
    dados = pegar(BUSCA, {
        "query": "", "category1": 998, "vrsupport": 401, "specials": 1,
        "cc": "br", "l": "portuguese", "json": 1,
    })
    appids = []
    for item in dados.get("items", []):
        achado = RE_APPID.search(item.get("logo", ""))
        if achado and int(achado.group(1)) not in appids:
            appids.append(int(achado.group(1)))
        if len(appids) >= n:
            break

    precos, descontos, gratis = [], [], 0
    for appid in appids:
        try:
            bloco = pegar(DETALHES, {"appids": appid, "cc": "br", "l": "portuguese"})
            ficha = bloco.get(str(appid), {})
            if not ficha.get("success"):
                continue
            dados_jogo = ficha["data"]
            if dados_jogo.get("is_free"):
                gratis += 1
                continue
            preco = dados_jogo.get("price_overview")
            if preco:
                precos.append(preco["final"] / 100)
                descontos.append(preco.get("discount_percent", 0))
        except Exception:
            continue
    return precos, descontos, gratis, len(appids)


def main():
    print("Coletando dados do catalogo VR da Steam...\n")
    total_vr = contar()
    em_promo = contar(specials=1)
    precos, descontos, gratis, amostrados = amostrar_precos()

    relatorio = {
        "coletado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fonte": "Steam Web API (store.steampowered.com) - acesso publico sem chave",
        "total_jogos_vr": total_vr,
        "jogos_vr_em_promocao": em_promo,
        "percentual_em_promocao": round(em_promo / total_vr * 100, 1) if total_vr else 0,
        "amostra_analisada": amostrados,
        "preco_medio_promocao_brl": round(statistics.mean(precos), 2) if precos else 0,
        "preco_mediano_promocao_brl": round(statistics.median(precos), 2) if precos else 0,
        "preco_min_brl": round(min(precos), 2) if precos else 0,
        "preco_max_brl": round(max(precos), 2) if precos else 0,
        "desconto_medio_pct": round(statistics.mean(descontos), 1) if descontos else 0,
        "titulos_gratuitos_na_amostra": gratis,
    }

    largura = 62
    print("=" * largura)
    print("LEVANTAMENTO DO CATALOGO VR - STEAM".center(largura))
    print("=" * largura)
    for chave, valor in relatorio.items():
        print(f"  {chave.replace('_', ' '):<34} {valor}")
    print("=" * largura)

    destino = Path(__file__).resolve().parent.parent / "data" / "levantamento_diagnostico.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(
        json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSalvo em: {destino}")
    return relatorio


if __name__ == "__main__":
    main()
