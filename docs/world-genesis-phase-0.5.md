# World Genesis — fase 0.5: clima C1

## Auditoria e decisões antes da implementação

Revisados V4 (`formation_config`, `formation_tectonics`, `formation_plan`), topologia/área esférica, H1 (oceano amostrado, assinatura e persistência), HR1 (cotas potenciais, mudanças separadas) e exclusão de campanhas. Não existe balanço hídrico nem contrato de atmosfera. O menor relevo V4 na referência permanece ~316 km; não é necessário ou autorizado implementar T1.

| Alternativa | Decisão |
| --- | --- |
| Ruído climático por setor | Rejeitado: sem transporte ou continuidade física entre territórios. |
| Modelo atmosférico dinâmico global | Rejeitado: custo/complexidade inadequados ao RPG. |
| Faixas de latitude sem oceanos/relevo | Insuficiente: ignora continentalidade e sombra de chuva. |
| Campos globais limitados + transporte iterativo amostrado + interpolação regional | Escolhido para C1. |

C1 é opt-in sobre V4/H1, com assinatura/configuração próprias, independente de HR1. H1 fornece a hipótese de oceano conectado; seus planos, cotas e cursos não são alterados. Não é presumida evaporação de lagos interiores ainda indeterminados.

A malha tem vértices compartilhados pelas seis faces, permitindo interpolação bilinear contínua nas emendas, inclusive nos polos. O número máximo de vértices é 6.146. A preparação global ocorre uma vez; consultas não reexecutam transporte. O detalhe regional inicial corrige temperatura pela altitude V4 consultada, mantendo precipitação e umidade na resolução global.

As hipóteses são de um preset ficcional configurável: forçamento solar geométrico, quatro períodos orbitais iguais, atmosfera com gradiente térmico e bandas de circulação prescritas, transporte de umidade aproximado e resposta orográfica. Raio não determina gravidade, composição atmosférica ou rotação. Comprimentos de influência podem ser explícitos ou calibrados pela escala geográfica V4; isso é uma política de RPG, não extrapolação geofísica da Terra.

Referências conceituais primárias: [NASA: energia solar, latitude e inclinação](https://science.nasa.gov/earth/earth-observatory/climate-and-earths-energy-budget/) e [NWS: levantamento orográfico](https://www.weather.gov/media/sgx/documents/The_Weather_Guide.pdf). As equações/coeficientes C1 são aproximações do projeto, não implementação ou validação desses modelos científicos.

## Arquitetura e versionamento entregues

O plano C1 é um dataclass imutável, separado de `GenesisWorld.plan`, H1 e HR1. A assinatura inclui a assinatura V4, H1 e toda a configuração climática. Não há segundo gerador de elevação, sementes de ruído climático ou consultas LLM. A seed do mundo influencia clima através da geografia determinística existente. Alterar o modelo autoritativo depois desta entrega exige outra versão explícita; vetores congelados verificam tanto o plano quanto um resultado de consulta C1.

`ClimateConfig` é imutável e estrito, com versão inteira 1. Parâmetros principais:

| Parâmetro | Padrão | Significado |
| --- | ---: | --- |
| `level` | 5 | Resolução climática própria; aceita 3–5, com 386/1.538/6.146 vértices. |
| `axial_tilt_mdeg` | 23.440 | Inclinação em milésimos de grau; configurável entre 0° e 60°. |
| `year_days` | 360 | Duração do ano usada nos totais de precipitação/demanda; não modifica o calendário do jogo. |
| `radiative_offset_centi_c`, `insolation_gain_centi_c` | −5.200; 26.000 | Resposta térmica fictícia ao índice solar, em centésimos de °C. |
| `poleward_heat_transport_ppm` | 150.000 | Mistura prescrita do forçamento anual com referência uniforme. |
| `lapse_centi_c_per_km` | 600 | Resfriamento com altitude acima do datum: 6 °C/km. |
| Resposta sazonal terrestre/oceânica | 350.000 / 100.000 ppm | Amortecimento da temperatura, interpolado pela influência marítima. |
| Limites Hadley/polar | 30° / 60° | Bandas prescritas e configuráveis, não derivadas de rotação/massa planetária. |
| `wind_scale_milli_m_s` | 8.000 | Escala do vetor predominante; a velocidade efetiva depende de latitude/banda. |
| `transport_iterations` | 40 | Passadas globais síncronas, limite configurável 8–64. |
| Condensação basal/convectiva/orográfica | 50.000 / 300.000 / 150.000 ppm por km de subida | Eficiências limitadas para a aproximação de chuva e perda de umidade. |
| Escalas de chuva / PET | 12.000 / 4.500 milésimos de mm/dia | Conversões climatológicas configuráveis, não volumes efetivos de água. |

Os demais limites e parâmetros estão em `climate/config.py`. A configuração não pretende deduzir física de uma super-Terra: não há massa, gravidade, pressão, gases, albedo dinâmico, excentricidade orbital ou rotação resolvida. Para outro tipo de atmosfera, é necessário escolher explicitamente outro conjunto de parâmetros. Manter o mesmo preset em outro raio significa manter essas hipóteses, não afirmar que planetas distintos possuem necessariamente a mesma atmosfera.

## Modelo numérico C1

### Geometria e continuidade

São `6 × 4^level + 2` raios de vértices únicos, compartilhados entre as cartas. A adjacência é construída das arestas das seis faces, deduplicada: vértices comuns têm um único campo, inclusive nos cantos. A distância de transporte usa comprimento de corda em metros calculado com direções inteiras; é uma aproximação de arco curto, não uma nova unidade de viagem. Nenhuma unidade ou conexão do sistema de movimentação foi modificada.

Consultas usam quatro vértices e pesos bilineares racionais. Nas emendas, os dois lados reduzem à mesma interpolação dos mesmos dois vértices de borda; nos cantos, ao mesmo vértice. Portanto não há quebra de carta. As saídas são quantizadas em centésimos de °C, mm e ppm, e sua continuidade é até essa quantização. Não se promete continuidade de derivada.

As decisões usam inteiros e `isqrt`. A geometria solar usa uma aproximação racional versionada para seno da inclinação e 16 cossenos horários congelados. A latitude é obtida pela componente Z da direção unitária; não depende de latitude textual ou de uma face especial. Números de ponto flutuante aparecem somente na visualização e nas métricas diagnósticas de área.

### Energia, estações e temperatura

A insolação é a média de 16 projeções solares diurnas não negativas, para quatro declinações: `0`, `+inclinação`, `0`, `−inclinação`. Os quatro estados representam períodos orbitais de mesma duração. Médias anuais usam quadratura simplificada de quatro estados representativos, não integração astronômica exata. Os períodos 0/2 coincidem no modelo circular sem defasagem térmica; o período 1 favorece o hemisfério norte e o 3 o sul. Com inclinação zero, o forçamento sazonal desaparece.

Uma mistura prescrita representa redistribuição térmica meridional. A temperatura anual ao nível do mar é offset + ganho × energia média. A variação sazonal é amortecida pela influência marítima. O gradiente térmico é aplicado somente à altura acima do datum, sem tratar o fundo do oceano como altitude atmosférica negativa. Não há temperatura de correntes oceânicas, balanço radiativo fechado ou meteorologia diária.

### Oceano e continentalidade

Um vértice é fonte oceânica quando a altura V4 é inferior ao datum **e** a célula H1 correspondente pertence ao oceano de referência. Não se usa identidade continental macro como prova de conexão. Essa classificação herda a resolução/hipótese de reservatório do H1; não equivale a uma costa R1 global exata.

Uma busca multiorigem de menor distância no grafo mede a proximidade ao oceano. A influência marítima é `L²/(L+d)²`, quantizada em ppm. Continentalidade é seu complemento. Sem oceano amostrado, as distâncias são desconhecidas, a influência é zero e não é inventada água atmosférica inicial.

Os comprimentos podem ser fornecidos explicitamente. No modo automático, `L_marítimo = escala_placa_V4/3` e `L_umidade = 2 × escala_placa_V4`. Na referência são aproximadamente **4.216 km e 25.298 km**. A política acompanha as estruturas geográficas e o orçamento angular, sem afirmar uma lei atmosférica científica. A mesma lógica funciona no limite de raio de 10¹² m; nesse extremo a resolução física continua grosseira.

### Ventos, umidade e relevo

São prescritas bandas de circulação com componente zonal invertida entre trópicos/polos e médias latitudes. Uma migração sazonal aproximada desloca a faixa de convergência pela declinação. Vetores são tridimensionais e tangentes à esfera, sem um bearing singular no polo. A velocidade prescrita tende a zero nos polos; ali, ou em calma por quantização, o transporte usa mistura isotrópica entre vizinhos.

Cada vértice recebe umidade dos vizinhos a barlavento, ponderados pela direção do vento. O transporte sofre atenuação por distância; a condensação combina base, convergência tropical e subida do relevo em relação aos vizinhos de origem. Condensação reduz a umidade remanescente, permitindo precipitação intensificada a barlavento e depleção a sotavento. O oceano é um reservatório de origem cuja oferta depende da temperatura; frio reduz essa oferta sem afirmar gelo marinho já formado.

As passadas são **síncronas**: todos os vértices leem o estado anterior. Mudar a ordem de iteração não muda resultados. O custo é limitado pelo número de vértices × quatro períodos × até 64 passadas. Não há transporte climático a cada tick. O plano registra a diferença máxima em ppm na última passada; o modelo não afirma conservação hídrica global de alta precisão ou convergência matemática exata.

A eficiência de condensação por ligação e a amostragem do relevo tornam os resultados dependentes da resolução climática fixada. Níveis 3/4/5 são configurações distintas, não níveis LOD intercambiáveis do mesmo campo. O modelo não resolve tempestades, frentes, monções explícitas, föhn, correntes oceânicas ou evaporação de lagos cuja existência ainda é indeterminada.

## Contratos de consulta e hidrologia

`sample_climate(plan, point)` retorna climatologia interpolada com altitude macro. `sample_regional_climate(source_v4, plan, point)` consulta exatamente o avaliador V4 e ajusta temperatura/PET/neve potencial pela altitude local. **A precipitação, a umidade e os ventos permanecem na resolução climática global.** Não são inventadas chuvas locais ou canais subgrid; a resolução fica registrada em cada resposta.

As saídas contêm temperatura média/amplitude, totais anuais e quatro períodos de precipitação, índice de umidade atmosférica, vetor/velocidade predominante, continentalidade, demanda evaporativa potencial, índices de aridez e condições potenciais de congelamento/neve. O índice de umidade não é umidade relativa termodinâmica medida. Neve potencial é uma fração da precipitação no período conforme temperatura, não estoque de neve ou geleira criada.

PET é um proxy de demanda atmosférica por temperatura e energia; **não é evaporação real**. `precipitation_to_pet_ppm` mede P/PET, e `aridity_index_ppm` mede o déficit relativo de P frente à demanda. Quando PET é zero, ambos ficam `None`, com estado `energy_limited_undefined`: frio não é classificado falsamente como umidade abundante. Nenhum desses índices define automaticamente um bioma.

`season_at_phase(sample, phase_ppm)` permite ao futuro calendário consultar uma fase orbital normalizada e cíclica, com temperatura e taxa climatológica interpoladas. A unidade temporal é explícita: ano configurado, quatro períodos, duração racional `[year_days, 4]`. O helper não prevê um dia específico e não altera o calendário/tempo do Everreach. Não há estações obrigatórias de gameplay.

`hydrology_inputs(sample, season_index)` oferece um contrato somente de leitura com assinatura C1/V4/H1, posição, duração, precipitação, temperatura, demanda evaporativa e neve potencial. `available_runoff_mm`, evapotranspiração efetiva, variação de armazenamento, vazão, perenidade e permanência de lago permanecem `None`. Resolver escoamento ainda requer balanço hídrico, armazenamento e compatibilidade das rotas H1/HR1. Corredores bloqueados não são ativados pelo clima.

## Persistência e geração progressiva

Foram adicionadas `genesis_climate_plans` e `genesis_climate_sectors`. A migração **`l20l3g4h5i6j`**, posterior a `k19k2f3g4h5i`, somente cria tabelas, sem editar linhas antigas. A configuração e assinaturas/checksums V4/H1 ficam fixados no cabeçalho C1; o payload global tem carga adiada e cache imutável limitado a dois planos. A geometria tem cache de dois níveis. Divergências resultam em erro, sem regeneração silenciosa.

Exemplo de uso interno, depois de V4 e H1 já inicializados:

```python
from app.game.world.genesis.climate.service import (
    initialize_climate, get_climate_plan, query_climate, materialize_climate_sector,
)

initialize_climate(db, campaign_id)  # prepara somente o plano global C1
sample = query_climate(db, campaign_id, surface_point)  # altitude V4 sob demanda
snapshot = materialize_climate_sector(db, campaign_id, sector_key)
# Commit/rollback pertencem ao chamador.
```

Inicializar não materializa setores, HR1 ou novos cursos de água. Uma consulta de ponto não grava nada. Materializar um setor salva uma amostra de seu centro, com `coverage` explícito; não afirma que todo o setor tenha clima uniforme. Baseline e `changes` ficam separados, e o retorno a um setor preserva alterações sem reconsultar a geografia. A aplicação de eventos futuros sobre mudanças climáticas não foi implementada; esses dados são conservados, não simulados.

Saves anteriores não recebem C1 automaticamente, inclusive V4/H1/HR1 existentes. O serviço requer H1 como fonte oceânica, mas não exige materialização HR1. A exclusão de campanha remove os filhos C1 antes de H1. Checksum/proveniência são conferidos nas leituras; como nas camadas existentes, o contrato é de baselines imutáveis, sem monitoramento contínuo de alterações manuais fora da API enquanto um plano estiver em cache.

**O banco real não foi migrado nesta execução.** Upgrade, runtime, preservação de V4/H1/HR1 e downgrade foram exercitados em banco temporário com chaves estrangeiras ativas. Para habilitar C1 em execução, aplicar a migração pelo fluxo habitual e chamar o opt-in explicitamente.

## Ferramenta offline e reprodução

A partir de `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_climate --suite --measure-memory --export-plans --output ../artifacts/climate-c1
```

Também aceita seed, raio, nível climático e resolução da imagem. A ferramenta não abre saves/banco, não chama mapas públicos e não divulga locais desconhecidos. Exporta temperatura média, precipitação anual e temperaturas dos períodos 1/3 nas seis faces, resumo, comparação entre mundos e plano C1 opcional.

Artefatos: [comparação completa](../artifacts/climate-c1/comparison.json), [atlas seed 42](../artifacts/climate-c1/seed-42-r63710000/climate.png), [atlas seed 0](../artifacts/climate-c1/seed-0-r63710000/climate.png), [atlas seed 2026](../artifacts/climate-c1/seed-2026-r63710000/climate.png). Imagens são técnicas e mostram a resolução declarada; não são um Atlas Interativo.

## Qualidade e comparação entre mundos

Todas as seis amostras usam o preset C1 padrão, nível 5 e H1/V4 padrão para cada raio. Métricas globais distribuem um quarto da área esférica exata de cada célula entre seus vértices e ponderam os campos discretos. Isso evita contar centros, bordas e cantos do cubo como áreas iguais, mas continua sendo quadratura de campos amostrados, não integração exata da superfície climática contínua.

| Seed | Raio (km) | Temperatura média ponderada | Precipitação anual média ponderada | Terra com déficit P/PET > 75% | Residual máximo de umidade |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 63.710 | 9,37 °C | 295,7 mm | 83,2% | 11 ppm |
| 42 | 63.710 | 8,91 °C | 304,9 mm | 82,1% | 14 ppm |
| 2026 | 63.710 | 10,07 °C | 382,7 mm | 76,0% | 24 ppm |
| 42 | 6.371 | 8,26 °C | 186,9 mm | 90,4% | 1.039 ppm |
| 42 | 637.100 | 8,73 °C | 273,6 mm | 78,4% | 2 ppm |
| 42 | 1.000.000.000 | 8,73 °C | 273,6 mm | 78,4% | 2 ppm |

A média de precipitação inclui oceanos e terras. O déficit compara chuva com a **demanda potencial parametrizada**, não mede água disponível ou aridez ecológica observada. Terras frias com demanda nula não recebem classificação úmida por esse indicador. O preset produz grande déficit continental: **isso é uma limitação de calibração para o RPG**, não evidência de que todos esses territórios sejam desertos ou precisem ganhar chuva artificial. Antes de usar índices para biomas/ecologia, será necessário avaliar a calibração de transporte/PET com objetivos de worldbuilding explícitos, sem forçar diversidade por seed.

Não houve campos constantes, chuva negativa, descontinuidade de face ou instabilidade numérica nas amostras. Temperaturas variam com latitude, relevo e estação; regiões marítimas têm amplitude menor. Um teste controlado verifica aumento de precipitação numa subida e redução a sotavento. Isso confirma a regra do modelo, não validação observacional de um planeta real.

No raio de referência, seed 42, as médias anuais amostradas variaram de **−40,94 a +24,35 °C**, precipitação anual de **0 a 2.807 mm** e amplitude térmica sazonal de **0,67 a 33,49 °C**. Não são extremos diários. A semelhança dos dois raios extremos decorre da escala angular saturada da formação e da calibração geográfica automática; não estabelece equivalência física entre atmosferas.

## Desempenho observado

Preparo C1 em nível 5: **1,69–2,34 s**, separado dos **3,11–7,53 s** de preparação V4/H1 quando ainda não existem em memória. C1 usa 6.146 avaliações distintas do terreno e até 64 passadas globais, sem custo proporcional a todos os setores físicos. Os testes usam limites estruturais/memória, não tempos rígidos de CPU.

Os payloads compactos ficaram em **1,07–1,10 MB**. A recarga JSON com validação levou **38–43 ms**, sem reexecutar transporte. Em 100 consultas por amostra, medianas em memória ficaram em **0,17–0,18 ms** para interpolação global e **0,27–0,37 ms** com uma avaliação adicional V4 regional. Excluem ORM, checksums de fonte e desserialização da fonte V4; não são latências medidas da ação do jogador. Cada leitura de campo usa somente quatro vértices, inclusive os vetores de vento.

Uma construção separada da seed 42 de referência, com geometria C1 fria, teve pico instrumentado de **17.165.596 bytes (~16,4 MiB)** e retenção de **11.498.441 bytes (~11,0 MiB)**. O escopo exclui V4/H1 já existentes, ORM e imagens; não é RSS do processo. A instrumentação não participa dos tempos normais de construção. As estruturas transitórias de transporte são descartadas após a preparação, sem filas, workers ou simulação contínua.

## Arquivos desta fase

| Arquivo | Entrega |
| --- | --- |
| `backend/app/game/world/genesis/climate/config.py` | Versão, limites e preset configurável C1. |
| `.../climate/geometry.py` | Vértices esféricos compartilhados, adjacência e interpolação de quatro pontos. |
| `.../climate/physics.py` | Forçamento solar, temperatura, ventos, PET, condensação, distância e transporte. |
| `.../climate/plan.py` | Plano imutável, preparação, validação e recarga sem solver. |
| `.../climate/query.py` | Leitura global/regional, fase anual e contrato futuro de balanço hídrico. |
| `.../climate/service.py`, `__init__.py` | Opt-in, cache limitado, snapshots e persistência. |
| `.../climate/preview.py` | Métricas com área esférica e imagens offline. |
| `backend/app/db/models/world_climate.py`, `models/__init__.py` | Modelos C1 e registro ORM. |
| `backend/app/game/world/reset.py` | Exclusão C1 antes dos pais H1. |
| `backend/alembic/versions/l20l3g4h5i6j_add_climate_c1.py` | Migração aditiva sem conversão de saves. |
| `backend/app/tests/test_genesis_climate.py`, `test_genesis_climate_persistence.py` | Núcleo, contratos, recursos, compatibilidade e migração. |
| `backend/scripts/preview_climate.py` | Comparação multi-seed/raio e benchmarks offline. |
| `docs/world-genesis-phase-0.5.md`, `artifacts/climate-c1/` | Decisões, métricas, imagens e planos reproduzíveis. |

As alterações das fases anteriores presentes no workspace foram preservadas. Nenhum algoritmo de altitude V4, H1, HR1, R1, grafo de movimento, mapa público, sistema de tempo ou dataset foi modificado nesta fase.

## Testes executados

**445 testes selecionados passaram em 148,81 s**, sendo 410 casos existentes e 35 novos casos C1. Não foi executada a suíte completa do backend/frontend. Permanece o aviso preexistente Starlette/httpx; não houve falha nessa rodada final.

A seleção inclui `test_genesis*.py`, `test_map*.py`, `test_travel*.py`, `test_world_gen*.py`, `test_regional_boundaries.py`, `test_cross_region_routes.py`, `test_explor*.py`, `test_campaign_reset.py`, `test_region_skeleton.py`, `test_neighbor_region_materialization.py`, `test_world_simulation_integration.py`, `test_simulation_scope.py` e `test_world_time*.py`.

Novos casos: configuração estrita/versionada; orçamento nos níveis 3/4/5; interpolação idêntica entre cartas nas bordas/cantos; gradiente de latitude e altitude; inversão sazonal entre hemisférios; amortecimento marítimo; inclinação zero e insolação polar; ventos tangentes e polos; regra orográfica/sombra de chuva; transporte síncrono independente da ordem; planeta todo oceânico ou sem fonte oceânica; ausência de água interior inventada; roundtrip sem solver; fontes preservadas; quatro vértices por consulta; ajuste regional somente de altitude; periodicidade/contrato temporal; entradas hidrográficas sem vazão; aproximação às emendas e polos; rejeição de payloads inválidos; hashes congelados do plano/leitura; replay em dois processos com `PYTHONHASHSEED` diferente; quatro combinações de seeds/raios até 10¹² m; memória/payload limitados; aridez indefinida quando PET é zero; viewer offline; opt-in; configuração fixada; snapshots em ordem inversa; mudanças persistidas; recarga/carga adiada/cache sem reconstrução; rollback; cache de dois planos; exclusão por campanha; checksums/fontes; migração aditiva com V4/H1/HR1 preservados.

Também passaram `compileall`, `git diff --check` e a conferência Alembic com cabeça única `l20l3g4h5i6j`. Os seis planos técnicos foram gerados e recarregados com validação. O atlas de referência foi inspecionado visualmente. Não foram alterados mapas ou saves de jogo para produzir os artefatos.

## Limitações e próximas etapas

C1 entrega uma base climática global funcional, contínua na resolução declarada e consultável regionalmente. É climatologia parametrizada: não resolve clima diário, extremos meteorológicos, estoque de neve/gelo, rios alimentados ou lagos permanentes. A resposta orográfica regional menor que a grade climática permanece pendente; a correção local implementada usa somente altitude V4 para temperatura/demanda/neve potencial.

Próximos passos devem avaliar a calibração do preset e, separadamente, definir um balanço hídrico versionado com armazenamento, evaporação efetiva e eventual alimentação das rotas **compatíveis** H1/HR1. Não é necessário iniciar T1, biomas, flora, fauna ou civilizações para consumir os contratos C1; resultados subgrid continuarão explicitamente fora das garantias até que esses sistemas tenham modelos próprios.
