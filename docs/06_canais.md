# Microsserviço e canais

**Projeto:** Radar VR
**Disciplina:** AI Factory, Etapa 2 (PUCPR)

---

## 1. Visão geral

A Etapa 1 entregava um boletim único, igual para todos, aberto pelo próprio
usuário. A Etapa 2 inverte a direção: o boletim vai até cada assinante, com o
recorte do que ele acompanha, pelo canal adequado à urgência do fato.

```
                 ┌─────────────────────── n8n ────────────────────────┐
 agendamento ──► │ Gerar edição ─► Personalizar ─► E-mail ─► Urgente? │
                 │      │               │            │          │     │
                 │      ▼               ▼            ▼          ▼     │
                 │  log local       log local    /falha    Telegram   │
                 │  + interrompe    + interrompe              │ falhou│
                 │                                            ▼       │
                 │                                 alerta por e-mail  │
                 └────────────────────────────────────────────────────┘
                        │ HTTP (127.0.0.1:8765)
                 ┌──────▼────────── microsserviço Python ─────────────┐
                 │ Steam + ITAD → eventos → LLM → voz → personalização │
                 │ envio (SMTP, Telegram, WhatsApp) + auditoria       │
                 └────────────────────────────────────────────────────┘
```

O n8n orquestra; a regra de negócio fica em Python, num único lugar. Cada
canal é uma rota HTTP separada, o que permite ao fluxo tratar a falha de um
canal sem afetar os outros.

## 2. Rotas

| Rota | Função |
|---|---|
| `GET /saude` | estado do Ollama, do ITAD, de cada canal e do modo de teste |
| `POST /edicao` | gera a edição do dia; `{"reaproveitar": true}` devolve a atual |
| `GET /edicao/atual` | última edição publicada, completa |
| `POST /personalizar` | um envelope por assinante com novidade relevante |
| `POST /enviar/email` | envia o boletim personalizado, com a narração anexa |
| `POST /enviar/instantaneo` | envia o alerta por Telegram ou WhatsApp |
| `POST /falha` | registra falha vinda do n8n e avisa o operador por e-mail |
| `GET /metricas` | chamadas ao LLM, acertos de cache, textos pela regra |

Envio que falha responde **502** com o resultado no corpo. Para o n8n, isso é
erro, e o item segue pela saída de erro do nó, que leva à contingência.

## 3. Personalização

Cada assinante declara jogos seguidos, gêneros, orçamento e o canal
instantâneo (`perfis.json`, fora do Git; modelo em `perfis.exemplo.json`).

| Decisão | Quem decide | Critério |
|---|---|---|
| O que entra | regra | evento de jogo seguido ou de gênero de interesse |
| Urgência | regra | menor preço da história, ou promoção que acaba em até 2 dias, dentro do orçamento |
| Canal | regra | e-mail sempre que há fato relevante; alerta instantâneo só com urgência |
| Texto | LLM | assunto, abertura e alerta, a partir dos fatos já apurados |

O mesmo princípio da Etapa 1: **a regra apura, o modelo redige.** Canal e
urgência precisam ser explicáveis e reproduzíveis.

O texto do modelo passa por uma conferência antes de sair: todo número
presente no texto gerado precisa constar nos fatos de entrada. Se o modelo
inventar ou arredondar um preço, o texto é descartado e entra a frase padrão.

Os jogos seguidos pelos assinantes entram na watchlist mesmo fora dos 15 mais
avaliados. A edição passa a cobrir o que a base de assinantes de fato
acompanha.

## 4. Histórico de preços (IsThereAnyDeal)

A Steam informa só o preço de agora. Para dizer "menor preço da história", a
Etapa 1 precisava acumular cinco edições. Com a API do IsThereAnyDeal, a
afirmação vale desde a primeira execução, com anos de histórico de várias
lojas.

| Chamada | Uso | Cache |
|---|---|---|
| `/lookup/id/shop/61/v1` | appid da Steam → id do ITAD, em lote | permanente |
| `/games/overview/v2` | preço atual e menor histórico, em lote | 6 horas |

São duas requisições por edição, independente do tamanho da watchlist. O
limite da API é de 1.000 requisições a cada 5 minutos.

Os termos de uso exigem crédito à fonte e proíbem alterar dados ou links:
o e-mail cita o IsThereAnyDeal no rodapé e repassa o link do histórico como
veio. O SteamDB foi descartado: não oferece API, e coletar a página violaria
os termos do site.

## 5. Canais

| Canal | Papel | Integração |
|---|---|---|
| E-mail | boletim completo, com narração anexa | SMTP do Gmail, senha de app |
| Telegram | alerta urgente | Bot API, `@radar_vr_boletim_bot` |
| WhatsApp | alerta urgente (alternativo) | WhatsApp Cloud API, oficial da Meta |

O alerta instantâneo remete ao e-mail ("boletim completo no seu e-mail:
*assunto*"). Se o e-mail falhou, o n8n informa o status ao enviar o alerta, e
a referência é retirada do texto.

### WhatsApp

A integração com a Cloud API está implementada e foi validada até o aceite da
mensagem pela Meta (app, número de teste, token e destinatário verificado). A
entrega, porém, é recusada pela Meta com o erro **130497**: desde setembro de
2025 a Meta bloqueia envio de remetentes de fora do Brasil para números
+55, como medida contra golpes. O número de teste da Meta é americano, e o
mesmo vale para os sandboxes de Twilio e Zenvia. O retorno da Meta está em
`evidencias/whatsapp_130497.json`.

O único caminho oficial é um número brasileiro dedicado ao remetente, que não
esteja em uso no WhatsApp. APIs não oficiais (Baileys, Evolution, Z-API)
foram descartadas: violam os termos do WhatsApp e expõem o número pessoal a
bloqueio.

O Telegram assume o papel de canal instantâneo. Para o produto, ele também é a
escolha certa: a API é gratuita e ilimitada, enquanto no WhatsApp cada
mensagem iniciada pela empresa é cobrada. Trocar de canal é editar
`instantaneo.canal` no perfil, sem mudar código.

## 6. Tratamento de erros

| Falha | Tratamento |
|---|---|
| SMTP, Telegram ou WhatsApp instável | até 3 tentativas com espera exponencial (1,5 s, 3 s) |
| Título da Steam sem resposta | título ignorado, edição segue com os demais |
| Credencial inválida, destinatário recusado | falha definitiva, sem nova tentativa |
| ITAD fora do ar | edição segue sem histórico de preços |
| Ollama fora do ar | texto pela regra; disjuntor evita esperar o timeout a cada assinante |
| LLM inventa número | texto descartado, frase padrão |
| Canal instantâneo falha | n8n desvia o alerta para o e-mail |
| E-mail falha | n8n registra em `/falha`, que avisa o operador |
| Microsserviço fora do ar | n8n tenta de novo, grava `logs/n8n_falhas.log` e encerra com erro |
| Falha em execução agendada | fluxo "Tratamento de falhas" (Error Trigger) registra e avisa |
| Repetição do mesmo envio | bloqueada: um envio por assinante, canal e edição |
| Corpo inválido | 400 com os campos ausentes |
| Anexo com caminho arbitrário | só o nome do arquivo é usado, dentro de `audio/` |

## 7. Registros

| Arquivo | Conteúdo |
|---|---|
| `logs/jornal.log` | etapas do pipeline e acesso às rotas, legível |
| `logs/auditoria.jsonl` | uma linha JSON por decisão e por envio |
| `logs/n8n_falhas.log` | falhas registradas pelo próprio n8n |

Exemplo de linha da auditoria:

```json
{"ts": "2026-10-17T08:15:14.020", "evento": "envio", "edicao_id": "2026-10-17T08-14-29",
 "perfil": "rafael", "destino": "***2136", "canal": "telegram", "status": "enviado",
 "tentativas": 1, "latencia_ms": 1023, "erro": "", "id": "4"}
```

Contatos aparecem mascarados. O log serve para depurar, não para guardar dado
pessoal.

## 8. Variáveis de ambiente

Toda credencial e todo parâmetro operacional vêm do ambiente ou do `.env`
(modelo em `.env.example`). Nenhum valor sensível está no código ou nos
fluxos do n8n, que leem `RADAR_SERVICO_URL` e `RADAR_DIR_LOGS` por `$env`.

| Variável | Efeito |
|---|---|
| `RADAR_DRY_RUN` | nenhuma mensagem sai da máquina; usado nos testes de carga |
| `RADAR_FALHAR_CANAIS` | força falha de um canal para exercitar a contingência |
| `RADAR_COLETA_PARALELA` | coletas simultâneas na Steam |
| `RADAR_PERSONALIZACAO_PARALELA` | assinantes processados em paralelo |
| `RADAR_CACHE_REDACAO` | reaproveita o texto entre assinantes de mesmo interesse |
| `RADAR_FORCAR_IPV4` | evita o timeout de IPv6 até a API do Telegram |
| `RADAR_REAPROVEITAR_EDICAO` | no n8n, reenvia a edição atual sem gerar outra |

## 9. Dados pessoais e envio responsável

- O assinante só é processado com data de consentimento registrada no perfil.
- O Telegram só entrega a quem iniciou conversa com o bot.
- Cada e-mail informa a data de inscrição e como sair.
- Nenhum envio repete para o mesmo assinante, canal e edição.
- Só há alerta instantâneo com urgência real; sem novidade, nada é enviado.
- Testes de carga usam DRY_RUN e endereços `@exemplo.invalid`.
