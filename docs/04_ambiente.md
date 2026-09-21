# Ambiente e Evidências

**Projeto:** Radar VR
**Disciplina:** AI Factory, Etapa 1 (PUCPR)
**Data:** 17/09/2026

---

## 1. Hardware

| Componente | Especificação |
|---|---|
| CPU | AMD Ryzen 7 5700X, 8 núcleos e 16 threads |
| RAM | 32 GB |
| GPU | NVIDIA GeForce RTX 5060 Ti, 16 GB de VRAM |
| SO | Windows 11 Pro 26200 |
| Headset | Meta Quest 3, em modo PC VR |

## 2. Stack

| Componente | Versão | Papel |
|---|---|---|
| Python | 3.11.9 | runtime |
| requests | 2.34.2 | chamadas HTTP |
| Ollama | (sem versão fixa) | servidor de LLM local |
| llama3.1:8b | 4,92 GB, Q4_K_M | redação das chamadas |
| kokoro-onnx | (sem versão fixa) | síntese de voz |
| onnxruntime | 1.30.0 | inferência do Kokoro |
| soundfile | 0.14.0 | gravação do `.wav` |
| espeak-ng | (sem versão fixa) | phonemizer PT-BR |
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

O modelo de 8B roda integralmente na VRAM. O Kokoro roda em CPU, porque
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

Quatro edições publicadas entre 17 e 20/09, todas presentes em
`data/jornal_vr.db`. Os valores abaixo saem de `logs/jornal.log` e podem ser
conferidos contra o banco.

| Edição | Títulos | Eventos detectados | No boletim | Duração | Áudio |
|---|:-:|:-:|:-:|:-:|:-:|
| 17/09 03:13 | 12 | 13 | 6 | 62,5 s | 68,8 s |
| 17/09 21:36 | 15 | 9 | 6 | 89,0 s | 60,1 s |
| 19/09 09:22 | 15 | 3 | 3 | 90,5 s | 39,0 s |
| 20/09 15:08 | 15 | 3 | 3 | 74,5 s | 36,1 s |

**Leitura do resultado.** A contagem de eventos cai de 13 para 3 ao longo da
série, e a duração do áudio acompanha. Não é perda de capacidade: é o
comportamento esperado de um boletim. As promoções noticiadas na primeira
edição deixaram de ser novidade nas seguintes, e os anúncios já publicados
foram suprimidos pela memória de publicação. Só o que mudou é reportado.

### Artefatos gerados

| Arquivo | Tamanho |
|---|---|
| `audio/boletim_2026-09-17_03-13.wav` | 3.302.604 bytes |
| `audio/boletim_2026-09-17_21-36.wav` | 2.883.052 bytes |
| `audio/boletim_2026-09-19_09-22.wav` | 1.872.652 bytes |
| `audio/boletim_2026-09-20_15-08.wav` | 1.734.412 bytes |
| `data/jornal_vr.csv` | 4.417 bytes |
| `data/jornal_vr.db` | 40.960 bytes |

Cada edição grava também a própria página em `data/boletim_AAAA-MM-DD_HH-MM.html`.

### Estado do banco

```
edições publicadas ..... 4
leituras acumuladas .... 57
títulos distintos ...... 15
anúncios em memória .... 7
```

## 7. Critérios de sucesso

| # | Critério | Resultado |
|---|---|---|
| 1 | Quatro etapas com código de saída 0 | ✅ entre 62 e 91 s por edição |
| 2 | `.wav` com narração e página com links | ✅ quatro edições completas |
| 3 | CSV com uma linha por manchete | ✅ 18 manchetes em 4 edições |
| 4 | SQLite acumulando snapshots | ✅ 57 leituras |
| 5 | Anúncio publicado não reaparece | ✅ 13 eventos na 1ª edição, 3 na 4ª |
| 6 | Fluxo n8n com todos os nós em `success` | ✅ 5/5 |
| 7 | Nenhuma credencial paga | ✅ |

## 8. Objetivos do Canvas

| Objetivo | Meta | Medido |
|---|---|---|
| O1 | edição em menos de 2 min | **62,5 s a 90,5 s** |
| O2 | lista curta e estável | 15 títulos, mesmos appids nas quatro edições |
| O3 | áudio com menos de 2 min | **36,1 s a 68,8 s** |
| O4 | custo R$ 0,00 | nenhuma credencial no código |
| O5 | não repetir notícia publicada | 7 anúncios retidos em memória |
| O6 | ponto de entrada único | `Radar VR.cmd` |
