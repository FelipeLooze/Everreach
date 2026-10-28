# World Genesis — fase 0.5.1: auditoria e calibração climática

## Diagnóstico e decisão técnica

A auditoria inicial separou continentes, oceano de referência H1 e terreno abaixo do datum desconectado. Pesos usam área esférica, não contagem uniforme de vértices do cubo. Classes de umidade são índices P/PET, sem gerar biomas.

Na seed 42 de referência, C1 produz 167,2 mm/ano sobre terra e 444,7 mm sobre o oceano. Terras a mais de 10.000 km da fonte oceânica recebem 11,9 mm/ano; sua aridez é coerente com o fetch e rainout do modelo. Entretanto, os oceanos 45°–60° recebem somente 145,4 mm/ano: esse resultado independe de um supercontinente distante.

Foi identificada uma lacuna específica: C1 prescreve três bandas de circulação, mas a condensação em baixa altitude fora dos trópicos cai à base de 5%, sem representar ascensão junto à borda polar. A referência conceitual da [NOAA sobre circulação global](https://www.noaa.gov/jetstream/global/global-atmospheric-circulations) descreve o papel das médias latitudes nesse esquema terrestre. C2 não deduz que o planeta seja a Terra; fecha de maneira parametrizada o próprio preset de bandas já escolhido em C1.

Experimentos controlados na mesma geografia: dobrar o comprimento de transporte eleva P terrestre de 167,2 para 182,8 mm; remover orografia reduz P para 89,4 mm; dobrar a conversão de chuva ou reduzir PET à metade ainda deixa ~76–77% de terra com P/PET < 0,25. Isso não justifica multiplicar chuva indiscriminadamente ou reduzir demanda para alcançar um percentual de umidade.

**Decisão:** criar C2 explícito, acrescentando somente ascensão extratropical estacionária à regra de condensação existente. Mantêm-se oferta oceânica, temperaturas, PET, ventos, influência marítima, perdas de distância, orografia e número de passadas. O ganho novo é configurável; seu padrão de 250.000 ppm é comparável à eficiência convectiva tropical, não foi escolhido para impor cobertura de ambientes. C1 permanece reproduzível, com seus vetores congelados e sem conversão automática.

Uma banda triangular contínua cresce de zero na borda Hadley ao máximo na borda polar e cai a zero nos polos. A chuva extra só existe onde há umidade transportada. Não se acrescentam fontes sobre terra, meteorologia diária, correntes, frentes móveis ou simulação atmosférica. A maior perda por condensação também pode **reduzir** chuva a sotavento; não se promete tornar todo continente mais úmido.

## Escopo da auditoria

Foram avaliadas **15 seeds distintas** no raio de 63.710 km: **0–12, 42 e 2026**. Acrescentaram-se três amostras da seed 42 em raios de 6.371 km, 637.100 km e 10⁹ km (10¹² m). São 18 geografias/configurações pareadas, todas no nível climático 5, com 6.146 vértices. Não houve seleção de seeds por clima favorável.

Os planos C1 existentes da fase 0.5 foram carregados quando disponíveis; os demais foram gerados com os mesmos defaults V4/H1/C1. Cada C1 foi depois reconstruído a partir de suas amostras fixadas e comparado por igualdade completa, antes de calcular C2 sobre as mesmas alturas e máscara oceânica. O construtor público C2 também foi executado sobre V4/H1 na referência e produziu exatamente o mesmo plano C2 do kernel pareado.

Os pesos distribuem a área esférica exata das células aos quatro vértices compartilhados. Não são usados pesos iguais por amostra. É uma quadratura de campos discretos, não integração exata da superfície contínua. As três superfícies são registradas separadamente: terra acima do datum, oceano de referência H1 e terreno abaixo do datum desconectado do oceano. Este último não é automaticamente considerado lago, continente seco ou fonte oceânica.

Há tabelas por latitude absoluta, distância física ao oceano e distância normalizada pelo comprimento marítimo, altitude, período sazonal e posição a barlavento/sotavento. A distância é a do **grafo climático até um vértice oceânico**, não uma medição exata da costa. Na referência, as ligações têm escala de milhares de quilômetros; a ausência de amostras na classe costeira menor que 1.000 km é limite de resolução, não ausência física de litoral.

## Investigação dos mecanismos

| Mecanismo | Resultado da auditoria | Ação |
| --- | --- | --- |
| Oferta oceânica | Na seed 42/período 0, índice fonte médio do oceano ~573.448 ppm; fontes quentes tropicais já produzem precipitação. | Preservada; não se multiplicou a umidade oceânica. |
| Transporte continental | Todos os vértices terrestres das 18 amostras têm algum caminho dirigido à fonte oceânica. No caso de referência, o maior caminho mínimo tem 22 passos. | Preservado; não foram constatadas áreas absolutamente isoladas por um grafo quebrado. |
| Atenuação por distância | Retenção média terrestre de ~894.583 ppm por passo (~2.990 km) na referência/período 0. Dobrar o comprimento de transporte muda pouco a fração seca. | Preservada; fetch longo continua reduzindo a oferta. |
| Condensação/rainout | Perda média terrestre C1 de ~211.074 ppm por ligação no mesmo período; acumula-se ao longo do percurso. | Preservadas a base/tropical/orográfica; acrescentada somente ascensão extratropical em C2. |
| Chuva fora dos trópicos | Oceanos 30°–45° e 45°–60° muito secos mesmo com fonte local de umidade. | Corrigida a omissão da ascensão extratropical do preset de circulação. |
| Orográfica/sombra de chuva | Remover a regra reduz muito a chuva terrestre; subida amostrada recebe mais chuva e depleta umidade a jusante. | Preservada; não foram removidas montanhas nem suas perdas para umedecer interiores. |
| PET | Proxy de demanda aumenta com temperatura/energia e zera sob forte limitação térmica. Reduzi-lo à metade melhora índices, mas não corrige a distribuição de chuva. | Preservado; não se usou PET para ajustar percentuais de aridez. |
| Temperatura/amplitude | Campos térmicos, insolação, marítimo/continentalidade e ventos são exatamente iguais entre C1/C2 nas 18 amostras. | Preservados integralmente. |
| Estações | Mantidos quatro períodos iguais; chuva reage às fontes, ventos e relevo de cada período. | Sem novo calendário, eventos diários ou estações obrigatórias. |

O teste de alcance dirigido verifica a existência de caminho, não garante umidade significativa depois das perdas. Na amostra de raio terrestre, até ~1% da área terrestre possui caminho mínimo de fonte maior que as 40 passadas padrão; o residual registrado e as limitações numéricas continuam explícitos. Não há promessa de equilíbrio atmosférico exato.

Um experimento de 40 → 64 passadas na seed 42 verificou esse limite sem alterar o default: no raio de 6.371 km, P terrestre C2 muda de 60,6272 para 60,6310 mm/ano e o residual máximo cai de 137 para 10 ppm. Na referência, muda de 173,2805 para 173,2810 mm e o residual cai de 12 para 1 ppm. A fração seca não muda em nenhum dos dois casos; o horizonte numérico não explica o déficit geral observado. [Resultados completos](../artifacts/climate-calibration-0.5.1/iteration-sensitivity.json).

### Ablações na seed 42 de referência

Todas usam a mesma geografia e alteram apenas o parâmetro indicado. São experimentos offline com configuração explícita, não substituições de C1 salvo.

| Experimento | P terrestre (mm/ano) | P oceânica (mm/ano) | Terra com P/PET < 0,25 |
| --- | ---: | ---: | ---: |
| C1 padrão | 167,2 | 444,7 | 82,10% |
| Sem condensação orográfica | 89,4 | 366,7 | 80,7% |
| Comprimento de umidade dobrado | 182,8 | 444,7 | 80,9% |
| Conversão de chuva dobrada | 336,2 | 891,5 | 76,4% |
| PET reduzida à metade | 167,2 | 444,7 | 76,8% |
| Condensação basal 50.000 → 150.000 ppm | 179,0 | 691,6 | 80,0% |

Não se adotaram esses ajustes globais. A sensibilidade do ganho extratropical C2 (0/150.000/250.000/400.000 ppm) também foi exportada: P terrestre é respectivamente **167,2/171,7/173,3/174,7 mm**, enquanto P oceânica é **444,7/509,6/552,6/617,0 mm**. A resposta terrestre saturada mostra por que elevar ganhos indefinidamente não resolveria os interiores distantes e poderia agravar rainout. Com ganho zero, **todos os campos físicos C2 coincidem com C1**; somente versão/assinatura/configuração diferem.

## Comparação C1/C2 por seed

Cada célula de comparação abaixo mostra **C1 → C2**. Os totais são médias anuais ponderadas por área da superfície indicada, em mm. A porcentagem seca é um índice terrestre P/PET < 0,25, não percentual de desertos ou de biomas. Não se impuseram limites de aprovação por percentuais.

| Seed | P global | P terrestre | P oceano de referência | Índice seco terrestre |
| --- | ---: | ---: | ---: | ---: |
| 0 | 295,7 → 358,7 | 157,7 → 164,3 | 425,5 → 536,7 | 83,24% → 81,75% |
| 1 | 336,6 → 410,7 | 214,5 → 222,1 | 422,8 → 541,3 | 78,14% → 76,32% |
| 2 | 356,8 → 429,0 | 204,4 → 210,2 | 460,7 → 574,9 | 78,72% → 77,65% |
| 3 | 360,7 → 431,8 | 191,6 → 198,8 | 467,3 → 574,7 | 74,34% → 72,60% |
| 4 | 279,3 → 332,3 | 133,0 → 138,3 | 445,5 → 547,1 | 84,51% → 83,63% |
| 5 | 272,8 → 326,6 | 141,6 → 147,0 | 430,5 → 538,4 | 84,91% → 83,13% |
| 6 | 304,1 → 365,8 | 156,3 → 161,0 | 427,0 → 533,9 | 82,78% → 81,34% |
| 7 | 296,4 → 343,5 | 162,6 → 166,4 | 491,0 → 593,6 | 82,96% → 81,57% |
| 8 | 307,8 → 372,7 | 157,0 → 161,2 | 434,9 → 549,6 | 82,67% → 81,42% |
| 9 | 317,6 → 367,7 | 153,9 → 159,1 | 472,3 → 561,8 | 83,20% → 81,97% |
| 10 | 311,7 → 383,6 | 166,5 → 173,8 | 421,8 → 541,2 | 81,60% → 80,40% |
| 11 | 300,9 → 381,8 | 179,1 → 185,6 | 391,8 → 526,5 | 80,68% → 79,16% |
| 12 | 179,5 → 209,1 | 96,5 → 99,8 | 474,8 → 573,4 | 88,40% → 87,44% |
| 42 | 304,9 → 363,8 | 167,2 → 173,3 | 444,7 → 552,6 | 82,10% → 80,00% |
| 2026 | 382,7 → 453,3 | 227,1 → 234,6 | 462,7 → 563,8 | 75,98% → 74,19% |

**O ganho principal é a coerência da chuva extratropical, não uma eliminação da aridez continental.** A fração seca de C2 continua entre 72,60% e 87,44% nas seeds de referência. Não se interpreta isso como prova geofísica de desertificação, nem como defeito apenas por diferir da Terra: são saídas do preset de fetch, condensação e demanda sobre geografia gigantesca.

Outros raios, seed 42:

| Raio (km) | P global C1 → C2 | P terrestre C1 → C2 | P oceânica C1 → C2 | Índice seco C1 → C2 |
| --- | ---: | ---: | ---: | ---: |
| 6.371 | 186,9 → 227,8 | 58,4 → 60,6 | 432,8 → 544,2 | 90,43% → 88,76% |
| 637.100 | 273,6 → 342,8 | 190,5 → 196,0 | 375,6 → 509,6 | 78,44% → 77,46% |
| 1.000.000.000 | 273,6 → 342,8 | 190,5 → 196,0 | 375,6 → 509,6 | 78,44% → 77,46% |

A semelhança dos dois raios extremos deriva da escala angular saturada da V4 e dos comprimentos automáticos do preset, não de uma afirmação sobre atmosferas reais.

A amostra de 6.371 km é mais seca que a gigante: portanto não se atribui a aridez apenas ao tamanho do raio. Ela também possui outra geografia V4 e outra máscara de fontes: ~54,65% de terra e 35,32% de oceano de referência amostrado, contra ~43,38% e 50,72% na referência. O terreno abaixo do datum desconectado (~10,03% e ~5,90%, respectivamente) não recebe oferta oceânica automaticamente. Estes são efeitos da geografia **e das hipóteses/resolução do modelo**, não evidência de que todo território seco seja um resultado geofísico inevitável.

## Distribuição geográfica e sazonal

Na seed 42, chuva oceânica por latitude absoluta:

| Latitude | C1 (mm/ano) | C2 (mm/ano) |
| --- | ---: | ---: |
| 0°–15° | 1.006,6 | 1.006,6 |
| 15°–30° | 461,9 | 461,9 |
| 30°–45° | 197,7 | 373,3 |
| 45°–60° | 145,4 | 496,9 |
| 60°–75° | 83,0 | 261,1 |
| 75°–90° | 59,8 | 86,1 |

No mesmo planeta, as amostras terrestres na classe de distância climática 1.000–3.000 km têm P média **634,2 → 668,6 mm**, e 32,08% → 30,39% de índice seco. A mais de 10.000 km, P é **11,9 → 12,4 mm** e 98,74% → 98,53% de índice seco. Existem amostras relativamente marítimas com P ≥ PET, mas não se promete que toda costa seja úmida: direção do vento, latitude e relevo continuam determinantes.

Por altitude, C2 apresenta cerca de **216,6 mm a 0–500 m**, **202,0 mm a 500–1.500 m**, **129,9 mm a 1.500–3.000 m** e **268,2 mm acima de 3.000 m**. A média térmica correspondente é 14,06/5,57/0,79/−12,55 °C, **idêntica em C1/C2**. A correlação de altitude e chuva não é monotônica: latitude, fonte e exposição ao vento também variam; não se usou altitude isolada como gerador de chuva.

No período 0, a precipitação de C2 em equivalente anual é ~527 mm nas amostras de subida a barlavento >300 m por ligação e ~18 mm nas de descida a sotavento <−300 m. É uma estatística descritiva com populações diferentes, não estimativa causal isolada. O teste controlado de uma crista confirma separadamente aumento da condensação na subida e redução da umidade disponível a jusante.

Classes terrestres da seed 42:

| Índice, sem bioma | Definição | C1 | C2 |
| --- | --- | ---: | ---: |
| Úmido pelo índice | P/PET ≥ 1 | 10,35% | 10,66% |
| Déficit moderado | 0,5 ≤ P/PET < 1 | 2,78% | 2,84% |
| Semiárido pelo índice | 0,25 ≤ P/PET < 0,5 | 2,95% | 4,69% |
| Seco pelo índice | P/PET < 0,25 | 82,10% | 80,00% |
| Demanda limitada por energia | PET = 0, aridez indefinida | 1,82% | 1,82% |

O descritor térmico temperado (média anual entre 0 e 20 °C) cobre ~61,46% da terra e **sobrepõe** essas classes; não é uma sexta classe de umidade nem um bioma. Cada relatório exporta temperaturas, amplitudes e totais por período. Uma média planetária sazonal pequena não implica ausência de estações locais: os hemisférios se compensam. Temperaturas/amplitudes dos quatro períodos são exatamente preservadas em C2; a distribuição sazonal de chuva muda conforme umidade e ventos existentes.

## Compatibilidade e integração

`ClimateConfig` continua sendo C1 e os defaults das chamadas existentes continuam C1. Para um novo mundo com C2, a escolha deve ser explícita:

```python
from app.game.world.genesis.climate.v2 import ClimateConfigV2
from app.game.world.genesis.climate.service import initialize_climate

initialize_climate(db, campaign_id, ClimateConfigV2())
```

Um mundo já fixado em C1 rejeita reconfiguração para C2. Comparações usam mundos/campanhas separados ou planos offline sobre a mesma geografia. Não há conversão automática, sobrescrita de snapshots antigos ou alteração de eventos em `changes`.

O dispatch distingue versões 1/2, tags de payload e assinaturas. A leitura e a persistência compartilham as estruturas existentes, com verificação de versão/configuração/proveniência. O esquema `l20l3g4h5i6j` já suporta o campo de versão inteiro; **não foi necessária nova migração**, nem foi aplicado comando ao banco real. Testes exercitam C1 e C2 juntos nesse esquema, preservando payloads, baselines e mudanças C1.

O contrato de entradas para balanço hídrico mantém nomes/unidades e duração dos períodos. A tag identifica `climatological_water_balance_inputs_c1` ou `_c2`, com a assinatura correspondente. Precipitação continua sendo forçamento climatológico; PET continua demanda potencial. Vazão, escoamento efetivo, armazenamento, perenidade e lago permanente continuam indeterminados. Nada foi alterado em V4, H1, HR1, R1, movimento, mapa público ou conhecimento do personagem.

## Imagens e reprodução

A partir de `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.audit_climate_calibration --output ../artifacts/climate-calibration-0.5.1
.\.venv\Scripts\python.exe -m scripts.compare_climate_versions --output ../artifacts/climate-calibration-0.5.1 --measure-memory
.\.venv\Scripts\python.exe -m scripts.benchmark_climate_calibration --output ../artifacts/climate-calibration-0.5.1/performance.json --measure-memory
```

O primeiro comando gera/carrega os 18 C1, métricas e ablações. O segundo verifica replay C1, calcula C2 e comparações. O terceiro deve ser executado isoladamente para medir preparo completo, alternando a ordem de C1/C2 em três repetições. Os scripts não abrem saves do jogo nem alteram mapas públicos. A prévia geral também aceita `--climate-version 2`, mantendo o default 1 existente.

Para as seeds 0, 42 e 2026 na referência, há sete imagens pareadas por planeta: temperatura anual, precipitação anual, aridez, temperatura dos períodos 1/3 e chuva dos períodos 1/3. Os painéis sazonais de P exibem **equivalente anual 4× o total do período** para usar uma única escala de cores; os JSONs conservam os totais reais por período.

Artefatos principais:

- [Comparação de 18 casos](../artifacts/climate-calibration-0.5.1/comparison.json), com 15 seeds de referência, relatórios por superfície e bins geográficos.
- [Ablações C1](../artifacts/climate-calibration-0.5.1/c1-ablations-seed42.json) e [sensibilidade do ganho C2](../artifacts/climate-calibration-0.5.1/c2-sensitivity-seed42.json).
- [Precipitação C1/C2, seed 42](../artifacts/climate-calibration-0.5.1/seed-42-r63710000/precipitation-comparison.png).
- [Aridez C1/C2, seed 42](../artifacts/climate-calibration-0.5.1/seed-42-r63710000/aridity-comparison.png).
- [Temperatura C1/C2](../artifacts/climate-calibration-0.5.1/seed-42-r63710000/temperature-comparison.png), [chuva no período 1](../artifacts/climate-calibration-0.5.1/seed-42-r63710000/period_1_precipitation-comparison.png) e [período 3](../artifacts/climate-calibration-0.5.1/seed-42-r63710000/period_3_precipitation-comparison.png).

As pastas por seed/raio contêm planos C1/C2 e relatórios individuais. Campos térmicos iguais nos painéis não são falha do renderizador: a correção deliberadamente não altera temperatura ou PET.

## Desempenho

O [benchmark isolado](../artifacts/climate-calibration-0.5.1/performance.json) usa a seed 42 de referência, três construções completas por versão alternando a ordem, com geografia climática fria. Inclui as 6.146 avaliações V4 e o transporte climático; exclui o preparo V4/H1 já salvo. Memória é instrumentada em execuções separadas, para não contaminar os tempos.

| Medida | C1 | C2 |
| --- | ---: | ---: |
| Mediana do preparo completo | 3,597 s | 3,630 s |
| Pico de alocações Python nesse preparo | 17.358.764 bytes (~16,55 MiB) | 17.029.016 bytes (~16,24 MiB) |
| Payload compacto | 1.090.529 bytes | 1.091.034 bytes |
| Mediana de consulta global em memória | 0,317 ms | 0,321 ms |
| Mediana de consulta regional, com altitude V4 | 0,775 ms | 0,771 ms |

O custo mediano de preparo aumentou ~0,9%; os orçamentos estruturais permanecem iguais. A pequena diferença de memória depende do alocador/cache e não indica uma otimização de memória de C2. A medida não é RSS e exclui fonte V4/H1 preexistente, ORM e imagens. Os tempos variaram entre repetições, estão registrados integralmente e não são limites rígidos de CPU.

Os 18 pares também têm tempos do kernel C1/C2, recarga e consulta em seus relatórios; essas medições ocorreram durante outras validações e não devem substituir o benchmark isolado. Não há novo worker, simulação contínua, fila, setor distante gerado ou cache sem limite. O cache de dois planos é compartilhado entre versões e consultas continuam lendo quatro vértices.

## Arquivos desta fase

| Arquivo | Mudança |
| --- | --- |
| `backend/app/game/world/genesis/climate/v2.py` | Configuração C2 e única correção física: ganho extratropical compacto na condensação. |
| `.../climate/dispatch.py` | Seleção explícita de configurações C1/C2, sem fallback. |
| `.../climate/plan.py` | Tags/assinaturas por versão, seleção da regra e recarga C1/C2; mesmo kernel e amostras. |
| `.../climate/query.py` | Identificação da versão consultada e da origem dos inputs hidrográficos; campos/unidades preservados. |
| `.../climate/service.py` | Persistência e cabeçalhos fixados por versão, preservando default e saves C1. |
| `.../climate/calibration.py` | Área esférica, classes diagnósticas, bins geográficos, fluxos prescritos e alcance das fontes. |
| `.../climate/calibration_preview.py` | Sete comparações técnicas pareadas, sem mapa público. |
| `.../climate/preview.py`, `backend/scripts/preview_climate.py` | Legenda versionada e opção explícita `--climate-version`, com default 1 preservado. |
| `backend/scripts/audit_climate_calibration.py` | Auditoria de 15 seeds + outros raios e ablações C1. |
| `backend/scripts/compare_climate_versions.py` | Replay pareado, métricas C2, imagens, sensibilidade de ganho e iterações. |
| `backend/scripts/benchmark_climate_calibration.py` | Preparo completo, consultas e memória antes/depois em escopos iguais. |
| `backend/app/tests/test_genesis_climate_v2.py` | Determinismo, compatibilidade física, continuidade, fontes, sombra de chuva, recursos e visualização. |
| `backend/app/tests/test_genesis_climate_v2_persistence.py` | C1/C2 coexistentes, snapshots, mudanças, caches, rollback e esquema anterior. |
| `docs/world-genesis-phase-0.5.1.md`, `artifacts/climate-calibration-0.5.1/` | Diagnóstico, decisões, relatórios, imagens e planos reproduzíveis. |

`climate/config.py` e `climate/physics.py` de C1 permaneceram intactos. Não houve edição adicional de V4/H1/HR1/R1, modelos/esquema de banco, reset, grafo de movimento, exploração, mapa, calendário, datasets ou sistemas ambientais. As alterações das fases anteriores já presentes no workspace foram preservadas.

## Testes e verificação

**469 testes selecionados passaram em 269,66 s: 445 anteriores e 24 novos casos C2.** A execução coincidiu com diagnósticos offline; não é benchmark isolado. A suíte completa do backend/frontend não foi executada. Permanece apenas o aviso preexistente Starlette/httpx.

Foram cobertos: dispatch/valores inválidos; C2 de ganho zero idêntico à física C1; hashes congelados C1 e C2; temperaturas/PET/ventos/altitudes intactos; suporte espacial e limite de condensação; ausência de chuva sem fonte; sombra de chuva e ordem síncrona; continuidade em emendas/cantos/polos; contratos sazonais e inputs hidrográficos; altitude regional; roundtrip sem solver; proveniência; processos com `PYTHONHASHSEED` distintos; múltiplos raios/seeds e memória limitada; soma de áreas esféricas e classes; sete imagens pareadas; opt-in sem conversão; C1/C2 simultâneos; persistência em ambas as ordens; alterações salvas preservadas; retorno sem regeneração; caches limitados; rollback; exclusão por campanha; cabeçalhos/payloads incompatíveis; runtime das duas versões no esquema Alembic já existente.

A regressão selecionada inclui `test_genesis*.py`, `test_map*.py`, `test_travel*.py`, `test_world_gen*.py`, `test_regional_boundaries.py`, `test_cross_region_routes.py`, `test_explor*.py`, `test_campaign_reset.py`, `test_region_skeleton.py`, `test_neighbor_region_materialization.py`, `test_world_simulation_integration.py`, `test_simulation_scope.py` e `test_world_time*.py`.

Também passaram `compileall` e `git diff --check`; Alembic continua com a cabeça única `l20l3g4h5i6j`. Os 18 planos C1 foram reproduzidos por igualdade completa, os 18 C2 foram serializados/recarregados e todos preservaram temperatura/vento. As imagens de chuva/aridez/sazonalidade foram conferidas. Nenhuma migração ou reconfiguração de save real foi aplicada.

## Limitações e parecer

C2 corrige uma omissão do preset de circulação; **não elimina o viés seco geral do modelo nem o valida cientificamente**. O transporte é uma aproximação com perdas por passo, sem reciclagem terrestre explícita, correntes oceânicas, frentes móveis ou conservação atmosférica rigorosa. O nível climático faz parte da configuração autoritativa: não é LOD intercambiável e a calibração foi avaliada principalmente no nível 5.

A resolução global não mede microclimas costeiros, estreitos ou sombra de chuva de vales locais. P/PET não é estoque de água nem diagnóstico ecológico definitivo; campos abaixo do datum desconectados não viram lagos. Valores configuráveis fora do preset exigem nova avaliação; as 15 seeds não provam qualidade de todas as seeds possíveis.

**Podemos avançar para o balanço hídrico como camada versionada, usando C2 explicitamente nos novos mundos e conservando C1 nos antigos.** O balanço deve consumir os campos com sua resolução, preservar massa de água local e só alimentar trechos H1/HR1 compatíveis quando houver disponibilidade/armazenamento suficiente. Isso não autoriza rios perenes, lagos permanentes ou biomas por simples classificação climática. Antes de integrar ecologia detalhada, convém validar conjuntamente demanda, solo/armazenamento e escalas regionais, sem impor percentuais de ambientes.
