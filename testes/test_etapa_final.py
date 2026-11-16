"""Testes das correcoes da etapa final. Nenhum acessa a rede.

    python testes/test_etapa_final.py

Casos que motivaram cada teste:
- a Steam desligou a rota de avaliacoes e o boletim passou a sair sem esses
  dados, sem avisar ninguem;
- a rota nova devolve dados do autor de uma avaliacao, que nao podem ficar;
- uma leitura de avaliacoes que falhou gravava total zero, e a leitura
  seguinte viraria uma "onda" com todas as avaliacoes do jogo;
- o nome do assinante era obrigatorio e o e-mail nao avisava do uso de IA.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import coleta  # noqa: E402
import config  # noqa: E402
import noticias  # noqa: E402
import personalizacao  # noqa: E402

RESPOSTA_STEAM = {
    "query_summary": {"num_reviews": 1, "review_score_desc": "Very Positive",
                      "total_positive": 900, "total_negative": 100, "total_reviews": 1000},
    "reviews": [{"recommendationid": "1", "author": {"steamid": "76561190000000000"},
                 "review": "texto de uma pessoa"}],
    "cursor": "abc",
}


def _trocar_get(resposta):
    chamadas = []

    def falso(url, params=None):
        chamadas.append((url, params))
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
    coleta._get = falso
    return chamadas


def test_avaliacoes_usa_a_rota_nova_e_pede_o_minimo():
    chamadas = _trocar_get(RESPOSTA_STEAM)
    coleta.buscar_avaliacoes(620980)
    url, params = chamadas[0]
    assert url == config.STEAM_AVALIACOES
    assert "IUserReviewsService/GetAppReviews" in url
    consulta = json.loads(params["input_json"])
    assert consulta["appid"] == 620980
    assert consulta["num_per_page"] == 1  # o minimo que a rota aceita


def test_avaliacoes_le_so_os_totais():
    _trocar_get(RESPOSTA_STEAM)
    dados = coleta.buscar_avaliacoes(620980)
    assert dados == {"aprovacao_pct": 90.0, "total_reviews": 1000,
                     "review_desc": "Very Positive"}
    # Nada do autor da avaliacao segue adiante.
    assert "steamid" not in json.dumps(dados)
    assert "texto de uma pessoa" not in json.dumps(dados)


def test_avaliacoes_aceita_resposta_embrulhada():
    _trocar_get({"response": RESPOSTA_STEAM})
    assert coleta.buscar_avaliacoes(1)["total_reviews"] == 1000


def test_avaliacoes_sem_resposta_nao_derruba_a_coleta():
    _trocar_get(ValueError("Expecting value"))  # a rota antiga devolvia HTML
    assert coleta.buscar_avaliacoes(1)["aprovacao_pct"] is None
    _trocar_get({"query_summary": {}})
    assert coleta.buscar_avaliacoes(1)["aprovacao_pct"] is None


def test_onda_de_avaliacoes_exige_as_duas_leituras():
    jogo = {"appid": 1, "nome": "Jogo", "preco": "R$ 10,00", "total_reviews": 76471, "url": ""}
    # A leitura anterior tinha falhado e gravado zero: nao e uma onda.
    assert noticias._eventos_de_avaliacoes(jogo, {"total_reviews": 0}) == []
    assert noticias._eventos_de_avaliacoes(jogo, {"total_reviews": None}) == []
    # A leitura de agora falhou: tambem nao.
    assert noticias._eventos_de_avaliacoes({**jogo, "total_reviews": 0},
                                           {"total_reviews": 76000}) == []
    assert noticias._eventos_de_avaliacoes(jogo, None) == []


def test_onda_de_avaliacoes_continua_detectando():
    jogo = {"appid": 1, "nome": "Jogo", "preco": "R$ 10,00", "total_reviews": 1100, "url": ""}
    eventos = noticias._eventos_de_avaliacoes(jogo, {"total_reviews": 1000})
    assert len(eventos) == 1
    assert eventos[0]["dados"]["novas"] == 100
    # Abaixo do limiar nao e noticia.
    assert noticias._eventos_de_avaliacoes(jogo, {"total_reviews": 1090}) == []


def _email(perfil):
    selecao = {"urgentes": [], "itens": []}
    mensagem = {"abertura": "Uma novidade nos seus jogos."}
    edicao = {"publicada_em": "2026-11-13T09:00:00", "audio": ""}
    return (personalizacao.montar_email(perfil, selecao, mensagem, edicao),
            personalizacao.montar_texto(perfil, selecao, mensagem))


def test_email_funciona_sem_nome():
    pagina, texto = _email({"id": "a", "consentimento": "2026-10-01"})
    assert "Olá<" in pagina and "Olá," not in pagina
    assert texto.splitlines()[0] == "Olá"


def test_email_com_nome():
    pagina, texto = _email({"id": "a", "nome": "Ana", "consentimento": "2026-10-01"})
    assert "Olá, Ana" in pagina
    assert texto.splitlines()[0] == "Olá, Ana"


def test_email_avisa_do_uso_de_ia_e_de_como_sair():
    pagina, texto = _email({"id": "a", "nome": "Ana", "consentimento": "2026-10-01"})
    for corpo in (pagina, texto):
        assert "escritos por IA" in corpo
        assert "voz sintética" in corpo
        assert "responda SAIR para cancelar" in corpo
    assert "inscrito em 01/10/2026" in pagina


def test_retorno_desconta_a_leitura_do_boletim():
    # O ganho contava os 15 minutos inteiros, como se ler o boletim fosse de graça.
    import painel_metricas
    premissas = json.loads((Path(__file__).resolve().parent.parent / "evidencias" / "premissas_roi.json")
                           .read_text(encoding="utf-8"))
    premissas.update(minutos_manuais_por_dia=15, minutos_manuais_pessimista=5, minutos_leitura_boletim=1)
    resumo = {"fluxo": {"p50_s": 40}, "gpu_w_medio": 30}
    roi = painel_metricas.retorno(resumo, premissas)
    assert roi["base"]["minutos_por_dia"] == 14
    assert roi["pessimista"]["minutos_por_dia"] == 4
    assert abs(roi["base"]["ganho_h"] - 14 * 365 / 60) < 1e-9
    assert roi["pessimista"]["payback_dias"] > 365


if __name__ == "__main__":
    testes = [f for nome, f in sorted(globals().items()) if nome.startswith("test_")]
    for teste in testes:
        teste()
        print(f"ok  {teste.__name__}")
    print(f"{len(testes)} testes passaram")
