"""Console do operador.

Ponto unico de entrada: dispara a edicao, acompanha o progresso e abre os
resultados. Usa apenas tkinter, incluido na biblioteca padrao.

    Radar VR.cmd            duplo clique, sem console
    python src/painel.py    a partir do terminal
"""
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, scrolledtext

RAIZ = Path(__file__).resolve().parent.parent
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"
DIR_DADOS = RAIZ / "data"
DIR_AUDIO = RAIZ / "audio"
BANCO = DIR_DADOS / "jornal_vr.db"

FUNDO = "#17171a"
CARTAO = "#202024"
BORDA = "#303036"
TEXTO = "#e8e8e6"
SUAVE = "#9a9aa0"
AZUL = "#2563eb"
VERDE = "#059669"
AMBAR = "#b45309"


class Painel:
    def __init__(self, raiz):
        self.raiz = raiz
        self.fila = queue.Queue()
        self.rodando = False

        raiz.title("Radar VR — redação")
        raiz.configure(bg=FUNDO)
        raiz.geometry("700x560")
        raiz.minsize(620, 480)

        self._cabecalho()
        self._botoes()
        self._console()
        self._rodape()

        self.atualizar_estado()
        self.raiz.after(100, self._drenar_fila)

    # ------------------------------------------------------------ interface
    def _cabecalho(self):
        topo = tk.Frame(self.raiz, bg=FUNDO)
        topo.pack(fill="x", padx=24, pady=(20, 4))
        tk.Label(topo, text="Radar VR", bg=FUNDO, fg=TEXTO,
                 font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(topo, text="o que mudou no catálogo de realidade virtual da Steam",
                 bg=FUNDO, fg=SUAVE, font=("Segoe UI", 10)).pack(anchor="w")

        tk.Frame(self.raiz, bg=BORDA, height=1).pack(fill="x", padx=24, pady=(12, 0))
        self.rotulo_estado = tk.Label(
            self.raiz, text="", bg=FUNDO, fg=SUAVE,
            font=("Segoe UI", 9), justify="left",
        )
        self.rotulo_estado.pack(anchor="w", padx=24, pady=(10, 0))

    def _botao(self, pai, texto, legenda, cor, comando):
        quadro = tk.Frame(pai, bg=CARTAO, highlightbackground=BORDA,
                          highlightthickness=1)
        quadro.pack(side="left", expand=True, fill="both", padx=4)
        botao = tk.Button(
            quadro, text=texto, command=comando, bg=cor, fg="white",
            font=("Segoe UI", 11, "bold"), relief="flat", cursor="hand2",
            activebackground=cor, activeforeground="white", pady=10, bd=0,
        )
        botao.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(quadro, text=legenda, bg=CARTAO, fg=SUAVE, font=("Segoe UI", 8),
                 wraplength=180, justify="center").pack(padx=10, pady=(0, 10))
        return botao

    def _botoes(self):
        faixa = tk.Frame(self.raiz, bg=FUNDO)
        faixa.pack(fill="x", padx=20, pady=14)
        self.btn_rodar = self._botao(
            faixa, "Fechar edição de hoje",
            "consulta a Steam, detecta o que mudou e narra o boletim",
            AZUL, self.rodar,
        )
        self.btn_ouvir = self._botao(
            faixa, "Ouvir boletim", "abre a narração da última edição",
            VERDE, self.ouvir,
        )
        self.btn_ler = self._botao(
            faixa, "Ler edição",
            "abre a página com os nomes escritos e links da loja",
            AMBAR, self.ler,
        )

    def _console(self):
        tk.Label(self.raiz, text="ACOMPANHAMENTO", bg=FUNDO, fg=SUAVE,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=24, pady=(4, 4))
        self.console = scrolledtext.ScrolledText(
            self.raiz, bg="#101013", fg="#c8c8c6", insertbackground=TEXTO,
            font=("Consolas", 9), relief="flat", wrap="word", height=12,
            state="disabled", padx=12, pady=10,
        )
        self.console.pack(fill="both", expand=True, padx=24)
        self.console.tag_config("etapa", foreground="#6ea8ff")
        self.console.tag_config("ok", foreground="#4ade80")
        self.console.tag_config("erro", foreground="#f87171")
        self.console.tag_config("info", foreground="#9a9aa0")

    def _rodape(self):
        self.barra = ttk.Progressbar(self.raiz, mode="indeterminate")
        self.barra.pack(fill="x", padx=24, pady=(10, 4))
        tk.Label(self.raiz,
                 text="Dados das rotas públicas da Steam · IA executada nesta máquina",
                 bg=FUNDO, fg="#5a5a60", font=("Segoe UI", 8)).pack(pady=(0, 12))

    # --------------------------------------------------------------- estado
    def atualizar_estado(self):
        partes = []
        self.audio = None
        self.pagina = None

        if BANCO.exists():
            conexao = None
            try:
                # sqlite3.connect como gerenciador de contexto faz commit, nao
                # fecha. Manter aberta trava o arquivo do banco.
                conexao = sqlite3.connect(BANCO)
                conexao.row_factory = sqlite3.Row
                edicoes = conexao.execute("SELECT COUNT(*) FROM edicoes").fetchone()[0]
                leituras = conexao.execute(
                    "SELECT COUNT(*) FROM snapshots"
                ).fetchone()[0]
                ultima = conexao.execute(
                    "SELECT arquivo_audio, arquivo_pagina, publicada_em "
                    "FROM edicoes ORDER BY id DESC LIMIT 1"
                ).fetchone()

                if edicoes == 0:
                    partes.append("Nenhuma edição publicada ainda.")
                else:
                    # Audio e pagina saem da mesma linha: os .wav acumulam com
                    # carimbo de data e a pagina tem nome fixo, entao buscar
                    # cada um por conta propria poderia cruzar edicoes.
                    momento = datetime.fromisoformat(ultima["publicada_em"])
                    partes.append(
                        f"{edicoes} {'edição' if edicoes == 1 else 'edições'} "
                        f"no histórico · {leituras} leituras acumuladas · "
                        f"última em {momento:%d/%m às %H:%M}"
                    )
                    if ultima["arquivo_audio"]:
                        caminho = DIR_AUDIO / ultima["arquivo_audio"]
                        self.audio = caminho if caminho.exists() else None
                    if ultima["arquivo_pagina"]:
                        caminho = DIR_DADOS / ultima["arquivo_pagina"]
                        self.pagina = caminho if caminho.exists() else None
                if edicoes == 1:
                    partes.append("A próxima edição já poderá comparar preços "
                                  "e jogadores.")
            except sqlite3.Error:
                partes.append("Banco encontrado, mas ainda sem tabelas.")
            finally:
                if conexao is not None:
                    conexao.close()
        else:
            partes.append("Primeira execução: esta edição estabelece a linha de base.")

        self.rotulo_estado.config(text="\n".join(partes))
        self.btn_ouvir.config(state="normal" if self.audio else "disabled")
        self.btn_ler.config(state="normal" if self.pagina else "disabled")

    # ------------------------------------------------------------- execucao
    def escrever(self, texto, tag="info"):
        self.console.config(state="normal")
        self.console.insert("end", texto + "\n", tag)
        self.console.see("end")
        self.console.config(state="disabled")

    def rodar(self):
        if self.rodando:
            return
        self.rodando = True
        self.btn_rodar.config(state="disabled", text="Fechando edição...")
        self.barra.start(12)
        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")
        self.escrever("Iniciando. A edição leva cerca de 80 segundos.", "info")
        threading.Thread(target=self._executar, daemon=True).start()

    def _executar(self):
        """Subprocesso em thread separada, para nao bloquear a janela."""
        executavel = str(PYTHON) if PYTHON.exists() else sys.executable
        try:
            processo = subprocess.Popen(
                [executavel, "-u", str(RAIZ / "src" / "jornal.py")],
                cwd=str(RAIZ / "src"),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for linha in processo.stdout:
                self.fila.put(("linha", linha.rstrip()))
            processo.wait()
            self.fila.put(("fim", processo.returncode))
        except Exception as erro:
            self.fila.put(("erro", str(erro)))

    def _drenar_fila(self):
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "linha":
                    self._mostrar(dado)
                elif tipo == "fim":
                    self._encerrar(dado)
                elif tipo == "erro":
                    self.escrever(f"Falha ao iniciar: {dado}", "erro")
                    self._encerrar(1)
        except queue.Empty:
            pass
        self.raiz.after(100, self._drenar_fila)

    def _mostrar(self, linha):
        """Filtra o log do pipeline para o que interessa ao operador."""
        if "ETAPA" in linha:
            self.escrever(linha.split("|")[-1].strip().strip("= "), "etapa")
        elif "EDIÇÃO PUBLICADA" in linha:
            self.escrever(linha.split("|")[-1].strip(), "ok")
        elif any(m in linha for m in ("MANCHETE", "DESTAQUES", "PROMOCOES", "RADAR")):
            self.escrever("  " + linha.strip(), "info")
        elif "ERROR" in linha or "Traceback" in linha:
            self.escrever(linha.strip(), "erro")
        elif linha.strip().startswith(("Áudio", "Leitura", "Planilha")):
            self.escrever(linha.strip(), "ok")

    def _encerrar(self, codigo):
        self.rodando = False
        self.barra.stop()
        self.btn_rodar.config(state="normal", text="Fechar edição de hoje")
        if codigo == 0:
            self.escrever("\nEdição publicada. Já dá para ouvir e ler.", "ok")
        else:
            self.escrever(
                f"\nA edição não foi concluída (código {codigo}). "
                "Verifique se o Ollama está no ar.", "erro",
            )
        self.atualizar_estado()

    # ---------------------------------------------------------------- acoes
    def ouvir(self):
        if not self.audio:
            self.escrever("Nenhum boletim gravado ainda.", "erro")
            return
        self.escrever(f"Abrindo {self.audio.name}", "info")
        try:
            os.startfile(str(self.audio))
        except AttributeError:
            subprocess.Popen(["xdg-open", str(self.audio)])

    def ler(self):
        if not self.pagina:
            self.escrever("Nenhuma edição publicada ainda.", "erro")
            return
        self.escrever(f"Abrindo {self.pagina.name} no navegador", "info")
        webbrowser.open(self.pagina.as_uri())


def main():
    raiz = tk.Tk()
    Painel(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
