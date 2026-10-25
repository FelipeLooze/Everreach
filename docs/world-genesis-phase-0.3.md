# World Genesis — fase 0.3: formação planetária

## Auditoria e decisão antes da implementação

Foram lidos `sphere_config.py`, `sphere_topology.py`, `sphere_metric.py`, `sphere_geography.py`, `service.py`, `spatial.py`, os modelos GenesisWorld/GenesisSphereSector e os testes de topologia, migração e integração espacial. V2 já fornece raios inteiros canônicos, vizinhos entre faces, métrica esférica, configurações fixadas e snapshots recuperados antes de gerar. Seu relevo atual é um campo 3D simplificado, sem tectônica ou componentes físicos. Não será alterado.

| Alternativa | Avaliação |
| --- | --- |
| Somente ruído/fractal com limiar marítimo | Barato, mas sem causa para continentes e cordilheiras; rejeitado como fundamento. |
| Simular deriva, colisões e erosão por milhões de anos em alta resolução | Mais expressivo, mas incompatível com o custo e o escopo desta fase. |
| Reconstrução cinemática simplificada de placas + isostasia aproximada + relevo multiescala | Escolhida: propriedades persistentes de placas e movimento relativo explicam bacias, colisões, subducção e riftes; detalhe é função global da direção esférica. Não é um simulador geofísico. |

Referências de mecanismos físicos: [NOAA sobre formações de borda de placas](https://oceanexplorer.noaa.gov/ocean-fact/tectonic-features/) e [NPS sobre evidências dos movimentos de placas](https://www.nps.gov/subjects/geology/plate-tectonics-evidence-of-plate-motions.htm). A associação de convergência, divergência e cisalhamento a relevo é uma simplificação de engenharia desta implementação; não há reprodução quantitativa da Terra ou garantia astrofísica para raios gigantescos.

### Contratos decididos

- Configuração/gerador v3 explícitos, ainda sobre a topologia cube-sphere v2; raio inicial 63.710.000 m. V1/v2 permanecem legíveis, sem conversão ou mudança de defaults legados.
- Calibrar automaticamente nível de setores por tamanho físico desejado; escala característica de placas cresce com o raio e com o orçamento global. Registrar calibração e degradações por limite de resolução, em vez de assumir que mudar só raio é suficiente.
- Nucleação determinística e probabilística em candidatos esféricos limitados. Candidatos são orçamento de planejamento, não quantidade fixa de continentes/placas. Não escolher contagens de massas terrestres, oceanos ou montanhas para preencher o mundo.
- Placas têm direção, eixo de rotação, velocidade, tipo de crosta e idade. Interações recebem IDs derivados do par de placas e do mecanismo. Relevo deve registrar contribuição e proveniência para futura integração mineral/geológica.
- Mistura contínua de influências de placas, sem elevação por face ou corte abrupto de Voronoi. Campos em 3D globais apenas modulam a estrutura tectônica; não a substituem.
- Componentes globais identificados uma vez em grafo macro de no máximo 6.144 células com adjacência exata entre faces. IDs derivam do menor endereço do componente, seed e configuração; independem da exploração. Garantia é conectividade no grafo macro, não conectividade exata de toda costa local. A consulta deve sinalizar discordância terra/água entre amostra local e célula macro.
- Plano global de baixa resolução fica persistido em GenesisWorld.plan. Setores e suas alterações continuam na tabela esférica existente. Nenhum tick ou movimento deve enumerar a malha planetária de setores.
- Visualização será ferramenta offline de desenvolvimento; sem endpoint de jogo, alterações de descoberta, datasets ou dependência de LLM.

## Formação entregue

### Escala e orçamento

`FormationConfig` herda os contratos esféricos, fixa config/generator **3** e mantém o raio configurável entre 1.000 e 10^12 m. Somente a configuração nova assume raio inicial **63.710 km**. Nenhum default de v1/v2 foi alterado.

O nível de setor é escolhido automaticamente para um vão nominal de 16 km, usando o comprimento de um quarto de círculo e subdivisões binárias, limitado ao nível 24 da topologia existente. É escala **nominal**, não garantia de arestas idênticas: a projeção radial do cubo tem distorção, e a métrica esférica continua autoritativa. Sobrescrever explicitamente nível/resolução é permitido e fica persistido; reabrir não recalibra o save.

A escala característica de placas é aproximadamente `4.000 km * sqrt(R / 6.371 km)`, limitada superiormente por R e inferiormente por R/8 no regime de raios enormes. Esse piso adapta o tamanho das estruturas ao orçamento global em vez de tentar colocar uma quantidade ilimitada de placas de tamanho terrestre num planeta gigantesco. Largura de orogenia, ondulações regionais e detalhe derivam dessa escala, respectivamente L/25, L/3 e L/40. Não há multiplicação silenciosa do número de setores carregados.

No raio de referência, os valores resolvidos são:

| Propriedade | Valor |
| --- | --- |
| Setor | nível 13; vão nominal ~12,2 km |
| Escala característica de placas | ~12.649 km |
| Largura característica de orogenia | ~506 km |
| Comprimento de onda regional | ~4.216 km |
| Comprimento de onda do detalhe | ~316 km |
| Identidades globais | nível 5, 6.144 células, vão nominal ~3.127 km |

No raio máximo, o nível 24 não atende 16 km nominais: o plano registra `sector_resolution_limited=true`. O planejamento também registra `macro_resolution_limited` quando sua resolução fica abaixo da escala solicitada. Não se promete resolução local ilimitada em qualquer raio; ampliar a hierarquia exigirá uma versão de contrato apropriada.

### Placas, bacias e relevo

1. **Nucleação:** 384 posições candidatas de uma malha esférica nível 3 são deslocadas deterministicamente dentro de suas células. Cada posição é ativada por uma probabilidade derivada da área física e da escala característica. A quantidade efetiva varia por seed e configuração; não é uma contagem pedida de conteúdo. O mínimo de dois sites serve ao particionamento cinemático, não força terra/oceano. Não se trata de um processo de Poisson uniforme em área: o cube-sphere radial tem variação de área por célula.
2. **Propriedades:** cada placa tem slot estável, centro esférico, eixo de rotação, velocidade em mm/ano, idade parametrizada e tipo de crosta. O parâmetro de fração de crosta continental é probabilístico por placa, não uma meta exata de área terrestre. Configurações inteiramente continentais ou oceânicas são válidas; não se força diversidade para preencher o planeta.
3. **Contornos orgânicos:** deformação global suave em 3D modifica o domínio de reconstrução das placas. Ela evita costas poligonais e mantém a mesma função nas emendas e nos polos. É uma deformação estática de engenharia, não advecção de placas rígidas resolvida fisicamente.
4. **Mistura contínua:** influências compactas dependem dos produtos escalares com os centros e do maior escore contínuo. A mistura não troca abruptamente a altura quando muda a placa dominante, inclusive em junções triplas. A identidade de placa pode mudar numa fronteira, mas o campo de altura permanece compartilhado.
5. **Bimodalidade de crosta:** crosta continental tem sustentação positiva aproximada; bacias oceânicas têm base negativa com proxy de resfriamento/idade. Essa estrutura explica a distribuição principal terra/oceano. Ondulações de manto e variação regional modulam a costa e podem formar depressões e águas interiores; não são o único critério que cria continentes.
6. **Cinemática de bordas:** velocidades tangenciais relativas são projetadas na normal do par de placas. Compressão continental produz faixa elevada e ombros amplos, preparando cadeias e planaltos; extensão continental produz depressões/riftes. Subducção usa arco elevado no lado sobrejacente e depressão no lado de subducção. Oceanos divergentes recebem dorsais; convergência oceânica pode produzir arcos insulares. Idade desempata qual crosta oceânica subducta. Cisalhamento produz relevo de falha e recebe mecanismo `transform_fault` quando domina.
7. **Detalhe multiescala:** campos globais de sustentação, variação regional e rugosidade modulada pelo relevo tectônico produzem áreas suaves, planícies, depressões, cristas e variação ao longo das cadeias. Nenhuma formação exige nomes ou número fixo de locais. Não há geração de geometria de cavernas, rochas, jazidas ou materiais nesta fase.

Aritmética autoritativa é inteira: direções em ponto fixo de 30 bits, normalização por raiz quadrada inteira, hashes SHA-256 por subsistema/coordenada e interpolação smoothstep. Taxas de movimento ficam em ponto fixo até o cálculo de altura, evitando degraus de dezenas de metros por arredondamento prematuro a mm/ano inteiros. Amostras em faces diferentes usam o mesmo raio canônico e resultam no mesmo registro de geologia. Altura final é quantizada a metro, não uma superfície analítica de precisão infinita.

### Causas rastreáveis

Cada amostra pode ser consultada por `sample_at(plan, SurfacePoint(...))` e registra:

- Elevação, placa dominante e fração de crosta continental interpolada.
- Contribuições de sustentação de crosta, ondulação de manto, variação regional, interação tectônica e detalhe. A soma dos termos é a elevação final.
- Pares de placas contribuintes, mecanismo, taxa relativa, cisalhamento, distância aproximada à borda no domínio reconstruído, soerguimento, subsidência e relevo de falha.
- IDs de estrutura derivados de assinatura do mundo, slots das placas e mecanismo. Esses IDs se repetem ao longo da interação, incluindo através de faces/setores.

As taxas são parâmetros da reconstrução; não são uma previsão de deslocamento ao avançar o relógio do jogo. Termos como sustentação/isostasia e resfriamento são proxies parametrizados, sem solução de equilíbrio térmico, densidade, gravidade ou conservação de massa.

## Identidade física global

O plano avalia o centro de cada célula macro e classifica terra/água pelo relevo e nível do mar. Um flood-fill com os vizinhos esféricos reais une células de mesmo tipo, incluindo emendas. A varredura usa ordem canônica; o menor índice do componente é sua âncora estável. A assinatura inclui seed e configuração inteira; o ID final é `landmass:<assinatura>:<âncora>` ou `water_body:<assinatura>:<âncora>`.

Não se escolhe quantos continentes ou corpos d'água haverá. A mesma massa pode cruzar qualquer número de faces. Corpos d'água conectados representam oceanos, mares conectados ou águas interiores; nomenclatura oceanográfica e distinção lago/mar não são inferidas artificialmente pelo tamanho.

**Garantia exata:** componentes conectados do grafo de centros de células na resolução macro fixada, determinados antes de qualquer exploração. `macro_component_id`, nível e `guarantee=macro_cell_center_connectivity` são explícitos na resposta. A classificação local pode discordar da macro: nesse caso `resolution_mismatch=true` e `physical_component_id=null`. Quando coincide, o ID ainda tem a garantia macro declarada; não prova conectividade da costa em alta resolução.

**Limites:** ilhas, canais, istmos ou mares menores que uma célula podem não ser detectados; a malha pode unir ou separar costas de modo diferente do detalhe. Não haverá renumeração automática conforme o jogador explora. Refinamento futuro deve adicionar identidades subordinadas/relacionamentos versionados, preservando o significado dos IDs salvos. IDs de interações tectônicas identificam uma causa/par/mecanismo, não certificam que todos seus trechos formem uma única cordilheira conectada. Identificação exata de cada cadeia e de toda ilha local continua fora desta etapa.

Region, Subregion, fronteiras políticas e descoberta do personagem não participam desse flood-fill e não determinam IDs físicos.

## Persistência e integração incremental

`initialize_world(db, campaign_id, FormationConfig(...))` calcula e persiste o plano global simplificado: configuração resolvida, calibração, placas, componentes e índice compacto de células. Não cria um único setor local. `materialize_sector` recupera snapshots existentes antes de carregar/avaliar o plano; setores novos leem o plano salvo, sem reconstruí-lo. `prepare_location_sector` e âncoras/coberturas da fase 0.2 funcionam com v3 por meio do mesmo contrato esférico.

O plano é uma estrutura imutável em memória, com cache LRU de no máximo dois planos. Exportar produz cópia JSON independente. O carregador rejeita versão, seed, configuração ou índices inconsistentes, sem tentar consertar/recriar o mundo salvo. Setores guardam alturas e causas por amostra e preservam o campo separado `changes` já existente. Não se implementou replay de acontecimentos nem aplicação de deslizamentos ao relevo nesta fase.

**Nenhuma migração nova de esquema foi necessária:** GenesisWorld.plan e os snapshots JSON de GenesisSphereSector já acomodam a v3. A configuração fixada na raiz impede trocar v2 por v3 num save. Não se reinterpretam coordenadas ou setores antigos e não se altera o grafo de movimento, duração, risco ou unidades de viagem. O banco `everreach.db` não foi aberto para migração ou gravação nesta tarefa.

O dispatch de configuração aceita v3 explicitamente. Configuração omitida continua abrindo a versão persistida ou criando v1 no contrato genérico anterior. O fluxo público de início de campanha ainda não escolhe v3 automaticamente; esse continua sendo um serviço opt-in para uma futura criação de novos mundos. Não se atribui formação nova à geografia legada de uma campanha existente por conversão implícita.

## Visualização técnica entregue

Ferramenta offline, sem servidor, endpoint de jogo ou acesso ao banco:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.preview_planet --seed 42 --radius-m 63710000 --face-size 128 --output ../artifacts/planet-v3-seed42
.\.venv\Scripts\python.exe -m scripts.preview_planet --plan ../artifacts/planet-v3-seed42/plan.json --inspect-ray 1 1 0
```

Ela gera atlas das seis faces com relevo, componentes macro e causas tectônicas; exporta `plan.json`, `summary.json` e PNGs individuais/compostos. A consulta por raio inteiro mostra elevação, identidade e termos geológicos. Limite de imagem: 16..256 amostras por eixo/face. As bordas douradas da camada tectônica são anotações de desenvolvimento, não barreiras físicas.

A camada de componentes usa amarelo para discordância entre terreno local e célula macro. O relevo usa apenas altitude (azul, tons de areia/marrom/branco), sem biomas. PNG é projeção técnica, sem igualdade de área. O JSON de fração de terra representa fração das amostras das faces, **não medição exata da área da esfera**. A ferramenta não altera `CharacterLocationDiscovery`, `CharacterConnectionDiscovery`, mapa público ou qualquer save.

Prévia inspecionada: `artifacts/planet-v3-seed42/planet.png`. Para seed 42, configuração de referência e 128×128 pontos por face, a amostragem encontrou 95 placas, 15 componentes terrestres e 14 aquáticos na malha macro, alturas entre −6.972 e 13.031 m e ~3,94% de discordância local/macro. Esses números são resultados desse exemplo, não metas, garantias globais de relevo ou contagens impostas ao gerador. O atlas mostrou costas inicialmente poligonais na primeira iteração; a deformação contínua foi adicionada e a versão final foi inspecionada visualmente.

## Arquivos desta fase

| Arquivo | Alteração |
| --- | --- |
| `backend/app/game/world/genesis/formation_config.py` | Novo: configuração v3, resolução automática e calibração de estruturas. |
| `.../genesis/formation_noise.py` | Novo: direções e campos 3D inteiros independentes por domínio. |
| `.../genesis/formation_plates.py` | Novo: nucleação limitada e propriedades tectônicas reproduzíveis. |
| `.../genesis/formation_tectonics.py` | Novo: reconstrução de relevo e contribuições causais. |
| `.../genesis/formation_plan.py` | Novo: planejamento global, componentes, IDs, exportação/carregamento e cache limitado. |
| `.../genesis/formation_geography.py` | Novo: amostra física, identidades e geração de snapshots de setores v3. |
| `.../genesis/formation_preview.py` | Novo: atlas técnico offline e inspeção de camadas. |
| `.../genesis/sphere_config.py` | Modificado somente para dispatch explícito da configuração v3. |
| `.../genesis/service.py` | Modificado para planejamento/materialização v3, preservando caminhos v1/v2. |
| `.../genesis/spatial.py` | Mensagem ajustada para aceitar semanticamente mundos esféricos v2/v3. |
| `backend/scripts/preview_planet.py` | Novo CLI de geração de atlas e inspeção por raio canônico. |
| `backend/app/tests/test_genesis_formation.py` | Novo: testes de formação, escala, identidade, continuidade, persistência e visualização. |
| `backend/app/tests/test_genesis_sphere_topology.py` | Caso de versão desconhecida atualizado de 3 para 4, pois 3 passou a ser suportada. Nenhum vetor v2 alterado. |
| `docs/world-genesis-phase-0.3.md` | Novo: auditoria, alternativas, implementação, garantias, resultados e limites. |
| `artifacts/planet-v3-seed42/` | Novo: prévia técnica, plano, resumo e medição de recursos deste exemplo. |

Reaproveitados: topologia cube-sphere v2, pontos inteiros, vizinhança e métrica, Campaign/world_seed, derive_seed/coordinate_seed, GenesisWorld/GenesisSphereSector, transações, limpeza de campanha, hooks espaciais e filtro de conhecimento do mapa. Alterações locais preexistentes de quests, recompensas, engine, simulação, frontend e arquivos das fases anteriores foram preservadas. Nenhum dataset foi integrado ou alterado.

## Validação executada

- **48 testes novos passaram.** Determinismo de plano/setores entre processos e ordens; vetor fixo do plano v3 e de elevação; continuidade de geologia e IDs nas 24 orientações de borda, seus cantos, interiores de setores e perturbações em emendas/polo.
- IDs: união controlada de massa entre faces, componentes macro canônicos, corpos terrestres e aquáticos reais atravessando faces, consulta consistente e discordância submacro explícita.
- Geologia: caso controlado com faixa de colisão >10.000 km, efeito oposto de rifte, dorsal oceânica acima de bacia com placas estacionárias, soma de termos e IDs de interações extensas no planeta real gerado. São testes de mecanismos e contratos, não validação geocientífica quantitativa.
- Persistência: v1/v2/v3 juntas no mesmo banco de teste, planos e alterações preservados ao reabrir, proibição de reconstrução de planos/terreno salvo, uso do plano persistido para setor novo, início com um único setor, rollback e exclusão com FKs ativas. Mudança implícita de versão/raio é rejeitada.
- Escala: configuração de referência recalibrada, raio até 10^12 m com limites declarados, plano ≤6.144 células e ≤384 candidatos de placa, cache limitado, serialização abaixo do orçamento de teste e medição de alocações. Não se testa nem se materializa a superfície em alta resolução.
- Visualização: PNGs/JSONs gerados, plano inalterado após visualização, consulta CLI a partir de exportação e inspeção visual do artefato final. Teste de mapa v3 confirma que plano autoritativo e terreno preparado não revelam coordenadas de locais desconhecidos ou apenas conhecidos sem visita.
- **207 testes anteriores passaram**, incluindo Genesis v1/v2, mapa, descoberta, viagens, fronteiras, relógio, materialização, simulação por escopo e exclusão. A execução ampliada passou 254 casos antes do último teste adicional; a suíte v3 final passou 48, totalizando **255 casos distintos aprovados**. A suíte completa do backend e os testes frontend não foram executados.
- `compileall`, `git diff --check` e cadeia Alembic foram verificados. A cabeça continua única: `i17i1d2e3f4g`. Aviso preexistente de depreciação Starlette/httpx, sem falhas nos testes selecionados.

Medição em processo novo, com tracemalloc ativo, do plano padrão seed 42: **6.144 células**, **95 placas**, **38.363 bytes** de JSON com espaçamento padrão, **350.316 bytes de pico de alocações Python rastreadas**, **12,465 s** com instrumentação. Não é RSS do processo, memória total de SQLAlchemy/UI ou limite universal de tempo. O plano foi medido antes de serializar/exportar; snapshots locais crescem somente com setores materializados. O custo global é limitado pela malha macro e pelos candidatos; cada ponto custa O(P + A²), com P placas e A influências ativas, mais um número fixo de consultas de ruído. A medição está em `artifacts/planet-v3-seed42/resources.json`.

## Limitações e próxima etapa

Modelo estático de reconstrução, sem deriva histórica integrada, convecção, erosão física, drenagem, sedimentação, rochas, minerais, solos, gravidade recalibrada ou simulação de densidade de planetas gigantes. A escala horizontal se adapta; amplitudes verticais são parâmetros do modelo de jogo e não uma previsão para densidades/gravidades extremas. Crosta, idade e movimento são parâmetros procedurais rastreáveis, não medições ou dados importados.

Arquipélagos, bacias e mares interiores podem emergir, mas não são forçados em toda seed. Não há catálogo nomeado de cada planície, depressão ou ilha; IDs macro e IDs de causa tectônica têm as garantias declaradas. A resolução macro limitada troca precisão de costa por planejamento previsível e persistência estável.

Próxima etapa recomendada: estabilizar critérios de aceitação de relevo usando várias seeds e raios, e definir a estratégia de refinamento de costas/bacias mantendo IDs macro. Depois preparar hidrologia global simplificada e condições de contorno por bacia, sem transformar setores locais em fontes independentes de rios. Integração de início de campanha v3 e projeção de mapa continuam tarefas explícitas próprias. Datasets, ecossistemas, assentamentos e Living Frontiers dinâmicas não foram antecipados.
