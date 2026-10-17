"""Microsservico HTTP do Radar VR.

Expoe o pipeline e os canais para o n8n, que orquestra a sequencia:

    POST /edicao              gera a edicao do dia (coleta -> eventos -> voz)
    GET  /edicao/atual        ultima edicao publicada, sem gerar outra
    POST /personalizar        um envelope por assinante: e-mail e alerta
    POST /enviar/email        envia o boletim personalizado
    POST /enviar/instantaneo  envia o alerta por Telegram ou WhatsApp
    POST /falha               registra falha reportada pelo n8n e avisa o operador
    GET  /saude               dependencias e configuracao
    GET  /                    lista das rotas

Envio que falha responde 502 com o resultado no corpo: o n8n trata o status
como erro e desvia o item para o ramo de contingencia.

Uso:
    python src/servico.py
"""
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

import auditoria
import canais
import config
import jornal
import personalizacao

log = logging.getLogger("servico")

_edicao_em_curso = threading.Lock()


class ErroCliente(Exception):
    def __init__(self, status, mensagem):
        super().__init__(mensagem)
        self.status = status


def _ler_edicao():
    if not config.ARQ_EDICAO.exists():
        raise ErroCliente(404, "nenhuma edição publicada; chame POST /edicao")
    return json.loads(config.ARQ_EDICAO.read_text(encoding="utf-8"))


def _exigir(corpo, *campos):
    faltam = [c for c in campos if not corpo.get(c)]
    if faltam:
        raise ErroCliente(400, f"campos obrigatórios ausentes: {', '.join(faltam)}")


# ---------------------------------------------------------------- rotas

def indice(_):
    return 200, {"servico": "Radar VR", "dry_run": config.DRY_RUN,
                 "rotas": [f"{metodo} {caminho}" for metodo, caminho in ROTAS]}


def saude(_):
    try:
        requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=3).raise_for_status()
        ollama = True
    except Exception:
        ollama = False
    return 200, {
        "status": "ok",
        "dry_run": config.DRY_RUN,
        "ollama": ollama,
        "itad": bool(config.ITAD_API_KEY),
        "canais": canais.verificar(),
        "perfis": config.ARQ_PERFIS.exists(),
        "edicao_atual": config.ARQ_EDICAO.exists(),
    }


def gerar_edicao(corpo):
    if corpo.get("reaproveitar"):
        return 200, _ler_edicao()
    if not _edicao_em_curso.acquire(blocking=False):
        raise ErroCliente(409, "já existe uma edição em geração")
    try:
        extras = personalizacao.jogos_seguidos(personalizacao.carregar_perfis())
        edicao = jornal.publicar(corpo.get("titulos"), corpo.get("audio", True), extras)
    finally:
        _edicao_em_curso.release()
    auditoria.registrar("edicao", edicao_id=edicao["id"],
                        manchetes=len(edicao["manchetes"]), tempos=edicao["tempos"])
    resumo = {k: v for k, v in edicao.items() if k not in ("eventos", "catalogo")}
    return 200, resumo


def edicao_atual(_):
    return 200, _ler_edicao()


def personalizar(corpo):
    edicao = _ler_edicao()
    perfis = personalizacao.carregar_perfis()
    if corpo.get("perfis"):
        perfis = [p for p in perfis if p["id"] in corpo["perfis"]]
    if corpo.get("perfis_extras"):
        perfis += corpo["perfis_extras"]  # usado pelos testes de carga

    inicio = time.perf_counter()
    envelopes = personalizacao.personalizar(edicao, perfis)
    for envelope in envelopes:
        auditoria.registrar(
            "decisao", edicao_id=envelope["edicao_id"], perfil=envelope["perfil_id"],
            itens=envelope["itens"], urgentes=envelope["urgentes"],
            email=bool(envelope["email"]),
            instantaneo=(envelope["instantaneo"] or {}).get("canal"),
            motivo=envelope["motivo"],
            latencia_ms=envelope["latencia_ms"],
        )
    log.info("Personalização: %d perfis em %.2f s", len(perfis),
             time.perf_counter() - inicio)
    if corpo.get("todos"):
        return 200, envelopes
    return 200, [e for e in envelopes if e["email"]]


def _anexo(nome):
    if not nome:
        return None
    caminho = (config.DIR_AUDIO / Path(nome).name).resolve()
    if caminho.parent != config.DIR_AUDIO.resolve():
        raise ErroCliente(400, "anexo fora da pasta de áudio")
    return caminho


def _enviar(corpo, canal, funcao, **detalhes):
    edicao_id, perfil_id = corpo["edicao_id"], corpo["perfil_id"]
    destino = corpo.get("para") or corpo.get("destino")
    if not auditoria.reservar_envio(edicao_id, perfil_id, canal):
        auditoria.registrar("envio", edicao_id=edicao_id, perfil=perfil_id, canal=canal,
                            status="duplicado", destino=auditoria.mascarar(destino))
        return 200, {"canal": canal, "status": "duplicado"}

    resultado = funcao()
    auditoria.concluir_envio(edicao_id, perfil_id, canal, resultado["status"])
    auditoria.registrar("envio", edicao_id=edicao_id, perfil=perfil_id,
                        destino=auditoria.mascarar(destino), **detalhes, **resultado)
    nivel = logging.WARNING if resultado["status"] == "falhou" else logging.INFO
    log.log(nivel, "%-9s %-8s %-9s %5d ms %s", canal, perfil_id, resultado["status"],
            resultado["latencia_ms"], resultado["erro"])
    return (502 if resultado["status"] == "falhou" else 200), resultado


def enviar_email(corpo):
    _exigir(corpo, "edicao_id", "perfil_id", "para", "assunto", "html")
    anexo = _anexo(corpo.get("anexo"))
    canal = "email_contingencia" if corpo.get("contingencia") else "email"
    return _enviar(corpo, canal, lambda: canais.enviar_email(
        corpo["para"], corpo["assunto"], corpo["html"], corpo.get("texto", ""), anexo))


def enviar_instantaneo(corpo):
    _exigir(corpo, "edicao_id", "perfil_id", "canal", "destino", "texto")
    funcao = canais.INSTANTANEOS.get(corpo["canal"])
    if not funcao:
        raise ErroCliente(400, f"canal desconhecido: {corpo['canal']}")
    texto = corpo["texto"]
    # O n8n informa como foi o e-mail. Se ele falhou, o alerta leva tambem as
    # demais novidades do dia, que so estariam no e-mail.
    if corpo.get("email_status") == "falhou" and corpo.get("complemento"):
        texto += "\n\n" + corpo["complemento"]
    return _enviar(corpo, corpo["canal"], lambda: funcao(corpo["destino"], texto),
                   email_status=corpo.get("email_status"),
                   com_complemento=texto != corpo["texto"])


def registrar_falha(corpo):
    auditoria.registrar("falha_fluxo", **{k: str(v)[:500] for k, v in corpo.items()})
    log.error("Falha no fluxo n8n: %s em %s", corpo.get("mensagem"), corpo.get("no"))
    aviso = canais.enviar_email(
        config.GMAIL_USER,
        f"[Radar VR] Falha no fluxo: {str(corpo.get('no', '?'))[:60]}",
        "<p>O n8n reportou uma falha.</p><pre>"
        + json.dumps(corpo, ensure_ascii=False, indent=2)[:4000] + "</pre>",
    ) if config.GMAIL_USER else {"status": "sem destinatário"}
    return 200, {"registrado": True, "aviso_operador": aviso["status"]}


ROTAS = {
    ("GET", "/"): indice,
    ("GET", "/saude"): saude,
    ("GET", "/edicao/atual"): edicao_atual,
    ("POST", "/edicao"): gerar_edicao,
    ("POST", "/personalizar"): personalizar,
    ("POST", "/enviar/email"): enviar_email,
    ("POST", "/enviar/instantaneo"): enviar_instantaneo,
    ("POST", "/falha"): registrar_falha,
}


# ------------------------------------------------------------- servidor

class Manipulador(BaseHTTPRequestHandler):
    server_version = "RadarVR/2.0"

    def _responder(self, status, corpo):
        dados = json.dumps(corpo, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _tratar(self, metodo):
        inicio = time.perf_counter()
        rota = ROTAS.get((metodo, self.path.split("?")[0]))
        try:
            if not rota:
                raise ErroCliente(404, f"rota inexistente: {metodo} {self.path}")
            corpo = {}
            if metodo == "POST":
                tamanho = int(self.headers.get("Content-Length") or 0)
                bruto = self.rfile.read(tamanho) if tamanho else b"{}"
                try:
                    corpo = json.loads(bruto or b"{}")
                except json.JSONDecodeError:
                    raise ErroCliente(400, "corpo não é JSON válido")
            status, resposta = rota(corpo)
        except ErroCliente as erro:
            status, resposta = erro.status, {"erro": str(erro)}
        except Exception as erro:
            log.exception("Erro interno em %s %s", metodo, self.path)
            status, resposta = 500, {"erro": f"{type(erro).__name__}: {erro}"}
        self._responder(status, resposta)
        log.info("%s %-20s %d %6.0f ms", metodo, self.path, status,
                 (time.perf_counter() - inicio) * 1000)

    def do_GET(self):
        self._tratar("GET")

    def do_POST(self):
        self._tratar("POST")

    def log_message(self, *_):
        pass  # o registro de acesso e feito em _tratar, no formato do projeto


def main():
    jornal.configurar_log()
    servidor = ThreadingHTTPServer((config.SERVICO_HOST, config.SERVICO_PORTA), Manipulador)
    log.info("Radar VR em http://%s:%d", config.SERVICO_HOST, config.SERVICO_PORTA)
    if config.DRY_RUN:
        log.info("MODO ENSAIO (DRY_RUN): o fluxo roda inteiro, nenhuma mensagem sai da máquina")
    else:
        log.info("MODO REAL: e-mail e alertas são entregues aos assinantes")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        log.info("Encerrado")


if __name__ == "__main__":
    main()
