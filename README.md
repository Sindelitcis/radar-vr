# Radar VR

Boletim diário em áudio sobre o que mudou nos jogos de realidade virtual que
você acompanha na Steam: atualizações, promoções, prazos e movimentação de
jogadores.

Na Etapa 2, cada assinante recebe a própria edição: só os jogos e gêneros que
acompanha, por e-mail, e um alerta no Telegram quando algo não pode esperar.

**AI Factory, Etapas 1 e 2 (PUCPR)** por Rafael Probst

---

## O problema

> A loja mostra **estado**. O que falta é **mudança**.

Ninguém abre a página de cada jogo todo dia pra ver se saiu patch novo ou se
tem mais gente jogando. No máximo você repara numa promoção, e olhe lá.

O resto passa batido. Numa semana qualquer, quatro dos quinze títulos
monitorados aqui receberam anúncio do desenvolvedor, e nenhum deles apareceu na
vitrine da loja. Movimentação de jogadores e histórico de preço a Steam não
mostra de jeito nenhum.

Essa informação só existe comparando duas leituras no tempo. Por isso o banco
de dados aqui não é registro, e sim o próprio produto.

## Uso

Duplo clique em **`Radar VR.cmd`**.

| Botão | Ação |
|---|---|
| Fechar edição de hoje | consulta a Steam, detecta mudanças e narra o boletim |
| Ouvir boletim | abre a narração da última edição |
| Ler edição | abre a página com os nomes escritos e links da loja |

Pela linha de comando:

```bash
python src/jornal.py                 # edição completa
python src/jornal.py --titulos 8     # watchlist reduzida
python src/jornal.py --sem-audio     # sem síntese de voz
```

## Boletim personalizado

```
executar_servico.cmd          microsserviço em http://127.0.0.1:8765
executar_n8n.cmd import       importa os fluxos
executar_n8n.cmd run          edição → personalização → e-mail → alerta
```

`executar_servico.cmd teste` liga o modo DRY_RUN: o fluxo roda inteiro e
nenhuma mensagem sai da máquina.

Assinantes ficam em `perfis.json`, fora do Git (modelo em
`perfis.exemplo.json`); credenciais, no `.env` (modelo em `.env.example`).

## Pipeline

```
ETAPA 1            ETAPA 2                ETAPA 3           ETAPA 4
Steam, 5 rotas  →  detecção de eventos →  redação e voz  →  áudio, HTML,
sem chave          + série temporal        LLM + Kokoro      CSV e SQLite
```

| Módulo | Responsabilidade |
|---|---|
| [`coleta.py`](src/coleta.py) | cinco rotas públicas da Steam |
| [`historico.py`](src/historico.py) | snapshots, comparação, memória de publicação |
| [`noticias.py`](src/noticias.py) | detecção de eventos e relevância |
| [`redacao.py`](src/redacao.py) | redação das chamadas com LLM local |
| [`pronuncia.py`](src/pronuncia.py) | texto escrito para texto falado |
| [`voz.py`](src/voz.py) | roteiro e síntese com Kokoro |
| [`boletim_html.py`](src/boletim_html.py) | edição em página |
| [`itad.py`](src/itad.py) | menor preço da história, pela API do IsThereAnyDeal |
| [`jornal.py`](src/jornal.py) | orquestrador da edição |
| [`personalizacao.py`](src/personalizacao.py) | recorte, urgência e texto por assinante |
| [`canais.py`](src/canais.py) | e-mail, Telegram e WhatsApp |
| [`auditoria.py`](src/auditoria.py) | trilha de envios e bloqueio de repetição |
| [`servico.py`](src/servico.py) | microsserviço HTTP chamado pelo n8n |
| [`painel.py`](src/painel.py) | console do operador |

## Saídas

| Arquivo | Finalidade |
|---|---|
| `audio/boletim_*.wav` | narração |
| `data/boletim_atual.html` | leitura, com preço no formato da loja |
| `data/jornal_vr.csv` | manchetes publicadas |
| `data/jornal_vr.db` | série temporal, insumo da próxima edição |
| `data/edicao_atual.json` | edição estruturada, entregue ao n8n |
| `logs/jornal.log` | registro das etapas e das rotas |
| `logs/auditoria.jsonl` | uma linha por decisão e por envio |

Áudio e página são complementares: a narração serve para varrer o boletim sem
tirar o headset; a página resolve o nome escrito e leva à loja por link.

## Instalação

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

Instala Ollama, espeak-ng, o virtualenv, os modelos do Kokoro, o `llama3.1:8b`
e o n8n, importa o fluxo e verifica cada item. É idempotente.

## Decisões de projeto

**LLM local, não API paga.** O catálogo é reprocessado a cada edição. Um modelo
local tem custo marginal zero e não impõe limite de requisições. A RTX 5060 Ti
comporta um modelo de 8B integralmente em VRAM.

**O modelo não decide fato com número.** Ele redige apenas onde há texto livre
a resumir, que é o corpo de um anúncio. Preço, desconto e variação chegam como
frase pronta de regra determinística, auditável e consistente entre execuções.

**A memória de publicação não cresce.** A retenção é derivada da janela de
detecção: um anúncio mais antigo que ela já é descartado por idade, então
guardar seu identificador além disso não altera resultado. A tabela fica
limitada a algumas dezenas de linhas.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Diagnóstico](docs/01_diagnostico.md) | problema, dados, causas e oportunidades |
| [Canvas](docs/02_canvas.md) | objetivos, escopo, riscos e critérios |
| [Arquitetura](docs/03_arquitetura.md) | módulos, eventos, limiares e saídas |
| [Ambiente](docs/04_ambiente.md) | stack, instalação e evidências de execução |
| [n8n](docs/05_n8n.md) | fluxos, passagem de dados e contingência |
| [Microsserviço e canais](docs/06_canais.md) | rotas, personalização, canais e erros |
| [Testes de carga](docs/07_testes.md) | gargalos, melhorias e números antes e depois |

---

Preços históricos: [IsThereAnyDeal](https://isthereanydeal.com). Preços,
jogadores e anúncios: Steam.

