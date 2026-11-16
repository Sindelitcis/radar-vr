# Ética, privacidade e conformidade

**Projeto:** Radar VR
**Disciplina:** AI Factory, Etapa Final (PUCPR)

---

## 1. Situação

Hoje o Radar VR tem dois perfis de assinante, e os dois são do autor. A LGPD
não se aplica ao tratamento feito por pessoa natural para fins exclusivamente
particulares e não econômicos (art. 4º, I). No dia em que outra pessoa se
inscrever, o operador passa a ser o controlador dos dados dela (art. 5º, VI).
Este documento foi escrito para esse cenário, antes de ele acontecer.

## 2. Dados pessoais, campo a campo

| Campo em `perfis.json` | Para que serve | É indispensável? |
|---|---|---|
| `id` (apelido) | identifica o perfil nos registros, no lugar do contato | sim; funciona como pseudônimo |
| `nome` | saudação do e-mail | não; opcional desde a etapa final |
| `email` | entregar o boletim | sim |
| `instantaneo` (chat do Telegram) | entregar o alerta urgente | só para quem quer o alerta |
| `jogos`, `generos` | escolher o que enviar | sim; é o próprio serviço |
| `orcamento` | só tratar como urgente a oferta que cabe no orçamento | não; opcional |
| `consentimento` (data) | comprovar a inscrição e mostrá-la no e-mail | sim; perfil sem data é ignorado |

O serviço não pede CPF, endereço, idade, telefone, conta da Steam nem dado de
pagamento, e não trata dado pessoal sensível (art. 5º, II).

Os dados da Steam e do IsThereAnyDeal são de catálogo. A exceção é a rota de
avaliações (`IUserReviewsService/GetAppReviews`), que devolve ao menos uma
avaliação com o identificador do autor. `coleta.buscar_avaliacoes` lê só os
totais e descarta o resto, sem gravar.

### Por onde os dados passam

| Onde | O que fica | Cuidado |
|---|---|---|
| `perfis.json` | os perfis completos | fora do Git; arquivo em texto simples |
| `logs/auditoria.jsonl`, `logs/jornal.log` | apelido e contato mascarado (`ra***@gmail.com`) | fora do Git |
| Tabela `envios` do SQLite | apelido, canal, edição e resultado | fora do Git |
| `evidencias/metricas_execucoes.jsonl` | canal, resultado e latência de cada envio | versionado; sem contato nem apelido |
| Ollama e Kokoro | texto público dos anúncios e roteiro do boletim | rodam no computador; não recebem dado de assinante |
| Gmail | endereço e conteúdo do boletim | serviço externo |
| Telegram | identificador do chat e texto do alerta | serviço externo |

## 3. LGPD, princípio por princípio

| Princípio | Como é atendido | Lacuna e ação antes de abrir o serviço |
|---|---|---|
| Finalidade (art. 6º, I) | os dados servem só para avisar o que mudou nos jogos escolhidos; sem publicidade, venda de dados ou link de afiliado próprio | escrever a finalidade no formulário de inscrição, em uma frase |
| Necessidade (art. 6º, III) | sete campos, três opcionais; contato mascarado nos registros | os registros crescem sem prazo: apagar envios com mais de 90 dias e o perfil em até 7 dias após o cancelamento (arts. 15 e 16) |
| Transparência (art. 6º, VI; art. 9º) | o e-mail mostra a data da inscrição, como sair, a fonte dos preços e o uso de IA | publicar um aviso de privacidade curto |
| Segurança (art. 6º, VII; art. 46) | credenciais em variáveis de ambiente; perfis fora do Git; serviço só em `127.0.0.1`; contato mascarado | criptografar o arquivo de perfis; trocar senhas e chaves a cada semestre; revisar os registros |
| Não discriminação (art. 6º, IX) | o sistema não classifica pessoas; a personalização usa só o que o assinante declarou | nenhuma lacuna encontrada |
| Consentimento (art. 7º, I; art. 8º) | perfil sem data de consentimento é ignorado; o Telegram só entrega a quem iniciou a conversa; para sair, basta responder SAIR | a inscrição e o cancelamento são manuais: formulário com confirmação por e-mail e link de cancelamento que funcione sozinho |
| Direitos do titular (art. 18) | acesso, correção e exclusão por resposta ao e-mail | painel do assinante |
| Transferência internacional (art. 33) | Gmail e Telegram têm servidores fora do Brasil; vão só endereço, chat e conteúdo do boletim | informar no aviso de privacidade; em um serviço público, usar provedor com contrato de tratamento de dados |
| Incidentes (art. 48) | os registros mostram o que foi enviado, para qual perfil e quando | escrever o plano de resposta, com aviso aos assinantes e comunicação à ANPD (Resolução CD/ANPD nº 15/2024) |

Como pessoa natural que trata poucos dados e sem alto risco, o projeto se
enquadra como agente de tratamento de pequeno porte (Resolução CD/ANPD nº
2/2022): fica dispensado de indicar encarregado, mas mantém um canal de
comunicação com o titular, que é a resposta ao e-mail. A proposta é restringir
a inscrição a maiores de 18 anos (art. 14).

## 4. IA responsável

| Diretriz | Situação | Evidência ou ação |
|---|---|---|
| Robustez | na Etapa 2 o modelo escrevia o assunto dos e-mails e inventou detalhes; saiu dessa função | o modelo só resume anúncios; números e urgência vêm de regra; ação: link do anúncio original no cartão |
| Transparência | o assinante não era avisado do uso de IA | corrigido: aviso no e-mail (`personalizacao.AVISO_IA`) e na página do boletim |
| Supervisão humana | o boletim sai sem revisão; conteúdo de baixo risco, e a compra é decisão do assinante | ler uma amostra de edições por semana; aceitar a resposta "ERRO" |
| Justiça | a lista padrão favorece os jogos com mais avaliações | os jogos seguidos por cada assinante entram na lista |
| Responsabilização | operador identificado, trilha de auditoria e aviso de falha | falta avisar quando a edição sai incompleta ([08_metricas.md](08_metricas.md)) |
| Voz sintética | voz pronta do Kokoro; o projeto não clona a voz de ninguém | a página do boletim identifica a narração como voz sintética |

## 5. Riscos e mitigação

| Risco | Mitigação existente | Proposta |
|---|---|---|
| Envio em massa por erro | um envio por assinante, canal e edição, testado com 50 pedidos simultâneos; testes em ensaio | – |
| Vazamento dos perfis | arquivo fora do Git; contato mascarado | criptografia; retenção de 90 dias |
| Informação errada | preço e recorde por regra, com link para o histórico | aviso de edição incompleta |
| Dependência de plataformas | cada fonte e cada canal falham sem derrubar o resto | teste diário das rotas |
| Uso das fontes fora dos termos | intervalo de 1,2 s entre as fichas dos jogos, `User-Agent` identificado, crédito ao IsThereAnyDeal; SteamDB e APIs não oficiais de WhatsApp descartados | trocar a leitura do prazo de promoção por rota oficial, quando existir |
| Mensagem indesejada | nada é enviado sem novidade; cada fato é avisado uma vez; alerta só com urgência real | cancelamento automático |

## 6. Implicações sociais

- **Consumo.** Um aviso de promoção acabando também empurra para a compra. O
  serviço só avisa sobre jogos que a pessoa escolheu, respeita o orçamento
  dela e não recomenda nada. Mostrar o menor preço da história permite ver
  que um desconto é comum, e esperar.
- **Acesso à informação.** O serviço entrega de graça o que a loja não
  organiza. O áudio ajuda quem está com o visor no rosto.
- **Privacidade por construção.** A IA roda no computador do operador; só o
  canal de entrega é externo.
- **Confiança.** O maior dano possível é de confiança. Por isso o aviso de
  edição incompleta e o cancelamento automático vêm antes de abrir o serviço.

## 7. Rotina de revisão

| Quando | O quê |
|---|---|
| A cada semestre | trocar senhas e chaves; conferir as variáveis de ambiente |
| Todo mês | ler os registros em busca de falha ou acesso fora do padrão |
| A cada mudança no cadastro | perguntar se o campo é mesmo necessário |
| A cada mudança | registrar aqui o que mudou e por quê |

### Mudanças

| Data | Mudança | Motivo |
|---|---|---|
| 11/2026 | `nome` passou a ser opcional | minimização: o campo só servia à saudação |
| 11/2026 | aviso de uso de IA no e-mail e na página | transparência |
| 11/2026 | a leitura de avaliações descarta os dados do autor | a rota nova da Steam devolve dado de pessoa |
| 11/2026 | o registro de medições não guarda contato nem apelido | o arquivo é versionado e público |
