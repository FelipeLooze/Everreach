# World Genesis — fase 0

Data: 25/10/2026. Fontes: código, modelos e cadeia Alembic do checkout local.

## Auditoria do sistema existente

| Área | Evidência no repositório | Conclusão |
| --- | --- | --- |
| Backend | `backend/pyproject.toml`, `app/main.py`, `app/db/database.py` | FastAPI, Pydantic 2, SQLAlchemy 2, SQLite configurável, Alembic. SQLite habilita FKs. Serviços usam a Session do chamador; rotas controlam commit. |
| Mundo e seed | `app/db/models/campaign.py`, `app/game/world/generation.py`, `seed.py`; migração `ao15a1b2c3d4` | Campaign já é a raiz de um mundo/save. `world_seed` pode ser nula em saves antigos. `derive_seed` usa SHA-256 e 63 bits. Region registra seed e versão. Não criar outro agregado concorrente de Campaign. |
| Hierarquia | `models/region.py`, `subregion.py`, `location.py`; migrações `aq15c1d2e3f4`, `at15g1h2i3j4` | Region > Subregion > Location com `parent_location_id`, assentamentos e interiores. LocationFeature representa características perceptíveis. LocationConnection é o grafo físico; descoberta pertence ao personagem. Setores físicos planetários ainda não existiam. |
| Geração | `world/seed.py`, `generator.py`, `region_content.py`, `content_pools.py`, `neighbor_region.py` | Geração atual usa pools manuais e RNGs derivados por estágio. Cria esqueleto regional e conteúdo com faixas de quantidades. Vizinho recebe continuidade de bioma da âncora; não há campo global físico. Consulta nomes já usados na campanha: resultados completos não são independentes da ordem de materialização. |
| Progressividade | `world/materialization.py`, `materialization_orchestrator.py`, `region_materialization.py` | Existem tiers de locais, detalhes sob demanda e solicitações persistentes de região. Orquestrador gera, conecta, valida e atende pedido na mesma transação. `region_index` é fornecido ao gerador; não é uma coordenada planetária. Reutilizar orquestração e não substituir seu grafo. |
| Exploração | `exploration/service.py`, `travel/service.py`, `discovery/service.py`, `game/engine.py` | Busca ativa usa resolução mecânica, conexões desconhecidas e tempo; chegada registra visita e materializa destino. Viagem calcula custo, duração e risco sobre conexões. `BASE_MINUTES_PER_DISTANCE=15`; não existe contrato que permita tratar essa unidade como metro. |
| Mapa | `api/routes/map.py`, `game/map/service.py`, `view.py`, `planning.py`, `frontend/src/api/map.ts`, `features/map/InteractiveMap.tsx` | Dados vêm de descobertas por personagem e rotas conhecidas. Coordenadas exatas só para locais visitados; escopo, LOD e viewport filtram conteúdo. Frontend normaliza eixos pelas posições visíveis e dispõe locais incertos em anel. Não é projeção métrica planetária. Expor atlas inteiro revelaria fatos desconhecidos. |
| Fronteiras | `models/regional_boundary.py`, `boundary_barrier.py`, `boundary_route.py`, `world/boundaries.py`, `crossing.py`, `cross_region_routes.py`; migração `aw16b1c2d3e4` | Fronteira, barreira e rota são entidades distintas. Acessibilidade considera estação; avaliação de preparação é consultiva, sem nível mínimo. Há caminhos e canon entre regiões. Não é necessário um sistema paralelo de bosses ou fronteiras. Atualizações autônomas arbitrárias por desastres/conflitos ainda precisam de integração específica. |
| Tempo/simulação | `models/campaign.py:WorldTime`, `game/time/clock.py`, `simulation/world_simulation.py`, `scope.py`, `cadence.py`, `world/simulation_integration.py` | Relógio persistente com subminutos, ticks de chegadas, grupos, sociedade, jogadores simulados, NPCs, acontecimentos e conhecimento. Escopo detalhado/relevante/abstrato e população agregada já existem. Região materializada habilita chegadas. Nenhum tick deve percorrer todos os futuros setores. |
| Datasets | `game/creatures/species.py`, `population.py`, `loot_catalog.py`, `app/data/bestiary.json`, `game/economy/shops.py` | Bestiário e saques têm integração real. Arquivos ZIP em `datasets/` não constituem integração de ambientes/geologia. Fauna atual usa tipos de locais, faixas de distância por saltos e pesos de nível; isso requer revisão futura para ecologia independente do ponto inicial. Não foi alterado nesta fase. |
| Narrativa/canon | `ai/retrieval/world_generation.py`, `world/cross_region_canon.py`, `api/routes/campaigns.py` | Retrieval oferece contexto de canon; resolução física nova não chama LLM. A existência dessa capacidade não implica uso por todos os geradores. Narrativa deve receber fatos após resolução mecânica. |
| Saves/exclusão | `game/world/reset.py`, `app/tests/test_campaign_reset.py`, `alembic/env.py` | Exclusão é explícita por dependência. Novas tabelas precisam ser removidas antes da Campaign. Migração atual anterior é `g15g1b2c3d4e` (já presente como alteração local do usuário). |

Havia alterações locais em quests, recompensas, engine, simulação, tipos e interface antes do trabalho. Foram preservadas. Os dois arquivos compartilhados alterados por esta fase (`models/__init__.py` e `world/reset.py`) receberam apenas registro/limpeza das novas tabelas.

## Decisões de arquitetura

### Coordenadas e topologia

V1 usa atlas cilíndrico finito: x periódico, y limitado, coordenadas inteiras em metros do atlas. Padrão: 40.960 km × 20.480 km; setores de 16 km; células macro de 512 km; amostras locais de 4 km. Esses valores configuram resolução e extensão, não quantidades de continentes ou conteúdo. Ambos os eixos são independentes dos `Location.x/y` existentes. Limites de y são limites do atlas técnico, não barreiras de gameplay implementadas.

Não se afirma uma esfera: os extremos y não são polos colapsados e as distâncias não são geodésicas. Para planeta esférico, projetar atlas em faces esféricas ou implementar identificação polar e métrica antes de integrar viagens. A topologia é versionada justamente para impedir reinterpretar coordenadas v1 silenciosamente. Isso será uma nova versão de gerador/configuração, não uma alteração retroativa.

Particionamento usa intervalos semiabertos; a amostra final de cada setor é compartilhada com o próximo. Ponto no extremo superior y pertence ao último setor. x negativo e emendas são normalizados por módulo. Coordenadas fora de y são rejeitadas.

### Planejamento global sem materialização total

Plano persistido contém seed, configuração e identificação do campo macro implícito. Ele determina toda a elevação simplificada sem alocar uma matriz mundial. Nós macro são endereçados por hash de seed, versão, subsistema e coordenadas canônicas. Interpolação smoothstep com aritmética inteira produz elevação contínua, quantizada em metros, inclusive na emenda x. Zero metros é o nível do mar padrão; terras e oceanos emergem do campo, sem selecionar contagens de continentes.

Esta aproximação não identifica continentes conexos, não produz cadeias tectônicas e não garante oceanos navegáveis ou costas realistas. É uma fundação verificável. A versão 1 não deve receber silenciosamente novos algoritmos que alterem esse campo.

### Camadas futuras (proposta, não implementação)

1. **Estrutura planetária e tectônica:** campos globais multiescala de placas e soerguimento, com sementes espaciais e critérios físicos; não escolher uma contagem fixa de continentes. Resolver macrocontornos antes de detalhes. Identidades continentais devem derivar do planejamento global, não da ordem de descoberta.
2. **Relevo/geologia:** compor detalhe com campos globais e restrições macro imutáveis. Formações e materiais recebem proveniência e versão. Relevo autoritativo precede seleção em datasets.
3. **Hidrologia/erosão:** grafo de drenagem macro persistido por bacia; saídas entre bacias/setores são contratos compartilhados. Refinamento local usa halo e condições de contorno globais, evitando rios terminados na borda. Desempate determinístico para depressões/platôs. Não usar apenas ruído local como rio. A solução pode exigir planejamento regional de bacias, sem terreno mundial em alta resolução.
4. **Clima:** latitude/métrica planetária, altitude, oceano, ventos e umidade em baixa resolução; interpolação global. Clima básico difere de estado meteorológico temporal e de bioma selecionado por dataset.
5. **Hierarquia:** continentes físicos > macrorregiões físicas > setores > áreas locais; Region/Subregion existentes continuam como agrupamentos de gameplay, políticos ou culturais e poderão referenciar coberturas de setores. Limite cultural não precisa coincidir com quadrícula.
6. **Streaming:** fila limitada, idempotente e priorizada por proximidade/direção, usando `nearby_sectors`. Um worker processa orçamento fixo por tick; movimento só aguarda destinos necessários. Cancelar preparação não apaga terreno. A fase 0 fornece o plano de vizinhança, sem worker nem carregamento automático.
7. **Simulação distante:** reutilizar `SimulationScope`/cadência. Agregados de população, economia, clima e conflitos por região materializada; checkpoint temporal e catch-up por eventos, sem instanciar locais ou percorrer todos os setores. Eventos sobre fronteiras atualizam entidades já existentes.
8. **Living Frontiers:** reaproveitar RegionalBoundary, BoundaryBarrier, BoundaryRoute e avaliação de travessia. Ancorar barreiras físicas em geografia persistida e condições temporais em eventos. Soluções podem incluir rota alternativa, preparação, construção, combate ou negociação; boss nunca obrigatório por estrutura. Condições mudam por simulação mesmo sem protagonista.

### Contrato futuro com datasets e mapa

Adaptador de dataset recebe configuração/versão, endereço global, relevo, água, clima e geologia disponíveis, com proveniência e campos ausentes explícitos. Retorna candidatos compatíveis, IDs reais do dataset e versão; não pode mudar costa, altitude ou rio para encaixar um candidato. Nenhum candidato é um resultado válido. Não passar nível do protagonista ao seletor de geografia/ecossistemas.

Antes de integrar geração regional, definir um vínculo persistente Region/Location → cobertura/endereço físico. Validar posições e rotas contra terreno, resolver nomes por endereço estável e substituir gradualmente quantidades fixas do gerador antigo apenas para novos mundos opt-in. Sem esse vínculo, atribuir terrenos ao mapa atual produziria contradições. Preservar descobertas, precisão e filtros de conhecimento; nunca expor diretamente o plano autoritativo na API de mapa. Viagem exige conversão explícita entre comprimento métrico e a unidade antiga, seguida de testes de tempo/risco.

## Implementação entregue

| Arquivo | Responsabilidade |
| --- | --- |
| `backend/app/game/world/genesis/__init__.py` | Delimita a camada opt-in. |
| `genesis/config.py` | Configuração imutável estrita, versão e limites de resolução. |
| `genesis/randomness.py` | Entropia por endereço/subsistema, reutilizando `derive_seed`. |
| `genesis/coordinates.py` | Canonização, particionamento, emenda e planejamento limitado de vizinhança. |
| `genesis/geography.py` | Plano implícito e elevação macro determinística; materialização de amostras de setor. |
| `genesis/service.py` | Inicialização explícita, configuração/seed fixadas, recuperação idempotente de setores. |
| `backend/app/db/models/world_genesis.py` | GenesisWorld por Campaign; GenesisSector com chave composta e snapshots JSON. |
| `backend/alembic/versions/h16h1c2d3e4f_add_world_genesis.py` | Migração aditiva de duas tabelas, sem backfill ou mudança de saves. |
| `backend/app/db/models/__init__.py` | Registra e exporta novos modelos. |
| `backend/app/game/world/reset.py` | Remove setores e metadados ao excluir a campanha correspondente. |
| `backend/app/tests/test_world_genesis.py` | Determinismo, continuidade, persistência, limites, compatibilidade e migração. |
| `docs/world-genesis-phase-0.md` | Auditoria, arquitetura, limites e validação. |

Reutilizados efetivamente: Campaign/world_seed, derivação SHA-256, Base/Session SQLAlchemy, convenção transacional, Alembic, exclusão de campanha e fixtures de banco com FKs ativas. Sistemas de fronteira, mapa, descoberta e simulação foram auditados e preservados para a integração futura; não se afirma que já consomem Genesis.

Uso interno após aplicar a migração em ambiente escolhido:

```python
from app.game.world.genesis.service import initialize_world, materialize_sector
from app.game.world.genesis.coordinates import SectorKey, nearby_sectors
from app.game.world.genesis.config import WorldConfig

world = initialize_world(db, campaign_id, WorldConfig())
sector = materialize_sector(db, campaign_id, SectorKey(100, 200))
pending = nearby_sectors(WorldConfig.model_validate(world.config), SectorKey(100, 200))
db.commit()  # chamador controla a transação
```

Inicializar salva apenas o plano/configuração, nenhum setor. Cada chamada de materialização lê ou gera um único setor. No padrão, cada setor salva 25 amostras; memória por geração depende da resolução do setor, não da extensão do mundo. `nearby_sectors` retorna no máximo 81 chaves e não acessa banco. Nenhuma rota pública ou criação automática de campanha foi modificada.

## Persistência, compatibilidade e riscos

- Saves antigos permanecem no gerador atual; migração apenas cria tabelas vazias. Inicializar Genesis é escolha explícita de serviço e não converte a geografia antiga.
- Seed/configuração são fixadas no snapshot; reinicialização divergente falha. Versões desconhecidas são rejeitadas. Suporte a novas versões exige manter dispatch/implementações antigas, sem atualizar registros já salvos.
- Setor existente é recuperado, nunca regenerado. `baseline` separa fatos gerados de `changes`, reservados para acontecimentos. Descobertas continuam nas tabelas existentes, sem segunda fonte de conhecimento. Ainda não há serviço de aplicação/replay de eventos em `changes`; consumidores devem atribuir dicionário novo, pois JSON simples não rastreia mutações internas.
- PK composta impede duplicatas por campanha/coordenada canônica. Chamadas concorrentes ao mesmo setor podem gerar IntegrityError; chamador deve rollback/reler ou serializar a fila. Worker com retentativas ainda planejado. Não há lock distribuído implementado.
- Persistência cresce com setores visitados/preparados, não com área total. Compactação, descarregamento de cache, cotas e observabilidade precisam ser definidos antes de streaming em produção.
- A migração depende da revisão local `g15g1b2c3d4e`, já existente no início do trabalho. Essa revisão precisa acompanhar a entrega; reconciliar a cadeia ao integrar em outro branch. Banco real `everreach.db` não foi migrado nesta tarefa.
- Nenhuma simulação geológica fictícia, integração dos ZIPs, fauna adicional ou conteúdo de preenchimento foi incluído. Continentes reconhecidos, hidrologia, clima, esfera, ecologia, simulação distante por setor e ligação ao mapa permanecem planejados.

## Validação

Testes em `app/tests/test_world_genesis.py`: reprodução entre processos com PYTHONHASHSEED diferente; isolamento por subsistema/seed/versão; geração em ordem inversa em duas campanhas; arestas iguais em x/y e emenda global; vizinhança de um metro nas emendas macro; partição e validação de configuração; ausência de geração global antecipada; recarga em outra Session; preservação de alterações; proibição de regenerar snapshot existente; rollback e exclusão isolada; versões desconhecidas; upgrade/downgrade em banco temporário com campanha legada preservada.

Regressão selecionada: world_generation_metadata, region_skeleton, neighbor_region_materialization, regional_boundaries, cross_region_routes, exploration, explore_action, map_view, map_view_route, world_simulation_integration, simulation_scope e campaign_reset.

Resultados: **18 testes novos passaram** e **58 testes de regressão passaram** (76 no total). Upgrade e downgrade foram executados somente em banco temporário, construído a partir da cadeia Alembic real. `alembic heads` encontrou uma única cabeça, `h16h1c2d3e4f`; `git diff --check` passou. Há aviso preexistente de depreciação Starlette/httpx. Não foi executada a suíte completa do backend nem a suíte frontend; nenhuma interface foi alterada. Vetores fixos de seed e elevação protegem o contrato v1 contra mudanças acidentais futuras.

## Próxima etapa recomendada

Definir a métrica/topologia planetária definitiva e o contrato espacial Region/Location sem alterar saves antigos. Depois adicionar um fluxo opt-in de criação de novos mundos, que planeje o macroterritório e gere apenas os setores necessários ao início. Essa etapa deve validar um percurso cruzando setores e a emenda global, com mapa respeitando descoberta e persistência após reabertura, antes de integrar datasets ou hidrologia refinada.
