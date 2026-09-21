# Diagnóstico

**Projeto:** Radar VR
**Autor:** Rafael Probst
**Disciplina:** AI Factory, Etapa 1 (PUCPR)
**Data:** 21/09/2026

---

## 1. Contexto

Uso realidade virtual como hobby. Tenho um Meta Quest 3 que rodo em modo PC VR,
o que significa que o headset consome a biblioteca da **Steam** e não a loja da
Meta. Como qualquer pessoa com um hobby, eu acompanho um punhado de jogos, não
o catálogo inteiro. São os que já jogo, os que pretendo jogar e alguns que
estão sempre no radar.

## 2. O problema

> A loja mostra **estado**. O que falta é **mudança**.

A página de um jogo informa quanto ele custa agora e quantas pessoas estão
jogando agora. Não informa o que aconteceu desde a última vez que eu olhei.

Das três coisas que eu de fato quero saber sobre um jogo que acompanho, a loja
entrega uma, e mal:

| O que eu quero saber | A loja mostra? |
|---|---|
| Entrou em promoção? | Sim, e a página até informa quando termina, mas só se eu abrir a página |
| Recebeu atualização relevante? | O anúncio existe, mas fica enterrado na página do jogo |
| Está ganhando ou perdendo jogadores? | Mostra o número de agora, sem nada pra comparar |

Repare que a loja não esconde nada. Ela simplesmente exige que eu vá buscar,
jogo por jogo, e não guarda nada do que eu vi da última vez.

Na prática, a única forma de descobrir o que mudou é abrir a página de cada
jogo, um por um, e tentar lembrar como estava antes. Ninguém faz isso.

## 3. Dados

Medições feitas com `src/levantamento.py` e com o próprio pipeline, sobre os 15
títulos que acompanho. A saída bruta do levantamento está em
[`data/levantamento_diagnostico.json`](../data/levantamento_diagnostico.json).

### 3.1 O que passa despercebido

Na semana de 15 a 21/09, entre os títulos monitorados:

| Título | Anúncios do desenvolvedor | Mais recente |
|---|:-:|---|
| Half-Life: Alyx | 2 | há 4 dias |
| VTOL VR | 2 | há 3 dias |
| UNDERDOGS | 1 | há 5 dias |
| Walkabout Mini Golf VR | 1 | há 7 dias |

Quatro títulos com novidade, entre quinze. Nenhum deles aparece na vitrine da
loja: pra encontrar esses quatro eu teria que abrir as quinze páginas e rolar
até a seção de anúncios de cada uma.

### 3.2 Por que a lista é curta

Monitorar o catálogo inteiro não traria mais notícia, traria mais ruído. Numa
amostra de 50 jogos VR em promoção, medida em 21/09:

| Jogadores simultâneos | Jogos | % |
|---|:-:|:-:|
| Nenhum | 37 | 74 % |
| 1 a 9 | 12 | 24 % |
| 50 a 199 | 1 | 2 % |

Três em cada quatro não tinham ninguém jogando. Acompanhar esses títulos
geraria movimentação sem significado, e nenhum deles chegaria perto do limiar
mínimo que o sistema exige pra considerar variação relevante.

### 3.3 Escala do catálogo, como contexto

Pra dimensionar: a Steam tem **5.693** jogos com suporte a VR. Em 17/09 havia
770 em promoção; em 21/09, com o fim da liquidação, sobraram 71. Esses números
não são o problema em si, já que ninguém acompanha um catálogo desse tamanho.
Eles só mostram que a informação relevante está diluída em muito volume.

## 4. Causas

### 4.1 Cinco Porquês

| # | Pergunta | Resposta |
|---|---|---|
| 1 | Por que eu não sei o que mudou nos jogos que acompanho? | Porque teria que abrir a página de cada um pra descobrir. |
| 2 | Por que abrir as páginas não resolve? | Porque a página mostra o estado de agora. Sem o valor anterior, um número não significa nada. |
| 3 | Por que a loja não mostra o valor anterior? | Ela é otimizada pra conversão. Mostrar que o preço já foi menor desestimula a compra de hoje. |
| 4 | Por que eu não guardo esses valores por conta própria? | Guardar à mão exigiria anotar preço e jogadores de cada jogo, todo dia, sem falhar. |
| 5 | Por que ninguém já resolveu isso? | O SteamDB acompanha parte disso, mas não oferece API pública pra reutilizar os dados: `steamdb.info/api/` responde 403. E ele também não recebe a série pronta da Valve, precisa construí-la ao longo do tempo, da mesma forma que este projeto faz em escala menor. |

**Causa raiz:** a informação temporal não existe pronta em nenhuma fonte
acessível. Ela precisa ser construída por acumulação, uma leitura por vez.

### 4.2 Ishikawa

| Categoria | Causa |
|---|---|
| Método | Verificação manual, jogo a jogo, sem registro entre uma visita e outra |
| Medição | Nenhuma métrica comparável ao longo do tempo |
| Material | Anúncios existem, mas ficam enterrados na página de cada jogo |
| Máquina | Vitrine otimizada pra conversão, não pra acompanhamento |
| Mão de obra | Um único usuário, em tempo de lazer |
| Meio ambiente | Promoções com janela curta e prazo que a API não expõe |

## 5. Consequências

A mais direta é simplesmente **não ficar sabendo**. Um jogo que você comprou
recebe uma atualização grande e você descobre semanas depois, por acaso. Foi o
que aconteceu com quatro dos quinze títulos só nesta semana.

Nas promoções, a decisão acontece sem referência. O desconto exibido é
calculado sobre o preço cheio e nunca sobre o histórico real, então não há como
distinguir uma oferta relevante de um desconto rotineiro. O prazo de término
existe na página do jogo, mas nenhuma rota JSON o expõe, o que significa que
saber quanto tempo resta exige abrir cada página de novo.

A alternativa manual custa mais do que o hobby justifica. Acompanhar quinze
jogos exigiria abrir quinze páginas, todo dia, e ainda anotar os números pra
poder comparar depois.

## 6. Oportunidades

| # | Oportunidade | Justificativa técnica |
|---|---|---|
| 1 | Coleta programática de cinco rotas públicas da Steam | Nenhuma delas exige chave de autenticação, e todas retornam preço em BRL e texto em português |
| 2 | Série temporal própria em SQLite | É a única forma de obter variação, já que a informação não existe em fonte externa acessível |
| 3 | Lista curta e estável de títulos | Acompanhar poucos jogos relevantes produz notícia. Acompanhar o catálogo inteiro produziria ruído, como mostra a seção 3.2 |
| 4 | Classificação por LLM local | Um modelo local tem custo marginal zero e não impõe limite de requisições, e a RTX 5060 Ti de 16 GB comporta um modelo de 8B inteiro em VRAM |
| 5 | Decisão por regra determinística | Afirmações com número precisam ser auditáveis e consistentes entre execuções, então o LLM fica restrito a resumir texto livre |
| 6 | Saída em áudio e em página | O consumo acontece com o headset em uso, onde ler texto é desconfortável. A página resolve o nome próprio e leva à loja por link |

## 7. Situação-alvo

| Dimensão | Atual | Alvo |
|---|---|---|
| Descobrir uma atualização | por acaso, semanas depois | no dia seguinte, no boletim |
| Movimentação de jogadores | invisível | comparada com a leitura anterior |
| Prazo de promoção | não exibido em API | avisado com antecedência |
| Esforço por dia | abrir quinze páginas | um clique |
| Consumo | texto, fora do headset | áudio de um minuto, e página pra consultar |
| Histórico | inexistente | série acumulada |

---

**Fonte:** Steam Web API, acesso público sem autenticação. Levantamento de
catálogo em 17/09/2026, medições de anúncios e jogadores em 21/09/2026.
