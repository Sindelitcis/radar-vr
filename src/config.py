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
ARQ_EDICAO = DIR_DADOS / "edicao_atual.json"
ARQ_AUDITORIA = DIR_LOGS / "auditoria.jsonl"


def _carregar_env(caminho):
    """Le um arquivo .env simples. Variaveis ja definidas no ambiente vencem."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"'))


_carregar_env(RAIZ / ".env")

if os.environ.get("RADAR_DB"):  # os testes de carga usam um banco separado
    ARQ_DB = DIR_DADOS / os.environ["RADAR_DB"]


def _env(chave, padrao=""):
    return os.environ.get(chave, padrao)


def _env_bool(chave, padrao=False):
    return _env(chave, str(padrao)).lower() in ("1", "true", "sim", "yes")


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
PRAZO_URGENTE_DIAS = 2         # promocao acabando vira alerta instantaneo
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
# IP literal: o Node do n8n resolve localhost como ::1
OLLAMA_URL = _env("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODELO = "llama3.1:8b"
OLLAMA_TEMP = 0.2  # classificacao exige consistencia entre execucoes
OLLAMA_TIMEOUT = 180
# Depois de uma recusa de conexao, o Ollama nao e chamado por este tempo.
PAUSA_DISJUNTOR_S = int(_env("RADAR_DISJUNTOR_S", "60"))

# ------------------------------------------------------------ sintese TTS
KOKORO_MODELO = DIR_MODELOS / "kokoro-v1.0.onnx"
KOKORO_VOZES = DIR_MODELOS / "voices-v1.0.bin"
KOKORO_VOZ = "pf_dora"
KOKORO_IDIOMA = "pt-br"
KOKORO_VELOCIDADE = 1.0
KOKORO_VOZ_FALLBACK = "af_heart"
KOKORO_IDIOMA_FALLBACK = "en-us"

# ---------------------------------------------------- historico de precos
ITAD_URL = "https://api.isthereanydeal.com"
ITAD_API_KEY = _env("ITAD_API_KEY")
ITAD_LOJA_STEAM = 61
ITAD_CACHE_HORAS = 6
# Preco atual ate 5% acima do menor historico ainda conta como "no minimo":
# a loja arredonda centavos e o cambio oscila entre leituras.
ITAD_MARGEM_MINIMO = 1.05

# ------------------------------------------------------------ microsservico
SERVICO_HOST = _env("RADAR_HOST", "127.0.0.1")
SERVICO_PORTA = int(_env("RADAR_PORTA", "8765"))
ARQ_PERFIS = RAIZ / _env("RADAR_PERFIS", "perfis.json")

# Com DRY_RUN ligado nenhuma mensagem sai da maquina; o envio e registrado
# como simulado. Os testes de carga dependem disso.
DRY_RUN = _env_bool("RADAR_DRY_RUN")

# Com o historico fixo a edicao compara sempre com a mesma leitura e nao grava
# outra: as mesmas novidades se repetem a cada execucao, o que serve para
# ensaiar com envio real. O ensaio (DRY_RUN) ja implica historico fixo.
HISTORICO_FIXO = DRY_RUN or _env_bool("RADAR_HISTORICO_FIXO")

# Canais que devem falhar de proposito, para exercitar os desvios de erro em teste.
# Exemplo: RADAR_FALHAR_CANAIS=telegram
FALHAR_CANAIS = {c.strip() for c in _env("RADAR_FALHAR_CANAIS").split(",") if c.strip()}

COLETA_PARALELA = int(_env("RADAR_COLETA_PARALELA", "4"))

# --------------------------------------------------------------- canais
GMAIL_USER = _env("GMAIL_USER")
GMAIL_APP_PASSWORD = _env("GMAIL_APP_PASSWORD")
SMTP_HOST = _env("SMTP_HOST", "smtp.gmail.com")
SMTP_PORTA = int(_env("SMTP_PORTA", "465"))

TELEGRAM_TOKEN = _env("TELEGRAM_TOKEN")
# Chat do operador: recebe o aviso de falha quando o e-mail nao sai.
OPERADOR_TELEGRAM = _env("RADAR_OPERADOR_TELEGRAM")

WHATSAPP_TOKEN = _env("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = _env("WHATSAPP_PHONE_ID")
WHATSAPP_API = "https://graph.facebook.com/v25.0"

# A rota IPv6 ate api.telegram.org nao responde nesta rede: cada conexao nova
# espera 21 s pelo timeout antes de cair para IPv4. Ver docs/07_testes.md.
FORCAR_IPV4 = _env_bool("RADAR_FORCAR_IPV4", True)

TENTATIVAS_ENVIO = 3
ESPERA_BASE_S = 1.5  # backoff exponencial: 1,5 s e depois 3 s
