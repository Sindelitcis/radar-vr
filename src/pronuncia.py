"""Conversao de texto escrito para texto falado.

O sintetizador le exatamente o que esta escrito, o que exige normalizar antes
da sintese: numero vira palavra, data vira expressao relativa, versao sai do
texto e sigla e soletrada.

Todas as regras operam sobre a FORMA do texto - se e numero, data, versao ou
sigla - e nao sobre uma lista de conteudos conhecidos. Valem para qualquer
entrada, sem manutencao.

Limitacao assumida: nomes proprios em ingles sao lidos com fonema portugues e
soam aproximados. Corrigir exigiria detectar o idioma de cada nome e alternar
o phonemizer no meio da frase. A pagina HTML cobre esse caso, exibindo o nome
escrito e o link da loja.
"""
import re

UNIDADES = [
    "zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito",
    "nove", "dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis",
    "dezessete", "dezoito", "dezenove",
]
DEZENAS = [
    "", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta",
    "oitenta", "noventa",
]
CENTENAS = [
    "", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
    "seiscentos", "setecentos", "oitocentos", "novecentos",
]
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
]

# Siglas de duas a tres letras sao soletradas. O limite de tres preserva
# titulos em caixa alta como DOOM ou RAGE, lidos como palavra.
ALFABETO = {
    "A": "á", "B": "bê", "C": "cê", "D": "dê", "E": "é", "F": "éfe", "G": "gê",
    "H": "agá", "I": "i", "J": "jóta", "K": "cá", "L": "éle", "M": "ême",
    "N": "êne", "O": "ó", "P": "pê", "Q": "quê", "R": "érre", "S": "ésse",
    "T": "tê", "U": "u", "V": "vê", "W": "dáblio", "X": "xis", "Y": "ípsilon",
    "Z": "zê",
}
# O lookahead aceita digito logo apos a sigla, cobrindo sequencias como "VR2".
RE_SIGLA = re.compile(r"(?<![\wÀ-ÿ])([A-Z]{2,3})(?=\d|(?![\wÀ-ÿ]))")
RE_VERSAO = re.compile(
    r"\s*\b(?:v(?:ers[ãa]o)?\.?\s*)?\d+\.\d+(?:\.\d+)*\b", re.IGNORECASE
)
RE_DATA = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")

# Remover versao ou data pode deixar artigo e preposicao orfaos antes da
# pontuacao, como em "anunciou a, com melhorias".
RE_CONECTOR_ORFAO = re.compile(
    r"\s+\b(?:[ao]s?|d[ao]s?|para|de|em|com|n[ao]s?)\b\s*(?=[,.;:])", re.IGNORECASE
)


def numero_por_extenso(n):
    n = int(n)
    if n < 0:
        return "menos " + numero_por_extenso(-n)
    if n < 20:
        return UNIDADES[n]
    if n < 100:
        dezena, unidade = divmod(n, 10)
        return DEZENAS[dezena] + (f" e {UNIDADES[unidade]}" if unidade else "")
    if n == 100:
        return "cem"
    if n < 1000:
        centena, resto = divmod(n, 100)
        return CENTENAS[centena] + (f" e {numero_por_extenso(resto)}" if resto else "")
    if n < 1_000_000:
        milhar, resto = divmod(n, 1000)
        prefixo = "mil" if milhar == 1 else f"{numero_por_extenso(milhar)} mil"
        if not resto:
            return prefixo
        return prefixo + (" e " if resto < 100 else " ") + numero_por_extenso(resto)
    return str(n)


def preco_falado(valor):
    if valor is None:
        return "preço indisponível"
    reais = int(valor)
    centavos = int(round((valor - reais) * 100))
    texto = f"{numero_por_extenso(reais)} {'real' if reais == 1 else 'reais'}"
    return texto + (f" e {numero_por_extenso(centavos)}" if centavos else "")


def percentual_falado(valor):
    return f"{numero_por_extenso(int(round(valor)))} por cento"


def data_relativa(dias):
    if dias <= 0:
        return "hoje"
    if dias == 1:
        return "ontem"
    if dias == 2:
        return "anteontem"
    if dias <= 7:
        return f"há {numero_por_extenso(dias)} dias"
    if dias <= 14:
        return "na semana passada"
    # "semana" e feminino: duas semanas, nunca dois semanas
    extenso = numero_por_extenso(dias // 7)
    extenso = {"um": "uma", "dois": "duas"}.get(extenso, extenso)
    return f"há {extenso} semanas"


def data_por_extenso(quando):
    """Data com barra soa como fracao; "17 de setembro" evita o problema."""
    return f"{quando.day} de {MESES[quando.month - 1]}"


def soletrar_siglas(texto):
    def _soletra(achado):
        # o espaco final separa a sigla de um digito colado, como em "VR2"
        return " ".join(ALFABETO.get(c, c) for c in achado.group(1)) + " "
    return RE_SIGLA.sub(_soletra, texto)


def preparar_para_fala(texto):
    texto = RE_VERSAO.sub("", texto)
    texto = RE_DATA.sub("", texto)

    def _preco(achado):
        valor = float(achado.group(1).replace(".", "").replace(",", "."))
        return preco_falado(valor)

    texto = re.sub(r"R\$\s*([\d.]+,\d{2}|\d+)", _preco, texto)
    texto = re.sub(r"(\d+)\s*%", lambda m: percentual_falado(int(m.group(1))), texto)
    texto = soletrar_siglas(texto)

    # O lookahead bloqueia apenas decimais; numero em fim de frase deve passar.
    texto = re.sub(
        r"(?<![\w,.])(\d{1,4})(?![\w%]|[.,]\d)",
        lambda m: numero_por_extenso(int(m.group(1))),
        texto,
    )

    texto = texto.replace("&", " e ").replace("_", " ")
    # Aplicado ate estabilizar: remover um conector pode expor o anterior,
    # como em "para a," -> "para," -> ",".
    while True:
        reduzido = RE_CONECTOR_ORFAO.sub("", texto)
        if reduzido == texto:
            break
        texto = reduzido
    texto = re.sub(r"\s+([:.,;])", r"\1", texto)
    texto = re.sub(r"([:,;])\s*(?=[.,;:])", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()

    # Capitalizacao no fim da cadeia: numeros so viram palavra nesta funcao.
    return re.sub(
        r"(^|[.!?]\s+)([a-záàãâéêíóôõúüç])",
        lambda m: m.group(1) + m.group(2).upper(),
        texto,
    )
