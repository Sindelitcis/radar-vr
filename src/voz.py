"""Montagem do roteiro e sintese de voz com Kokoro.

A estrutura do boletim e fixa - manchete, destaques, promocoes, radar - porque
audio nao se rele: a posicao informa ao ouvinte que tipo de conteudo vem a
seguir. Apenas a moldura varia entre edicoes; os fatos vem prontos.
"""
import logging
import random
import re
from datetime import datetime

import config
import pronuncia

log = logging.getLogger("voz")

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

SAUDACOES = {
    "madrugada": ["Boa madrugada", "Olá, madrugador", "Boa madrugada pra você"],
    "manha": ["Bom dia", "Bom dia pra você", "Olá, bom dia"],
    "tarde": ["Boa tarde", "Olá, boa tarde", "Boa tarde pra você"],
    "noite": ["Boa noite", "Olá, boa noite", "Boa noite pra você"],
}

APRESENTACOES = [
    "aqui é o Radar VR, o seu resumo do que mudou na realidade virtual",
    "Radar VR no ar, com o que mexeu no catálogo de realidade virtual",
    "este é o Radar VR, acompanhando o catálogo de realidade virtual da Steam",
    "no ar o Radar VR, com as novidades da realidade virtual",
]

DATAS = [
    "Hoje é {dia} de {mes}.",
    "É {dia} de {mes}.",
    "Estamos em {dia} de {mes}.",
    "{dia} de {mes}.",
]

CHAMADAS_MANCHETE = [
    "A manchete:",
    "Começando pela principal:",
    "O destaque da vez:",
    "Abrindo a edição:",
    "Manchete:",
]

TRANSICOES = {
    "destaques": [
        "Vamos aos destaques do dia.",
        "Nos destaques de hoje.",
        "Começando pelos destaques.",
    ],
    "promocoes": [
        "Agora, as promoções.",
        "Passando para as promoções.",
        "E nas promoções.",
    ],
    "radar": ["Ainda no radar.", "Fechando, no radar.", "E no radar."],
}

DESPEDIDAS = [
    "É isso por hoje. Até a próxima edição, e bom jogo!",
    "Por aqui é só. Até amanhã, e aproveite o headset!",
    "Fechamos por hoje. Até a próxima, e bons jogos!",
    "É tudo por enquanto. Te espero na próxima edição. Bom jogo!",
    "Por hoje é só. Até amanhã, e divirta-se aí dentro!",
]

DESPEDIDAS_COM_PROMOCAO = [
    "É isso por hoje. Corre que promoção não espera. Até amanhã!",
    "Por aqui é só. Dá uma olhada nessas ofertas antes que acabem. Até a próxima!",
]

SEM_NOVIDADE = [
    "Catálogo tranquilo hoje, sem movimentação relevante.",
    "Dia parado por aqui: nada de relevante mexeu no catálogo.",
    "Hoje o catálogo ficou quieto, sem novidade que valha o seu tempo.",
]

ORDEM_SECOES = ["destaques", "promocoes", "radar"]


def _periodo(hora):
    if hora < 6:
        return "madrugada"
    if hora < 12:
        return "manha"
    if hora < 19:
        return "tarde"
    return "noite"


def _pontuar(frase):
    """Garante ponto final: sem ele as frases se fundem na narracao."""
    frase = (frase or "").strip()
    if frase and frase[-1] not in ".!?:":
        frase += "."
    return frase


def montar_roteiro(eventos, titulos_observados, primeira_edicao):
    agora = datetime.now()
    data = random.choice(DATAS).format(dia=agora.day, mes=MESES[agora.month - 1])
    partes = [
        f"{random.choice(SAUDACOES[_periodo(agora.hour)])}, "
        f"{random.choice(APRESENTACOES)}. {data}"
    ]

    if not eventos:
        partes.append(random.choice(SEM_NOVIDADE))
        partes.append(
            f"Foram {titulos_observados} títulos conferidos, "
            f"e nenhum deles pediu a sua atenção."
        )
        partes.append(random.choice(DESPEDIDAS))
        return pronuncia.preparar_para_fala(" ".join(partes))

    partes.append(_pontuar(f"{random.choice(CHAMADAS_MANCHETE)} {eventos[0]['linha']}"))

    agrupados = {}
    for evento in eventos[1:]:
        agrupados.setdefault(evento["secao"], []).append(evento)

    for secao in ORDEM_SECOES:
        bloco = agrupados.get(secao)
        if not bloco:
            continue
        partes.append(random.choice(TRANSICOES[secao]))
        partes += [_pontuar(e["linha"]) for e in bloco]

    fecho = (
        "um movimento que valia ser contado"
        if len(eventos) == 1
        else f"{len(eventos)} movimentos que valiam ser contados"
    )
    partes.append(f"No total, {titulos_observados} títulos acompanhados e {fecho}.")

    if primeira_edicao:
        partes.append(
            "Vale dizer que esta é a primeira edição, então ela serve de ponto "
            "de partida. Da próxima vez eu já consigo comparar preços e "
            "jogadores com hoje."
        )

    tem_promocao = any(e["secao"] == "promocoes" for e in eventos)
    partes.append(
        random.choice(DESPEDIDAS_COM_PROMOCAO if tem_promocao else DESPEDIDAS)
    )
    return pronuncia.preparar_para_fala(" ".join(partes))


def _carregar_kokoro():
    from kokoro_onnx import Kokoro

    if not config.KOKORO_MODELO.exists() or not config.KOKORO_VOZES.exists():
        raise FileNotFoundError(
            f"Modelos do Kokoro ausentes em {config.KOKORO_MODELO.parent}. "
            "Execute setup.ps1."
        )
    return Kokoro(str(config.KOKORO_MODELO), str(config.KOKORO_VOZES))


def sintetizar(roteiro, nome_arquivo=None):
    """Gera o arquivo .wav. Devolve (caminho, duracao em segundos, voz)."""
    import soundfile as sf

    log.info("=== Síntese de voz com Kokoro ===")
    log.info("Roteiro: %d caracteres", len(roteiro))

    kokoro = _carregar_kokoro()
    voz, idioma = config.KOKORO_VOZ, config.KOKORO_IDIOMA

    try:
        amostras, taxa = kokoro.create(
            roteiro, voice=voz, speed=config.KOKORO_VELOCIDADE, lang=idioma
        )
    except Exception as erro:
        # A voz PT-BR depende do phonemizer espeak-ng; sem ele, o ingles
        # mantem a etapa funcional.
        log.warning("Voz %s indisponível (%s); usando %s",
                    voz, erro, config.KOKORO_VOZ_FALLBACK)
        voz, idioma = config.KOKORO_VOZ_FALLBACK, config.KOKORO_IDIOMA_FALLBACK
        amostras, taxa = kokoro.create(
            roteiro, voice=voz, speed=config.KOKORO_VELOCIDADE, lang=idioma
        )

    destino = config.DIR_AUDIO / (
        nome_arquivo or f"boletim_{datetime.now():%Y-%m-%d_%H-%M}.wav"
    )
    sf.write(str(destino), amostras, taxa)

    duracao = len(amostras) / taxa
    log.info("Áudio gerado: %s (%.1f s, voz %s)", destino.name, duracao, voz)
    return destino, duracao, voz
