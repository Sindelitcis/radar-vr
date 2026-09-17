# Diagnóstico

**Radar VR** · Rafael Probst · AI Factory — Etapa 1 · PUCPR · 17/09/2026

---

## 1. Contexto

Uso realidade virtual como hobby, com um Meta Quest 3 em modo PC VR — o headset
consome a biblioteca da **Steam**, não a loja da Meta. O ciclo é recorrente: a
cada poucos dias abro a loja para verificar se algo mudou.

## 2. O problema

> A loja mostra **estado**. O que falta é **mudança**.

A página de um jogo informa o preço de agora, os jogadores de agora e a
aprovação acumulada. Não informa o que interessa a quem já conhece o catálogo:

- entrou em promoção hoje, ou já estava assim há duas semanas?
- recebeu atualização relevante, ou está abandonado?
- está ganhando ou perdendo jogadores?

Essa informação não existe em campo algum da API. Ela só aparece ao **comparar
duas leituras no tempo** — e é por isso que a consulta à loja nunca é
conclusiva: ela devolve exatamente o que já se sabia.

## 3. Dados

Coletados por `src/levantamento.py` na Steam Web API em **17/09/2026**. Saída
bruta em [`data/levantamento_diagnostico.json`](../data/levantamento_diagnostico.json).

| Indicador | Valor |
|---|---|
| Jogos com suporte a VR | **5.693** |
| Em promoção simultânea | **770** (13,5 %) |
| Preço médio em promoção | R$ 39,26 |
| Preço mediano | R$ 39,58 |
| Faixa de preço | R$ 5,59 – R$ 86,39 |
| Desconto médio | 53,2 % |

Jogadores simultâneos na mesma data, para dimensionar a dispersão do catálogo:

| Título | Jogadores |
|---|---|
| VRChat | 37.110 |
| Half-Life: Alyx | 332 |
| Beat Saber | 265 |
| Pavlov VR | 44 |
| SUPERHOT VR | 7 |

## 4. Causas

### 4.1 Cinco Porquês

| # | Pergunta | Resposta |
|---|---|---|
| 1 | Por que é preciso visitar a loja repetidamente? | Não há como saber, de fora, se algo mudou. |
| 2 | Por que não dá para saber o que mudou? | A loja exibe apenas o estado atual. |
| 3 | Por que o estado atual não basta? | Sem o valor anterior, um número não significa nada. R$ 39,26 é caro ou barato? 332 jogadores é muito ou pouco? |
| 4 | Por que a loja não expõe o histórico? | É otimizada para conversão. Mostrar que o preço já foi menor desestimula a compra de hoje. |
| 5 | Por que ninguém resolveu? | O SteamDB resolve, mas não tem API pública e proíbe raspagem. E ele também não recebe a série pronta: constrói-a consultando as mesmas rotas públicas, diariamente, há anos. |

**Causa raiz:** a informação temporal não existe pronta em fonte acessível.
Precisa ser construída por acumulação, uma leitura por vez.

### 4.2 Ishikawa

| Categoria | Causa |
|---|---|
| Método | Verificação ad-hoc, sem registro entre visitas |
| Medição | Nenhuma métrica comparável ao longo do tempo |
| Material | Anúncios dispersos, sem hierarquia de relevância |
| Máquina | Vitrine otimizada para conversão, não para acompanhamento |
| Mão de obra | Um usuário, em tempo de lazer |
| Meio ambiente | Promoções com janela curta e prazo não exibido em API |

## 5. Consequências

**Operacional.** A visita não conclui nada. Sem o preço da semana passada ou a
contagem anterior de jogadores, a consulta devolve o estado atual — que já era
conhecido.

**Financeira.** Decisão sem referência. O desconto exibido é calculado sobre o
preço cheio, nunca sobre o histórico real de preços, então não há como
distinguir oferta relevante de desconto rotineiro.

**De oportunidade.** Promoções expiram sem aviso. O prazo de término não é
exposto por nenhuma rota JSON pública, e a loja só o mostra a quem abre a
página do jogo.

## 6. Oportunidades

| # | Oportunidade | Justificativa técnica |
|---|---|---|
| 1 | Coleta programática de cinco rotas públicas da Steam | Nenhuma exige chave de autenticação; retornam preço em BRL e texto em português nativamente |
| 2 | Série temporal própria em SQLite | Única forma de obter variação: a informação não existe em fonte externa acessível |
| 3 | Classificação por LLM local | O catálogo é reprocessado a cada edição; modelo local tem custo marginal zero e não impõe limite de requisições. A RTX 5060 Ti (16 GB) comporta um modelo de 8B integralmente em VRAM |
| 4 | Decisão por regra determinística | Afirmações com número precisam ser auditáveis e consistentes entre execuções — o LLM fica restrito a resumir texto livre |
| 5 | Saída em áudio e em página | O consumo ocorre com o headset em uso, onde ler texto é desconfortável; a página resolve nome próprio e leva à loja por link |

## 7. Situação-alvo

| Dimensão | Atual | Alvo |
|---|---|---|
| Natureza da informação | estado instantâneo | variação no tempo |
| Conclusão da consulta | inconclusiva | boletim do que aconteceu |
| Anúncios | dispersos | resumidos e ordenados por relevância |
| Prazo de promoção | invisível | avisado com antecedência |
| Consumo | texto, fora do headset | áudio e página |
| Histórico de preço | inexistente | série acumulada |

---

**Fonte:** Steam Web API, acesso público sem autenticação, consultada em 17/09/2026.
