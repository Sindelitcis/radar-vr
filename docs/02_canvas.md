# Canvas de Projeto

**Projeto:** Radar VR
**Autor:** Rafael Probst (trabalho individual)
**Disciplina:** AI Factory, Etapa 1 (PUCPR)

---

## 1. Justificativa

Quem acompanha alguns jogos de VR não tem como saber o que mudou neles sem
abrir a página de cada um, todo dia. Na semana de 15 a 21/09, quatro dos quinze
títulos monitorados receberam anúncio do desenvolvedor, e nenhum deles apareceu
na vitrine da loja. Movimentação de jogadores e histórico de preço não são
exibidos de forma alguma. O detalhamento está no
[Diagnóstico](01_diagnostico.md).

## 2. Objetivo

Publicar um boletim diário do que mudou nos jogos de realidade virtual que o
usuário acompanha, consumível em áudio e em página, rodando inteiro na máquina
dele e sem custo recorrente.

## 3. Objetivos específicos

| # | Objetivo | Métrica | Prazo |
|---|---|---|---|
| O1 | Publicar uma edição completa em menos de 2 minutos | tempo total em `logs/jornal.log` | 17/09/2026 |
| O2 | Monitorar uma lista curta e estável de títulos entre execuções | `SELECT COUNT(DISTINCT appid) FROM snapshots` | 17/09/2026 |
| O3 | Entregar briefing em áudio com menos de 2 minutos de duração | duração dos `.wav` em `audio/` | 17/09/2026 |
| O4 | Operar com custo recorrente de R$ 0,00 | ausência de credenciais no código | 17/09/2026 |
| O5 | Não repetir uma notícia já publicada | tabela `noticias_publicadas` | 17/09/2026 |
| O6 | Executar todas as etapas a partir de um único ponto de entrada | `Radar VR.cmd` | 17/09/2026 |

## 4. Escopo

**Incluído**

- Coleta de cinco rotas públicas da Steam Web API
- Série temporal própria em SQLite
- Redação das chamadas por LLM local
- Síntese de voz em português
- Publicação em áudio, página HTML, planilha e banco
- Painel operacional e agendamento via n8n

**Excluído**

- Compra automatizada, já que a decisão continua sendo humana
- Integração com a loja da Meta Quest, que não possui API pública
- Aplicação web, empacotamento ou distribuição pra terceiros
- Dados históricos anteriores à primeira execução, que não existem em fonte pública

## 5. Papéis

O trabalho é individual, então as funções abaixo são acumuladas pela mesma
pessoa. Elas ficam declaradas pra delimitar responsabilidades em cada etapa.

| Papel | Responsabilidade | Entregável |
|---|---|---|
| Analista | Levantamento de dados, causas e consequências | Diagnóstico |
| Gerente de projeto | Objetivos, escopo, riscos | Canvas |
| Engenheiro de ambiente | Instalação e validação da stack | Ambiente |
| Desenvolvedor | Implementação dos módulos | `src/` |
| QA | Execução ponta a ponta e coleta de evidências | `evidencias/` |

## 6. Entregáveis

| Etapa | Entregável | Arquivo |
|---|---|---|
| E1 | Levantamento de dados do catálogo | `src/levantamento.py` |
| E2 | Diagnóstico | `docs/01_diagnostico.md` |
| E3 | Canvas | `docs/02_canvas.md` |
| E4 | Ambiente configurado | `setup.ps1`, `docs/04_ambiente.md` |
| E5 | Pipeline | `src/` |
| E6 | Painel operacional | `src/painel.py` |
| E7 | Fluxo de agendamento | `n8n/fluxo_radar_vr.json` |
| E8 | Coleção de requisições | `postman/colecao_radar_vr.json` |
| E9 | Evidências de execução | `evidencias/` |

## 7. Riscos

Escala: P = probabilidade, I = impacto (1 baixo, 3 alto).

| # | Risco | P | I | P×I | Mitigação | Contingência |
|---|---|:-:|:-:|:-:|---|---|
| R1 | Voz PT-BR indisponível por ausência do phonemizer | 2 | 2 | 4 | `espeak-ng` instalado por `setup.ps1` | Recaída automática pra voz em inglês, já implementada em `voz.py` |
| R2 | Steam bloquear requisições por volume | 2 | 3 | 6 | Intervalo de 1,2 s entre chamadas e `User-Agent` identificado | Reduzir `TAM_WATCHLIST`. Os dados já coletados permanecem no banco |
| R3 | LLM devolver JSON malformado | 2 | 2 | 4 | `format: json` na chamada e extração por expressão regular | Chamada montada por regra substitui a do modelo |
| R4 | Alteração na página da loja quebrar a leitura do prazo de promoção | 3 | 1 | 3 | Função isolada, com falha silenciosa | O boletim deixa de anunciar o prazo e nenhuma outra etapa é afetada |
| R5 | VRAM insuficiente pro modelo | 1 | 3 | 3 | 16 GB comportam 8B quantizado com folga | Ollama recai pra CPU |
| R6 | Primeira edição sem base de comparação | 3 | 1 | 3 | Condição declarada no próprio boletim e na página | As variações passam a ser reportadas a partir da segunda edição |

## 8. Critérios de sucesso

1. `src/jornal.py` conclui as quatro etapas com código de saída 0
2. Existe `.wav` com a narração e `boletim_atual.html` com os links da loja
3. `jornal_vr.csv` abre em planilha, com uma linha por manchete
4. `jornal_vr.db` acumula snapshots entre execuções
5. Um anúncio já publicado não reaparece na edição seguinte
6. O fluxo n8n executa com todos os nós em `success`
7. Nenhuma credencial paga aparece no código

## 9. Recursos

| Recurso | Especificação | Custo |
|---|---|---|
| Hardware | Ryzen 7 5700X, 32 GB de RAM, RTX 5060 Ti de 16 GB | já disponível |
| LLM | Ollama com llama3.1:8b | R$ 0,00 |
| TTS | Kokoro ONNX 82M | R$ 0,00 |
| Dados | Steam Web API | R$ 0,00 |
| Orquestração | n8n self-hosted | R$ 0,00 |
| Persistência | SQLite e CSV | R$ 0,00 |
