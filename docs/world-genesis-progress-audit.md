# Auditoria de progresso do World Genesis

**Data:** 27 de outubro de 2026. **Escopo:** checkout local de `D:\Games\Codigo\vrmmo`, documentos, código, catálogos extraídos e ZIP, histórico Git, resultados existentes e banco local consultado somente para leitura.

Esta auditoria não implementou sistemas, não recalibrou geradores, não executou migrações nem ativou campanhas. Sua única alteração autorizada é este documento. Não foram executadas suítes de testes nem gerados novos mundos. Foram usadas inspeção estática, leitura de resultados existentes e consultas SQLite `mode=ro&immutable=1`.

## A. Resumo executivo

**O World Genesis possui uma fundação procedural extensa e funcional em ambientes experimentais, mas ainda não está concluído como fornecedor do mundo explorado pela campanha normal.** O principal trabalho restante é conectar essa fundação ao jogo e estabelecer conteúdo natural visitável; não construir outro simulador de clima, tectônica ou botânica.

Há implementações de geografia esférica V4, terreno T1, geologia J1/JR1, clima C3 R1-55, hidrologia/balanços H1/HR1/W1/W2/P1, ambientes E1 e vegetação Vg2/R1/L1/L2/S1/GA1/GA2. Elas têm serviços, persistência e testes, incluindo provas com espécies e nascimentos reais. Isso é diferente de estarem ligadas ao fluxo normal de criação e exploração.

**As lacunas comprovadas mais importantes são:**

1. **Schema local incompatível com o código atual.** `backend/everreach.db` tem duas campanhas, revisão Alembic `f15f1a2b3c4d`, nenhuma tabela `genesis_*` e ausência das colunas R1 de `item_instances`. Há **19 revisões pendentes** até `y33y6t7u8v9w`: uma anterior ao Genesis e dezoito da cadeia Genesis. Nenhuma foi aplicada nesta auditoria.
2. **Não há inicialização normal da cadeia Genesis.** A criação/start usa `world/seed.py`, seus pools e o grafo legado. Não escolhe V4/C3/Vg2/GA1/GA2 nem ancora automaticamente os locais no planeta.
3. **Existe API de ações vegetais, mas não seu percurso completo no frontend.** `plant_action` chega ao backend, resolve encontro/coleta/remoção e participa do undo. O cliente web envia texto e técnica; não envia esse contrato vegetal. A precisão de peso do inventário já recebeu integração parcial.
4. **Hidrologia técnica não equivale a rios e lagos exploráveis.** Há drenagem, geometria, contas finitas e uma transferência local demonstrada. Não há geração integrada de corpos hídricos com dimensão, estado e acesso pelo personagem em toda a campanha.
5. **Fauna planetária continua sem integração ambiental.** Há caça legada jogável com um bestiário ativo de 250 criaturas. Não foi encontrado consumidor que distribua populações animais por V4/E1/Vg2. O bestiário de 500 criaturas está no ZIP, sem estar ativo nesse fluxo.
6. **Microambientes/extremos e locais especiais físicos ainda não têm um produtor operacional integrado.** A taxonomia e as 96 espécies extremas existem, assim como POIs legados; isso não constitui geração dos novos locais naturais/fantásticos do Genesis.

**Estamos avançados na infraestrutura, mas ainda distantes de declarar o MVP do World Genesis fechado.** A distância não corresponde a dezenas de novas fases científicas: concentra-se em integração jogável, conteúdo natural local e distribuição ambiental de fauna. Não há base documental para atribuir um percentual honesto de conclusão ou dizer que “basta implementar fauna”.

**Próxima implementação recomendada:** uma única fatia vertical de **campanha nova explicitamente opt-in**, do início à observação/coleta vegetal e revisita usando as autoridades existentes. A seção I delimita essa tarefa; esta auditoria não a iniciou.

## B. Roadmap original recuperado

### B.1. O que foi encontrado — e o que não foi

Foi encontrado o documento original de fundação, [World Genesis — fase 0](world-genesis-phase-0.md), e conferido o pedido original fornecido no anexo `67a4cd11-122d-4831-bde2-f1d26b33ac7d/Pasted text.txt`, fora do repositório. Esse pedido define princípios e áreas de arquitetura, mas **não contém uma sequência completa de futuras fases numeradas até a conclusão**.

O pedido original abrange: coordenadas/escala; seed; estrutura planetária; relevo/tectônica/geologia; hidrologia/erosão/clima; hierarquia física; geração incremental; persistência/versionamento; simulação distante; integração com datasets; Living Frontiers; integração futura com mapa e exploração. Menciona enriquecimento posterior por ambientes, materiais, flora, fauna e civilizações. A primeira implementação solicitada é apenas a fundação.

O documento da fase 0 organiza uma **proposta de camadas futuras**, nesta ordem: estrutura planetária/tectônica; relevo/geologia; hidrologia/erosão; clima; hierarquia; streaming; simulação distante; Living Frontiers. O contrato com datasets e mapa vem em seguida. Essas camadas não são fases numeradas aprovadas; a ordem efetivamente executada depois mudou — por exemplo, hidrologia/clima precederam T1 e J1.

**Não foram encontrados:** um documento mestre com todo o roadmap numerado do World Genesis; uma fase futura formalmente denominada “1.2 — Fauna”; uma fase numerada de “Locais Fantásticos”; um arquivo separado de fase 0.1. As referências posteriores a “0.1 concluída” correspondem à fundação documentada como fase 0. Não foi inventado um documento ou número para essas lacunas.

O [README](../README.md) contém o roadmap geral do RPG, com fases 1–14, além do histórico de vila/caça. Comentários de código preservam nomes como Phase 15/16/17 para geração regional, fronteiras e exploração. **Essa numeração do RPG não é a série 0.x/1.x do World Genesis.** Não foi recuperada a especificação completa dessas fases gerais apenas a partir de seus nomes.

Pesquisa do histórico Markdown em todos os refs Git encontrou somente `README.md` e os documentos Genesis 0, 0.2 e 0.3. Os demais relatórios existem no checkout, mas não estão registrados como arquivos versionados nesse histórico. O HEAD observado foi `14b820a` (“feat: implement quest objective progress tracking”). A auditoria cobre o código de trabalho atual, não apenas esse commit.

### B.2. Sequência real documentada, sem renumerar

| Ordem documentada | Entrega/nomenclatura preservada | Referência |
|---|---|---|
| Fundação 0, posteriormente chamada 0.1 | Atlas v1, seeds, setores e persistência mínima | [fase 0](world-genesis-phase-0.md) |
| 0.2 | Topologia esférica v2 e contrato espacial | [fase 0.2](world-genesis-phase-0.2.md) |
| 0.3 → 0.3.1 → 0.3.2 | Formação V3; validação/costa R1; correção por área e V4 | [0.3](world-genesis-phase-0.3.md), [0.3.1](world-genesis-phase-0.3.1.md), [0.3.2](world-genesis-phase-0.3.2.md) |
| 0.4 → 0.4.1 | Hidrologia H1 e refinamento HR1 | [0.4](world-genesis-phase-0.4.md), [0.4.1](world-genesis-phase-0.4.1.md) |
| 0.5 → 0.5.1 | Clima C1; auditoria e calibração C2 | [0.5](world-genesis-phase-0.5.md), [0.5.1](world-genesis-phase-0.5.1.md) |
| 0.6 | Balanço hídrico W1 | [fase 0.6](world-genesis-phase-0.6.md) |
| 0.7 → 0.7.1 → 0.7.2 → 0.7.3 | Terreno T1; hidrografia G1; reconciliação W2; fechamento prático P1 | [0.7](world-genesis-phase-0.7.md), [0.7.1](world-genesis-phase-0.7.1.md), [0.7.2](world-genesis-phase-0.7.2.md), [0.7.3](world-genesis-phase-0.7.3.md) |
| 0.8 → 0.8.1 | Integração D14/J1; geologia regional JR1 e calibração de fontes | [0.8](world-genesis-phase-0.8.md), [0.8.1](world-genesis-phase-0.8.1.md) |
| 0.9 | Ambientes E1 | [fase 0.9](world-genesis-phase-0.9.md) |
| Auditoria após E1; 0.9.1 e ajuste final | Diagnóstico climático; C3; seleção de R1-55 | [auditoria](world-genesis-climate-audit-after-e1.md), [0.9.1](world-genesis-phase-0.9.1.md), [ajuste final](world-genesis-c3-final-validation.md) |
| 0.9.2 | Compatibilidade hídrica C3 R1-55 com W1/W2/P1 | [fase 0.9.2](world-genesis-phase-0.9.2.md) |
| 1.0 → 1.0.1 → 1.0.2 | Flora Vg1; composição/cobertura Vg2; recursos R1 e coleta | [1.0](world-genesis-phase-1.0.md), [1.0.1](world-genesis-phase-1.0.1.md), [1.0.2](world-genesis-phase-1.0.2.md) |
| 1.1 → 1.1.1 → 1.1.2 | L1; renovação L2; S1, estrutura VSR1 e estabilização | [1.1](world-genesis-phase-1.1.md), [1.1.1](world-genesis-phase-1.1.1.md), [1.1.2](world-genesis-phase-1.1.2.md) |
| Revisão geral AP1 → GA1 → GA2 | Direção de fantasia/gameplay; maturação curta; reposição e estabelecimento curtos | [AP1](world-genesis-gameplay-policy.md), [revisão/GA1](world-genesis-gameplay-review.md), [GA2](world-genesis-ga2.md) |

Essas subfases de refinamento e políticas foram acrescentadas ao longo do desenvolvimento. Não há evidência de que a sequência detalhada inteira já estivesse prevista no pedido de fase 0.

### B.3. Qual orientação prevalece

1. **AP1 é a direção de design atual:** diversão, exploração, variedade e consequências; realismo apenas quando agrega valor. As propostas anteriores de rigor científico ou workers de streaming não tornam essas soluções obrigatórias para o MVP.
2. **C3 R1-55 é a referência experimental atual**, não o candidato C3 de 45% recomendado em uma versão anterior do relatório. O código confirma isso em `water/config.py:check_climate_contract`: C3 com W1 exige `ClimateConfigV3R1` e `land_recycling_ppm=550000`.
3. **GA1/GA2 não apagam L1/L2/S1 anteriores.** São políticas assinadas; as versões antigas continuam compatíveis. `regional_canopy_v2` permanece a referência de composição vegetal.
4. **README não é prova suficiente de ativação.** A seção antiga “fora do MVP” ainda exclui geração complexa/mapa gráfico, enquanto há código posterior de Genesis e mapa. O código atual e as decisões específicas mais recentes prevalecem; o roadmap geral declarado “COMPLETE” não encerra World Genesis.

## C. Matriz de progresso

### C.1. Como ler a classificação

- **CONCLUÍDO:** escopo delimitado da entrega comprovado; não significa que o planeta inteiro ou sua ativação normal estejam concluídos.
- **IMPLEMENTADO EXPERIMENTALMENTE:** código, contratos, persistência/testes ou provas isoladas existem, mas o uso normal depende de ativação/integração ou validação de gameplay.
- **PARCIAL:** componentes úteis existem, faltando requisito importante da etapa ampla.
- **NÃO INICIADO:** não foi encontrado implementador relevante para o objetivo específico.
- **NÃO VERIFICADO:** evidência insuficiente para confirmar a exigência ou sua conclusão.

Os testes citados foram inspecionados como código; os resultados históricos foram lidos nos artefatos/logs. Nenhuma contagem significa execução de toda a suíte agora. Código experimental pode ter sua entrega técnica concluída sem estar disponível nas duas campanhas do banco local.

### C.2. Fases implementadas e auditorias

Nos caminhos abaixo, o diretório-base é `backend/app/game/world/genesis/` quando não houver outro prefixo.

| Fase / objetivo | Situação | Implementação e evidência concreta | Persistência/testes | Pendência para o jogador |
|---|---|---|---|---|
| 0/0.1 — fundação v1 | **CONCLUÍDO**, no escopo mínimo opt-in | [service.py](../backend/app/game/world/genesis/service.py): `initialize_world`, `materialize_sector`; `coordinates.py`, `randomness.py`, `geography.py` | `GenesisWorld`, `GenesisSector`; [test_world_genesis.py](../backend/app/tests/test_world_genesis.py) | Não há chamada no start normal. O default de `initialize_world` ainda é `WorldConfig` v1, não V4. |
| 0.2 — esfera e associação espacial | **IMPLEMENTADO EXPERIMENTALMENTE** | [sphere_topology.py](../backend/app/game/world/genesis/sphere_topology.py), `sphere_metric.py`; [spatial.py](../backend/app/game/world/genesis/spatial.py): `bind_location`, `add_coverage`, `prepare_location_sector`; `spatial_view.py:known_spatial_locations` | `GenesisSphereSector`, `EntitySpatialCoverage`, `LocationSpatialAnchor`; [test_genesis_spatial_integration.py](../backend/app/tests/test_genesis_spatial_integration.py) | Âncoras/coberturas são explícitas; não há vinculação automática de Region/Location ou consumo pelo mapa/viagem normal. |
| 0.3 — formação V3 | **IMPLEMENTADO EXPERIMENTALMENTE** | [formation_plan.py](../backend/app/game/world/genesis/formation_plan.py): plano/identidades macro; `formation_tectonics.py`, `formation_geography.py` | Plano em `GenesisWorld`, snapshots; [test_genesis_formation.py](../backend/app/tests/test_genesis_formation.py) | Geografia física não dirige o gerador regional legado. V3 preservada, não é a referência nova V4. |
| 0.3.1 — validação geográfica/costa R1 | **CONCLUÍDO**, como validação/refinamento técnico | [coast_refinement.py](../backend/app/game/world/genesis/coast_refinement.py), `validation_report.py`; [test_genesis_geographic_validation.py](../backend/app/tests/test_genesis_geographic_validation.py); amostras em `artifacts/planet-validation-0.3.1/` | IDs macro preservados, refinamento subordinado | Não constitui costa navegável, canais ou sistema de locais exploráveis. |
| 0.3.2 — distribuição tectônica V4 | **CONCLUÍDO**, como correção versionada | [formation_v4.py](../backend/app/game/world/genesis/formation_v4.py): `nucleate_plates_v4`, pesos de área e amostragem esférica; [test_genesis_formation_v4.py](../backend/app/tests/test_genesis_formation_v4.py) | Dispatch e planos antigos preservados; `artifacts/tectonic-distribution-0.3.2/` | V4 continua opt-in; não há motivo encontrado para reabrir sua calibração. |
| 0.4 — drenagem H1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [hydrology/plan.py](../backend/app/game/world/genesis/hydrology/plan.py), `drainage.py`, `service.py:initialize_hydrology` | `GenesisHydrologyPlan`/setores; [test_genesis_hydrology_persistence.py](../backend/app/tests/test_genesis_hydrology_persistence.py) | Drenagem/armazenamento potencial, não rios perenes ou lagos visitáveis. |
| 0.4.1 — HR1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [hydrology/regional.py](../backend/app/game/world/genesis/hydrology/regional.py), `regional_graph.py`, `regional_service.py` | Regiões/portas assinadas; [test_genesis_hydrology_regional.py](../backend/app/tests/test_genesis_hydrology_regional.py) | Rotas regionais amostradas não são automaticamente leitos locais utilizáveis. |
| 0.5 — C1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [climate/plan.py](../backend/app/game/world/genesis/climate/plan.py), `physics.py`, `query.py`, `service.py` | Planos/setores climáticos; [test_genesis_climate_persistence.py](../backend/app/tests/test_genesis_climate_persistence.py) | Versão histórica; novos mundos de referência precisam do preset C3 correto, explicitamente. |
| 0.5.1 — calibração C2 | **CONCLUÍDO**, como auditoria/calibração versionada | [climate/v2.py](../backend/app/game/world/genesis/climate/v2.py), `calibration.py`; [test_genesis_climate_v2.py](../backend/app/tests/test_genesis_climate_v2.py) | Dispatch C1/C2, persistência e comparações históricas | C2 não é convertido automaticamente nem deve ser renomeado para C3. |
| 0.6 — W1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [water/balance.py](../backend/app/game/world/genesis/water/balance.py): `solve`; `plan.py`, `service.py` | Balanços/estoques; [test_genesis_water.py](../backend/app/tests/test_genesis_water.py), persistência | Disponibilidade regional não é estoque hídrico acessível em cada ponto do personagem. |
| 0.7 — T1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [terrain/field.py](../backend/app/game/world/genesis/terrain/field.py): campo de altura; `service.py:initialize_terrain`, `query_altitude`; `geometry.py` | `GenesisTerrainPlan`/tiles; [test_genesis_terrain.py](../backend/app/tests/test_genesis_terrain.py) | Não há movimento normal sobre a esfera, conversão de distâncias ou rotas ajustadas ao terreno. |
| 0.7.1 — hidrografia local G1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [hydro_geometry/geometry.py](../backend/app/game/world/genesis/hydro_geometry/geometry.py), `depressions.py`, `service.py`; [test_genesis_hydro_geometry.py](../backend/app/tests/test_genesis_hydro_geometry.py) | Geometria/evidências persistidas | Depressão ou seção amostrada não instancia corpo hídrico explorável. Há estados `pending_*` explícitos. |
| 0.7.2 — W2 | **IMPLEMENTADO EXPERIMENTALMENTE** | [water_reconciliation/ledger.py](../backend/app/game/world/genesis/water_reconciliation/ledger.py), `service.py`, `events.py` | Domínios, revisões, transferências; [test_genesis_water_reconciliation_persistence.py](../backend/app/tests/test_genesis_water_reconciliation_persistence.py) | Reconciliação não cria automaticamente rios/lagos, acesso ou recarga temporal contínua. |
| 0.7.3 — P1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [water_reconciliation/practical/service.py](../backend/app/game/world/genesis/water_reconciliation/practical/service.py): `prepare_natural_passage`, `reconcile_practical`; `allocation.py`, `hydraulics.py` | Contas locais/capacidades; [test_genesis_practical_hydrology_persistence.py](../backend/app/tests/test_genesis_practical_hydrology_persistence.py) | Prova de episódio local não é uma rede hidrográfica explorável. `future.py` tem propostas F1 com `credit_authorized=False`. |
| 0.8 — J1/D14 | **IMPLEMENTADO EXPERIMENTALMENTE** | [geology/field.py](../backend/app/game/world/genesis/geology/field.py), `adapter.py:evaluate_opportunities`, `service.py:materialize_test_deposit` | Unidades/jazidas finitas; [test_genesis_geology.py](../backend/app/tests/test_genesis_geology.py) | Fonte técnica não assegura exposição, descoberta ou mineração pelo jogador. |
| 0.8.1 — JR1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [geology/regional/field.py](../backend/app/game/world/genesis/geology/regional/field.py), `occurrence.py`, `service.py:materialize_regional_formation` | Formações/fontes regionais; [test_genesis_geology_regional_persistence.py](../backend/app/tests/test_genesis_geology_regional_persistence.py) | Consulta declara `access_authorized=False`; fontes dependem de política experimental. Extração jogável não está integrada aqui. |
| 0.9 — E1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [environment/adapter.py](../backend/app/game/world/genesis/environment/adapter.py): `EnvironmentSampler`; `classifier.py`, `service.py` | Probes/mosaicos; [test_genesis_environment.py](../backend/app/tests/test_genesis_environment.py), persistência | Potencial ambiental não é vegetação/água/caverna confirmada. 100 construídos e 50 anômalos têm contratos, não geradores de locais. |
| Auditoria após E1 | **CONCLUÍDO**, como diagnóstico | [test_climate_after_e1_audit.py](../backend/app/tests/test_climate_after_e1_audit.py), `scripts/audit_climate_after_e1.py` | Relatório/artefatos em `artifacts/climate-audit-after-e1/` | Parecer histórico não autoriza ativação global. |
| 0.9.1 e ajuste final — C3 R1-55 | **IMPLEMENTADO EXPERIMENTALMENTE**; auditorias concluídas | [climate/v3.py](../backend/app/game/world/genesis/climate/v3.py): `ClimateConfigV3R1`; `dispatch.py`; [test_genesis_climate_c3_final.py](../backend/app/tests/test_genesis_climate_c3_final.py) | Assinaturas, comparação C2/C3 e cinco seeds | Não há seleção desse clima na criação normal de campanha. |
| 0.9.2 — água sob C3 | **IMPLEMENTADO EXPERIMENTALMENTE** | [water/config.py](../backend/app/game/world/genesis/water/config.py): `WaterConfigC3R155`, `check_climate_contract`; [test_genesis_water_c3.py](../backend/app/tests/test_genesis_water_c3.py) | Balanços e persistência C2/C3 distintos; `artifacts/water-c3-compatibility/` | Compatibilidade técnica entregue, sem liberar automaticamente contas/campanhas reais. |
| 1.0 — Vg1 e v22 | **IMPLEMENTADO EXPERIMENTALMENTE** | [vegetation/catalog.py](../backend/app/game/world/genesis/vegetation/catalog.py), `field.py:VegetationSampler`, `service.py` | Comunidades, indivíduos, recibos; [test_genesis_vegetation.py](../backend/app/tests/test_genesis_vegetation.py), persistência | Espécies comuns reais geradas; categorias/extremos com bloqueios. Não entra automaticamente na região inicial. |
| 1.0.1 — Vg2 | **IMPLEMENTADO EXPERIMENTALMENTE** | [vegetation/v2.py](../backend/app/game/world/genesis/vegetation/v2.py): `VegetationSamplerV2`, coortes regionais, cobertura/estratos; [test_vegetation_calibration_v2.py](../backend/app/tests/test_vegetation_calibration_v2.py) | Mesmas tabelas com descritor novo, saves Vg1 preservados | Continuidade visual técnica demonstrada, mas ausência de integração a paisagens/locais do frontend. |
| 1.0.2 — R1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [vegetation/resources.py](../backend/app/game/world/genesis/vegetation/resources.py), `actions.py:resolve_plant_action`; [rota actions](../backend/app/api/routes/actions.py) | Estoques, massa/pools, recibos e undo; [test_plant_resources_r1.py](../backend/app/tests/test_plant_resources_r1.py) | API funciona em ambiente preparado. Faltam schema de implantação, âncora/contexto e fluxo frontend. Peso já tem apresentação genérica no inventário. |
| 1.1 — L1 | **IMPLEMENTADO EXPERIMENTALMENTE** | [vegetation/lifecycle.py](../backend/app/game/world/genesis/vegetation/lifecycle.py): `initialize_life`, `project`, `disperse`, `sync`; `life_math.py` | Estados/eventos; [test_vegetation_lifecycle_l1.py](../backend/app/tests/test_vegetation_lifecycle_l1.py) | Perfil histórico de dias ativos; GA1 é a alternativa de ritmo. Não há população L1 na campanha local auditada. |
| 1.1.1 — L2 | **IMPLEMENTADO EXPERIMENTALMENTE** | [vegetation/renewal.py](../backend/app/game/world/genesis/vegetation/renewal.py), `renewal_batch.py` | Fronteira ecológica, bancos, ocupação, eventos; [test_vegetation_renewal_l2.py](../backend/app/tests/test_vegetation_renewal_l2.py) | Política histórica lenta preservada; não equivale a renovação ativada no jogo normal. |
| 1.1.2 — S1 e VSR1 | **IMPLEMENTADO EXPERIMENTALMENTE**; estabilização técnica comprovada | [vegetation/sexual.py](../backend/app/game/world/genesis/vegetation/sexual.py), `recovery_structure.py:measure_community`; [test_vegetation_stabilization_s1.py](../backend/app/tests/test_vegetation_stabilization_s1.py) | S1 assinada, estrutura derivada e 260 casos históricos no manifesto | Autorização reprodutiva não materializa habitat; VSR1 não é renderização. |
| AP1 e GA1 | **CONCLUÍDO** como direção AP1; **IMPLEMENTADO EXPERIMENTALMENTE** como GA1 | [política AP1](world-genesis-gameplay-policy.md); [growth_gameplay.py](../backend/app/game/world/genesis/vegetation/growth_gameplay.py): `LifeConfigGA1`, `attach_profile`; [test_vegetation_growth_ga1.py](../backend/app/tests/test_vegetation_growth_ga1.py) | Configuração/assinatura sem migrar perfis anteriores | Maturação em dias/semanas existe, mas não é preset normal de criação. |
| GA2 | **IMPLEMENTADO EXPERIMENTALMENTE** | [renewal_gameplay.py](../backend/app/game/world/genesis/vegetation/renewal_gameplay.py): `initialize_ga2`, `advance_ga2`, `materialize_child`; [test_vegetation_renewal_ga2.py](../backend/app/tests/test_vegetation_renewal_ga2.py) | Bancos/eventos/ocupantes compactos, hidratação, rollback/undo; 60 provas e 113 testes históricos no manifesto | Sem bootstrap/UI normal. Custo de catch-up e recuperação incompleta continuam relevantes para playtest. |

### C.3. Itens do planejamento amplo ainda abertos

| Objetivo recuperado / sistema conhecido | Situação | Evidência e limite atual |
|---|---|---|
| Hierarquia física ligada a Region/Subregion/Location | **PARCIAL** | Identidades físicas e `EntitySpatialCoverage`/`LocationSpatialAnchor` existem; a geração regional normal não os preenche. Uma Region não foi transformada automaticamente em continente. |
| Geração progressiva durante deslocamento | **PARCIAL** | `materialize_sector`, `location_preparation_plan` e `nearby_cells` existem. `travel/service.py` usa `ensure_location_materialized`, não `prepare_location_sector`. Não há streaming planetário ligado à chegada. |
| Terreno efetivamente navegável pelo personagem | **PARCIAL** | T1 tem altura e geometria; a navegação jogável continua no grafo legado, sem contrato métrico planetário integrado. |
| Corpos hídricos exploráveis | **PARCIAL** | H1/HR1/G1/W1/W2/P1 são reutilizáveis; falta instanciar local, contorno/dimensões, estado e uso mecânico de corpos hídricos no mapa/região. Locations legadas `river` não comprovam esse vínculo. |
| Microambientes e flora extrema | **PARCIAL** | Há 96 espécies, 16 ambientes extremos e auditoria de evidências. `vegetation/field.py:eligibility` devolve pendência incondicional para `extreme_json`; `extreme_evidence` não possui caminho de materialização positiva. Gerador canônico de microambientes: **NÃO INICIADO** no código encontrado. |
| Locais especiais/formações naturais exploráveis | **PARCIAL** | `world/generator.py:generate_pois`, `content_pools.py` e Location/LocationFeature geram locais legados; E1 e 6A fornecem candidatos/semântica. Falta um produtor que una formação natural Genesis, identidade persistente, localização e descoberta. |
| Dataset dedicado “Locais Fantásticos” | **NÃO INICIADO / não encontrado localmente** | Não existe arquivo identificado com esse papel no checkout ou pacote inspecionado. Há fontes parciais reutilizáveis; ver D. Não existe número de fase original comprovado para sua criação. |
| Fauna e populações animais ambientais | **PARCIAL** | Caça legada tem `creatures/population.py`, NPCs, combate e loot. Adaptador/distribuição populacional V4/E1/Vg2: **NÃO INICIADO** no código encontrado. Fauna pertence ao enriquecimento natural mencionado no pedido original, sem fase futura numerada recuperada. |
| Descobertas e mapa consumindo o planeta | **PARCIAL** | Mapa/descoberta individuais funcionam no RPG; `known_spatial_locations` é um adaptador interno não usado na API de mapa. Não há Atlas Genesis público. |
| Living Frontiers geográficas/dinâmicas | **PARCIAL** | Modelos e serviços `boundaries.py`, `crossing.py`, rotas e orquestração regional existem. Não há consumidor Genesis que derive barreiras do terreno/eventos e as incorpore à exploração normal. Não foi comprovado uso ativo de todos esses serviços antigos. |
| Simulação distante de territórios naturais | **PARCIAL** | Escopo/cadência do RPG existem; vegetação tem catch-up sob demanda. Não existe uma simulação natural planetária integrada nem ela é obrigatória como loop global para concluir o MVP. |
| Civilizações/povoamentos ambientais completos | **NÃO VERIFICADO** como exigência interna integral do Genesis | O pedido original menciona enriquecimento futuro; não foi encontrado um plano de fase delimitando a responsabilidade. Há assentamentos/NPCs/organizações legados e 6A/B/C no ZIP, sem integração ambiental Genesis. Não se exige aqui recriar esses outros subsistemas. |

### C.4. O que as provas atuais realmente confirmam

Foram lidos [o manifesto GA2](../artifacts/vegetation-ga2/validation.json), seus logs, [a estabilização S1](../artifacts/vegetation-stabilization-1.1.2/validation.json), [a revisão GA1](../artifacts/genesis-gameplay-review/validation.json) e os manifests/relatórios de E1 e R1. Exemplos históricos conferidos:

- GA2: **113 casos distintos** no escopo afetado, sendo 25 GA2 e 88 anteriores; sessenta campanhas isoladas, trinta pares com remoções físicas idênticas. A execução de 88 anteriores registrou `88 passed` em 496,51 s. A contagem não deve ser somada aos 825/906 de relatórios antigos como se fossem casos distintos adicionais.
- Na seed 42, após 700 remoções de uma população de 1.037 árvores: 337 sobreviventes, 353 vivos no dia 15, 377 no dia 30, 420 no dia 60, 426 no dia 90 e 438 no dia 180. GA2 mantém as mortes e não restaura automaticamente 700 adultos.
- A comparação GA2 de sessenta dias levou aproximadamente 1,63 s de atualização/consulta; dez anos, 6,62 s, com preparação medida separadamente. Esses são benchmarks técnicos históricos, não tempo fim a fim do frontend nem garantia para qualquer região.
- P1 tem demonstração histórica de passagem T1 de 2,772 m, com 19 L entregues e 11 L para molhamento. Isso não comprova um rio perene ou um lago visitável.
- R1 tem provas de trinta coletas em cinco bancos, massas positivas, replay, persistência e undo. Isso comprova a mecânica quando preparada, não sua disponibilidade no start normal.

Não foram executadas novas simulações ou reabertos esses bancos de prova para alterar seu estado. A validação do produto completo permanece **NÃO VERIFICADA**, e a incompatibilidade de schema local é um bloqueio concreto anterior a esse playtest.

## D. Datasets — inventário e integração real

### D.1. Fontes extraídas e consumidores ativos no código

| Dataset / localização | Entradas verificadas e versão | Consumidor / cobertura real | Limites |
|---|---|---|---|
| [`datasets/00_Taxonomia_Ambientes/`](../datasets/00_Taxonomia_Ambientes/) | EV-ECO-1.1.1 ativo: **250** IDs = 100 naturais, 100 construídos, 50 anômalos; taxonomia-base 1.1 e regras 1.1.1 | `environment/catalog.py` verifica manifesto/hashes; `NaturalClassifier` e `EnvironmentSampler` classificam naturais e contratos especiais | Construídos/anômalos não são criados pelo catálogo. Ambiente potencial não é local/água/vegetação estabelecida. |
| [`datasets/02_Flora/`](../datasets/02_Flora/) | Pacote v22; fonte de flora **v7.2**, não “schema 22”: **3.096 espécies**, 3.096 perfis, **6.192 partes/itens**, 96 novas extremas em 16 ambientes e oito extensões de habitat | `vegetation/catalog.py` faz pin por SHA; Vg1/Vg2, R1, L1/GA1, L2/S1/GA2 usam IDs reais | Nem toda espécie é estabelecível. Extremas, aquáticas e dependentes de suportes/energia locais têm bloqueios. 2.930 rotas reprodutivas ordinárias não significam 2.930 espécies presentes em cada mundo. |
| [`datasets/11_Geologia_Materiais_D14/`](../datasets/11_Geologia_Materiais_D14/) | D14 v4: **120 materiais**, 14 propriedades por material e **360 perfis de extração** | `geology/catalog.py`, `adapter.py`, J1/JR1 e oportunidades/fontes finitas | Perfis de extração cadastrados não são um fluxo de mineração jogável. Lendários/condições excepcionais não são sorteados genericamente. |
| [`datasets/11_Geologia_Materiais_D14_Complemento_v4_1/`](../datasets/11_Geologia_Materiais_D14_Complemento_v4_1/) | Extensão v4.1: **20 substratos**, **18 pontes**, **24 origens alternativas** | Adaptador e história J1/JR1; deduplicação de oportunidade por unidade/material | Complementa, não substitui os 120 materiais. Exposição/acesso reais ainda não decorrem automaticamente da reserva. |
| [`backend/app/data/bestiary.json`](../backend/app/data/bestiary.json) | Bestiário ativo `schema_version=1.0.0`: **250 monstros**, **713 itens**, dez biomas | `creatures/species.py:BESTIARY_PATH`, `population.py`, `loot_catalog.py` e colheita de corpos | Integração legada por tipo de Location e distância em trilhas. Não consome E1/Vg2 nem o catálogo de 500 do ZIP. O comentário antigo de “225 criaturas” no módulo está desatualizado em relação ao JSON lido. |

### D.2. Conteúdo disponível somente dentro do pacote ZIP

O arquivo [`datasets/Everreach_TODOS_Datasets_Flora_Extrema_v22.zip`](../datasets/Everreach_TODOS_Datasets_Flora_Extrema_v22.zip) contém **61 arquivos**. Sua presença foi verificada abrindo o diretório ZIP e lendo JSONs **sem extrair ou modificar arquivos**. Contém também cópias das fontes já extraídas acima. O prefixo “TODOS” não demonstra integração automática.

| Pasta/arquivo interno | Conteúdo contado | Relação com Genesis e integração encontrada |
|---|---|---|
| `01_Bestiario/Everreach_Bestiario_500_Anatomia_Aproveitamento_v7.json` | **500 monstros**, **810 itens**, dez biomas e modelo de aproveitamento v7 | Material disponível para futura fauna; não é a fonte carregada pelo backend atual. |
| `01_Bestiario/Everreach_Expansao_250_Monstros_Novos_v3.json` | 250 monstros, 97 itens | Expansão separada; não somar cegamente aos 500 como 750 espécies distintas. Não foi encontrado importador ativo desses arquivos. |
| `03_Diretor_de_Missoes/...430_Povos_v3.json` | 430 modelos e 38 papéis de moradores | Conteúdo de missões; consumidor desse arquivo não encontrado. Missões legadas existem, mas não comprovam importação. Subsistema externo ao núcleo físico. |
| `04_Economia_e_Oficios/...2220...v4.json` | 1.000 mercadorias, 150 serviços, 120 ofícios, 500 receitas, 250 perfis de estoque, 200 de demanda | 2.220 registros propostos; consumidor desse arquivo não encontrado. Economia/crafting não são pendência interna obrigatória do Genesis inteiro. |
| `05_NPCs/Aparencia_Fisica/...2000...v3.json` | 2.000 atributos e 80 exemplos | Catálogo de apresentação, não 2.000 NPCs existentes. Fora da geração natural. |
| `05_NPCs/Personalidades/...1000...v2.json` | Dez listas de 100 entradas: **1.000 traços/elementos**; 48 perfis ilustrativos | São catálogos combináveis, não 1.000 NPCs gerados. Consumidor desse arquivo não encontrado. |
| `06_Nomes/Lugares/...4000...v3.json` | **4.000 nomes de lugares**, 25 tipos | Nomes não são locais, coordenadas ou formações materializadas. Não foi encontrado carregamento desse arquivo pelo gerador atual. |
| `06_Nomes/Pessoas/...4500...v3.json` | **3.000 nomes próprios** (1.200 masculinos, 1.200 femininos, 600 neutros) e **1.500 sobrenomes** | Fonte de 4.500 elementos de nomes, não população. Consumidor desse arquivo não encontrado. |
| `07_Povos_e_Ancestralidades/...v1.json` | Cinco povos, dez pares de compatibilidade | Interface para personagens/sociedade, sem distribuição de civilizações V4 comprovada. |
| `08_Povoados_Estruturas_6A/...1500_Matriz_250x100_v7.json` | **250 arquétipos**, 500 edifícios, 400 infraestruturas e **350 características regionais** | Há candidatos como “Nascente rasa”, com exigência de evidência/instanciação. Não são 1.500 locais existentes. Não foi encontrado consumidor Genesis desse arquivo. |
| `08_Povoados_Estruturas_6A/...Matriz_250x100_v7.json` | 250 linhas de arquétipos e 65 ambientes naturais com potencial ecológico | Compatibilidade de povoamentos, não um gerador de formações naturais ou locais fantásticos. |
| `09_Papeis_Sociais_Rotinas_6B/...2200_v1.json` | 350 papéis, 1.200 atividades, 650 variações de rotina | Catálogo social disponível, sem importação ambiental comprovada. |
| `10_Vida_Comunitaria_6C/...1500_v1.json` e expansão | 400 eventos, 400 problemas, 350 costumes, 350 interações; expansão de mais 200 modelos | Sem prova de consumo desses arquivos pelo Genesis; conteúdo de simulação/sociedade. |
| `12_Profiencias_Universais/...136_v1.json` | 136 proficiências, 408 especializações e 272 atividades de referência | Proficiências existentes no RPG não comprovam importação deste catálogo inteiro. Não é geração geográfica. |

**Locais Fantásticos:** não foi encontrado um dataset dedicado com esse nome/função, nem seu importador/gerador. Existem materiais parciais: os 50 ambientes anômalos E1, as 350 características regionais 6A, nomes e contratos da flora extrema. A discussão de um futuro dataset não equivale à sua criação. A necessidade de criá-lo ou apenas selecionar/revisar candidatos existentes surgirá ao implementar **locais/feições naturais e microambientes**; não foi recuperado um número de fase original para isso.

**Fauna:** o catálogo de 500 está presente **no arquivo ZIP**; dizer simplesmente “não existe dataset de fauna” seria incorreto. Dizer que o jogo já o usa também seria incorreto. Hoje a fonte ativa é a de 250 em `app/data`.

## E. Sistemas experimentais e integração com o jogo real

### E.1. Caminho normal, confrontado com o necessário

| Ponto do fluxo | Código e comportamento atual | Falta para usar Genesis |
|---|---|---|
| Criar campanha | [campaigns.py:create_campaign_route](../backend/app/api/routes/campaigns.py) chama `world/seed.py:create_campaign`; persiste seed e WorldTime. [CampaignCreateRequest](../backend/app/schemas/campaign.py) recebe apenas `name`. | Seleção explícita de um perfil novo. A presença de `world_seed` não inicializa uma autoridade Genesis. |
| Iniciar campanha | `start_world` chama `seed_initial_region`; gera vila, assentamentos, NPCs/economia/POIs pelo pipeline legado | Bootstrap versionado de V4 e camadas necessárias, antes de materializar terreno; nenhum chamado desses inicializadores foi encontrado nesse caminho. |
| Posicionar o personagem | `character.region_id/location_id`, `Location.x/y` e conexões legadas | Ancorar o local em `SurfacePoint` e associar coberturas quando necessárias. `bind_location` não é chamado pelo start. |
| Consultar terreno/ambiente | Serviços Genesis explícitos e ferramentas de diagnóstico existem | A observação normal do engine não consulta automaticamente T1/E1/Vg2. |
| Preparar vegetação | `initialize_vegetation` exige opt-in e fontes coerentes; R1 exige Vg2; GA2 exige GA1 e assinatura própria | Um orquestrador de campanha, não uma sequência manual de comandos técnicos. |
| Encontrar/observar | `vegetation/actions.py:encounter` procura até oito indivíduos próximos de uma âncora real; `inspect` respeita identificação | Encaminhar a intenção/UI para esse contrato após bootstrap. Sem âncora, o serviço recusa. |
| Coletar/remover | [actions.py](../backend/app/api/routes/actions.py) aceita `plant_action`; `resolve_plant_action` usa estoque, ferramentas, proximidade, relógio e recibo | [frontend/src/api/actions.ts](../frontend/src/api/actions.ts): `postAction` envia `text`, `action_key`, `technique_id`, não `plant_action`. Não foi encontrada UI que o envie. |
| Mostrar resultado | Backend retorna `plant_result`; inventário genérico já mostra pesos pequenos com precisão | Exibir encontro, partes disponíveis, motivos de bloqueio e operação vegetal. Formatação de peso, isoladamente, não fecha o fluxo. |
| Persistir e desfazer | Modelos e checkpoints/undo existentes incluem a mecânica vegetal; provas HTTP existem | Schema do banco-alvo e teste completo da UI/campanha configurada. |
| Revisitar/avançar tempo | L1/GA1/L2/GA2 consultam o calendário oficial e fazem catch-up sob demanda | Fazer a exploração/observação realmente consumir essas autoridades. Ausência de loop global não é defeito: catch-up é a estratégia válida. |

**Resposta direta:** uma campanha normal, criada pela interface atual, **não consegue utilizar Vg2, R1, GA1 e GA2 de ponta a ponta sem preparação técnica manual**.

As ferramentas `scripts/prove_vegetation.py`, `validate_water_c3.py` e `validate_adventure_renewal.py` montam campanhas de prova e, em parte do fluxo, importam planos/evidências técnicas previamente produzidos. Demonstram componentes e integração de teste, não um onboarding de produção para qualquer seed escolhida pelo jogador.

Também não basta chamar todos os inicializadores com defaults: `initialize_world` escolhe v1; o clima default é histórico; Vg2 e C3 R1-55 precisam de configurações explícitas; L1/L2 sem GA1/GA2 preservam os perfis antigos. Um futuro bootstrap deve fixar a cadeia e não depender de defaults incompatíveis.

### E.2. Banco real e migrações pendentes

A configuração local informa `sqlite:///./everreach.db`; o banco inspecionado foi `backend/everreach.db`, correspondente à execução documentada a partir de `backend`. Outros deployments/caminhos de execução não foram acessados.

| Evidência somente leitura | Resultado |
|---|---|
| Tamanho / última alteração UTC | 2.027.520 bytes; `2026-10-26 21:53:21.638774` |
| Campanhas | 2; não foram expostos nomes ou alterados personagens |
| `alembic_version` | `f15f1a2b3c4d` |
| Head obtido lendo o grafo dos arquivos Alembic | `y33y6t7u8v9w` |
| Tabelas `genesis_*` | **Nenhuma** |
| `item_instances.unit_weight_override`, `weight_authority` | **Ambas ausentes** |
| Consulta de prova, somente leitura | `SELECT unit_weight_override,weight_authority FROM item_instances LIMIT 0` → `no such column: unit_weight_override` |

Essa última evidência é uma incompatibilidade concreta entre schema e o [modelo ItemInstance](../backend/app/db/models/item.py). `inventory/service.py:list_inventory` e rotas de inventário consultam o modelo completo; portanto, esse caminho não está compatível com o banco auditado. Não foi feita uma requisição HTTP mutável para provocar o erro nem se afirma que todos os endpoints do jogo falham.

A revisão R1 [v30v3q4r5s6t](../backend/alembic/versions/v30v3q4r5s6t_plant_resources_r1.py) adiciona essas colunas. A cadeia pendente, sem executar nada, é:

```text
g15g1b2c3d4e  daily_request_director (anterior ao Genesis)
h16h1c2d3e4f  world_genesis
i17i1d2e3f4g  spherical_spatial_contracts
j18j1e2f3g4h  hydrology_h1
k19k2f3g4h5i  regional_hydrology_hr1
l20l3g4h5i6j  climate_c1
m21m4h5i6j7k  water_w1
n22n5i6j7k8l  terrain_t1
o23o6j7k8l9m  hydro_geometry_g1
p24p7k8l9m0n  water_reconciliation_w2
q25q8l9m0n1o  practical_hydrology_p1
r26r9m0n1o2p  geology_j1
s27s0n1o2p3q  regional_geology_jr1
t28t1o2p3q4r  environment_e1
u29u2p3q4r5s  vegetation_vg1
v30v3q4r5s6t  plant_resources_r1
w31w4r5s6t7u  vegetation_life_l1
x32x5s6t7u8v  vegetation_renewal_l2
y33y6t7u8v9w  vegetation_sexual_s1
```

Schema atualizado e ativação de autoridades são decisões diferentes. C2/C3, Vg2, GA1 e GA2 usam também contratos/descritivos versionados em JSON; não têm necessariamente uma migração própria. Nenhuma campanha deve ser convertida implicitamente só porque uma tabela foi criada.

### E.3. Fauna realmente existente

[`creatures/population.py`](../backend/app/game/creatures/population.py) seleciona espécies por tipo de Location, biomas antigos, hops até a vila, raridade e níveis das espécies. O roster usa o ID persistido do lugar como seed e limites como três espécies por lugar/grupo máximo quatro. O módulo prevê reposição ao amanhecer; `seed_initial_region` já chama `creature_population.replenish`.

Isso é fauna funcional do RPG legado, com NPCs marcados por espécie, horários, estágios, combate e loot. **Não é uma população animal planetária por ambiente Genesis**, nem deve ser descartado e refeito inteiro. Os consumidores de combate, aparência e loot são reutilizáveis.

Não foi encontrada leitura direta do nível do protagonista na função `roster`; existem pesos por nível da **espécie** e distância da vila. Ainda assim, essa regra espacial é diferente da independência geográfica pretendida para Genesis e precisa de um adaptador/política própria para novos mundos. Não se deve chamar essa fauna de ambientalmente integrada só porque já há animais na campanha.

### E.4. Mapa, distâncias e fronteiras

O mapa existente é real e individual por personagem: `map/service.py:known_map`, `map/view.py:get_map_view` e `frontend/.../InteractiveMap.tsx`. Usa o grafo e a descoberta; coordenadas precisas dependem de visita. O adaptador Genesis `known_spatial_locations` respeita isso, mas **não é consumido pela API de mapa**.

Viagens usam `LocationConnection` e `BASE_MINUTES_PER_DISTANCE=15`. Não foi encontrada conversão dessa unidade antiga para metros geográficos. A busca ativa usa `DC_SEARCH=12` e conexões desconhecidas; não aplica terreno/clima Genesis. Não reinterpretar a distância antiga silenciosamente para “fechar” essa pendência.

Living Frontiers possuem serviços/modelos, mas buscas de chamadas encontraram várias funções restritas a serviços internos e testes. O histórico Git inclui a simplificação `532b6b6`, que removeu sistemas não ligados ao jogo. Existência residual de modelos, comentários de fases e testes não prova exposição ativa atual. A integração geográfica/dinâmica dessas fronteiras permanece parcial; não é necessário criar bosses ou um grafo concorrente.

## F. Lacunas de gameplay e pendências objetivas

Prioridades: **P0** bloqueia o uso/comprovação do caminho jogável; **P1** fecha conteúdo ou integração essencial do MVP natural; **P2** amplia variedade ou otimiza após medição. Esta lista não cria fases novas.

| Pendência / classe | Etapa original relacionada | O que falta ao jogador | Infraestrutura reutilizável / menor trabalho | Dependências | Prioridade |
|---|---|---|---|---|---|
| Compatibilidade de implantação — infraestrutura | Persistência/versionamento, desde fase 0; R1 e cadeia posterior | O código atual não tem schema correspondente no banco local | Conferir a cadeia em cópia/banco novo e revisar implantação; nenhuma migração foi autorizada nesta auditoria | Backup/decisão explícita sobre o ambiente, separando schema de ativação | **P0** |
| Bootstrap opt-in de campanha nova — integração | Geração progressiva e território inicial do pedido 0 | A campanha usa outro gerador e não recebe autoridades Genesis | Orquestrar inicializadores existentes com preset explícito, posição inicial real e preparação local limitada; não depender de artefatos das cinco seeds | Schema compatível; política de campanha nova, sem migrar antigas | **P0** |
| Encontro/coleta/revisita vegetal no frontend — jogador | Integração de exploração; fases 1.0/1.0.2/GA1/GA2 | Flora nova não pode ser encontrada/coletada pelo fluxo normal da UI | Encaminhar `plant_action`, exibir `plant_result`, usar a âncora do local e inventário/checkpoints existentes | Bootstrap/âncora/R1 e controles de conhecimento | **P0** |
| Associação de regiões, rotas e terreno — consistência/jogador | 0.2 e arquitetura original de hierarquia/mapa | Viagem não corresponde à superfície nem prepara os setores percorridos | Usar `bind_location`, coberturas e hooks de materialização; integrar ao grafo existente; definir conversão explícita/testada quando adotar medidas geográficas | Spawn/local físico e política de distâncias | **P1** |
| Corpos hídricos naturais canônicos — jogador | Hidrologia e enriquecimento físico original; 0.4–0.7.3 | Falta rio/lago/nascente como lugar com dimensões, estado, acesso e água utilizável quando aplicável | Instanciar poucos tipos com identidade e estado; distinguir água cenográfica e estoque mecânico; reutilizar contas/contratos onde adequado | Âncora/Location, origem explícita do recurso e interação externa | **P1**, essencial para fechar variedade natural básica |
| Formações/locais naturais interessantes — jogador | Relevo, feições e datasets; E1 | Uma classificação ou corredor de 50 km não fornece, por si, um destino interessante | Selecionar pequena base de feições e regras canônicas; reutilizar E1, T1, J1/JR1, POIs e candidatos 6A; ligar a descoberta | Contrato de local, posicionamento, persistência | **P1** |
| Distribuição ambiental de fauna — jogador/geração | Fauna citada como enriquecimento futuro na fase 0 | Os animais continuam presos ao modelo legado de locais/biomas/hops | Escolher explicitamente catálogo ativo e adaptar seleção/população à região física; reutilizar corpos, combate e loot; não fazer IA animal completa | Âncoras/ambientes e ciclo temporal; decisão 250 ativo × 500 disponível | **P1**, antes de declarar o mundo natural completo |
| Consumidor de microambiente/extremos — variedade | 1.0/v22 e AP1; sem fase futura numerada recuperada | As 96 espécies não encontram um produtor de seu habitat | Gerar poucos microambientes autorizados junto a espécies compatíveis; substituir veto permanente por contrato consumidor, sem falsear autoridades antigas | Local canônico e condições próprias; anomalias específicas quando obrigatórias | **P2** para MVP; não exige as 96 nem todos os ambientes |
| Fronteiras naturais e eventos — integração | Living Frontiers do pedido original | Geografia/eventos não passam automaticamente a barreiras/rotas acessíveis | Reusar limites, barreiras, rotas e eventos; comprovar uma alteração real com alternativa de travessia | Locations/conexões físicas e simulação externa | **P1** no contrato; variedade completa pode vir depois |
| Preparação antecipada e escala distante — desempenho | Streaming/simulação distante propostos na fase 0 | Picos de preparação e falta de antecipação podem interromper exploração | Medir a fatia jogável; preparar vizinhança com orçamento e cache; aproveitar catch-up e escopos existentes | Fluxo real para medir | **P2**, sem obrigatoriedade de worker ou tick planetário |
| Critério de aceitação do MVP — verificação | Integração/persistência, desde a fundação | Não há playtest atual que una início, descoberta, coleta, viagem e revisita | Testes fim a fim e roteiro curto de exploração, com saves, mortes, recursos e conhecimento persistidos | Os caminhos acima | **P0** de verificação; não substitui conteúdo ausente |

**Não são bloqueios obrigatórios:** clima mais preciso, outro solver tectônico, erosão científica global, estratigrafia 3D completa, meteorologia diária, simulação contínua de milhões de indivíduos, todas as 3.096 plantas presentes, todas as 96 extremas, todos os 250 ambientes, todos os catálogos sociais, renderização planetária completa ou um novo Atlas. A direção AP1 permite regras regionais fantásticas explícitas sem alegar que C3/W1 as previram.

## G. Fronteiras do escopo

| Assunto | Responsabilidade do World Genesis | Sistema externo / interface necessária |
|---|---|---|
| Local natural × exploração | Estabelecer existência, tipo, posição/cobertura, origem, estado e versão | Exploração/descoberta decide o que o personagem encontrou e conhece; deve receber os fatos, não inventá-los |
| Fauna × IA animal | Distribuição, identidade/população, origem e renovação compatível com a região | Comportamento, percepção, combate, animação e narrativa pertencem aos sistemas de criaturas/IA; reutilizar o legado |
| Formação natural × dungeon | Cavidade/feição/local natural e suas interfaces físicas/canônicas | Layout de dungeon, encontros, puzzles e progressão não são automaticamente obrigações do Genesis |
| Recursos × crafting | Disponibilidade, quantidade finita, identidade, estado e referência aos materiais/partes | Extração/coleta, inventário, receitas, economia e ferramentas são consumidores; R1 já fornece uma integração específica |
| Geografia × mapa | Autoridade espacial e consulta filtrável | Mapa é projeção do conhecimento do personagem, não cópia pública do planeta. Atlas completo não é requisito interno para um MVP jogável |
| Existência × conhecimento | Lugar/espécie pode existir antes da visita | Descobertas, identificação e informações aprendidas continuam individuais; não expor coordenadas/nomes ocultos |
| Terreno × movimento | Altura, posição, barreiras/portas e contratos de rota | Viagem usa o grafo existente, duração, risco e recursos; conversão de unidades deve ser explícita |
| Mundo natural × sociedade | Suporte físico e, se contratado, candidatos de ocupação/recursos | Civilizações completas, política, economia, missões e rotinas sociais não podem ser cobradas integralmente sem um escopo recuperado que as atribua ao Genesis |
| Estado distante × simulação | Catch-up e eventos determinísticos nas entidades materiais pertinentes | Relógio, escopos e acontecimentos do RPG coordenam consumidores. Não é preciso um loop diário para todo o planeta |

O Genesis não precisa implementar todo o RPG para concluir. Precisa fornecer conteúdo natural consistente **e interfaces realmente consumíveis**, além de pelo menos um caminho real que prove essa integração. A construção de um frontend completo de cartografia, um sistema de crafting ou IA animal científica não é critério razoável para encerrar sua base.

## H. Caminho mínimo para conclusão

Esta é uma sequência de trabalho recomendada, **não uma renumeração do roadmap nem uma autorização de implementação**.

1. **Fechar uma fatia jogável com as autoridades existentes.** Validar o schema em ambiente isolado; criar campanha nova opt-in com preset explícito; ancorar um local inicial; permitir observar, coletar e revisitar com GA1/GA2 pelo cliente. Preservar campanhas antigas. Essa entrega prova que a infraestrutura chega ao jogador.
2. **Ligar preparação territorial e grafo existente.** Associar os locais necessários ao espaço físico, preparar somente destinos/vizinhança necessários e respeitar a descoberta. Adotar medidas geográficas em viagens somente por conversão explícita/testada; não lançar um novo grafo ou Atlas.
3. **Entregar conteúdo natural local mínimo.** Um conjunto pequeno de corpos hídricos/feições com identidade, dimensões, estado e acesso, usando regras procedurais canônicas AP1. Garantir pelo menos destinos reais em percursos, não apenas rótulos ambientais. Não exigir recálculo científico global para cada lago ou vale.
4. **Conectar fauna ambiental ao mundo novo.** Selecionar a versão do catálogo, distribuir populações pelos contratos ambientais e manter origem/tempo/persistência. Reaproveitar o backend de criaturas, combate e loot. A IA comportamental completa não faz parte dessa conclusão.
5. **Comprovar continuidade e consequências no percurso integrado.** Nova região/limite físico, recursos finitos, coleta/remoção, revisita, save/restart, undo e proteção do desconhecido. Medir os custos do caminho real e só otimizar o gargalo comprovado. Confirmar interfaces de barreiras/eventos sem implementar toda a sociedade.

**MVP completo:** uma campanha nova consegue fornecer geografia consistente, território acessível pelo grafo, ambientes/vegetação variados, recursos naturais, alguns locais/corpos hídricos realmente visitáveis, populações animais no escopo natural, ciclos em ritmo de jogo e persistência/descoberta integradas. Não requer variedade exaustiva de todo catálogo.

**Expansões posteriores:** mais microambientes/extremos, mais tipos de feições/anomalias, variedade adicional de fauna, maior sofisticação de barreiras, recarga hídrica dinâmica e ferramentas cartográficas avançadas. A ausência de todos esses exemplos não invalida um MVP que já ofereça o caminho natural básico.

Não se recomenda reabrir C3, W1 ou Vg2 por maior fidelidade científica. A prioridade atual é tornar seus resultados utilizáveis.

## I. Próxima etapa recomendada — uma tarefa concreta

**Entregar uma campanha nova experimental opt-in com o percurso completo “iniciar → observar vegetação → coletar → avançar tempo → revisitar”, usando V4/T1/JR1/C3 R1-55/W1/E1/Vg2/R1/GA1/GA2 existentes.**

Escopo mínimo verificável dessa próxima tarefa:

- Validar a cadeia de schema em banco novo/cópia isolada, sem migrar automaticamente as duas campanhas atuais.
- Fixar um preset explícito e uma seed; inicializar a cadeia em ordem compatível. Não depender de arquivos de demonstração das cinco seeds para uma campanha nova.
- Escolher e persistir um local inicial físico válido, ancorado no planeta, com preparação local limitada. Não reescrever geografia para fazer caber a espécie desejada.
- Expor no frontend o contrato vegetal já existente, com observação/identificação, partes e motivos de indisponibilidade. O jogador não fornece coordenadas ou alegações de habitat.
- Coletar para o inventário com massa/estoque corretos, preservar removidos e demonstrar renovação após passagem do calendário, save/restart e undo.
- Registrar o resultado de um playtest curto e o custo fim a fim. Não exigir deslocamento planetário completo para provar esse primeiro local; a integração de rotas vem na sequência H.

**Por que essa tarefa, antes de fauna ou um novo dataset:** ela fecha o maior bloqueio comprovado, reaproveita a implementação já paga e torna possível avaliar diversão, ritmo, interação e custo no jogo real. Acrescentar mais conteúdo experimental antes disso não demonstraria que o jogador consegue acessar o conteúdo existente.

**Critério de encerramento:** o percurso funciona pela interface em uma campanha nova explicitamente selecionada, sem configuração manual de tabelas/âncoras e sem modificar saves anteriores. Não inclui novo clima, nova hidrologia, flora extrema, fauna, dungeon ou Atlas.

---

### Rastreabilidade e limites desta auditoria

Foram pesquisados documentos e arquivos Markdown atuais/anteriores do Git, fontes e chamadas em backend/frontend, modelos/migrações, os JSONs extraídos e os 61 arquivos do ZIP. A existência de testes não foi tratada como prova de um resultado de execução novo. Campos não contados internamente ou responsabilidades sem especificação recuperada foram marcados como tais.

O banco local foi aberto apenas em modo de leitura imutável. Seu SHA-256 conferido foi `88f5540cb26aec661b8808247ad18bc8762b2ba55f8fba0d1c5cdbc20d5971f3`. Nenhum deployment remoto foi acessado. Uma impressão agregada dos 1.230 arquivos de fontes, migrações, scripts, frontend, datasets e documentos preexistentes foi usada para conferir que a auditoria não os modificou; este relatório é excluído dessa comparação por ser a única escrita autorizada.
