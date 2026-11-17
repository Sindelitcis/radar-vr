# Métricas de desempenho

**Projeto:** Radar VR
**Disciplina:** AI Factory, Etapa Final (PUCPR)

---

## 1. O que é medido

| Métrica | Definição | De onde vem |
|---|---|---|
| Latência do fluxo | tempo do primeiro ao último nó | registro de execução do n8n |
| Latência por nó | tempo de cada nó | registro de execução do n8n |
| Latência por etapa | coleta, histórico de preços, redação e narração | `tempos`, medido pelo microsserviço em `/edicao` |
| Latência de envio | tempo de cada mensagem entregue | resultado de `/enviar/email` e `/enviar/instantaneo` |
| Taxa de sucesso | execuções que o n8n encerra sem erro, sobre o total | registro de execução do n8n |
| Taxa de edições completas | sucesso com áudio, com todos os anúncios resumidos pelo modelo e com os dados de avaliações | registro do n8n e `data/edicao_atual.json` |
| ROI | (ganho − custo) ÷ custo, no primeiro ano | medições e `evidencias/premissas_roi.json` |

A mediana (p50) e o p95 resumem a latência: metade das execuções termina
dentro da mediana, e 95% terminam dentro do p95.

## 2. Como medir

```
python testes/metricas.py campanha 30   30 execuções seguidas, em ensaio
python testes/metricas.py uma           uma execução em ensaio (para agendar)
python testes/metricas.py real 5        envio real, com histórico fixo
python src/painel_metricas.py           gera o painel e o resumo
```

Cada execução roda o fluxo completo pelo n8n (`n8n execute`), como no
agendamento diário, e grava uma linha em
`evidencias/metricas_execucoes.jsonl`. O microsserviço sobe em porta e banco
próprios, copiados do banco real a cada execução: a medição parte sempre da
mesma leitura anterior e não altera o histórico do boletim.

| Modo | O que acontece |
|---|---|
| Ensaio | coleta, modelo e narração rodam de verdade; nenhuma mensagem sai da máquina |
| Real | envia aos assinantes de `perfis.json`, sem gravar no histórico (`RADAR_HISTORICO_FIXO=1`) |

Junto de cada execução ficam o estado do Ollama (no ar, modelo instalado,
modelo já na memória), a carga do processador e o uso e o consumo da placa de
vídeo, lidos a cada 2 segundos. Isso permite separar uma execução lenta por
causa da rede de uma execução lenta por causa da máquina.

O registro não guarda contato nem apelido de assinante: de cada envio ficam
só o canal, o resultado, as tentativas e a latência.

## 3. Painel

`evidencias/painel_metricas.html` é gerado a partir dos registros e conta a
história em seis blocos: o problema, o antes e o depois, o que foi medido, o
que os dados revelaram, quanto vale e os próximos passos. Os mesmos números
ficam em `evidencias/metricas_resumo.json`.

As premissas do retorno ficam em `evidencias/premissas_roi.json`, separadas
do que foi medido: tempo da conferência manual, horas de desenvolvimento,
manutenção, valor da hora e tarifa de energia. Trocar uma premissa e gerar o
painel de novo refaz a conta.

## 4. O que a medição revelou

**Fluxo sem erro não é edição completa.** O tratamento de erros da Etapa 2 faz
o boletim sair mesmo quando uma fonte falha. Faltava avisar que saiu faltando
algo. Uma falha ficou escondida, com a taxa de sucesso em 100%:

| Falha | O que acontecia | Correção |
|---|---|---|
| A Steam desligou a rota `store.steampowered.com/appreviews/<appid>`, que passou a redirecionar para a página inicial da loja | a coleta registrava um aviso por jogo e a edição seguia sem aprovação e sem total de avaliações | `coleta.buscar_avaliacoes` usa `IUserReviewsService/GetAppReviews`, a rota indicada na documentação da Steam |

A leitura que falhava gravava total de avaliações igual a zero. Sem proteção,
a primeira leitura depois da correção viraria uma "onda de avaliações" com
todas as avaliações do jogo. `noticias._eventos_de_avaliacoes` passou a exigir
as duas leituras.

Depois da correção, uma edição em 53 saiu incompleta (13/11, 18h30): a
consulta de um único jogo voltou da Steam sem os totais, a única falha em
mais de 800 consultas. A proteção acima segurou o falso alerta e a execução
seguinte voltou ao normal. O caso passou sem aviso ao operador, que é a
primeira melhoria proposta abaixo.

Cada caso tem teste automatizado, sem acesso à rede:

```
python testes/test_etapa_final.py
```

**A rota nova devolve dado de pessoa.** Ela não aceita página vazia e devolve
ao menos uma avaliação, com o identificador de quem escreveu. O Radar VR pede
o mínimo (`num_per_page: 1`), lê só o resumo com os totais e descarta a lista.
O teste confere que nada do autor segue adiante.

**Manter o modelo na memória ajuda pouco na mediana, mas a carga lenta faz o
p95.** A redação leva cerca de 1,5 s com o modelo carregado e cerca de 3,8 s
com ele frio. Em 7 execuções em ensaio, porém, a carga demorou e a redação
levou de 12 s a 67 s (a mais longa passou de um
minuto). As 5 execuções acima do p95 são todas desse tipo. As 3 execuções com
coleta acima de 25 s, por lentidão da Steam, ficaram abaixo do p95. A saída
barata é carregar o modelo no início da edição, em paralelo com a coleta, em
vez de mantê-lo na placa de vídeo o dia inteiro.

**O envio é o limite de escala.** Cada e-mail leva cerca de 22 s. A primeira
suspeita era o áudio anexo (arquivo WAV de cerca de 2,8 MB), mas em 17/10
e-mails com áudio maior saíram em 9 s, e a maior parte dos envios fica logo
acima de 20 s, o padrão da espera por IPv6 já visto no Telegram (`docs/07`).
A causa ainda não foi isolada. O n8n dispara os
e-mails de uma edição ao mesmo tempo, o que funcionou com dois destinatários.
A personalização resolve 100 assinantes em 0,03 s; o envio dos mesmos 100
significaria cerca de 284 MB de áudio por edição, com limite de 60 s por
envio no nó. Esse volume não foi testado.

## 5. Melhorias propostas

| Gargalo ou risco medido | Proposta |
|---|---|
| Edição incompleta sem aviso | `/edicao` informa o que faltou e o n8n avisa o operador pelo caminho do aviso de falha |
| Rota externa desligada sem aviso | teste diário de cada rota, conferindo o formato da resposta |
| E-mail leva 22 s, sem causa isolada | medir um envio sem anexo e forçar IPv4 no SMTP; se for o anexo, áudio comprimido ou por link, e limite de envios simultâneos |
| Carga lenta do modelo frio (origem do p95) | carregar o modelo no início da edição, em paralelo com a coleta |
| Consulta lenta à Steam segura a edição | limite de espera menor por consulta, com uma nova tentativa |
| Narração no processador | gerar o áudio na placa de vídeo, ou só quando algum assinante pedir |
| Execução depende do computador do operador | publicar o microsserviço e o n8n em um servidor |

## 6. Limites da medição

- As execuções em ensaio não enviam mensagens: o envio real é medido à parte,
  com dois destinatários. A latência do fluxo é calculada só com as execuções
  em ensaio, e as execuções com envio real aparecem separadas.
- O computador ficou em uso normal durante as medições. A carga do processador
  fica registrada em cada linha.
- A conferência manual de 15 minutos por dia é uma estimativa, não uma medida.
  O painel mostra ao lado o cenário com 5 minutos. Nos dois cenários, o retorno
  desconta 1 minuto por dia para ler o boletim ou ouvir o áudio.
- Uma falha do próprio script de medição não conta como falha do Radar VR. Na
  primeira campanha, 28 execuções nem começaram porque o script recopiava o
  banco antes de o serviço anterior liberar o arquivo; o script foi corrigido
  e essas linhas foram descartadas.
