"""Testes da redacao: a origem de cada frase precisa refletir o que aconteceu.

Confere que cada frase registra se veio do modelo ou da regra, inclusive
quando a chamada ao Ollama falha.

    python testes/test_redacao.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import redacao  # noqa: E402


def _eventos():
    return [
        {"tipo": "PATCH_GRANDE", "nome": "Jogo A", "resumo": "recebeu um anúncio",
         "dados": {"texto": "Novo mapa e correções."}},
        {"tipo": "PATCH_GRANDE", "nome": "Jogo B", "resumo": "recebeu um anúncio",
         "dados": {}},
        {"tipo": "PROMOCAO_NOVA", "nome": "Jogo C", "resumo": "entrou em promoção",
         "dados": {}},
    ]


def _com(modelos, resposta):
    """Troca o acesso ao Ollama por respostas fixas."""
    redacao.verificar_servico = lambda: modelos
    if isinstance(resposta, Exception):
        def chamar(*_):
            raise resposta
    else:
        def chamar(*_):
            return resposta
    redacao.chamar = chamar


def test_modelo_responde():
    _com(["llama3.1:8b"], '{"linha": "Jogo A ganhou um mapa novo."}')
    eventos = redacao.redigir(_eventos())
    assert [e["origem_linha"] for e in eventos] == ["llm", "llm", "regra"]
    assert eventos[0]["linha"] == "Jogo A ganhou um mapa novo."


def test_chamada_falha_vira_regra():
    # Ollama no ar, mas o modelo configurado nao esta instalado (HTTP 404).
    _com(["outro-modelo"], RuntimeError("404 Not Found"))
    eventos = redacao.redigir(_eventos())
    assert [e["origem_linha"] for e in eventos] == ["regra", "regra", "regra"]
    assert eventos[0]["linha"] == "Jogo A recebeu um anúncio"


def test_resposta_vazia_vira_regra():
    _com(["llama3.1:8b"], '{"linha": ""}')
    eventos = redacao.redigir(_eventos())
    assert [e["origem_linha"] for e in eventos] == ["regra", "regra", "regra"]


def test_ollama_fora_do_ar():
    _com(None, ConnectionError("recusada"))
    eventos = redacao.redigir(_eventos())
    assert all(e["origem_linha"] == "regra" for e in eventos)
    assert all(e["linha"] for e in eventos)


if __name__ == "__main__":
    testes = [f for nome, f in sorted(globals().items()) if nome.startswith("test_")]
    for teste in testes:
        teste()
        print(f"ok  {teste.__name__}")
    print(f"{len(testes)} testes passaram")
