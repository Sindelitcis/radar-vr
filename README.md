# Radar VR

Boletim diário do que mudou no catálogo de realidade virtual da Steam —
promoções, prazos, atualizações e movimentação de jogadores — entregue em
áudio e em página.

**AI Factory — Etapa 1 · PUCPR · Rafael Probst**

---

## O problema

> A loja mostra **estado**. O que falta é **mudança**.

A página de um jogo informa quanto ele custa agora. Não informa se entrou em
promoção hoje, se recebeu atualização ontem ou se está perdendo jogadores.
Essa informação não existe em campo algum da API: só aparece comparando duas
leituras no tempo. O banco de dados, aqui, não é registro — é o produto.

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
| [`jornal.py`](src/jornal.py) | orquestrador |
| [`painel.py`](src/painel.py) | console do operador |

## Saídas

| Arquivo | Finalidade |
|---|---|
| `audio/boletim_*.wav` | narração |
| `data/boletim_atual.html` | leitura, com preço no formato da loja |
| `data/jornal_vr.csv` | manchetes publicadas |
| `data/jornal_vr.db` | série temporal — insumo da próxima edição |
| `logs/jornal.log` | registro das etapas |

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
a resumir — o corpo de um anúncio. Preço, desconto e variação chegam como
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
| [n8n](docs/05_n8n.md) | fluxo de agendamento |
