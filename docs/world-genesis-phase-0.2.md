# World Genesis — fase 0.2: topologia e integração espacial

## Decisão antes da implementação

### Alternativas avaliadas

| Alternativa | Vantagens | Limites / decisão |
| --- | --- | --- |
| Atlas cilíndrico v1 | Simples, já persistido, hashes inteiros estáveis | Não identifica polos e deixa limites em y. Preservar como v1, sem conversão. |
| Latitude/longitude | Familiar, geodésicas diretas | Quadrícula converge nos polos, longitude perde significado ali e vizinhança exige exceções. Usar apenas como entrada/saída auxiliar, não endereço persistente. |
| Malha icosaédrica | Boa distribuição espacial | Triângulos, hierarquia e cobertura exigem mais contratos novos. Não oferece vantagem necessária nesta fase. |
| Cube-sphere com quadtree | Superfície inteira coberta por seis faces, endereços inteiros hierárquicos, vizinhança limitada e polos interiores às faces | Distorção de área e orientação nas emendas precisam ser explícitas. **Escolhida para v2**, projeção radial do cubo na esfera verdadeira. |

A decomposição de esfera por faces de cubo e subdivisão quadtree tem precedente na [documentação primária do S2](https://s2geometry.io/devguide/s2cell_hierarchy). A implementação Everreach não usa IDs Hilbert nem a projeção não linear do S2, e não se declara compatível com seus IDs. Seis faces são cartas matemáticas, não seis continentes, oceanos ou regiões.

### Contratos fixados

- Configuração v2 independente: raio em metros, nível de setores quadtree, resolução de amostras e frequência macro. Raio não altera endereços angulares; altera distâncias físicas. Um setor não tem largura métrica constante. Nenhum cálculo de viagem pode usar índices de célula como distância.
- Ponto autoritativo: raio cartesiano inteiro primitivo `(x,y,z)` centrado no planeta, normalizado por MDC. Seu comprimento não é altitude. Ele identifica exatamente uma direção na esfera, inclusive polos, vértices e emendas. Pontos de malha não dependem de trigonometria. Importações e deslocamento usam quantização explícita, com tolerância métrica documentada.
- Célula: `(face, level, x, y)`. Orientações fixadas em código; empates de face pertencem ao menor índice. Amostras em arestas usam o mesmo raio inteiro em ambas as faces. Continuidade do campo é global em 3D, nunca um ruído independente por face.
- Distância é arco mínimo sobre a esfera, `R * atan2(|a×b|, a·b)`, e não corda nem distância no plano de face. Deslocamento é geodésico; orientação em um polo tem convenção explícita, sem limite físico de passagem.
- V1 continua com config/seed/algoritmo/tabela originais. V2 usa a mesma raiz GenesisWorld e uma tabela de setores distinta, evitando reinterpretar PK `(campaign,x,y)` como faces. Dispatch rejeita versões e endereços incompatíveis.
- Materialização é explícita e de custo limitado por setor. Inicialização grava plano global implícito, sem enumerar malha planetária. Preparação é BFS por vizinhos de aresta com limite de profundidade; não é streaming nem movimentação.

### Hierarquia física

Planeta → continentes físicos → macrorregiões → setores → áreas locais. Continentes serão componentes geográficos identificados pelo futuro plano físico, podendo cruzar faces. Não há identificação/contagem de continentes nesta etapa. Macrorregiões e coberturas são uniões esparsas de células quadtree, incluindo células ancestrais, sem expandir todos os setores. Áreas locais se ancoram por pontos, podendo receber coberturas posteriormente. Region e Subregion são entidades de gameplay independentes dessa hierarquia; sua cobertura pode atravessar faces, continentes e múltiplos setores. Não inferir continente a partir de Region ou número da face.

### Contrato de integração planejado nesta fase

Âncoras persistentes com FK para Location e coberturas persistentes com FK explícita para Region ou Subregion. Validar pertencimento à campanha, exclusividade do titular, endereços v2 e idempotência. Não alterar `Location.x/y`. Distância geográfica entre âncoras é informação adicional; `LocationConnection.distance`, duração, stamina e risco mantêm suas unidades atuais. Não introduzir outro grafo de movimento.

O adaptador de leitura para mapa deve reaproveitar a projeção de conhecimento existente: apenas Location já VISITED pode receber ponto esférico exato. Local conhecido mas não visitado continua sem coordenadas precisas; desconhecido não aparece. Nenhuma rota pública deve expor diretamente a tabela de âncoras ou o plano planetário.

## Auditoria dos pontos de integração

| Sistema real | Contrato observado e preparação entregue |
| --- | --- |
| `models/region.py`, `subregion.py`, `location.py` | Region pertence a Campaign; Subregion e Location chegam à campanha por Region. Location pode ter pai, subregião e tier. Novas FKs relacionam essas entidades sem substituir a hierarquia ou reinterpretar IDs. Region/Subregion aceitam células de cobertura em diferentes faces; Location tem uma âncora imutável por serviço. Cobertura é união de células, não limite político calculado. |
| `models/location.py:LocationConnection`, `game/travel/service.py` | Movimento exige conexão física ativa e rota conhecida, materializa detalhes de destino, desconta stamina e registra visita. A topologia fornece posições, sem criar caminhos caminháveis automaticamente. `connection_geographic_distance` calcula limite inferior por arco entre âncoras, sem alterar `distance`, `travel_time_modifier` ou `danger`. A distância real de uma rota pode ser maior por desvios. Sem âncoras retorna ausência explícita. |
| `game/exploration/service.py`, `game/discovery/service.py` | Busca revela conexões pelo sistema existente; não gera terreno como efeito colateral. `prepare_location_sector` e `location_preparation_plan` são hooks internos explícitos para uma futura orquestração de início/viagem. Preparar terreno não concede conhecimento. Atravessar uma face não requer descoberta de outra face nem cria uma barreira. |
| `game/map/view.py`, `map/service.py`, `api/routes/map.py`, `schemas/map_view.py`, `frontend/src/features/map/InteractiveMap.tsx` | View filtra descoberta do personagem, distingue APPROXIMATE/PRECISE e aplica escopo. UI atual normaliza x/y e não conhece esfera. `spatial_view.known_spatial_locations` primeiro reutiliza a view, depois retorna âncoras apenas para sua seleção precisa e campanha validada. O frontend e a API atuais permanecem iguais; não é um mapa esférico já entregue. Coberturas regionais não são expostas pelo adaptador. |
| `world/boundaries.py`, `crossing.py`, `cross_region_routes.py`, `models/regional_boundary.py` | Barreiras, rotas e fronteiras têm identidade distinta e locais-âncora existentes. Esses locais podem receber vínculo espacial como qualquer Location. Uma emenda de face é só troca de carta, sem bloqueio. Acessibilidade continua consultando estação e preparação. Atualmente múltiplas BoundaryRoute podem compartilhar a mesma conexão entre regiões; não inferir geometrias de rotas distintas desse grafo. |
| `game/time/clock.py`, `simulation/world_simulation.py`, `scope.py`, `cadence.py` | Tempo, cadência e escopo já são persistentes. Nesta fase nenhum tick percorre a malha esférica. Materialização/preparação não avança tempo; ações existentes continuam responsáveis por isso. Eventos futuros podem endereçar pontos/células e alterar barreiras sem o jogador estar presente; aplicação/replay de mudanças geográficas não foi implementada. |
| `world/seed.py`, `neighbor_region.py`, `materialization_orchestrator.py` | Geradores atuais não têm posições físicas e dependem de pools/nomes usados. Continuam legados. Inicializar um mundo v2 não executa esse pipeline para inventar uma associação automática. A integração futura de novo jogo deverá escolher a âncora inicial e associar explicitamente os locais produzidos. |
| `db/database.py`, `world/reset.py`, Alembic | Session e FK SQLite continuam sendo o contrato transacional. Migração acrescenta três tabelas e índices, sem UPDATE de dados antigos. Exclusão remove coberturas, âncoras e setores esféricos antes dos pais, só na campanha solicitada. |

## Implementação funcional

### Endereços, vizinhança e métrica

`SurfacePoint` reduz por MDC raios inteiros não nulos, com componentes até 53 bits. Latitude/longitude é importação opcional; não é a forma persistida. `CellKey` aceita níveis 0..24 e valida índices; empates canônicos são estáveis, mas `cell_contains` usa célula geometricamente fechada. Assim, um ponto sobre uma emenda pode pertencer às coberturas das duas faces, mesmo tendo um único endereço canônico de consulta.

Faces e eixos `(normal, u, v)` são fixados em `sphere_topology.py`; u/v locais não equivalem a leste/norte geográficos. `neighbor` transforma a aresta pelo seu ponto médio exato para o outro sistema de face e pode trocar orientação. Uma aplicação que mantém rumo deve usar `advance`, não repetir a mesma direção de grade após uma emenda. Os dois polos são pontos normais nas faces ±Z; exatamente no polo adota-se eixo leste +Y como convenção de rumo. Não há tratamento de polo como barreira.

`distance_m` usa produto escalar/vetorial inteiro e atan2. Importação lat/lon e deslocamento usam ponto flutuante, quantizando a direção a 10^15 antes de normalizar por MDC. O erro da etapa de quantização é inferior a `2e-15 * raio` metros (até 0,002 m no raio máximo); isso não inclui todo erro de trigonometria ou acúmulo de passos. Não exigir igualdade binária de resultados trigonométricos entre plataformas. Endereços de malha e terreno são inteiros; não dependem dessa trigonometria para reprodução. Altitude não altera a métrica da esfera de referência nesta fase.

O raio configurável vai de 1.000 a 10^12 metros. No limite superior a circunferência é aproximadamente 6,28 bilhões de quilômetros; isso não exige alocação proporcional. Nível de setor e raio são independentes, então escolher configuração adequada de resolução é responsabilidade da criação do mundo. A projeção radial não é de área igual; medir dimensões por geodésica em vez de assumir setor quadrado em metros.

### Plano global e geração progressiva

`SphereConfig` fixa config/generator v2, raio, nível de setores, frequência macro, nível do mar e amostras. Padrão: raio 6.371 km, setor nível 10, frequência macro nível 4 e quatro intervalos de amostra por eixo. Não existe contagem configurada de continentes ou recursos.

O plano global implícito persistido descreve um campo 3D de elevação em baixa resolução. Direção normalizada é aproximada em ponto fixo inteiro de 40 bits com raiz quadrada inteira; nós da malha 3D usam `coordinate_seed` com domínio v2; interpolação é inteira. A função é global e usa o mesmo raio nas arestas e nos oito vértices, evitando hashes diferentes por face. Não é tectônica ou identificação de continentes. Elevação é quantizada a metro e continuidade significa ausência de salto artificial de face/setor; não se afirma uma superfície diferenciável ou triangulação renderizável já pronta.

`initialize_world(..., SphereConfig(...))` grava apenas seed/configuração/plano. `materialize_sector` gera ou recupera uma célula no nível fixado, com no máximo 33×33 amostras. Raio, quantidade total de setores e ordem de visita não mudam o custo por setor. O tamanho do plano não cresce com o número potencial de setores.

`prepare_location_sector` materializa somente o setor da âncora; `location_preparation_plan` faz BFS por arestas, com raio de 0..4 saltos e limite superior conservador de 341 células. Não enumera o planeta, não materializa vizinhos, não altera descoberta. Existe continuidade de vizinhança nos cantos; não se promete uma janela quadrada 3×3 ao redor de um vértice. Workers, cancelamento, cache e orçamento de streaming ficam para a próxima integração.

### Persistência e compatibilidade

- `GenesisWorld` continua sendo a raiz por Campaign, com configuração/seed fixadas. `parse_config` valida versões e topologia antes do dispatch. Chamada sem configuração reabre a versão já fixada; nova inicialização sem configuração continua criando v1, preservando o contrato existente. Novos mundos esféricos optam explicitamente por `SphereConfig`.
- V1 mantém `WorldConfig`, `coordinates.py`, `geography.py`, hashes e `GenesisSector` inalterados. V2 usa `GenesisSphereSector` com chave `(campaign, face, x, y)` e nível registrado no config/snapshot. Endereço de v1 em v2 ou vice-versa é rejeitado. Mudar raio/versão de mundo existente é rejeitado. Não há conversão de saves.
- `LocationSpatialAnchor` tem FK para Location e GenesisWorld; o ponto persistido é lista JSON de três inteiros canônicos. `EntitySpatialCoverage` tem titular Region **ou** Subregion, CHECK de exclusividade, endereço validado e unicidade por titular/célula. A campanha do titular é validada pelo serviço. Uma célula ancestral representa milhares ou milhões de setores potenciais sem materializá-los.
- Não se exige que coberturas de Region sejam disjuntas nem que Subregion particione sua Region. Coberturas podem se sobrepor e cruzar emendas; relações culturais/políticas não são limites físicos. Identificação de continentes, macrorregiões físicas nomeadas e coberturas locais detalhadas não estão implementadas.
- Snapshots existentes vencem a regeneração; `changes` é preservado em tabela separada do baseline. JSON simples exige atribuir um dicionário novo para salvar alterações internas. Não há ainda aplicação de eventos ao relevo nem resolução de alterações na mesma borda de dois setores; futuros eventos físicos deverão usar endereço compartilhado de ponto/área.
- Serviços fazem flush, sem commit próprio; chamador controla rollback. PKs/uniques protegem duplicatas. Disputas concorrentes podem produzir IntegrityError e requerem rollback/releitura; fila com retentativas continua planejada. FKs não verificam sozinhas pertencimento à campanha via JSON: gravações devem usar os serviços, não SQL externo arbitrário.
- A migração `i17i1d2e3f4g` depende de `h16h1c2d3e4f`; a cadeia local anterior inclui a revisão de quests `g15g1b2c3d4e`. Foi validada em bancos temporários, sem migrar `everreach.db`. Downgrade remove dados v2; não converte um mundo esférico para cilindro. Não executar downgrade como forma de converter um save.

## Demonstração validada

O teste `test_route_crosses_multiple_sectors_and_face_seam_without_revealing_unknown_places` constrói uma fixture isolada com quatro locais reais no mesmo Region e conexões físicas existentes, ancorados nos setores:

```text
(face +X, nível 10, 1022,512)
 → (+X, 10, 1023,512)
 → (+Y, 10,    0,512)   # emenda planetária
 → (+Y, 10,    1,512)
```

Inicialmente só um setor é materializado. Planejar vizinhos encontra a outra face sem gerar terreno. Um local conhecido mas não visitado aparece no mapa com x/y nulos; os outros dois não aparecem. O adaptador espacial fornece apenas a âncora do local visitado. A cada passo o teste prepara somente o destino, chama `move_character`, avança o relógio existente e verifica que somente visitas concedem pontos exatos. Após commit e outra Session, âncoras, descobertas e quatro setores permanecem.

As distâncias de conexão desta fixture são 1 unidade legada, escolhidas para verificar o contrato de 15 minutos e risco zero. Não são uma conversão das distâncias geográficas calculadas. O teste comprova integração dos contratos e preservação de unidades, não balanceamento de uma campanha real. Separadamente, um percurso geodésico em passos de 1.000 m atravessa a emenda, mantendo comprimento entre passos e passando por múltiplos setores.

## Arquivos desta fase

| Criado/modificado | Responsabilidade |
| --- | --- |
| Novo `backend/app/game/world/genesis/sphere_config.py` | Config v2 e dispatch validado das versões. |
| Novo `.../genesis/sphere_topology.py` | Pontos, células, ancestrais, inclusão, arestas e vizinhança esférica. |
| Novo `.../genesis/sphere_metric.py` | Arco geográfico, latitude/longitude auxiliar e deslocamento geodésico. |
| Novo `.../genesis/sphere_geography.py` | Plano implícito v2 e campo 3D determinístico compartilhado. |
| Novo `.../genesis/spatial.py` | Âncoras, coberturas, preparação local e distância adicional de conexão. |
| Novo `.../genesis/spatial_view.py` | Adaptador interno que reutiliza descoberta/precisão da view atual. |
| Modificado `.../genesis/service.py` | Dispatch v1/v2 na raiz e materialização; caminho v1 preservado. |
| Novo `backend/app/db/models/world_spatial.py` | Três modelos persistentes com FKs, índices e restrições. |
| Modificado `backend/app/db/models/__init__.py` | Registro/exportação dos modelos. |
| Modificado `backend/app/game/world/reset.py` | Limpeza das dependências espaciais na exclusão da campanha. |
| Nova migração `backend/alembic/versions/i17i1d2e3f4g_add_spherical_spatial_contracts.py` | Criação aditiva de tabelas e índices. |
| Novos `backend/app/tests/test_genesis_sphere_topology.py` e `test_genesis_spatial_integration.py` | Validação geométrica, compatibilidade, persistência, migração e percurso. |
| Novo `docs/world-genesis-phase-0.2.md` | Avaliação, decisões, auditoria, implementação, limitações e validação. |

As alterações locais preexistentes de quests, recompensas, engine, simulação e frontend foram preservadas. Nenhum arquivo de dataset foi alterado; nenhuma nova população, bioma ou civilização foi gerada.

## Uso interno e próximas integrações

```python
from app.game.world.genesis.service import initialize_world
from app.game.world.genesis.sphere_config import SphereConfig
from app.game.world.genesis.sphere_topology import CellKey, cell_center
from app.game.world.genesis.spatial import (
    bind_location, add_coverage, prepare_location_sector, location_preparation_plan,
)

# campaign_id, location_id e region_id pertencem à mesma campanha.
# A escolha do ponto inicial cabe à futura geração física da campanha.
initialize_world(db, campaign_id, SphereConfig(radius_m=63_710_000, sector_level=14))
start = CellKey(0, 14, 8192, 8192)
bind_location(db, campaign_id, location_id, cell_center(start))
add_coverage(db, campaign_id, start.parent(4), region_id=region_id)
prepare_location_sector(db, campaign_id, location_id)
pending = location_preparation_plan(db, campaign_id, location_id, radius=1)
db.commit()
```

O exemplo escolhe uma âncora explicitamente; não migra nem valida a geografia de locais legados. Não existe seleção de topologia na UI/API pública nem substituição automática do fluxo de criação da campanha nesta fase.

Próxima etapa: integrar um fluxo opt-in de **novo** jogo que escolha/configure o planeta e a área inicial, atribua âncoras/coberturas coerentes aos locais e use os hooks de preparação nas transações existentes. Depois definir projeção e LOD esférico do mapa usando o adaptador de conhecimento. Só então calibrar uma conversão explícita e versionada de metros para unidades de viagem, considerando geometria de rota e desvios, antes de alterar duração/risco. Continuar sem datasets ou geração geológica complexa nessa estabilização.

## Validação executada

- Testes novos da v2: **59 passaram**. Incluem endereços, validação estrita, todas as 24 orientações de borda e seus cantos, reciprocidade de vizinhos, oito vértices compartilhados por três faces, conectividade de uma malha completa em resolução baixa, polos, emenda de longitude, arco versus corda, antípodas, raios até 10^12 m e deslocamento global.
- Determinismo: ordem inversa em memória e banco, subprocessos com PYTHONHASHSEED diferente, vetor de reprodução v2, elevação igual em pontos compartilhados e continuidade básica de pequenas perturbações nas emendas.
- Persistência: outra Session, baseline e alterações sem regeneração, coberturas esparsas, isolamento de campanha, rollback, exclusão com FKs ativas e rejeição de mudanças implícitas de configuração/âncora.
- Migração: banco construído pela cadeia Alembic real, save v1 populado antes do upgrade; comparação exata de linhas antigas após upgrade; criação/leitura/exclusão v2 via ORM sobre o schema migrado; downgrade preservando registros v1. Teste anterior da fase 0.1 também continuou passando.
- Regressão selecionada: **148 testes existentes passaram**, incluindo os 18 de Genesis v1 e testes de mapa, planejamento/anotações/posição, viagem, exploração, fronteiras, rotas regionais, materialização, escopo de simulação, relógio e exclusão de campanha. Execução ampliada passou 206 casos antes de acrescentar o teste final de conectividade; a suíte v2 final passou os 59 casos, totalizando **207 testes distintos aprovados**.
- `compileall` passou para os módulos novos; revisão Alembic tem uma única cabeça. A suíte completa do backend e a suíte frontend não foram executadas. Há aviso de depreciação preexistente Starlette/httpx, sem falhas nos testes selecionados.
