# Testes de carga e de falha

**Projeto:** Radar VR
**Disciplina:** AI Factory, Etapa 2 (PUCPR)

---

## 1. Método

`testes/estresse.py` sobe o microsserviço em processo próprio para cada
cenário, com `RADAR_DRY_RUN=1` e banco separado (`data/estresse.db`). Nenhuma
mensagem real sai da máquina, e os assinantes sintéticos usam endereços
`@exemplo.invalid`.

```
python testes/estresse.py                  todos os cenários
python testes/estresse.py personalizacao   um cenário
```

Os números brutos ficam em `evidencias/estresse.json`.

**Ambiente:** Windows 11, RTX 5060 Ti 16 GB, `llama3.1:8b` no Ollama, Python
3.11, Wi-Fi residencial. Medições de 17/10/2026.

**Assinantes sintéticos:** interesses combinados a partir do catálogo real
(3 pares de gêneros × 3 trios de jogos = 9 perfis distintos de interesse),
repetidos como numa base real, em que muita gente segue os mesmos jogos.

## 2. Linha de base

Tempo por etapa da edição, medido pelo próprio pipeline (`tempos` em
`/edicao`):

| Etapa | Etapa 1 (sequencial) | Etapa 2 |
|---|---:|---:|
| Coleta na Steam | 48 s | 20,9 s |
| Histórico de preços (ITAD) | não havia | 1,9 s |
| Detecção de eventos | < 0,1 s | < 0,1 s |
| Redação pelo LLM | 44 s | 3,8 s |
| Narração (Kokoro) | 18 s | 9,8 s |
| **Total** | **1 min 50 s** | **36,4 s** |

Redação e narração variam com o número de manchetes: a primeira edição da
Etapa 1 tinha 6 anúncios para resumir; a edição medida na Etapa 2, 2. A
comparação justa da coleta está no item 3.1.

## 3. Gargalos e melhorias

Cada melhoria foi feita depois da medição que a justifica, e medida de novo
nas mesmas condições.

### 3.1 Coleta sequencial

A coleta fazia uma requisição de cada vez, com pausa fixa de 1,2 s antes de
cada ficha de jogo, para respeitar o limite da Steam.

**Mudança:** quatro coletas em paralelo, com um ritmo compartilhado entre
elas. A pausa de 1,2 s continua valendo, agora entre quaisquer duas fichas,
de qualquer thread. Paralelizar sem coordenar o ritmo só anteciparia o
bloqueio por IP.

| 15 títulos, 3 execuções | Execuções | Mediana |
|---|---|---:|
| Sequencial | 29,4 · 29,8 · 30,0 s | 29,8 s |
| 4 em paralelo | 19,5 · 19,3 · 19,3 s | **19,3 s** (−35%) |

O piso teórico é 15 × 1,2 s = 18 s, imposto pelo ritmo. A coleta já está a
1,3 s dele; ir além exigiria pedir mais da Steam do que é prudente.

Numa das medições, um único pedido à Steam levou 14 s para responder e segurou
a coleta inteira (33,5 s), enquanto os outros 14 títulos terminaram em 20 s.
Latência de cauda é o próximo ponto: um timeout menor por requisição, com uma
nova tentativa, limitaria o atraso.

### 3.2 Banco de dados no caminho do envio

O primeiro teste de vazão mostrou p95 de 238 ms com um único cliente, para
uma operação que, em DRY_RUN, não faz rede. O caminho da requisição apontou o SQLite: cada
envio abria uma conexão e reaplicava o esquema, duas vezes (reserva e
conclusão).

**Mudança:** conexão única por processo, protegida pela mesma trava que já
garantia a atomicidade da reserva, esquema aplicado uma vez e modo WAL.

500 requisições a `POST /enviar/email`:

| Concorrência | Antes | Depois | p95 antes | p95 depois |
|---:|---:|---:|---:|---:|
| 1 | 28,6 req/s | **185,0 req/s** | 238,0 ms | 22,6 ms |
| 10 | 46,7 req/s | **822,7 req/s** | 393,3 ms | 16,5 ms |
| 50 | 131,9 req/s | **781,9 req/s** | 419,7 ms | 80,4 ms |

Nenhum erro em 3.000 requisições. Acima de 10 clientes a vazão estabiliza: a
trava serializa a reserva, por projeto, para que dois pedidos iguais não
passem juntos pela verificação.

### 3.3 Rede: IPv6 até o Telegram

O primeiro envio real ao Telegram levou 21 s. O DNS devolve endereço IPv6 e
IPv4; a rota IPv6 desta rede não responde, e cada conexão nova esperava o
timeout antes de tentar IPv4.

**Mudança:** preferência por IPv4 (`RADAR_FORCAR_IPV4`, ligada por padrão) e
sessão HTTP persistente entre envios.

| 3 conexões novas a api.telegram.org | Tempos |
|---|---|
| Com IPv6 | 23.065 · 44.038 · 44.022 ms |
| Somente IPv4 | **1.757 · 1.855 · 1.922 ms** |

Steam, ITAD e Meta não apresentaram o problema (medido: 0,3 a 0,9 s com ou
sem IPv6). A correção fica configurável porque depende da rede.

### 3.4 LLM na personalização

O modelo local atende uma requisição por vez, e cada assinante custava uma
chamada de 1,6 a 2,4 s. A personalização crescia linearmente com a base.

Assinantes com os mesmos interesses recebem os mesmos fatos, e o texto gerado
para um serve para todos. O nome entra depois, fora do texto do modelo.

**Mudança:** cache do texto gerado, com chave no conteúdo enviado ao modelo
(gêneros, fatos e urgências, sem dado pessoal), e montagem dos envelopes em
paralelo.

| Assinantes | Antes | Depois | Chamadas ao LLM (antes → depois) |
|---:|---:|---:|---:|
| 10 | 23,5 s | 14,1 s | 10 → 9 |
| 50 | 83,9 s | 19,3 s | 50 → 12 |
| 100 | 164,2 s | **19,8 s** | 100 → 12 |

Com 100 assinantes, a vazão foi de 0,61 para 5,06 assinantes por segundo. O
custo passa a depender do número de combinações distintas de interesse, e não
do número de assinantes.

### 3.5 LLM fora do ar

Com o Ollama desligado, todo assinante recebe o boletim com o texto padrão. O
primeiro teste levou 10,2 s para 20 assinantes: cada um esperava a conexão
ser recusada (no Windows, cerca de 2 s).

**Mudança:** disjuntor. Na primeira recusa de conexão, as chamadas seguintes
falham na hora durante 60 s.

| 20 assinantes, Ollama desligado | Tempo | Envelopes válidos |
|---|---:|---:|
| Antes | 10,2 s | 20 de 20 |
| Depois | **2,1 s** | 20 de 20 |

## 4. Falhas e proteções

| Cenário | Resultado esperado | Resultado |
|---|---|---|
| 50 pedidos simultâneos idênticos de envio | 1 envio, 49 bloqueados | 1 `simulado`, 49 `duplicado` |
| Canal instantâneo fora do ar | 502 com o motivo; n8n desvia para e-mail | 502; contingência executada |
| Microsserviço fora do ar | n8n registra e encerra com erro | `logs/n8n_falhas.log`, execução com erro |
| Corpo sem campos obrigatórios | 400 com a lista | 400: `edicao_id, para, assunto, html` |
| Anexo `../../.env` | nenhum arquivo fora de `audio/` | só o nome é usado; arquivo inexistente, nada anexado |
| LLM cita número que não está nos fatos | texto descartado | frase padrão (verificação em `personalizacao._confere`) |

Os cenários do n8n estão em [docs/05_n8n.md](05_n8n.md#5-evidências).

## 5. Leitura crítica

**O que ainda limita.** O modelo local continua sendo o recurso mais caro.
O cache funciona porque interesses se repetem; numa base com interesses muito
diversos, ele rende menos. O próximo passo seria agrupar os assinantes por
assinatura de interesse antes de chamar o modelo, e não depois, o que também
eliminaria chamadas concorrentes para a mesma chave.

**O que não deve melhorar.** A coleta está perto do piso de 18 s por escolha:
o ritmo protege o acesso à Steam, que é a fonte de tudo. Para cobrir mais
títulos, o caminho é cache entre edições de dados que mudam pouco (gêneros,
descrição), e não mais pressa.

**O que os números não cobrem.** Os testes de vazão usam DRY_RUN; o envio
real é limitado pelos provedores: o Gmail aceita cerca de 500 e-mails por dia
por conta, e o Telegram, 30 mensagens por segundo por bot. Para a base de
assinantes atual, nenhum dos dois é gargalo. Para um serviço público, o
e-mail precisaria de um provedor transacional.

**Onde a medição mudou a decisão.** Duas das cinco melhorias (banco e IPv6)
não estavam no plano: apareceram nos números. O banco, em especial, parecia
irrelevante ao lado de rede e LLM, e era o que mais limitava a vazão do envio.
