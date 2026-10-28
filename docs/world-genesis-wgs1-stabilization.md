# World Genesis — Estabilização WGS1

Status: **estável para teste opt-in; WGS1 não é o perfil padrão**. A implementação v1 permanece compatível. A v2 contextual é experimental e não converte campanhas anteriores.

## Auditoria e migração

O banco novo já chegava ao head Alembic e a migração R1 original adicionava `item_instances.unit_weight_override` e `item_instances.weight_authority`. A falha era no teste de schema: o conjunto esperado omitia as duas colunas que já existiam no ORM e na revisão aplicada. Corrigi a expectativa e ampliei o smoke em SQLite novo para criar campanha, personagem e uma pilha de inventário com as duas colunas persistidas. Não alterei uma revisão histórica nem executei migração no banco principal.

A revisão nova `z37_wgs1_candidate_decisions` cria somente `genesis_formation_candidates`. Ela armazena decisões v2 (aceitas, rejeitadas e materializadas) por campanha/endereço estável. A revisão não altera rows de formação v1 ou saves antigos.

## Elegibilidade contextual e versionamento

`world_genesis_ap1_tp1_wgs1_v1` mantém sua seleção, IDs, variações e resultados. A v2 opt-in (`world_genesis_ap1_tp1_wgs1_v2`, gerador `natural_formations_wgs1_v2`) tem hash, stable key e IDs próprios. Seu seletor marca 5,5% das células elegíveis como **candidatos brutos** antes do contexto; isso é uma proposta de exploração, não uma taxa de descobertas garantida.

No instante de preparação TP1, a v2 consulta o snapshot E1 persistido do mesmo ponto e classifica o candidato. Falta de T1/H1 confirmado, oceano aberto ou ponto abaixo do nível do mar rejeita formações terrestres. Caverna requer relevo local mínimo. Relevo rochoso, substrato, secura e relevo da formação fantástica são preferências com motivo registrado, não bloqueios absolutos. Nascente seca é permitida porque seu estoque finito é propriedade local WGS1; não implica crédito regional W1/W2/P1. O microambiente pode diferir da classe regional E1, mas não estabelece flora.

Uma decisão rejeitada é persistida para o endereço e não muda com a ordem de revisita. Decisões aceitas tornam-se `materialized` na mesma transação da formação. V1 continua usando sua autoridade já persistida sem esses filtros novos.

## Densidade: amostragem de rota

O diagnóstico `backend/scripts/diagnose_wgs1_route_density.py` percorre células TP1 adjacentes, medindo centros pela métrica esférica, para seeds 42, 0, 7, 2026 e 12345, três raios (31.855, 63.710 e 127.420 km) e percursos até 5, 20, 50, 100 e 500 km. O JSON reproduzível está em `backend/wgs1_route_density.json`.

No raio de referência, a rota de 500 km visitou em média 515 células. Candidatos brutos por seed:

| Seed | v1 (1,1% legado) | v2 (5,5% antes de E1) |
|---:|---:|---:|
| 42 | 10 | 21 |
| 0 | 8 | 24 |
| 7 | 5 | 19 |
| 2026 | 8 | 28 |
| 12345 | 4 | 29 |

A média foi 7,0 oportunidades v1 e 24,2 v2 por esse percurso; a média das medianas de espaçamento bruto foi 57,7 km e 13,6 km, respectivamente. Em 500 km, a média variou com o raio: v1 13,2 / 7,0 / 4,8 e v2 54,0 / 24,2 / 12,2 candidatos para raios 31.855 / 63.710 / 127.420 km. A mesma chance por célula diminui a frequência por distância em planetas maiores, como esperado da resolução angular atual.

Esse diagnóstico é um percurso geométrico local de vizinhos TP1 e conta **somente candidatos selecionados**: não aplica bloqueios E1, barreiras, acessibilidade do grafo ou descoberta pelo personagem; a rota amostral não cruza emenda de face. Portanto não calibra, por si só, a taxa de locais exploráveis. A v2 permanece experimental. Não alterei a v1 nem recomendo tornar a v2 padrão antes de amostragem contextual de várias campanhas reais.

## Progressão de gameplay

São etapas distintas: `CANDIDATO` é o resultado puro do seletor; `MATERIALIZADO` é a instância persistente; descoberta é registrada pelo sistema existente de descobertas de conexão/local; alcançabilidade vem do grafo `Location`/`LocationConnection`; exploração é comprovada por visita, observação e interações disponíveis. O registro de um candidato não equivale a descoberta. Nenhum sistema de exploração paralelo foi criado.

Formações atuais cobrem **uma célula TP1**, com dimensão horizontal limitada a 700 m; a v2 anota `WGS1_COVERAGE_V1` (`cell_limit: 1`, `max_horizontal_span_m: 700`). Não há cobertura multissetorial, arco colossal ou sistema extenso de cavernas.

A caverna usa conexões válidas `entrar`/`sair` ligadas ao local exterior. O conteúdo interno só se torna visível após a conexão ser descoberta e percorrida. Foi acrescentado um fallback estreito para pedidos explícitos de descanso quando o provedor opcional de intenção está desligado; ele despacha para o REST já existente e rejeita frases negativas, sem alterar recuperação ou simulação temporal. A nascente continua observável e persistente com estoque inicial local finito de 12.000 L e origem/versão explícitas; água ainda não pode ser coletada ou consumida porque o item existente é consumível, não recipiente reutilizável. Não criei item, recarga ou sistema de sobrevivência.

EV-LOC-0236 persiste o microambiente local, mas o contrato atual de Vg2 deriva elegibilidade de habitat de E1 e não recebe overlay local. Não injetei plantas nem alterei E1/Vg2. A integração ecológica permanece bloqueada até um contrato local de habitat versionado.

## Persistência e compatibilidade

O smoke WGS1 usa um SQLite temporário migrado ao head e um processo Uvicorn real. Ele cria campanha v1, personagem, percorre conexões vistas por ações normais, visita uma nascente e uma caverna, observa e sai do interior, encerra e reinicia o backend sobre o mesmo arquivo e compara local, instâncias, estoque de água, mapa e interiores. O teste isolado de duas campanhas na mesma seed confirma que o mesmo endereço físico escolhe o mesmo arquétipo, enquanto IDs e estoque de gameplay são independentes. Nenhuma coordenada física oculta é incluída no mapa público. O SQLite de teste fica em `%TEMP%`; o hash do banco real é comparado antes/depois.

## Validação

- Migração SQLite criada do zero até head: aprovada; schema inclui R1 e `genesis_formation_candidates`; smoke criou campanha, personagem e inventário.
- WGS1 v1 em Uvicorn real, seed 42: nascente e caverna foram localizadas por exploração/observação TP1, visitadas; caverna entrou, foi inspecionada e teve saída/revisita. O teste encerrou o processo e abriu outro apontando ao mesmo SQLite temporário. Posição, mapa, conteúdo inspecionado e IDs/arquétipos persistidos conferiram; ficaram exatamente 2 formações, 1 interior e estoque da nascente em 12.000 L, revisão 0. O mapa não expôs coordenadas físicas. O log registra 38 locais descobertos e 15 visitados. Migração, bootstrap e percurso/reinício levaram aproximadamente 148 s no total em máquina de desenvolvimento.
- No mesmo save, a separação geográfica entre a nascente e a caverna foi 6.205 m; desde o ponto inicial, 2.656 m até a nascente e 3.870 m até a caverna. O trajeto de retorno ao início usou conexões normais, não teleporte. Essas medidas são distância de grande círculo entre pontos persistidos; caminhos podem ser mais longos.
- Teste de campanhas iguais em seed produziu mesma formação canônica e estado de água inicialmente igual, mas IDs e alterações independentes.
- Teste de tentativa de entrar antes da descoberta da ligação interna manteve o personagem do lado externo. A regra pública continua usando o grafo de conexões existente.
- Testes de backend de formações + migrações: 12 passaram; o caso v2 adicional cobrindo decisão aceita/rejeitada persistida passou isoladamente. A regressão `test_genesis_territory.py` + `test_world_genesis.py` fechou com 24 testes aprovados em 189,35 s. O teste histórico de migração foi corrigido para usar o diretório Alembic e comparar os mesmos campos legados, aceitando as colunas aditivas nulas e sua remoção no downgrade; não houve alteração de dados legados.
- Testes de fallback de descanso explícito/regras contextuais: 3 passaram. Teste isolado de SQLite novo + descanso: 2 passaram.
- Frontend: 92 testes passaram; build TypeScript/Vite passou. A automação visual não foi concluída: o helper Windows respondeu `Computer Use native pipe is unavailable` antes de listar janelas. Portanto não há alegação de playtest visual.

## Limitações e próxima etapa

- A v2 ainda precisa de diagnóstico de rota usando E1 para separar candidato, rejeição contextual, descoberta e visita nos cinco seeds.
- A rota de densidade é local e não cruza faces; continuidade de topologia permanece responsabilidade dos testes de cube-sphere e da integração TP1.
- Nascente ainda não permite extração; falta recipiente reutilizável compatível com inventário.
- Microhabitat não influencia populações Vg2 nesta fase.
- Cobertura está limitada a uma célula e 700 m.
- O perfil continua explicitamente opt-in; não migrar saves antigos.
