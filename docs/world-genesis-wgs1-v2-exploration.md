# WGS1 V2 — Calibração da exploração e descobertas

## Escopo e decisão atual

Esta validação mede o funil de exploração através do jogo e das conexões TP1 reais. A WGS1 v1 permanece com a política de geração anterior. A v2 segue opt-in e experimental; o início de uma campanha v2 nova grava `wgs1-nearby-signals-r1`. Campanhas v1, v2 já iniciadas sem essa política e saves existentes não recebem migração nem mudança de autoridade. O banco principal não é migrado.

Os pesos, o seletor de candidatos e as posições canônicas não foram recalibrados. O baseline geométrico anterior encontrou 121 candidatos brutos em cinco corredores de 500 km (média 24,2; 62 cavernas, aproximadamente 51%). Isso não representa locais descobertos ou jogáveis. A fração de cavernas é compatível com o intervalo do seletor e, sozinha, não justifica alterar a distribuição.

## Mudanças funcionais

- A observação consulta indícios apenas nas arestas TP1 adjacentes ativas e nos candidatos v2 selecionados. Indícios descrevem fatos canônicos, indicam direção local e não revelam ID nem coordenada. Perceber um sinal não concede descoberta.
- O jogador ainda descobre, alcança, visita e inspeciona formações pelas mecânicas existentes. As rotas permanecem `LocationConnection`; nenhum grafo de viagem paralelo foi criado.
- Novas campanhas v2 recebem a política de sinal explicitamente no descriptor. Saves v2 antigos sem essa chave preservam o comportamento histórico.
- O validador de viagem territorial agora aceita arestas de acesso WGS1 v2, assim como já aceitava v1. O rótulo de acesso corrigido é limitado a novas campanhas v2 com a política nova; rótulos históricos permanecem iguais.
- Consultas de sinal reutilizam decisões de candidatos já persistidas e evitam repetir avaliação E1 para candidatos rejeitados.

## Método e ambiente

O harness `backend/scripts/playtest_wgs1_v2_exploration.py` cria SQLite temporário, aplica as migrações nesse banco isolado, inicia Uvicorn real com LLMs desativados e conduz as ações pelo endpoint normal de gameplay. Todos os novos saves usados para teste registraram raio de 63.710.000 m (63.710 km). A rota usa apenas arestas TP1 ativas para campos ainda não visitados. Nenhum endpoint administrativo descobre formações. A seleção interna de rota lê o estado do banco para construir um percurso determinístico; essa leitura serve ao harness e não ao jogador. O mapa público é inspecionado para campos de coordenadas ocultas e IDs de formações ainda desconhecidas.

Cada percurso tenta os limiares de 5, 10 e 20 km, observando antes de se mover, seguindo pistas direcionais e descansando quando a regra normal de stamina exige. Os snapshots são tomados após cruzar cada limiar em uma aresta TP1 completa, portanto podem ultrapassá-lo pela extensão de uma aresta. A distância registrada é a soma das rotas TP1 percorridas, e não distância em linha reta. A demonstração também inspeciona/interage, retorna e reinicia o backend sobre o mesmo arquivo SQLite. A seed 2026 terminou em 11,849 km e não alcançou o limiar de 20 km.

### Resultados HTTP — cinco seeds

| Seed | Percurso / células | Candidatos brutos | Decisões / rejeições | Materializados por arquétipo | Sinal → descoberta → visita | Tempo e persistência |
|---:|---|---:|---|---|---|---|
| 42 | 20,445 km; 30 campos; 29 movimentos; 3 descansos | 2 (`EV-LOC-0042`: 1; `EV-LOC-0036`: 1) | 2 elegíveis; 0 rejeitados | 1 Vale das Pontes Rochosas; 1 Anfiteatro das Agulhas | Sinais a 2,108 e 3,603 km; 1 descoberto a 2,927 km / 537 min; alcançável, visitado e inspecionado; interação feita e retorno concluído | Observação média 0,952 s; viagem 1,196 s; localização, mapa e inspeção persistiram após reinício |
| 0 | 20,065 km; 26 campos; 25 movimentos; 3 descansos | 4 (`EV-LOC-0050`: 3; `EV-LOC-0236`: 1) | 4 elegíveis; 0 rejeitados | 3 Galerias das Três Saídas; 1 Bolsa Verde em Encosta Árida | 3 alcançáveis, descobertos e visitados a 5,665 / 11,046 / 15,189 km; 3 inspeções/interações/retornos | Observação média 1,781 s; viagem 2,016 s |
| 7 | 20,749 km; 28 campos; 27 movimentos; 3 descansos | 1 (`EV-LOC-0050`: 1) | 1 elegível; 0 rejeitados | 1 Galeria das Três Saídas | Sem descoberta até 10 km; 1 descoberta, alcançável, visitada e inspecionada a 13,698 km / 793 min; interação e retorno concluídos | Observação média 3,232 s; viagem 3,517 s; tempos afetados pela execução concorrente dos testes |
| 2026 | 11,849 km (não alcançou 20 km); 22 campos; 21 movimentos; 1 descanso | 2 (`EV-LOC-0050`: 1; `EV-LOC-0068`: 1) | 2 elegíveis; 0 rejeitados | 1 Galeria das Três Saídas; 1 nascente | Descobertas, alcançáveis e visitadas a 0,719 e 5,738 km; 2 inspeções/interações/retornos; a água da nascente permaneceu em 12.000 L / revisão 0 após interação | Observação média 0,845 s; viagem 1,098 s; localização, mapa e inspeção persistiram após reinício |
| 12345 | 20,374 km; 30 campos; 29 movimentos; 3 descansos | 3 (`EV-LOC-0050`: 2; `EV-LOC-0236`: 1) | 3 elegíveis; 0 rejeitados | 2 Galerias das Três Saídas; 1 Bolsa Verde em Encosta Árida | 3 alcançáveis, descobertos e visitados a 4,007 / 7,689 / 13,154 km; 3 inspeções/interações/retornos | Observação média 1,701 s; viagem 1,930 s |

No percurso anterior sem seguir sinais, seed 42 percorreu 5,181 km em 8 campos, verificou 24 células e materializou 3 candidatos elegíveis, mas não descobriu uma formação. Isso mede a dependência da aproximação/direção, não uma experiência comparativa controlada. Ao seguir indícios na execução atual, uma descoberta foi alcançada por volta de 2,9 km. Portanto, indício e rota investigável melhoraram o acesso observado; ainda não há base para atribuir a diferença ao balanceamento de frequências.

Nas cinco rotas, foram percorridos 93,482 km de exploração e 131 movimentos, com 12 candidatos v2 selecionados/contextualizados, 12 formações materializadas e 10 descobertas efetivamente alcançáveis, visitadas e inspecionadas. Duas formações materializadas permaneceram sem descoberta nesse percurso. Quatro rotas tiveram pelo menos uma descoberta no snapshot do primeiro limiar de 5 km (capturado em até 5,738 km); quatro tiveram descobertas até o snapshot de 10 km. Todas alcançaram alguma formação durante a rota completa, embora a seed 7 só tenha encontrado a sua após 13,698 km. As formações materializadas incluíram 7 galerias, 1 vale, 1 anfiteatro, 2 microhabitats e 1 nascente. Isso demonstra variedade, mas a amostra curta não valida raridade em escala planetária.

## Distribuição e calibração

Os dados anteriores de 500 km eram um corredor unidimensional e contavam apenas o seletor bruto. A nova medição bidimensional inclui a consulta contextual E1, materialização, percepção, descoberta e visita. Os resultados por seed serão mantidos separados: uma amostra pequena e rotas iniciadas em um ponto não sustentam quotas por arquétipo nem uma alegação de densidade planetária.

Não aumentar a densidade nem alterar pesos. Conservar cavernas e outras formações conforme as identidades e elegibilidade atuais. As rotas confirmam oportunidades interessantes sem aparecer em toda esquina, e a variedade observada não justifica pesos iguais nem cotas. Aprovar a mecânica de indícios como funcional, mas manter a frequência v2 experimental: a amostra é pequena e as rotas são locais.

### Tentativas de percurso longo

O ensaio de 50 km da seed 42 atingiu 23,272 km de território novo (34 campos/33 movimentos) e parou sem aresta TP1 ativa para um campo ainda não percorrido. O trajeto com visita à formação e retorno somou 43,617 km; a descoberta continuou sendo a mesma Vale das Pontes Rochosas aos 2,927 km. A seed 0 percorreu 50,173 km de território novo (64 campos/63 movimentos; 9 descansos) e terminou com 64,534 km incluindo a visita e retorno. Nesse percurso, 8 formações foram materializadas e 6 foram descobertas, alcançadas, visitadas e inspecionadas: 5 galerias, 2 microhabitats e 1 anfiteatro entre as materializações. As descobertas ocorreram a 5,665; 11,046; 15,189; 30,143; 31,759; e 35,813 km. Foram persistidos 79 pontos ambientais e 117 locais incluindo stubs TP1; esses números incluem somente as áreas tocadas e vizinhas necessárias, não uma materialização global. A persistência da localização/mapa/inspeção foi verificada após reinício. Assim, 50 km são possíveis, mas não em todos os componentes locais; barreiras TP1 e geografia condicionam o percurso sem atalhos artificiais.

## Desempenho e limitações

Os tempos medidos são latências HTTP completas no backend real, com LLM desativado; incluem gameplay, consultas e fallback narrativo e não isolam CPU por subsistema. No teste das cinco seeds, criação/preparação levou 17,2–27,7 s, observações 0,845–3,232 s em média por ação e viagens 1,098–3,517 s. Cada observação limitou a busca a quatro células adjacentes. Uma amostragem de dois segundos da seed 42 mediu pico observado de working set de 311.275.520 bytes (~297 MiB) para o processo Uvicorn, incluindo código/imports e estado da campanha; não é memória incremental por setor. A latência varia por seed, trabalho de preparação e estado, portanto estes números não são um benchmark isolado da função de sinal.

Limitações: o percurso é um agente determinístico de teste, não playtest humano; cada campanha cobre uma região inicial e a duração de jogo depende de distância, terreno e descanso. Os testes não provam a distribuição em todo o planeta. Nenhuma formação, clima, geologia, hidrologia ou ecologia é inventada para elevar métricas.

## Arquivos e validação

- `backend/app/game/world/genesis/local_formations.py` — percepção de sinais v2 e reutilização das decisões persistidas.
- `backend/app/game/world/genesis/playable.py` — política explícita para novas campanhas v2.
- `backend/app/game/perception/service.py` e `backend/app/game/engine.py` — transporte e apresentação dos sinais na observação existente.
- `backend/app/game/world/genesis/territory.py` — aceitação de acessos locais v2 pelo validador.
- `backend/app/tests/test_genesis_local_formations.py` — isolamento entre perceber e descobrir, compatibilidade de save v2 antigo, persistência de decisão e travessia v2.
- `backend/scripts/playtest_wgs1_v2_exploration.py` — harness Uvicorn/HTTP e relatório reproduzível.
- `artifacts/wgs1-v2-exploration/route-funnel.json` — métricas sanitizadas das cinco seeds e dos percursos longos, sem IDs temporários de campanha ou caminhos de banco.

Validação: `compileall` passou; `test_genesis_local_formations.py` passou (14 testes); `test_genesis_territory.py` e `test_genesis_spatial_integration.py` passaram em conjunto (14 testes); o `git diff --check` não apontou erros de whitespace. O Playtest V2 dos cinco seeds e os dois ensaios de 50 km usaram Uvicorn real, LLM desativado e SQLite temporário; em todos o hash do banco principal permaneceu inalterado. O mapa público não revelou coordenadas ocultas nem IDs de formações desconhecidas.
