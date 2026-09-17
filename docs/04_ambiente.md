# Ambiente e Evidências

**Radar VR** · AI Factory — Etapa 1 · PUCPR · 17/09/2026

---

## 1. Hardware

| Componente | Especificação |
|---|---|
| CPU | AMD Ryzen 7 5700X — 8 núcleos / 16 threads |
| RAM | 32 GB |
| GPU | NVIDIA GeForce RTX 5060 Ti — 16 GB VRAM |
| SO | Windows 11 Pro 26200 |
| Headset | Meta Quest 3, em modo PC VR |

## 2. Stack

| Componente | Versão | Papel |
|---|---|---|
| Python | 3.11.9 | runtime |
| requests | 2.34.2 | chamadas HTTP |
| Ollama | — | servidor de LLM local |
| llama3.1:8b | 4,92 GB · Q4_K_M | redação das chamadas |
| kokoro-onnx | — | síntese de voz |
| onnxruntime | 1.30.0 | inferência do Kokoro |
| soundfile | 0.14.0 | gravação do `.wav` |
| espeak-ng | — | phonemizer PT-BR |
| n8n | 2.35.7 | agendamento |
| SQLite | embutido | série temporal |
| tkinter | embutido | painel operacional |

### Modelos em disco

| Arquivo | Tamanho |
|---|---|
| `modelos/kokoro-v1.0.onnx` | 310 MB |
| `modelos/voices-v1.0.bin` | 27 MB |
| `llama3.1:8b` | 4,92 GB |

### Alocação verificada

Consulta a `GET /api/ps` do Ollama durante a execução:

```
llama3.1:8b  size_vram = 5.27 GB
```

O modelo de 8B roda integralmente na VRAM. O Kokoro roda em CPU —
`onnxruntime.get_available_providers()` não inclui provider CUDA nesta
instalação. Não é limitante: o modelo tem 82M parâmetros e sintetiza 69
segundos de áudio em cerca de 19 segundos.

## 3. Instalação

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

Script idempotente. Instala Ollama e espeak-ng via `winget`, cria o
virtualenv, instala as dependências, baixa os modelos do Kokoro, puxa o
`llama3.1:8b`, instala o n8n, importa o fluxo e roda uma verificação item a
item.

## 4. Execução

```
Radar VR.cmd                      painel, com duplo clique
python src/jornal.py              linha de comando
python src/jornal.py --titulos 8  watchlist reduzida
python src/jornal.py --sem-audio   sem síntese de voz
executar_n8n.cmd run              via n8n, sem interface
```

## 5. Validação das rotas

Coleção importável em [`postman/colecao_radar_vr.json`](../postman/colecao_radar_vr.json).

| # | Rota | Retorno verificado |
|---|---|---|
| 1 | `/search/results` | 5.693 títulos VR; 770 em promoção |
| 2 | `/api/appdetails` | preço final, preço cheio e desconto em BRL |
| 3 | `GetNumberOfCurrentPlayers` | VRChat com 37.110 jogadores |
| 4 | `/appreviews/<appid>` | Half-Life: Alyx com 98,3 % em 105.304 avaliações |
| 5 | `ISteamNews/GetNewsForApp` | anúncios com `gid`, data e `feed_type` |
| 6 | `/api/tags` (Ollama) | `llama3.1:8b` disponível |
| 7 | `/api/generate` (Ollama) | resposta em JSON estruturado |

## 6. Execução ponta a ponta

### Edição 1 — linha de base

```
Coleta ..... 15 títulos observados
Eventos .... 16 detectados, 6 no boletim
             PROMOCAO_NOVA 11 · PATCH_GRANDE 4 · PROMOCAO_ACABANDO 1
Redação .... 6 linhas (4 do LLM, 2 por regra)
Voz ........ boletim_2026-09-17_02-59.wav (68,8 s, voz pf_dora)
Publicação . jornal_vr.csv + jornal_vr.db + boletim_2026-09-17_02-59.html
```

### Edição 2 — comparação com a anterior

```
Comparando com a leitura de 2026-09-17T02:58:50
Eventos .... 2 detectados, 2 no boletim
             PROMOCAO_ACABANDO 1 · PATCH_GRANDE 1
Voz ........ boletim_2026-09-17_03-00.wav (33,5 s, voz pf_dora)
```

**Leitura do resultado.** As 11 promoções da primeira edição não reapareceram:
já eram conhecidas, deixaram de ser novidade. Dos 4 anúncios, 3 foram
suprimidos pela memória de publicação. O comportamento distingue um boletim de
um catálogo — apenas o que mudou é reportado.

### Artefatos

| Arquivo | Tamanho |
|---|---|
| `audio/boletim_2026-09-17_02-59.wav` | 3.302.604 bytes |
| `audio/boletim_2026-09-17_03-00.wav` | 1.606.412 bytes |
| `data/boletim_atual.html` | 7.726 bytes |
| `data/jornal_vr.csv` | 2.132 bytes |
| `data/jornal_vr.db` | 32.768 bytes — 2 edições, 30 snapshots, 5 gids retidos |

## 7. Critérios de sucesso

| # | Critério | Resultado |
|---|---|---|
| 1 | Quatro etapas com código de saída 0 | ✅ 84 s |
| 2 | `.wav` com narração e `boletim_atual.html` com links | ✅ |
| 3 | CSV com uma linha por manchete | ✅ 6 linhas + cabeçalho |
| 4 | SQLite acumulando snapshots | ✅ 30 leituras em 2 edições |
| 5 | Anúncio publicado não reaparece | ✅ 4 → 1 na segunda edição |
| 6 | Fluxo n8n com todos os nós em `success` | ✅ 5/5 |
| 7 | Nenhuma credencial paga | ✅ |

## 8. Objetivos do Canvas

| Objetivo | Meta | Medido |
|---|---|---|
| O1 | edição em menos de 2 min | **84 s** |
| O2 | 15 títulos, conjunto estável | 15, mesmos appids nas duas edições |
| O3 | áudio com menos de 2 min | **68,8 s** |
| O4 | custo R$ 0,00 | nenhuma credencial paga |
| O5 | não repetir notícia publicada | 4 anúncios → 1 |
| O6 | ponto de entrada único | `Radar VR.cmd` |
