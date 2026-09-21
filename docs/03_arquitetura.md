# Arquitetura

**Projeto:** Radar VR
**Disciplina:** AI Factory, Etapa 1 (PUCPR)

---

## 1. Fluxo

```
ETAPA 1            ETAPA 2                ETAPA 3           ETAPA 4
Steam, 5 rotas  →  detecção de eventos →  redação e voz  →  áudio, HTML,
                   + série temporal        LLM + Kokoro      CSV e SQLite
```

A saída de uma edição é insumo da seguinte: sem a leitura de ontem não existe
variação a reportar.

## 2. Módulos

| Módulo | Responsabilidade |
|---|---|
| `config.py` | Parâmetros, limiares e caminhos |
| `coleta.py` | Consumo das cinco rotas da Steam |
| `historico.py` | Snapshots, comparação e memória de publicação |
| `noticias.py` | Detecção de eventos e ordenação por relevância |
| `redacao.py` | Redação das chamadas com LLM local |
| `pronuncia.py` | Normalização de texto escrito para texto falado |
| `voz.py` | Montagem do roteiro e síntese com Kokoro |
| `boletim_html.py` | Edição em página, com links da loja |
| `jornal.py` | Orquestrador |
| `painel.py` | Console do operador |
| `levantamento.py` | Coleta de dados para o diagnóstico |

## 3. Fontes de dados

| Rota | Fornece |
|---|---|
| `/search/results` | Descoberta de títulos com suporte a VR |
| `/api/appdetails` | Preço final, preço cheio, desconto, gêneros |
| `GetNumberOfCurrentPlayers` | Jogadores simultâneos |
| `/appreviews/<appid>` | Aprovação e volume de avaliações |
| `ISteamNews/GetNewsForApp` | Anúncios do desenvolvedor |

Nenhuma exige chave de autenticação.

**Prazo de promoção.** Nenhuma rota JSON pública expõe a data de término por
appid: `discount_expiration` existe apenas em `/api/featuredcategories`,
restrito a dez títulos em destaque. A alternativa é o contador na página da
loja, o que implica leitura de HTML. `coleta.buscar_fim_promocao()` isola essa
dependência e falha em silêncio. Sem a data, o boletim não anuncia o prazo e
nenhuma outra etapa é afetada.

## 4. Watchlist

Conjunto de 15 títulos ordenado por volume de avaliações, sem filtro de
promoção. A ausência do filtro é deliberada: o conjunto precisa ser o mesmo na
execução seguinte para que a comparação tenha significado.

## 5. Eventos

| Evento | Peso | Condição |
|---|:-:|---|
| `PROMOCAO_ACABANDO` | 90 | término informado pela loja em até 5 dias |
| `PRECO_MINIMO` | 85 | preço abaixo do menor já registrado |
| `PATCH_GRANDE` | 70 | anúncio do desenvolvedor nos últimos 7 dias, ainda não publicado |
| `PROMOCAO_NOVA` | 55 | desconto onde antes não havia |
| `PROMOCAO_ENCERRADA` | 50 | desconto que voltou a zero desde a edição anterior |
| `PICO_JOGADORES` | 45 | alta ≥ 25 % sobre base ≥ 80 jogadores |
| `QUEDA_JOGADORES` | 35 | queda ≥ 35 % sobre base ≥ 80 jogadores |
| `ONDA_AVALIACOES` | 30 | ≥ 40 avaliações novas desde a edição anterior |

### Limiares

Todo evento de variação exige base mínima além do percentual: uma alta de
200 % sobre três jogadores é ruído estatístico.

`PRECO_MINIMO` exige ao menos cinco edições de histórico e comparação estrita.
Com duas leituras, o preço atual é o mínimo por definição, o que tornaria a
afirmação vazia.

### Diversidade editorial

Máximo de dois eventos por título na mesma edição, e um anúncio por título
(o mais recente). Sem esses tetos, um jogo com vários patch notes ocuparia o
boletim inteiro.

### Agrupamento

Liquidações sazonais movem o catálogo inteiro de uma vez: todos os títulos
passam a ter a mesma data de término, e depois saem de promoção no mesmo dia.
Três ou mais promoções que compartilham o mesmo fato são reunidas em um único
evento, que mantém os individuais em `dados.membros`. O áudio usa a chamada
resumida e a página expande a lista completa.

## 6. Divisão entre LLM e regra

| Conteúdo | Origem | Motivo |
|---|---|---|
| Resumo de anúncio do desenvolvedor | LLM | texto livre; extrair o que mudou de um changelog é onde o modelo agrega valor |
| Frases com número (preço, desconto, variação) | Regra determinística | afirmação verificável precisa ser auditável e consistente entre execuções |

A separação é necessária por precisão: mesmo instruído a preservar o tempo
verbal, o modelo reescreve "está em promoção" como "entrou em promoção",
afirmando mudança não observada.

## 7. Memória de publicação

A janela de detecção de anúncios cobre sete dias, o que faria o mesmo patch
reaparecer em todas as edições da semana. Cada anúncio da Steam tem um `gid`
global; a tabela `noticias_publicadas` registra os já publicados.

A retenção é derivada da janela, não arbitrária: um anúncio mais antigo que
`NOTICIA_RECENTE_DIAS` já é descartado por idade, então guardar seu
identificador além disso não altera resultado. A poda usa o dobro da janela,
como folga para períodos sem execução.

```
tamanho máximo ≈ títulos monitorados × anúncios na janela ≈ 75 linhas
```

A tabela `snapshots` cresce, e deve: é a série temporal. O crescimento é
linear, com 15 linhas por edição e menos de 1 MB por ano.

## 8. Camada de pronúncia

O sintetizador lê exatamente o que está escrito. `pronuncia.py` normaliza antes
da síntese:

| Entrada | Saída falada |
|---|---|
| `R$ 40,50` | quarenta reais e cinquenta |
| `75%` | setenta e cinco por cento |
| `00h` | meia-noite |
| `v1.13.2` | removido |
| `14/09/2026` | removido; a data vira "ontem", "anteontem" |
| `VR` | vê érre |

Todas as regras operam sobre a **forma** do texto, ou seja, se é número, data,
versão ou sigla, e não sobre uma lista de conteúdos conhecidos. Por isso valem
pra qualquer entrada, sem precisar de manutenção.

Siglas de duas a três letras são soletradas. O limite de três preserva títulos
em caixa alta como `DOOM` ou `RAGE`, lidos como palavra.

**Limitação assumida.** Nomes próprios em inglês são lidos com fonema português
e soam aproximados. Corrigir exigiria detectar o idioma de cada nome e alternar
o phonemizer no meio da frase. A página HTML cobre o caso, exibindo o nome
escrito e o link da loja.

## 9. Estrutura do boletim

```
manchete    evento de maior relevância
destaques   atualizações e variação de jogadores
promoções   ofertas novas, prazos e mínimas
radar       quedas e movimento de avaliações
rodapé      títulos monitorados e movimentos da edição
```

A posição informa ao ouvinte o tipo de conteúdo, já que áudio não se relê.
Saudação, transições e despedida variam entre edições; os fatos não.

## 10. Saídas

| Arquivo | Finalidade |
|---|---|
| `audio/boletim_*.wav` | narração |
| `audio/ultimo_boletim.txt` | roteiro narrado |
| `data/boletim_atual.html` | leitura, com preço no formato da loja e links |
| `data/jornal_vr.csv` | manchetes publicadas |
| `data/jornal_vr.db` | série temporal e memória de publicação |
| `logs/jornal.log` | registro carimbado das etapas |

Áudio e página são complementares: a narração serve para varrer o boletim sem
tirar o headset; a página resolve o nome escrito e leva à loja.
