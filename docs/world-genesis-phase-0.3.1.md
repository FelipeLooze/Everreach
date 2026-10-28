# World Genesis — fase 0.3.1: validação geográfica

## Escopo e decisões antes das medições

Revisados os módulos v3 de configuração, placas, campos de relevo, plano, snapshots e visualização, além da topologia esférica. A prévia anterior conta pixels com pesos iguais: isso não mede área terrestre corretamente no cube-sphere radial. O primeiro ajuste será exclusivamente diagnóstico: usar o ângulo sólido exato de cada quadrilátero como peso, com testes de conservação de 4π esterradianos e comparação entre resoluções.

Serão amostradas pelo menos 15 seeds no raio de referência de 63.710 km, com repetições de seeds selecionadas em outros raios. O estudo usará amostragem global limitada, imagens e métricas de componentes **diagnósticos**, sem mudar os componentes macro salvos. Contagens não serão metas de conteúdo nem motivo para rejeitar uma seed por simplesmente ter um supercontinente ou oceano dominante.

Para refinamento, a alternativa de relabeling global progressivo foi rejeitada: descobrir uma ponte ou ilha não pode renumerar continentes já salvos. Será avaliado um patch fixo de tamanho limitado, com resolução explícita, IDs subordinados locais e portas de continuidade por endereço compartilhado. Ele consultará somente o campo v3 existente e preservará todos os IDs macro. A conectividade de um patch aberto será local/amostrada, sem alegar uma identidade global exata ou autorização de travessia pelo personagem.

Nenhuma mudança no relevo v3, datasets, hidrologia, mapa público, grafo de movimento ou simulação temporal faz parte desta fase.

## Execução e critérios de avaliação

Foram geradas **22 combinações seed/raio**: 15 seeds distintas no raio de referência, três delas repetidas em 6.371 km e 637.100 km, e a seed 42 no limite de 10^9 km. As seeds principais foram `0, 1, 2, 3, 4, 5, 7, 11, 17, 23, 42, 73, 101, 2026, 8675309`. Não houve substituição de seed, reroll de continentes, rejeição por contagem ou correção do terreno para melhorar métricas.

Cada combinação teve amostragem global diagnóstica nível 6: **24.576 centros de células**. As seeds 0, 23 e 42 foram reavaliadas no nível 7: **98.304 centros**. Esses limites são da ferramenta técnica; não materializam setores de jogo. Planos globais permanecem os planos v3 originais, com seus níveis macro resolvidos automaticamente.

As imagens foram inspecionadas em `artifacts/planet-validation-0.3.1/reference-terrain.png`, `radii-terrain.png` e nas janelas costeiras. Métricas completas, incluindo todas as combinações, estão em `comparison.md`, `comparison.csv`, `comparison.json` e nos diretórios por seed/raio.

Critérios de alerta são observacionais: ausência de terra/água amostradas, falta de continuidade, ausência de relevo extenso, uso de recursos sem limite e dependência da ordem. Não há quantidade mínima/máxima exigida de continentes ou ilhas. Um supercontinente ou oceano dominante não caracteriza, sozinho, uma falha.

## Métricas corrigidas por área

Na projeção radial do cube-sphere, a área angular de um retângulo de face é a integral de `(1+u²+v²)^(-3/2)`. Usa-se a primitiva `atan2(u*v, sqrt(1+u²+v²))` nos quatro cantos; multiplicar o ângulo sólido por R² fornece área física. A soma das seis faces é 4π esterradianos.

Em células muito pequenas, a subtração entre valores de canto perde precisão relativa. A partir do nível 10, `cell_solid_angle` usa duas áreas triangulares esféricas, com determinante **inteiro** no numerador e normas no denominador, evitando cancelamento. A implementação foi verificada por aditividade de subdivisão até o nível 24, soma da esfera e comparação independente entre retângulos e triângulos. Como referência primária de medição de área em células esféricas, foi consultado o [código de área de célula do S2](https://github.com/google/s2geometry/blob/master/src/s2/s2cell.cc); a fórmula de retângulo aqui usa a projeção **radial** própria do Everreach, não a parametrização não linear do S2.

O peso geométrico da célula é calculado com precisão numérica, mas sua classificação terra/água ainda é a do centro. Portanto, a cobertura é uma **estimativa ponderada**, sem alegação de integrar exatamente a costa dentro da célula. Quantis, média, variância e discordância macro/local também usam pesos de área. Os campos antigos sem peso da prévia foram preservados e novos campos ponderados foram acrescentados, sem mudar planos ou snapshots.

## Comparação no raio de referência

Resultados nível 6; T/A são componentes **diagnósticos** de centros adjacentes, não substituem IDs físicos persistidos.

| Seed | Terra ponderada | Água ponderada | Discordância macro/local | T/A | Maior massa / área terrestre |
| --- | --- | --- | --- | --- | --- |
| 0 | 33,20% | 66,80% | 4,21% | 97/19 | 38,6% |
| 1 | 41,42% | 58,58% | 4,07% | 72/27 | 65,6% |
| 2 | 37,13% | 62,87% | 3,92% | 55/26 | 42,6% |
| 3 | 36,68% | 63,32% | 3,79% | 70/17 | 65,6% |
| 4 | 39,40% | 60,60% | 3,87% | 39/26 | 58,8% |
| 5 | 32,88% | 67,12% | 3,68% | 62/17 | 25,3% |
| 7 | 37,95% | 62,05% | 4,25% | 42/37 | 69,5% |
| 11 | 43,79% | 56,21% | 3,80% | 47/21 | 36,5% |
| 17 | 41,38% | 58,62% | 3,39% | 36/16 | 77,7% |
| 23 | 45,69% | 54,31% | 3,91% | 34/18 | 90,5% |
| 42 | 43,14% | 56,86% | 3,85% | 55/27 | 42,4% |
| 73 | 37,01% | 62,99% | 4,24% | 63/13 | 29,1% |
| 101 | 40,33% | 59,67% | 4,35% | 81/23 | 40,5% |
| 2026 | 38,17% | 61,83% | 3,90% | 53/15 | 60,6% |
| 8675309 | 36,99% | 63,01% | 3,54% | 39/15 | 48,4% |

Achados:

- Nenhuma das 22 combinações ficou sem terra ou sem água amostradas. As 15 seeds principais variaram entre **32,88% e 45,69%** de cobertura terrestre ponderada.
- Há resultados fragmentados, massas grandes separadas por oceanos e casos dominados por uma massa terrestre. A participação da maior massa varia de **25,3% a 90,5%** da área terrestre na amostragem nível 6. Isso demonstra diversidade, sem impor que cada mundo contenha todas as formas.
- Foram observados corpos aquáticos dominantes, mares internos/áreas aquáticas menores e ilhas costeiras. A ferramenta não determina salinidade, lagos acima do nível do mar ou conexão hidrológica dinâmica; os rótulos seguem apenas a classificação física terra/água existente.
- A maior distância geodésica observada dentro de uma massa conectada amostrada ficou entre **148.458 e 200.151 km**, confirmando estruturas muito além de milhares de quilômetros. É limite inferior de extensão entre pontos encontrados, não comprimento da costa ou diâmetro exato.
- Faixas de relevo tectônico elevado, definidas para diagnóstico como terra com contribuição tectônica ≥1.000 m, tiveram extensões observadas de **6.856 a 23.944 km** no nível 6. Não se convertem essas faixas em novas entidades autoritativas.
- As alturas amostradas nas 15 seeds ficaram entre **−7.327 e 11.745 m**. Quantis e mapas evidenciam bacias oceânicas, áreas continentais suaves e elevações concentradas nas estruturas tectônicas. Máximos de amostragem não são máximos analíticos do planeta.
- O erro da contagem uniforme de pixels alcançou **2,74 pontos percentuais** de cobertura terrestre. Esse problema foi corrigido nas métricas, sem mudar a geografia.

## Convergência e limites de identidade

| Seed | Terra L6 → L7 | Variação em pontos percentuais | Componentes terrestres L6 → L7 | Maior massa / terra L6 → L7 |
| --- | --- | --- | --- | --- |
| 0 | 33,204% → 33,261% | +0,057 | 97 → 203 | 38,6% → 38,5% |
| 23 | 45,694% → 45,739% | +0,045 | 34 → 82 | 90,5% → 82,9% |
| 42 | 43,142% → 43,139% | −0,003 | 55 → 154 | 42,4% → 62,7% |

A **cobertura por área apresentou boa concordância** nessas duas resoluções; a **conectividade não convergiu**. Até a participação da maior massa pode mudar por pontes ou canais que uma amostragem não resolve. A seed 42 tem 15 massas macro persistidas, 55 componentes diagnósticos L6 e 154 L7. Nenhuma dessas diferenças autoriza renumerar os 15 IDs macro salvos.

Também não basta comparar apenas cobertura macro e cobertura fina: na seed 42 elas quase se cancelam no total, mas cerca de **3,85% da superfície amostrada discorda espacialmente** entre classificação macro e local. Nas 15 seeds de referência essa discordância variou de **3,39% a 4,35%**; nas comparações de outros raios chegou a **6,65%**.

O grafo diagnóstico global liga centros de mesmo tipo. Ele não certifica toda a faixa entre centros nem toda borda de costa. Essa limitação foi mantida explícita; o refinamento local acrescenta sondas intermediárias para impedir ligações falsas detectáveis, sem apresentar o raster global como topologia definitiva de navegação.

## Refinamento subordinado R1 entregue

`build_coast_patch(plan, tile, detail_level)` produz um grafo **fixo e limitado** sobre o campo v3 original. O tile é uma célula macro ou descendente; pode ser refinado em no máximo cinco níveis. Há até **1.024 células interiores**, um halo de vizinhos de aresta e orçamento rígido de **32.768 avaliações** por chamada. Não há busca que cresce conforme o jogador explora e nenhum planeta é materializado em alta resolução.

Cada ligação entre centros do mesmo tipo consulta três pontos na interpolação de direções normalizadas, com pesos de 25%, 50% e 75%. Esses parâmetros não equivalem exatamente a quartos de distância angular. Se uma sonda encontra o tipo oposto, a ligação não é considerada contínua no grafo amostrado e a ocorrência é registrada como `subcell_obstruction`. Isso ainda não prova ausência de obstáculos menores entre as sondas.

Entre centros de tipos opostos são feitas oito etapas determinísticas de bisseção, retornando um bracket de sinais opostos. Ele localiza **uma** transição da classificação v3, sem alegar que existe uma única costa no arco ou que a precisão do modelo geológico equivale à largura do bracket.

Contratos:

- IDs `coast-fragment-r1` incluem assinatura do plano, endereço do tile, resolução, tipo e menor endereço interior do fragmento. Ordem de consulta e exploração não altera o ID.
- IDs macro e baseline v3 são somente lidos. `macro_coverage_ids` registra onde o fragmento está; `same_kind_macro_ids` distingue associações do mesmo tipo. Uma ilha dentro de cobertura macro aquática não é declarada membro físico de um oceano.
- Portas `coast-port-r1` usam o par canônico de células adjacentes. Patches vizinhos, inclusive em faces diferentes e nos oito vértices triplos, produzem o mesmo contrato de ligação. Seus IDs locais podem ser relacionados por portas; não são fundidos ou renumerados automaticamente.
- Fragmentos que chegam ao halo são `open`. Fechado significa fechado **no grafo amostrado do patch**, não ilha global certificada. `fragment_at` consulta o fragmento do centro da célula proprietária; não substitui a consulta de altura num ponto arbitrário dentro dela.
- O patch informa `baseline_only=true`: não aplica eventos de `changes`, não reverte deslizamentos nem altera terreno salvo. Exportação JSON é sidecar técnico, não uma migração ou atualização automática do save.
- Continuidade terra/água não é permissão de travessia. Não há conexão nova no grafo de movimento, alteração de risco/duração ou consulta ao nível do protagonista.

Benefícios concretos inspecionados:

1. Seed 42, tile `[5,8,252,244]`, detalhe nível 13: o macro mostrava apenas terra; **387 das 1.024 células** locais eram água. O refinamento separou os dois fragmentos e registrou 73 brackets de costa. Imagem: `benchmarks/coast-r-63710000/coast.png`.
2. Seed 0, tile `[1,5,19,8]`, detalhe nível 10: foram encontrados seis fragmentos terrestres, dos quais cinco fechados no grafo amostrado, numa área predominantemente aquática que o macro classificava como terra. Imagem: `coast-seed0-islands/coast.png`. Esse exemplo foi escolhido após inspecionar seis patches existentes, sem alterar a geração; a seleção está registrada em `selection.json`.

Esses exemplos demonstram costas e um agrupamento insular emergente. Não impõem arquipélagos em toda seed e não produzem novos elementos geológicos para preencher mapas.

## Problemas sistemáticos identificados

### Densidade de placas alinhada ao cubo

A nucleação v3 distribui candidatos por células das faces com probabilidade igual, não por área esférica. Nas 15 seeds, os centros das faces concentram **38,46% da área e 25,34% dos sites**; zonas de canto concentram **15,56% da área e 24,95% dos sites**. Densidades relativas à média esférica: centro **0,66**, bordas **1,08**, cantos **1,60**. Isso dá cerca de 2,4 vezes mais sites por área nos cantos que nos centros.

É um viés estrutural real, não uma quebra de altura entre faces nem prova de que todos os continentes sejam degenerados. Está em `site-density.json` e é reproduzível pela ferramenta. **Não foi corrigido na formação v3**, porque mudar a nucleação mudaria as massas e IDs. Se a próxima geração exigir isotropia estatística, corrigir a amostragem esférica em uma **nova versão explícita**, mantendo saves v3 intactos. Não confundir a correção de peso das métricas, já realizada, com corrigir a distribuição das placas.

### Saturação de escala em planetas extremos

Acima do regime em que a escala de placas atinge o piso R/8, a quantidade de sites é limitada e a forma angular de uma seed pode ficar praticamente igual em raios diferentes. A comparação da seed 42 entre 637.100 km e 10^9 km mostra esse comportamento. O custo permanece limitado e as formas ficam fisicamente maiores, mas o aumento do planeta não gera automaticamente novos níveis de detalhe local.

No raio de referência, o menor comprimento de onda de detalhe v3 é ~316 km. Coordenadas e consultas podem resolver posições muito menores; a formação atual **não garante geração de desfiladeiros estreitos, incisões fluviais ou canais de poucos metros**. Uma passagem estreita pode existir como contorno emergente de altitude, e o R1 pode amostrá-la, mas nenhum refinamento deve inventar detalhe ausente ou renomear o mundo ao explorá-lo.

## Desempenho e correção sem mudança de geografia

O profiling identificou repetição de SHA-256/serialização da chave dos mesmos vértices de ruído. Foi acrescentado um **LRU de 8.192 valores inteiros**, com chave completa de seed/domínio/coordenadas. A fórmula v3, a precisão e os resultados foram preservados; não foi criada uma versão de formação nova para uma otimização transparente.

Testes com e sem memoização compararam registros físicos completos entre seeds; vetores de plano/elevação v3 e regressões v1/v2 continuaram iguais. Evicção e ordem do cache alteram somente custo, não resultados. O cache é limitado; nenhuma simulação contínua ou serviço de background foi adicionado.

Microbenchmarks em processo explícito, seed 42, 12 setores dispersos por raio, antes/depois da otimização:

| Raio km | Plano frio depois | Mediana setor antes → depois | Patch local antes → depois | Pico Python do patch depois |
| --- | --- | --- | --- | --- |
| 6.371 | 0,045 s | 4,25 → 1,59 ms | 1,59 → 0,72 s | ~3,10 MB |
| 63.710 | 0,834 s | 5,11 → 2,37 ms | 1,77 → 0,85 s | ~3,27 MB |
| 637.100 | 1,191 s | 6,31 → 3,43 ms | 1,96 → 1,04 s | ~3,11 MB |
| 10^9 | 1,210 s | 6,09 → 3,32 ms | 2,00 → 1,06 s | ~3,06 MB |

Resultados em `benchmarks/benchmarks-before-cache.json` e `benchmarks/benchmarks.json`, com perfis por função. Tempos são observações locais, não garantias universais: houve outras verificações de desenvolvimento em paralelo, 12 setores não formam uma distribuição completa de latência e o custo de SQL/renderização/IA não foi medido. Cache quente do plano é consulta LRU; não equivale a tempo de abrir um save em disco.

No raio de referência, desserializar/carregar o plano mediu ~0,80 ms de mediana e seu JSON padrão tem 38.363 bytes. Um setor de exemplo tinha ~13,9 KB. O patch usado tem 7.853 avaliações; a submalha não precisa ser materializada como setores do jogo.

Memória adicional medida com `tracemalloc`:

- Plano frio de referência **com cache de nós**: pico de alocações Python ~**3,19 MB**, cache limitado a 8.192 entradas; tempo instrumentado ~5,94 s. Arquivo `benchmarks/plan-memory.json`.
- Geometria da ferramenta offline no limite L7: 98.304 pontos, pico de alocações ~**48,09 MB**; cache de geometria limitado a dois níveis. Arquivo `benchmarks/geometry-memory.json`. Esse grafo é da ferramenta diagnóstica; não é carregado automaticamente no jogo.
- Patches: ~3,1–3,3 MB de pico por operação testada; medições instrumentadas são mais lentas e não entram na coluna normal de latência.

Esses picos não são RSS, memória total do jogo ou orçamento completo de todos os caches juntos. Um patch de ~0,85 s é inadequado para um tick de frame. R1 permanece explícito/on-demand/técnico: futura exploração deve usar preparação com orçamento e armazenamento por chave estável, sem recalcular esse grafo a cada movimento. Não foi antecipado um sistema de streaming.

## Ferramentas e reprodução

Executar a partir de `backend`:

```powershell
# 15 seeds principais e sete casos adicionais de raio
.\.venv\Scripts\python.exe -m scripts.validate_planets --level 6 --compare-radii --output ../artifacts/planet-validation-0.3.1

# Reavaliar só a resolução diagnóstica, preservando a formação
.\.venv\Scripts\python.exe -m scripts.validate_planets --seeds 0 23 42 --level 7 --output ../artifacts/planet-validation-0.3.1/convergence

# --resume reaproveita apenas casos com seed/configuração/resolução e arquivos compatíveis
.\.venv\Scripts\python.exe -m scripts.validate_planets --level 6 --compare-radii --resume --output ../artifacts/planet-validation-0.3.1

# Atlas costeiro subordinado a partir de plano exportado
.\.venv\Scripts\python.exe -m scripts.preview_planet --plan ../artifacts/planet-validation-0.3.1/seed-0_r-63710000/plan.json --coast-tile 1 5 19 8 --coast-level 10 --output ../artifacts/planet-validation-0.3.1/coast-seed0-islands

# Microbenchmarks e limite de memória da malha diagnóstica
.\.venv\Scripts\python.exe -m scripts.benchmark_planets --output ../artifacts/planet-validation-0.3.1/benchmarks
.\.venv\Scripts\python.exe -m scripts.benchmark_planets --geometry-only --output ../artifacts/planet-validation-0.3.1/benchmarks
```

As ferramentas são offline, sem banco, endpoint público, alteração de descoberta ou novos serviços. A prévia antiga continua funcionando; ela agora também exporta área ponderada, discordância ponderada, soma angular e método de cobertura. Camadas de conectividade são diagnósticas e não substituem o mapa de exploração.

## Arquivos criados ou alterados

| Arquivo | Entrega |
| --- | --- |
| Novo `backend/app/game/world/genesis/sphere_area.py` | Área angular/geométrica, com caminho estável para células pequenas. |
| Novo `.../genesis/formation_validation.py` | Amostragem limitada, estatísticas ponderadas, conectividade e diagnóstico de densidade de sites. |
| Novo `.../genesis/validation_report.py` | CSV/JSON/Markdown e imagens de comparação de seeds/raios a partir das mesmas amostras. |
| Novo `.../genesis/coast_refinement.py` | R1: patches limitados, IDs subordinados, portas, brackets e consulta local. |
| Novo `.../genesis/coast_preview.py` | Seleção técnica determinística de costa e comparação macro/local. |
| Modificado `.../genesis/formation_noise.py` | Somente memoização limitada de valores idênticos de vértices v3. |
| Modificado `.../genesis/formation_preview.py` | Métricas ponderadas adicionais, preservando os campos antigos. |
| Modificado `backend/scripts/preview_planet.py` | Modo de inspeção de costa, além do atlas e consulta por raio. |
| Novo `backend/scripts/validate_planets.py` | Estudo de múltiplas seeds/raios e retomada de relatórios. |
| Novo `backend/scripts/benchmark_planets.py` | Microbenchmarks, profiling, memória e prévias locais. |
| Novo `backend/app/tests/test_genesis_geographic_validation.py` | Testes da ponderação, refinamento, compatibilidade e cache. |
| Novo `docs/world-genesis-phase-0.3.1.md` | Decisões, comparação, problemas, limitações e parecer. |
| Novo `artifacts/planet-validation-0.3.1/` | 22 casos, três convergências, imagens, métricas, planos exportados e benchmarks. |

Não houve migração de esquema, alteração de geradores/configurações v1/v2, regeneração de snapshots, troca de seed ou conversão de saves. `GenesisWorld.plan`, `GenesisSphereSector.baseline` e `changes` permanecem intactos ao calcular/exportar R1, comprovados por recarga em outra Session. Nenhum dataset, entidade de fauna/flora/civilização, fronteira dinâmica, rio ou lago novo foi integrado.

## Testes e verificações

**301 testes selecionados passaram:** 255 anteriores e 46 novos. A execução ampliada final incluiu Genesis v1/v2/v3, mapas, rotas, descoberta/exploração, viagens, fronteiras, tempo, materialização, simulação por escopo e exclusão de campanha.

Os novos casos cobrem: soma 4π, distorção de área, subdivisão, triangulação independente e nível 24; acordo entre atlas antigo e métricas ponderadas; limites de amostragem; patch máximo, repetição entre processos/PYTHONHASHSEED e ordem de consulta; portas nas 24 orientações de emenda e oito vértices triplos; brackets com sinais opostos; canal estreito em campo controlado; obstrução subcélula que impede uma ligação falsa; IDs/relacionamentos preservados; exportação sem mutar save/alterações; CLI; e igualdade integral dos resultados com cache e sem cache.

Os casos sintéticos são fixtures declaradas de teste, não dados fictícios de integração. Os exemplos visuais e métricas de 15 seeds vêm do campo v3 real. Vetores anteriores de plano/altura mantiveram os valores esperados. `compileall` e `git diff --check` foram verificados; há o aviso preexistente Starlette/httpx. A suíte completa do backend e os testes frontend não foram executados. O banco real não foi aberto para escrita.

## Parecer para a próxima fase

**A formação está suficientemente estável para iniciar hidrologia e clima em escala macro, com validação explícita de saídas e conectividade. Não está validada como topologia definitiva de rios, canais e lagos locais.**

Há uma superfície determinística contínua, massas extensas e variedade observada, causas rastreáveis e custos limitados. A próxima fase pode planejar bacias e campos climáticos sobre essa fundação, sem depender do nível do jogador ou de datasets. Não usar o ID macro sozinho para decidir que duas águas estão conectadas, que uma ilha é fechada ou que existe uma passagem navegável: utilizar campo de alturas e refinamento de interfaces.

Antes de congelar uma geração nova destinada a conteúdo definitivo, decidir se o viés de nucleação por face será aceito como simplificação ou corrigido em uma v4. A correção, se escolhida, deve anteceder a dependência de novos mundos nessa geografia e preservar integralmente a reprodução da v3. Detalhe fluvial, erosão/incisão, preenchimento de lagos e refinamento de drenagem deverão ter versão e persistência próprias; R1 não os implementa nem autoriza regenerar territórios alterados.
