"""Parametros do Radar VR."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_DADOS = RAIZ / "data"
DIR_AUDIO = RAIZ / "audio"
DIR_LOGS = RAIZ / "logs"
DIR_MODELOS = RAIZ / "modelos"

for _pasta in (DIR_DADOS, DIR_AUDIO, DIR_LOGS):
    _pasta.mkdir(exist_ok=True)

ARQ_CSV = DIR_DADOS / "jornal_vr.csv"
ARQ_DB = DIR_DADOS / "jornal_vr.db"
ARQ_LOG = DIR_LOGS / "jornal.log"
ARQ_HTML = DIR_DADOS / "boletim_atual.html"

# O phonemizer PT-BR do Kokoro localiza a biblioteca do espeak-ng por variavel
# de ambiente. Definir aqui dispensa configurar o terminal antes de executar.
_ESPEAK = Path(r"C:\Program Files\eSpeak NG\libespeak-ng.dll")
if _ESPEAK.exists():
    os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", str(_ESPEAK))
    os.environ.setdefault("ESPEAK_DATA_PATH", str(_ESPEAK.parent / "espeak-ng-data"))

# ----------------------------------------------------------- Steam Web API
STEAM_BUSCA = "https://store.steampowered.com/search/results/"
STEAM_DETALHES = "https://store.steampowered.com/api/appdetails"
STEAM_JOGADORES = (
    "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
)
STEAM_AVALIACOES = "https://store.steampowered.com/appreviews/"
STEAM_NOTICIAS = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"

FILTRO_VR = {"category1": 998, "vrsupport": 401}  # 998 = jogos, 401 = suporte VR
ORDENACAO = "Reviews_DESC"
PAIS = "br"
IDIOMA = "portuguese"
TIMEOUT = 20
PAUSA_REQ = 1.2  # intervalo entre requisicoes, para respeitar o rate limit

# -------------------------------------------------------------- watchlist
TAM_WATCHLIST = 15
NOTICIAS_POR_JOGO = 3
MANCHETES_NO_BOLETIM = 6

# -------------------------------------------------- limiares de relevancia
NOTICIA_RECENTE_DIAS = 7
AVISO_FIM_PROMOCAO_DIAS = 5
PICO_BASE_MINIMA = 80          # jogadores na leitura anterior
PICO_VARIACAO_MINIMA = 25.0    # % de alta
QUEDA_VARIACAO_MINIMA = 35.0   # % de baixa
ONDA_REVIEWS_MINIMA = 40       # avaliacoes novas entre edicoes

# Edicoes necessarias antes de afirmar minima historica. Com duas leituras o
# preco atual e o minimo por definicao, o que tornaria a afirmacao vazia.
EDICOES_PARA_MINIMA_HISTORICA = 5

# Retencao da memoria de anuncios publicados. Derivada da janela de deteccao:
# um anuncio mais antigo que NOTICIA_RECENTE_DIAS ja e descartado por idade,
# entao guardar seu identificador alem disso nao altera resultado. O dobro
# cobre periodos sem execucao. A tabela fica limitada a
# (titulos observados x anuncios na janela), sem crescer com o tempo.
RETENCAO_NOTICIAS_DIAS = NOTICIA_RECENTE_DIAS * 2

# ------------------------------------------------------------- LLM local
OLLAMA_URL = "http://127.0.0.1:11434"  # IP literal: Node resolve localhost como ::1
OLLAMA_MODELO = "llama3.1:8b"
OLLAMA_TEMP = 0.2  # classificacao exige consistencia entre execucoes
OLLAMA_TIMEOUT = 180

# ------------------------------------------------------------ sintese TTS
KOKORO_MODELO = DIR_MODELOS / "kokoro-v1.0.onnx"
KOKORO_VOZES = DIR_MODELOS / "voices-v1.0.bin"
KOKORO_VOZ = "pf_dora"
KOKORO_IDIOMA = "pt-br"
KOKORO_VELOCIDADE = 1.0
KOKORO_VOZ_FALLBACK = "af_heart"
KOKORO_IDIOMA_FALLBACK = "en-us"
