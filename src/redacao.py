"""Redacao das chamadas do boletim com LLM local (Ollama).

O modelo escreve apenas onde ha texto livre a resumir: o corpo de um anuncio
do desenvolvedor. Eventos numericos - preco, desconto, variacao - ja chegam
como frase completa de `noticias.py` e nao passam pelo modelo.

A separacao e necessaria por precisao. Mesmo instruido a preservar o tempo
verbal, o modelo reescreve "esta em promocao" como "entrou em promocao",
afirmando uma mudanca que nao foi observada. Numero e verbo de mudanca sao
apuracao, nao redacao.
"""
import json
import logging
import re
import time

import requests

import config

log = logging.getLogger("redacao")

TIPOS_REDIGIDOS = {"PATCH_GRANDE"}

SISTEMA = (
    "Voce e redator de um boletim diario de audio sobre jogos de realidade "
    "virtual na Steam, em portugues do Brasil. Escreve para ser OUVIDO: "
    "frases curtas, diretas, sem adjetivo de propaganda. "
    "Todos os numeros ja vem prontos no material recebido; voce nunca inventa, "
    "estima ou altera um numero."
)

GABARITO = """Escreva UMA frase de noticia de radio sobre o fato abaixo.
Responda APENAS com JSON valido:

{{"linha": "a frase, no maximo 28 palavras"}}

Regras:
- Comece pelo nome do jogo.
- Escreva com acentuacao correta do portugues. O texto sera lido em voz alta.
- Nao escreva numero de versao nem data por extenso.
- Nao opine sobre valer a pena. Voce informa, nao recomenda.
- Resuma O QUE MUDOU no jogo, ignorando saudacao, agradecimento e pedido de
  wishlist.

JOGO: {nome}
FATO: {resumo}
{extra}"""


# Disjuntor: se o Ollama recusa conexao, as chamadas seguintes falham na hora
# durante config.PAUSA_DISJUNTOR_S em vez de esperar o timeout de TCP uma a uma.
_fora_do_ar_ate = 0.0


def chamar(prompt, sistema=SISTEMA):
    global _fora_do_ar_ate
    if time.monotonic() < _fora_do_ar_ate:
        raise ConnectionError("Ollama indisponível (disjuntor aberto)")
    try:
        return _chamar(prompt, sistema)
    except requests.ConnectionError:
        _fora_do_ar_ate = time.monotonic() + config.PAUSA_DISJUNTOR_S
        raise


def _chamar(prompt, sistema):
    resposta = requests.post(
        f"{config.OLLAMA_URL}/api/generate",
        json={
            "model": config.OLLAMA_MODELO,
            "prompt": prompt,
            "system": sistema,
            "stream": False,
            "format": "json",
            "options": {"temperature": config.OLLAMA_TEMP},
        },
        timeout=config.OLLAMA_TIMEOUT,
    )
    resposta.raise_for_status()
    return resposta.json().get("response", "")


def extrair_json(texto):
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    achado = re.search(r"\{.*\}", texto, re.DOTALL)
    if achado:
        try:
            return json.loads(achado.group(0))
        except json.JSONDecodeError:
            pass
    return None


def verificar_servico():
    """Lista os modelos disponiveis, ou None se o Ollama nao responder."""
    try:
        resposta = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
        resposta.raise_for_status()
        modelos = [m["name"] for m in resposta.json().get("models", [])]
        log.info("Ollama ativo: %s", ", ".join(modelos) or "nenhum modelo")
        return modelos
    except Exception as erro:
        log.error("Ollama indisponível em %s (%s)", config.OLLAMA_URL, erro)
        return None


def _redigir_um(evento):
    dados = evento.get("dados", {})
    prompt = GABARITO.format(
        nome=evento["nome"],
        resumo=evento["resumo"],
        extra=f"TEXTO DO ANUNCIO: {dados['texto'][:400]}" if dados.get("texto") else "",
    )
    parecer = extrair_json(chamar(prompt)) or {}
    return parecer.get("linha", "").strip()


def redigir(eventos):
    """Preenche `linha` em cada evento do boletim."""
    log.info("=== ETAPA 3/4 | Redação com LLM local (%s) ===", config.OLLAMA_MODELO)

    precisam_llm = [e for e in eventos if e["tipo"] in TIPOS_REDIGIDOS]
    # Sem o modelo a edicao segue: o resumo factual vira a chamada. Perde-se
    # a sintese do anuncio, nao o boletim.
    llm_ativo = bool(precisam_llm) and verificar_servico() is not None
    if precisam_llm and not llm_ativo:
        log.warning("Ollama indisponível: chamadas pela regra. Execute 'ollama serve'.")

    for evento in eventos:
        linha = ""
        if evento["tipo"] in TIPOS_REDIGIDOS and llm_ativo:
            try:
                linha = _redigir_um(evento)
            except Exception as erro:
                log.error("Redação falhou em %s: %s", evento["nome"], erro)
        # A origem fica no evento: a edicao sai mesmo sem o modelo, e so esse
        # campo mostra depois que o resumo do anuncio nao foi feito.
        evento["origem_linha"] = "llm" if linha else "regra"
        evento["linha"] = linha or f"{evento['nome']} {evento['resumo']}"
        log.info("  %-18s [%s] %s", evento["tipo"][:18], evento["origem_linha"],
                 evento["linha"][:52])

    pelo_llm = sum(e["origem_linha"] == "llm" for e in eventos)
    sem_resumo = len(precisam_llm) - pelo_llm
    log.info(
        "Etapa 3 concluída: %d linhas (%d do LLM, %d por regra)",
        len(eventos), pelo_llm, len(eventos) - pelo_llm,
    )
    if sem_resumo:
        log.warning("%d anúncio(s) saíram sem o resumo do modelo", sem_resumo)
    return eventos
