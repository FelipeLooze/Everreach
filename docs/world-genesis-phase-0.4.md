# World Genesis — fase 0.4: hidrologia planetária H1

## Auditoria e decisões antes da implementação

Fontes revisadas: `formation_v4.py`, `formation_plan.py`, `formation_geography.py`, `service.py`, `sphere_topology.py`, `sphere_metric.py`, `sphere_area.py`, `coast_refinement.py`, modelos de persistência, exclusão de campanhas e migração atual `i17i1d2e3f4g`.

- V4 já fixa placas, relevo e assinatura por mundo; não contém drenagem ou disponibilidade de água.
- Topologia e portas geométricas têm endereços inteiros estáveis entre faces. R1 oferece interpolação e contratos amostrados, não conectividade global exata.
- Snapshots de terreno têm baseline separado de changes. Acrescentar hidrologia dentro de baselines antigos modificaria dados já versionados; H1 terá persistência separada.
- Serviços usam a Session do chamador, sem commit próprio. Exclusão de campanha é explícita por dependências.

| Alternativa | Decisão |
| --- | --- |
| Ruído ou rios gerados isoladamente por setor | Rejeitado: não fixa bacias ou confluências globais. |
| Drenagem global em resolução de setor/local | Rejeitado: custo proporcional ao planeta inteiro em alta resolução. |
| Somente descida por altura dos centros | Insuficiente: pode saltar uma crista entre centros e prende depressões sem explicar saídas. |
| Grafo global esférico limitado + barreiras amostradas + superfície condicionada | Escolhido para H1: custo limitado, determinismo e explicação de armazenamento/vertedouro. Leitos locais terão refinamento posterior. |

O planejamento usa variante minimax/priority-flood com desempate determinístico, inspirada no [trabalho primário de Barnes, Lehman e Mulla](https://arxiv.org/abs/1511.04463). É uma superfície hidrológica **separada**, não preenchimento destrutivo do terreno. O plano conserva também drenagem sem condicionamento e depressões fechadas nessa superfície, para não apresentar todo armazenamento potencial como lago permanente.

H1 é opt-in sobre mundos V4, com algoritmo/configuração próprios. A malha hidrológica tem resolução independente das identidades continentais, até 6.144 células. Um perfil de relevo compartilhado amostra cada ligação entre células, passando pelo meio da borda real. O oceano de referência é o maior componente conectado abaixo do datum marítimo nesse grafo, com hipótese de reservatório declarada. Outros componentes são identificados como desconectados abaixo do datum, sem inferir salinidade ou permanência.

Área contribuinte geométrica sustenta a hierarquia potencial de canais, não precipitação, vazão, largura ou perenidade. Consultas por setor retornam corredores macro e portas estáveis, claramente pendentes de refinamento regional; não criam rios físicos finais ou revelam dados ao jogador.

## Entrega e contratos H1

Esta entrega implementa **planejamento macro funcional e persistente**, a primeira etapa autorizada no pedido. O refinamento de leitos regionais fica para uma segunda etapa. Não há cursos efetivamente alimentados por chuva: `discharge_m3_s`, `perennial`, volume disponível e permanência dos lagos permanecem indeterminados. A ausência de cursos efetivos no snapshot significa ausência de modelagem hídrica, não uma afirmação de que o planeta seja seco.

`HydrologyConfig` fixa versão 1, fonte V4 e nível 2–5; o padrão é 5. Nível 5 significa 6.144 nós e 12.288 ligações, independentemente do raio. Cada ligação possui cinco amostras do campo V4: centro, intermediário, meio da borda compartilhada, intermediário e centro vizinho. São 43.008 consultas distintas ao relevo no padrão. Não há segundo campo geográfico nem ruído hidrográfico.

O processamento conserva duas redes:

1. **Descida sem condicionamento:** receptores só são aceitos quando a barreira amostrada cabe na altura de partida. Empates em superfícies planas usam `(altura, índice)` decrescente. Terminais interiores são candidatos a bacias fechadas; não são ligados automaticamente a um rio ativo.
2. **Potencial de transbordamento:** caminho minimax até o oceano de referência. O custo é a maior altura necessária para ultrapassar barreiras amostradas. Sem oceano amostrado, o mínimo global é terminal fechado. Cabeças iguais têm desempate inteiro determinístico e o receptor sempre possui rank anterior; portanto não existem ciclos.

A cabeça condicionada é separada da elevação. Ao longo de cada perfil, um envelope máximo dos trechos a jusante produz cabeça não crescente e nunca abaixo do terreno amostrado. Toda diferença positiva fica registrada como necessidade de armazenamento/represamento potencial. Isso não corta montanhas, não muda alturas V4 e não garante que haverá água suficiente para transbordar.

As depressões agrupam nós submersíveis contíguos com a mesma cota potencial de saída, respeitando barreiras. Exportam fundo mínimo, área geométrica amostrada, saídas selecionadas e alternativas. Não se calcula volume preenchido, evaporação, vazão ou permanência. Um grupo abaixo do datum desconectado do oceano continua explicitamente separado; pode exigir outra interpretação no refinamento, sem ganhar salinidade presumida.

As áreas usam o jacobiano do cube-sphere radial `(1+u²+v²)^(-3/2)`, por quadratura de ponto médio 4×4 com `isqrt` e unidades de ângulo sólido `2^50`. A aritmética de decisão é inteira. É uma **aproximação de área esférica**, e não área UV uniforme ou fórmula exata: os testes comparam com `sphere_area.cell_solid_angle` e limitam erro de célula a 0,5% e total a 0,2% nos níveis testados. A conservação é exata dentro dessa medida quantizada. A área dos nós do reservatório oceânico não alimenta os canais terrestres.

A hierarquia usa área contribuinte e ordem potencial de Strahler. Os limites de representação são frações da área planetária, 125 ppm para canais e 500 ppm para destaque principal, configuráveis e fixados na assinatura. São filtros de visualização/LOD, sem impor número de rios, bacias ou lagos. Uma bacia H1 é associada ao terminal do grafo; várias saídas costeiras próximas ainda não formam automaticamente uma única bacia regional.

Os IDs incluem assinatura da formação e configuração H1. Reaches são segmentados em confluências; bacias, divisores, depressões, terminais e junções possuem IDs independentes da ordem de consulta. Continentes, `Region` e fronteiras políticas não participam do cálculo.

## Continuidade e materialização progressiva

Cada ligação usa uma única porta física no meio da borda. Corredores seguem centro → porta → centro; são hipóteses macro, não leitos finais. Em setores finos, o recorte usa frações exatas nas cartas do cubo. As duas faces produzem o mesmo raio, ID de porta e intervalo de cabeça. Confluências compartilham um ID de junção, inclusive entre reaches diferentes. Setores no nível 24 também são testados.

Uma consulta fina inspeciona a célula ancestral e suas ligações incidentes; não percorre novamente a rede inteira. Consultas em nível menor enumeram apenas as células macro cobertas, limitadas ao orçamento H1. Os índices derivados são construídos uma vez por plano. Portas entre setores recebem limites de cabeça até o refinamento, e centros macro recebem cabeça exata. Portas sobre uma borda podem aparecer nos dois snapshots: o ID identifica um único corredor compartilhado.

O contrato declara `requires_regional_refinement=True` e `river_bed_geometry_final=False`. Ele não obriga um futuro leito a seguir uma linha reta macro: o refinamento deverá escolher trajetórias topográficas regionais compatíveis, conferir novas barreiras/estreitos e estabelecer cotas locais compartilhadas antes de materializar cursos físicos. Não basta desenhar os corredores atuais no mapa público.

## Persistência e integração

São adicionadas `genesis_hydrology_plans` e `genesis_hydrology_sectors`, com migração **`j18j1e2f3g4h`**, posterior a `i17i1d2e3f4g`. A migração somente cria tabelas. Nenhum save existente recebe H1 automaticamente. Não se modifica `GenesisWorld.plan`, baselines de terreno, V1/V2/V3/V4 ou R1.

API interna, com a mesma Session do chamador:

```python
from app.game.world.genesis.hydrology.service import (
    initialize_hydrology, get_hydrology_plan, materialize_hydrology_sector,
)

# Depois de initialize_world(..., FormationConfigV4(...)), explicitamente:
initialize_hydrology(db, campaign_id)
plan = get_hydrology_plan(db, campaign_id)
snapshot = materialize_hydrology_sector(db, campaign_id, sector_key)
# Commit/rollback pertencem ao chamador.
```

Inicializar não cria setores físicos ou hidrológicos. Materializar H1 cria somente seu snapshot, com `baseline` e `changes` separados. Um setor existente é devolvido sem regeneração, preservando suas alterações. Como nos modelos existentes de JSON simples, alterações devem atribuir um novo dicionário para serem persistidas pelo ORM.

Assinatura, configuração e checksums fixam a fonte V4 e o plano H1. Uma divergência resulta em erro; não causa reconstrução silenciosa. A recarga valida arrays, conservação, receptores e ausência de ciclos sem executar novamente o flood. O payload global é uma coluna JSON de carga adiada; acertos no cache e em snapshots existentes dispensam sua desserialização. O checksum da fonte ainda é conferido no serviço; seu custo é limitado pelo plano V4 salvo.

Há cache de dois planos H1 imutáveis, protegido por lock, e cache de duas geometrias. Uma linha persistente continua obrigatória antes de consultar o cache, evitando resultados fantasmas após rollback. Checksums verificam integridade ao carregar; não oferecem detecção contínua de alterações manuais fora dos contratos enquanto o baseline estiver em cache. Não há ticks de rios, workers, serviço novo, API pública, mudanças em movimento, exploração ou divulgação de locais desconhecidos.

`delete_campaign` remove os filhos hidrológicos antes do mundo. A migração foi exercitada em bancos temporários, com chaves estrangeiras ativas, incluindo upgrade, runtime, exclusão e downgrade. **O banco real `everreach.db` não foi migrado nesta execução.** Para habilitar a camada em execução é necessário aplicar a migração pelo fluxo habitual do projeto e inicializar H1 explicitamente.

## Visualização e reprodução

Executar a partir de `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_hydrology --suite --measure-memory --export-plans --output ../artifacts/hydrology-h1
```

Também aceita `--seed`, `--radius-m` e `--level` para uma amostra. Não abre banco nem modifica saves. Cada pasta inclui relevo macro, bacias e drenagem potencial em seis faces; ciano indica descida amostrada, laranja necessidade de armazenamento em algum ponto do perfil, espessura representa área contribuinte e anéis indicam depressões candidatas. A geometria quadriculada é a resolução declarada do grafo macro.

Artefatos: [comparação estruturada](../artifacts/hydrology-h1/comparison.json), [seed 42, referência](../artifacts/hydrology-h1/seed-42-r63710000/hydrology.png), [seed 0](../artifacts/hydrology-h1/seed-0-r63710000/hydrology.png), [seed 2026](../artifacts/hydrology-h1/seed-2026-r63710000/hydrology.png). Planos fonte/H1 e `records.json` permitem inspecionar bacias, divisores, afluentes, saídas e depressões sem depender de uma campanha.

## Comparação de qualidade e escala

As seis amostras usam H nível 5 e formação V4 padrão para cada raio. Cobertura terrestre usa área esférica aproximada, com classificação pela altura do centro; não representa cobertura de costa refinada R1. Todas conservaram área contribuinte e passaram nas validações de DAG/barreiras ao gerar e carregar.

| Seed | Raio (km) | Terra amostrada | Reaches potenciais | Bacias por saída | Depressões candidatas | Ligações entre faces |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 63.710 | 40,60% | 1.377 | 367 | 297 | 43 |
| 42 | 63.710 | 43,19% | 1.527 | 409 | 333 | 71 |
| 2026 | 63.710 | 30,34% | 1.031 | 384 | 216 | 26 |
| 42 | 6.371 | 54,81% | 1.286 | 192 | 404 | 47 |
| 42 | 637.100 | 44,81% | 1.660 | 549 | 373 | 53 |
| 42 | 1.000.000.000 | 44,81% | 1.660 | 549 | 373 | 53 |

No raio de referência, a seed 42 tem 492 terminais interiores na rede sem condicionamento e 990 nós não marinhos acima da altura de terreno na superfície condicionada. São evidências de armazenamento **necessário**, não 492 lagos ou rios ativos. O caminho condicionado mais longo tem cerca de 120.221 km, atravessando muitas células; a medida soma arcos dos corredores, sem representar uma viagem ou extensão final de um rio.

Os dois raios extremos apresentam a mesma estrutura angular porque a calibração do relevo V4 já satura nessa escala; H1 não inventa microformas adicionais quando o raio cresce. O custo e a contagem de amostras não crescem com a área física. Isso é uma garantia de orçamento, acompanhada de uma limitação explícita de resolução.

## Desempenho observado

As métricas completas ficam em `comparison.json`. O benchmark separa construção da fonte V4, H1, desserialização/validação e consultas. As consultas medidas são `sector_snapshot` em memória, sem ORM, checksum da fonte ou I/O; não são latência de ação do jogador. A primeira consulta inclui a criação do índice de reaches.

Na medição final completa, H1 levou aproximadamente **3,42–6,70 s** entre os seis casos; no raio de referência, **5,0–5,3 s**. A recarga JSON com validação levou **20–24 ms** e consultas aquecidas tiveram medianas **0,01–0,10 ms** em 100 setores por caso. O payload compacto ficou entre **0,79 e 0,93 MB**. Valores dependem da máquina e não são limites rígidos de testes.

Na seed 42 de referência, uma construção separada sob `tracemalloc`, incluindo geometria fria e índices derivados mas excluindo a fonte V4 já existente, teve pico de **23.937.324 bytes (~22,8 MiB)** e retenção de **18.742.961 bytes (~17,9 MiB)**. Isso mede alocações Python desse escopo, não RSS total do processo, buffers do banco ou custo de todos os caches juntos. A instrumentação de memória não participa dos tempos normais de construção.

O principal custo é avaliar 43.008 posições do relevo V4; o grafo permanece pequeno. O nível é limitado por contrato e não existe tarefa de fundo. Mesmo no maior raio, os valores de área usam inteiros Python; os exports técnicos não devem ser convertidos para `Number` JavaScript sem tratamento de precisão acima de 2^53.

## Arquivos desta fase

| Arquivo | Entrega |
| --- | --- |
| `backend/app/game/world/genesis/hydrology/config.py` | Configuração e limites versionados H1. |
| `.../hydrology/geometry.py` | Malha, perfis/portas compartilhados e área esférica inteira. |
| `.../hydrology/drainage.py` | Oceano amostrado, flood minimax, rede bruta, área, hierarquia e depressões. |
| `.../hydrology/plan.py` | Plano imutável, IDs, reaches, bacias, divisores, saídas e serialização. |
| `.../hydrology/sectors.py` | Consulta localizada, recorte racional, portas e corredores macro. |
| `.../hydrology/service.py`, `__init__.py` | Inicialização explícita, persistência e cache limitado. |
| `.../hydrology/preview.py` | Métricas, atlas offline e exportação de registros. |
| `backend/app/db/models/world_hydrology.py`, `models/__init__.py` | Duas entidades persistentes e registro no ORM. |
| `backend/app/game/world/reset.py` | Exclusão na ordem de dependências. |
| `backend/alembic/versions/j18j1e2f3g4h_add_hydrology_h1.py` | Migração aditiva. |
| `backend/app/tests/test_genesis_hydrology.py`, `test_genesis_hydrology_persistence.py` | Testes do núcleo, continuidade, orçamento e persistência. |
| `backend/scripts/preview_hydrology.py` | Comparação de seeds/raios, exportação e benchmarks. |
| `docs/world-genesis-phase-0.4.md`, `artifacts/hydrology-h1/` | Decisões e evidências reproduzíveis. |

As alterações anteriores das fases 0.3.1 e 0.3.2 já presentes no workspace foram preservadas. Nenhum campo de formação anterior foi editado nesta fase.

## Testes executados

**379 testes selecionados passaram em 103,38 s**, incluindo 34 testes/casos H1 e a regressão existente. Não foi executada a suíte completa do backend ou frontend. Permanece um aviso preexistente de depreciação Starlette/httpx.

Os casos H1 cobrem confluência e conservação, Strahler, depressão fechada versus saída condicionada, barreiras em corpos abaixo do datum, planetas sem oceano e inteiramente marinhos, empates sem ciclos, configuração inválida, orçamento de amostras/área em três níveis, preservação do terreno e ausência de alegações de água permanente, digest H1 congelado e processos com `PYTHONHASHSEED` diferente, recarga e ordem de consulta, todas as emendas da malha, portas em níveis 5/13/24, junções compartilhadas, quatro combinações seed/raio, orçamento de memória e geração do atlas. Persistência cobre opt-in V4, rejeição de reconfiguração/conversão, coluna adiada/cache, mudanças preservadas, retorno sem reconstrução, cache limitado/rollback, checksums e divergência de cabeçalhos, exclusão por campanha e migração aditiva com dados legados.

A regressão selecionada inclui `test_genesis*.py`, `test_map*.py`, `test_travel*.py`, `test_world_gen*.py`, `test_regional_boundaries.py`, `test_cross_region_routes.py`, `test_explor*.py`, `test_campaign_reset.py`, `test_region_skeleton.py`, `test_neighbor_region_materialization.py`, `test_world_simulation_integration.py`, `test_simulation_scope.py` e `test_world_time*.py`.

Também passaram `compileall` dos módulos novos e `git diff --check`. A cadeia Alembic tem uma única cabeça, `j18j1e2f3g4h`. As seis amostras técnicas de nível 5 foram geradas, recarregadas, validadas e inspecionadas visualmente; seus planos, registros e métricas estão nos artefatos. Os testes de desempenho impõem orçamento estrutural/memória, sem depender de um tempo de CPU rígido.

## Limitações e próxima etapa

- A conectividade é amostrada: um estreito menor que a malha ou uma crista entre as cinco amostras pode exigir revisão regional. H1 não promete conectividade global exata da superfície contínua V4.
- A escala média característica de célula é `raio * sqrt(4π/6144)`: aproximadamente 2.881 km no raio de referência, com variação por posição no cubo. Não representa canais, desfiladeiros ou leitos de metros. A precisão dos endereços locais continua disponível, mas não equivale a detalhe hidrológico já gerado.
- A rede condicionada representa **possibilidade de transbordamento**; a rede bruta conserva candidatos endorreicos. Clima e armazenamento poderão manter uma bacia fechada em vez de ativar a saída potencial.
- Escolher o maior corpo amostrado abaixo do datum como oceano é uma condição de contorno documentada, não prova física de que toda água abaixo de zero seja marinha.
- Não há erosão, incisão, barragens reais, balanço hídrico, lagos permanentes, neve, águas subterrâneas, clima ou simulação contínua.

**Parecer:** a fundação macro H1 está pronta para o refinamento hidrográfico regional e para receber um futuro balanço climático. Antes de expor rios/lagos físicos em gameplay, a próxima etapa deve refinar trajetórias contra o relevo, estabilizar portas/cotas locais e só então resolver alimentação, armazenamento, vazão e sazonalidade. O mapa de exploração permanece independente e protegido pelo conhecimento existente.
