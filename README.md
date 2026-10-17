# Radar VR

Acompanha os jogos de realidade virtual da Steam e avisa o que mudou neles:
promoção nova, promoção perto do fim, menor preço da história, atualização
grande, alta ou queda de jogadores.

Cada assinante escolhe os jogos e gêneros que quer acompanhar. Quando há
novidade nesses jogos, recebe um e-mail curto. Se a novidade não pode esperar,
como uma promoção que acaba amanhã, recebe também um alerta no Telegram.

Projeto da disciplina AI Factory (PUCPR), por Rafael Probst.

## Exemplo

Um dia com o Moss II VR no menor preço da história:

| Canal | O que chega |
|---|---|
| E-mail | assunto "Moss II VR no menor preço histórico"; cartão com -50%, preço cheio riscado, preço atual e "visto pela última vez em 03/2025" |
| Telegram | 🔥 Moss II VR −50% · R$ 29,99 · menor preço histórico |

Quem não teve novidade nos seus jogos não recebe nada. O alerta do Telegram
traz só o urgente, porque o resto já está no e-mail.

## Como funciona

O fluxo roda no n8n. Cada passo chama um microsserviço Python
(`src/servico.py`), que faz o trabalho:

```
n8n                                  microsserviço
───────────────────────────────      ──────────────────────────────────────
1. Gerar edição               ───►   coleta a Steam e o IsThereAnyDeal
2. Personalizar por assinante ───►   escolhe as novidades de cada pessoa
3. Enviar e-mail              ───►   envia pelo Gmail
4. Tem alerta urgente?
   sim: Enviar alerta         ───►   envia pelo Telegram
```

Quando um passo falha, o n8n desvia o caminho:

| Falhou | O que acontece |
|---|---|
| E-mail | o alerta do Telegram leva também as outras novidades do dia, e o operador recebe um aviso |
| Telegram | o alerta vai por e-mail |
| E-mail e Telegram | nada chega ao assinante nessa edição; a falha fica registrada em log |
| Microsserviço fora do ar | o n8n grava a falha em `logs/n8n_falhas.log` e encerra a execução |

Rotas do microsserviço:

| Rota | O que faz |
|---|---|
| `POST /edicao` | coleta a Steam, consulta o histórico de preços, detecta o que mudou e grava a edição do dia |
| `POST /personalizar` | monta um e-mail (e, se houver urgência, um alerta) para cada assinante |
| `POST /enviar/email` | envia o e-mail |
| `POST /enviar/instantaneo` | envia o alerta pelo Telegram (ou WhatsApp) |
| `POST /falha` | registra uma falha do fluxo e avisa o operador |
| `GET /saude` | mostra o modo e quais canais estão configurados |

## Como rodar

**Instalação** (uma vez; instala Ollama, espeak-ng, o ambiente Python, os
modelos de voz e de linguagem e o n8n, e importa os fluxos):

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

**Boletim personalizado:** duplo clique em `Radar VR - n8n.cmd`. Ele pergunta o
modo, abre o microsserviço e o n8n e leva o navegador ao editor. No n8n, abra o
fluxo *Radar VR - Boletim personalizado* e clique em *Execute workflow*.

| Modo | O que acontece |
|---|---|
| Ensaio | o fluxo roda inteiro, mas nenhuma mensagem sai da máquina (`RADAR_DRY_RUN=1`) |
| Real | e-mail e Telegram chegam aos assinantes de `perfis.json` |

Cada assinante recebe no máximo uma mensagem por canal e por edição. Executar
de novo a mesma edição não reenvia nada.

**Boletim geral em áudio** (Etapa 1): duplo clique em `Radar VR.cmd` abre o
painel com os botões *Fechar edição de hoje*, *Ouvir boletim* e *Ler edição*.
Pela linha de comando: `python src/jornal.py` (`--sem-audio`, `--titulos 8`).

## Configuração

| Arquivo | Conteúdo | No Git? |
|---|---|---|
| `.env` | credenciais: Gmail, Telegram, IsThereAnyDeal, WhatsApp | não (modelo em `.env.example`) |
| `perfis.json` | assinantes: contato, jogos, gêneros, orçamento, data do consentimento | não (modelo em `perfis.exemplo.json`) |

Perfil sem data de consentimento é ignorado. As demais opções (porta, modo
ensaio, falha forçada de canal para teste) estão comentadas no `.env.example`.

## Código

| Módulo | Responsabilidade |
|---|---|
| [`coleta.py`](src/coleta.py) | consulta à Steam: busca, ficha da loja, jogadores, avaliações e anúncios |
| [`itad.py`](src/itad.py) | menor preço da história, pela API do IsThereAnyDeal |
| [`historico.py`](src/historico.py) | leituras anteriores em SQLite, para comparar |
| [`noticias.py`](src/noticias.py) | detecção dos eventos e ordem de importância |
| [`redacao.py`](src/redacao.py) | resumo dos anúncios dos desenvolvedores com LLM local (Ollama) |
| [`voz.py`](src/voz.py), [`pronuncia.py`](src/pronuncia.py) | narração do boletim geral (Kokoro) |
| [`boletim_html.py`](src/boletim_html.py) | página do boletim geral |
| [`jornal.py`](src/jornal.py) | gera uma edição completa |
| [`personalizacao.py`](src/personalizacao.py) | o que interessa a cada assinante, urgência e texto das mensagens |
| [`canais.py`](src/canais.py) | envio por e-mail, Telegram e WhatsApp, com novas tentativas |
| [`auditoria.py`](src/auditoria.py) | registro de cada envio e bloqueio de repetição |
| [`servico.py`](src/servico.py) | microsserviço HTTP chamado pelo n8n |
| [`painel.py`](src/painel.py) | painel do boletim geral |

Fluxos do n8n em [`n8n/`](n8n): o boletim personalizado, o tratamento de
falhas e o boletim geral da Etapa 1.

## Testes de carga

`python testes/estresse.py` roda os cenários em modo ensaio, com assinantes
fictícios. Principais resultados (detalhes em
[docs/07_testes.md](docs/07_testes.md)):

| Gargalo | Antes | Depois |
|---|---:|---:|
| Coleta na Steam, sequencial → 4 em paralelo | 29,8 s | 19,3 s |
| Envios por segundo, banco reaberto a cada envio → conexão única | 28,6 | 185 |
| Telegram esperando o IPv6 → IPv4 direto | 23 a 44 s | 1,8 s |
| Personalização de 100 assinantes, LLM → regra | 164 s | 0,03 s |
| Edição com o Ollama desligado | abortava | 2,1 s |

## Limitações

- **WhatsApp:** integrado pela API oficial da Meta, mas a Meta recusa a entrega
  para números do Brasil vindos de remetente estrangeiro (erro 130497), caso
  do número de teste. O Telegram cumpre o papel até haver um número brasileiro
  dedicado. Ver [docs/06_canais.md](docs/06_canais.md).
- **Volume de e-mail:** o Gmail aceita cerca de 500 envios por dia.
- **Cancelamento:** o pedido de saída chega por e-mail ao operador, que remove
  o perfil à mão.
- **Execução local:** roda no computador do operador; a versão pública na web
  é o próximo passo.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Diagnóstico](docs/01_diagnostico.md) | problema, dados disponíveis e oportunidades |
| [Canvas](docs/02_canvas.md) | objetivos, escopo, riscos e critérios |
| [Arquitetura](docs/03_arquitetura.md) | módulos, eventos e limiares |
| [Ambiente](docs/04_ambiente.md) | instalação e evidências da Etapa 1 |
| [n8n](docs/05_n8n.md) | fluxos, passagem de dados e contingência |
| [Microsserviço e canais](docs/06_canais.md) | rotas, personalização e tratamento de erros |
| [Testes de carga](docs/07_testes.md) | gargalos, melhorias e números |

---

Preços históricos: [IsThereAnyDeal](https://isthereanydeal.com). Preços,
jogadores e anúncios: Steam.
