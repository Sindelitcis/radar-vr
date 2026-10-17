"""Trilha de auditoria dos envios.

Cada decisao e cada tentativa de envio vira uma linha JSON em
logs/auditoria.jsonl, legivel por humano e por ferramenta (jq, pandas, n8n).
Contatos aparecem mascarados: o log serve para depurar, nao para guardar
dado pessoal.

A tabela `envios` garante no maximo uma mensagem por assinante, canal e
edicao. Uma nova tentativa do n8n, ou uma execucao repetida por engano, nao
chega duas vezes ao destinatario.
"""
import json
import sqlite3
import threading
from datetime import datetime

import config

_trava = threading.Lock()

# Em DRY_RUN cada execucao do servico tem seu proprio espaco de reservas: um
# envio simulado nao pode bloquear o envio real da mesma edicao, e testes
# repetidos nao devem colidir entre si.
_ESPACO = f"teste-{datetime.now():%H%M%S}:" if config.DRY_RUN else ""

ESQUEMA = """
CREATE TABLE IF NOT EXISTS envios (
    edicao_id TEXT NOT NULL,
    perfil_id TEXT NOT NULL,
    canal TEXT NOT NULL,
    status TEXT NOT NULL,
    registrado_em TEXT NOT NULL,
    PRIMARY KEY (edicao_id, perfil_id, canal)
);
"""


def mascarar(contato):
    contato = str(contato or "")
    if "@" in contato:
        nome, dominio = contato.split("@", 1)
        return f"{nome[:2]}***@{dominio}"
    return f"***{contato[-4:]}" if len(contato) > 4 else "***"


def registrar(evento, **campos):
    linha = {"ts": datetime.now().isoformat(timespec="milliseconds"), "evento": evento}
    linha.update(campos)
    texto = json.dumps(linha, ensure_ascii=False, default=str)
    with _trava, open(config.ARQ_AUDITORIA, "a", encoding="utf-8") as arquivo:
        arquivo.write(texto + "\n")


_compartilhada = None


def _conexao():
    """Conexao unica do processo, usada sempre sob `_trava`.

    Abrir a conexao e reaplicar o esquema a cada envio custava mais que o
    proprio envio simulado (docs/07_testes.md). O servidor cria uma thread por
    requisicao, entao conexao por thread nao seria reaproveitada. O modo WAL
    evita que a gravacao bloqueie as leituras do pipeline no mesmo banco.
    """
    global _compartilhada
    if _compartilhada is None:
        _compartilhada = sqlite3.connect(config.ARQ_DB, timeout=30, check_same_thread=False)
        _compartilhada.execute("PRAGMA journal_mode=WAL")
        _compartilhada.execute("PRAGMA synchronous=NORMAL")
        _compartilhada.executescript(ESQUEMA)
    return _compartilhada


def reservar_envio(edicao_id, perfil_id, canal):
    """True se o envio pode seguir; False se ja foi feito ou esta em curso.

    A reserva e gravada na mesma transacao da consulta, para que duas
    requisicoes simultaneas nao passem ambas pela verificacao.
    """
    edicao_id = _ESPACO + edicao_id
    with _trava:
        conexao = _conexao()
        linha = conexao.execute(
            "SELECT status FROM envios WHERE edicao_id=? AND perfil_id=? AND canal=?",
            (edicao_id, perfil_id, canal),
        ).fetchone()
        livre = not linha or linha[0] == "falhou"
        if livre:
            conexao.execute(
                "INSERT OR REPLACE INTO envios VALUES (?, ?, ?, 'enviando', ?)",
                (edicao_id, perfil_id, canal,
                 datetime.now().isoformat(timespec="seconds")),
            )
            conexao.commit()
    return livre


def concluir_envio(edicao_id, perfil_id, canal, status):
    edicao_id = _ESPACO + edicao_id
    with _trava:
        conexao = _conexao()
        conexao.execute(
            "INSERT OR REPLACE INTO envios VALUES (?, ?, ?, ?, ?)",
            (edicao_id, perfil_id, canal, status,
             datetime.now().isoformat(timespec="seconds")),
        )
        conexao.commit()
