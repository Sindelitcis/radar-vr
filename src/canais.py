"""Envio por e-mail, Telegram e WhatsApp.

Cada funcao devolve um dicionario de resultado e nunca deixa excecao escapar:
quem decide o que fazer com uma falha e o orquestrador (o n8n), que tem a
visao do fluxo inteiro.

Falhas transitorias - timeout, 429, 5xx - sao repetidas com espera
exponencial. Falhas definitivas - credencial invalida, destinatario
recusado - retornam na hora, porque repetir nao muda o resultado.
"""
import logging
import mimetypes
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import make_msgid

import requests
import urllib3.util.connection

import config

log = logging.getLogger("canais")

if config.FORCAR_IPV4:
    urllib3.util.connection.HAS_IPV6 = False

# Sessao persistente: reaproveita a conexao TLS entre envios da mesma edicao.
_http = requests.Session()


class FalhaDefinitiva(Exception):
    pass


def _com_tentativas(funcao, descricao):
    """Devolve (resultado, tentativas). Na falha, a excecao leva `tentativas`."""
    for tentativa in range(1, config.TENTATIVAS_ENVIO + 1):
        try:
            return funcao(), tentativa
        except Exception as erro:
            erro.tentativas = tentativa
            if isinstance(erro, FalhaDefinitiva) or tentativa == config.TENTATIVAS_ENVIO:
                raise
            espera = config.ESPERA_BASE_S * 2 ** (tentativa - 1)
            log.warning("%s falhou (%s); nova tentativa em %.1f s",
                        descricao, erro, espera)
            time.sleep(espera)


def _falha(canal, inicio, erro):
    return _resultado(canal, inicio, "falhou", getattr(erro, "tentativas", 1),
                      _sem_token(str(erro)))


def _resultado(canal, inicio, status, tentativas=0, erro="", id_externo=""):
    return {
        "canal": canal,
        "status": status,
        "tentativas": tentativas,
        "latencia_ms": round((time.perf_counter() - inicio) * 1000),
        "erro": erro,
        "id": id_externo,
    }


def _simular(canal, inicio):
    if canal in config.FALHAR_CANAIS:
        return _resultado(canal, inicio, "falhou", erro="falha simulada (RADAR_FALHAR_CANAIS)")
    if config.DRY_RUN:
        return _resultado(canal, inicio, "simulado")
    return None


def _verificar_http(resposta):
    if resposta.status_code == 429 or resposta.status_code >= 500:
        raise RuntimeError(f"HTTP {resposta.status_code}")
    if resposta.status_code >= 400:
        raise FalhaDefinitiva(f"HTTP {resposta.status_code}: {resposta.text[:200]}")
    return resposta.json()


# ------------------------------------------------------------------ e-mail

def enviar_email(para, assunto, html, texto="", anexo=None):
    inicio = time.perf_counter()
    if simulado := _simular("email", inicio):
        return simulado
    if not (config.GMAIL_USER and config.GMAIL_APP_PASSWORD):
        return _resultado("email", inicio, "falhou", erro="credenciais SMTP ausentes")

    mensagem = EmailMessage()
    mensagem["From"] = f"Radar VR <{config.GMAIL_USER}>"
    mensagem["To"] = para
    mensagem["Subject"] = assunto
    mensagem["Message-ID"] = make_msgid(domain=config.GMAIL_USER.split("@")[-1])
    # Botao "cancelar inscricao" do Gmail e do Outlook; a resposta cai na caixa
    # do operador, que remove o perfil.
    mensagem["List-Unsubscribe"] = f"<mailto:{config.GMAIL_USER}?subject=SAIR>"
    mensagem.set_content(texto or "Abra este e-mail em um leitor com suporte a HTML.")
    mensagem.add_alternative(html, subtype="html")

    if anexo and anexo.exists():
        tipo, _ = mimetypes.guess_type(anexo.name)
        principal, secundario = (tipo or "application/octet-stream").split("/")
        mensagem.add_attachment(anexo.read_bytes(), maintype=principal,
                                subtype=secundario, filename=anexo.name)

    def _enviar():
        contexto = ssl.create_default_context()
        try:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORTA,
                                  context=contexto, timeout=config.TIMEOUT) as smtp:
                smtp.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
                smtp.send_message(mensagem)
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as erro:
            raise FalhaDefinitiva(str(erro)) from erro

    try:
        _, tentativas = _com_tentativas(_enviar, "SMTP")
        return _resultado("email", inicio, "enviado", tentativas,
                          id_externo=mensagem["Message-ID"])
    except Exception as erro:
        return _falha("email", inicio, erro)


# ---------------------------------------------------------------- Telegram

def enviar_telegram(chat_id, texto):
    inicio = time.perf_counter()
    if simulado := _simular("telegram", inicio):
        return simulado
    if not config.TELEGRAM_TOKEN:
        return _resultado("telegram", inicio, "falhou", erro="TELEGRAM_TOKEN ausente")

    def _enviar():
        resposta = _http.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=config.TIMEOUT,
        )
        return _verificar_http(resposta)

    try:
        dados, tentativas = _com_tentativas(_enviar, "Telegram")
        return _resultado("telegram", inicio, "enviado", tentativas,
                          id_externo=str(dados["result"]["message_id"]))
    except Exception as erro:
        return _falha("telegram", inicio, erro)


def _sem_token(texto):
    return texto.replace(config.TELEGRAM_TOKEN, "***") if config.TELEGRAM_TOKEN else texto


# ---------------------------------------------------------------- WhatsApp

def enviar_whatsapp(numero, texto):
    """WhatsApp Cloud API (Meta).

    A API aceita a mensagem de forma sincrona e informa a entrega depois, por
    webhook. Um "enviado" aqui significa aceito pela Meta; recusas como a
    restricao de envio entre paises (130497) chegam apenas no webhook.
    """
    inicio = time.perf_counter()
    if simulado := _simular("whatsapp", inicio):
        return simulado
    if not (config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_ID):
        return _resultado("whatsapp", inicio, "falhou", erro="credenciais WhatsApp ausentes")

    def _enviar():
        resposta = _http.post(
            f"{config.WHATSAPP_API}/{config.WHATSAPP_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"},
            json={"messaging_product": "whatsapp", "to": numero, "type": "text",
                  "text": {"body": texto, "preview_url": False}},
            timeout=config.TIMEOUT,
        )
        return _verificar_http(resposta)

    try:
        dados, tentativas = _com_tentativas(_enviar, "WhatsApp")
        return _resultado("whatsapp", inicio, "enviado", tentativas,
                          id_externo=dados["messages"][0]["id"])
    except Exception as erro:
        return _falha("whatsapp", inicio, erro)


INSTANTANEOS = {"telegram": enviar_telegram, "whatsapp": enviar_whatsapp}


def verificar():
    """Estado de configuracao de cada canal, sem enviar nada."""
    return {
        "email": bool(config.GMAIL_USER and config.GMAIL_APP_PASSWORD),
        "telegram": bool(config.TELEGRAM_TOKEN),
        "whatsapp": bool(config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_ID),
    }
