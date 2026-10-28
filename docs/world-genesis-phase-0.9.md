# World Genesis 0.9 — ambientes EV-ECO-1.1.1 / E1

## Auditoria anterior à implementação

Foram lidos os dois `LEIA_PRIMEIRO.md`, o manifesto ativo e o guia Codex no pacote v20. A entrada runtime será exclusivamente `datasets/00_Taxonomia_Ambientes/`: taxonomia/índice v1.1 e regras físicas **1.1.1**. As pastas históricas não serão importadas, nem os 100 originais somados novamente aos 250 registros. Os arquivos ativos extraídos correspondem aos bytes ativos do ZIP; caminhos históricos semelhantes não são entradas ativas.

Auditoria real: V4 expõe termos tectônicos e referência global de terra/oceano; T1 altura e geometria por diferenças finitas; C2 quatro períodos de temperatura, precipitação, PET, influência marítima e potenciais de neve/congelamento. O `clima.indice_aridez` do dataset é **P/PET**, portanto corresponde a `precipitation_to_pet_ppm`, não a `aridity_index_ppm` (déficit). Neve potencial não confirma neve acumulada. H1/HR1 são drenagem potencial. W1 tem saldos macro; W2/P1 comprova um pequeno episódio local, sem perenidade, vegetação ou manchas inundadas. J1/JR1 fornecem hospedeiros/histórias, não cavernas, dunas, praias, solos erodidos ou edifícios vulcânicos instanciados.

`Subregion.biome` e as entidades Region/Subregion/Location continuam contratos legados de gameplay. O mapa público filtra conhecimento/precisão e `known_spatial_locations` não revela âncoras desconhecidas. E1 será uma autoridade técnica separada de classificação, sem escrever nesses campos, no grafo de movimento ou no mapa. Não haverá novas rotas públicas, Atlas ou autogeração em campanhas existentes.

Decisão: um classificador determinístico **E1** lê as regras de 100 naturais, com quatro estados e proveniência de cada campo. Potencial vegetal é independente de árvores/espécies. Feições não comprovadas ficam pendentes; contratos tipados reconhecem os 100 construídos e 50 anômalos sem criá-los. Intervalos serão configuráveis/versionados; C2 e as demais autoridades permanecerão imutáveis.

Uma única função física de ponto, independente de LOD, serve aos três níveis: resumos macro C2, mosaicos regionais associados às formações JR1 e condições locais. Ambientes principais, secundários, ecótonos e feições são camadas distintas. Confirmação de um registro físico não confirma cobertura vegetal. Os experimentos serão predefinidos nas seeds 42/0/7/2026/12345 e outros raios, sem escolher somente pontos favoráveis.

## Resultados

Implementado o contrato **E1**, opt-in e versionado. Foram classificados pontos físicos reais das cinco seeds exigidas, mais três raios adicionais. Nenhuma espécie, jazida, estrutura, anomalia ou habitat aquático definitivo foi criado. O banco real não foi migrado; a migração aditiva e a persistência foram exercitadas em bancos descartáveis.

## Entrada ativa e mapeamento físico

O carregador aceita somente os 250 IDs ativos, verifica integridade e não consulta versões históricas. Taxonomia e índice conservam seu schema 1.1; isso não autoriza carregar as regras antigas. As regras são exclusivamente 1.1.1. Os três arquivos autoritativos foram comparados com as entradas de mesmo caminho na raiz ativa do ZIP v20.

| Arquivo | SHA-256 |
|---|---|
| Taxonomia | `f3cfedee7e4196e71f796555e1cecf5ff69d7f0a464e124fb5f0f803808056d7` |
| Índice | `902ced64324b603aa8f51781769946708fee167399144049ad25360fa23c9d6f` |
| Regras 1.1.1 | `4eb814c21fec195536d43caf419b8b9ff8876bbdaf516461dcf53f9561653005` |

| Contrato lógico | Fonte realmente utilizada / limite |
|---|---|
| Temperatura, precipitação anual e sazonal | C2 consultado na altura T1; quatro períodos iguais, sem meteorologia diária |
| `clima.indice_aridez` | P/PET de C2, dividido por 1.000.000; PET zero produz desconhecido, nunca razão zero |
| Sazonalidade de precipitação | `(máximo-mínimo)/soma` dos quatro períodos; soma zero permanece desconhecida |
| Continentalidade e influência marítima | Diagnóstico C2 de continentalidade e distância oceânica; não prova litoral local |
| Altitude | Altura T1 menos o nível do mar configurado; datum original preservado nos dados de entrada |
| Declividade | Geometria T1 com sondagens simétricas a 8 m e tabela de tangentes fixa; aproximação explícita |
| Contexto montanhoso | Terra, altitude mínima e contexto tectônico T1; não apenas altitude |
| Granito, carbonatos e argilas | Hospedeiro JR1; contatos ainda pendentes não viram prova positiva ou negativa |
| Origem vulcânica | História J1 `volcanic_sequence`; não comprova edifício vulcânico ou caverna |
| Regime frio | Proxy E1 configurável da temperatura média C2, não neve acumulada |
| Rios, lagos, inundação, solo saturado | Desconhecidos sem comprovação local correspondente; H1/HR1 não bastam |
| Neve, geleiras, banquisa | Desconhecidos; potencial C2 e estoque macro W1 não comprovam uma feição local |
| Cavidades, dunas, praias, recifes | Desconhecidos; substrato e altitude não instanciam essas feições |
| Corpo/coluna oceânica e zonas submarinas | Desconhecidos; máscara oceânica H1 fica apenas no diagnóstico |
| Vegetação estabelecida | Desconhecida, independente da elegibilidade física; nenhum catálogo de espécies carregado |

`water_audit.py` fornece leitura opcional dos cabeçalhos e saldos W1/W2/P1 reais, sem transformar volume macro em área molhada local. O teste integrado usa o episódio P1 existente da seed 42 (19 L entregues, 11 L de umedecimento) e verifica que isso não confirma rio perene nem vegetação. O adaptador não afirma que W1/W2/P1 estejam ausentes quando não foram consultados.

## Classificação, escalas e persistência

Os estados são `incompativel`, `candidato_pendente`, `elegivel` e `confirmado`. Contradição física prevalece sobre evidência ausente; a ausência continua registrada. As métricas separam contradições, campos ausentes entre candidatos pendentes, requisitos adicionais de confirmação e vegetação não estabelecida. Um mesmo candidato pode ter vários motivos, portanto contagens de motivos não são mutuamente exclusivas.

O classificador usa os intervalos do catálogo, requisitos físicos e adequação relativa. Chuva/aridez com limite inferior zero usam adequação monotônica, evitando pontuar um deserto sem chuva como inadequado por estar na extremidade do intervalo. Os intervalos podem ser sobrescritos por ID/campo em uma configuração persistida, sem editar o dataset. Não houve alargamento de intervalos para forçar diversidade.

E1 acrescenta verificações conservadoras onde o nome da feição exige fatos que as regras genéricas não bastam para comprovar: inundação de campo alagável, nevoeiro de floresta nebulosa, cânion mapeado, erosão sobre argila, instabilidade de encosta e água em cavidade. Afloramento rochoso é requisito de **confirmação**, sem bloquear a elegibilidade básica de deserto pedregoso, colina pedregosa ou escarpa. Florestas exigem período mais quente de pelo menos 5 °C como proxy configurável de janela de crescimento; isso não exige árvores instanciadas.

Configuração inicial E1: regime frio até média de 10 °C; contexto montanhoso com altitude de pelo menos 250 m e termo tectônico de pelo menos 800 m; limiar relativo de ecótono 0,60; até quatro ambientes secundários. Esses são parâmetros da classificação E1, não mudanças nas autoridades físicas. Os resultados incluem sua configuração e hashes das fontes.

A consulta de um ponto produz todos os 100 resultados naturais, principal potencial, secundários, mistura de adequação, ecótono e camadas de feições. Uma cachoeira permanece feição local e não substitui o ambiente de cobertura. Ecótono significa sobreposição de adequação física; não é uma comunidade vegetal observada.

Macro, regional e local usam o mesmo campo de ponto: vínculo à célula climática C2, vínculo à formação JR1 e condições locais. O resumo regional aceita até 256 pontos, deduplica IDs, rejeita mistura de autoridades e mantém mosaicos em vez de atribuir um bioma uniforme à formação ou ao continente. Células e tiles não entram na identidade do ponto; coordenadas esféricas canônicas equivalentes nas emendas têm o mesmo resultado.

A inicialização E1 é explícita. A materialização persiste o snapshot e a formação física JR1 necessária, com `experimental_sources=False`. A classificação não depende dos estoques minerais, inclusive quando já há extração ou alterações de saldo pendentes na sessão. Reservas não são lidas como autoridade ambiental.

Persistir promove a confirmado somente um perfil elegível sem vegetação exigida e sem requisitos físicos adicionais de confirmação. A confirmação tem escopo de **classificação física do ponto**, não de árvores, neve, cavernas ou outros objetos não comprovados. Florestas e outros perfis vegetados permanecem elegíveis até a integração futura de flora. Consulta não materializa; retorno a um ponto não regenera. Baseline, checksum e alterações posteriores ficam separados; mudanças de terreno/geologia/ambiente exigem overlay explícito e podem ser inspecionadas pelo modo histórico `baseline_only`.

Os 100 construídos e 50 anômalos são reconhecidos, mas ficam pendentes no amostrador nativo. Os validadores exigem estrutura persistida com tipo, função, estado e âncora compatíveis, ou autorização canônica específica por ID anômalo, origem persistente e âncora. Não aceitam autorizações genéricas ou curingas. Esses validadores são contratos internos; não criam estruturas nem um sistema de autorização pública.

## Experimentos reais

Cada caso avalia 384 centros de células nas seis faces, três janelas regionais predefinidas de 1.024 km com 144 pontos cada e 57 pontos no meridiano de longitude zero. São 873 consultas por caso, antes de deduplicação: 6.984 no conjunto. As janelas são as três primeiras âncoras terrestres J1 na ordem determinística preexistente, sem seleção por ambiente ou resultado mineral. As provas persistidas são exemplos selecionados **após** a varredura global, e não são usadas como estimativa de distribuição.

| Seed | Raio (km) | Pontos terrestres globais | Principais distintos | IDs elegíveis | Terra sem principal |
|---|---:|---:|---:|---:|---:|
| 42 | 63.710 | 177 | 13 | 25 | 1 |
| 0 | 63.710 | 159 | 14 | 27 | 0 |
| 7 | 63.710 | 195 | 15 | 27 | 0 |
| 2026 | 63.710 | 120 | 12 | 28 | 0 |
| 12345 | 63.710 | 135 | 13 | 25 | 0 |
| 42 | 6.371 | 196 | 11 | 27 | 0 |
| 42 | 637.100 | 170 | 11 | 26 | 0 |
| 42 | 1.000.000.000 | 170 | 11 | 26 | 0 |

Nas cinco seeds de referência, a união foi de **28 IDs elegíveis e 20 principais distintos**. Apareceram potenciais de florestas temperadas, boreais e subalpinas, campos, estepes, tundras e desertos, entre outros. Isso não significa que esses ambientes tenham cobertura vegetal estabelecida. Os 15 substratos encontrados nas amostras foram lidos de JR1, não gerados por E1.

Cada ponto participa de 100 avaliações naturais; as contagens abaixo são avaliações ponto × ambiente, não quantidades de regiões ou área:

| Seed / raio em km | Incompatíveis | Pendentes | Elegíveis | Confirmados na consulta pura |
|---|---:|---:|---:|---:|
| 42 / 63.710 | 26.163 | 11.780 | 457 | 0 |
| 0 / 63.710 | 26.199 | 11.792 | 409 | 0 |
| 7 / 63.710 | 26.193 | 11.695 | 512 | 0 |
| 2026 / 63.710 | 26.303 | 11.779 | 318 | 0 |
| 12345 / 63.710 | 26.159 | 11.847 | 394 | 0 |
| 42 / 6.371 | 26.857 | 11.099 | 444 | 0 |
| 42 / 637.100 | 26.062 | 11.868 | 470 | 0 |
| 42 / 1.000.000.000 | 26.075 | 11.853 | 472 | 0 |

Total das cinco seeds de referência: 131.017 incompatíveis, 58.893 pendentes, 2.090 elegíveis e zero confirmados na consulta pura. Construídos e anômalos ficam, respectivamente, em 38.400 e 19.200 avaliações pendentes por caso. A prova de persistência gravou e reabriu **cinco pontos únicos**, com 500 avaliações naturais: 290 incompatíveis, 187 pendentes, 22 elegíveis e **uma classificação física confirmada**: `EV-BIO-DESERTO_FRIO` no ponto `(8, -3, -7)`. Commit, reabertura e revisita preservaram os snapshots; zero fontes minerais ou espécies foram criadas.

Na seed 42, entre os candidatos pendentes, os bloqueios mais frequentes são corpo de água doce (3.597), corpo oceânico (2.807), cavidade (2.632) e rede fluvial (2.563). Esses números se sobrepõem e incluem perfis distintos sobre o mesmo ponto. Outros exemplos são neve acumulada (49), dunas (156) e cânion (140). Entre os elegíveis, 158 avaliações ainda exigem vegetação estabelecida; 116 têm afloramento pendente de confirmação. Isso não impede o potencial físico de florestas e desertos básicos.

### Diversidade e limitações climáticas observadas

| Seed de referência | Chuva média terrestre amostrada (mm/ano) | P/PET < 0,2 / razões definidas |
|---|---:|---:|
| 42 | 124,62 | 142 / 173 |
| 0 | 130,00 | 128 / 156 |
| 7 | 149,39 | 160 / 194 |
| 2026 | 194,60 | 88 / 118 |
| 12345 | 187,33 | 101 / 132 |

Essas médias são dos pontos terrestres da malha diagnóstica, **sem ponderação de área**, e não substituem a auditoria climática C2. Na seed 42 os pontos terrestres vão de −25,29 a 22,90 °C e de zero a 1.995 mm/ano. A predominância seca acompanha os dados físicos reais; não é corrigida criando chuva ou espécies. A floresta tropical úmida não ficou elegível na amostra global da seed 42. Isso é ausência nesta amostra, não prova de inexistência em toda a superfície.

O único ponto terrestre global sem principal foi `(8, -5, -7)` na seed 42: −12,77 °C, 1.487 mm/ano, PET zero, 4.268,972 m e substrato granítico. P/PET é indefinido; requisitos de janela de crescimento, limites de precipitação de tundras e ausência de prova criosférica também restringem alternativas. São 71 perfis incompatíveis e 29 pendentes. Não foi transformado artificialmente em deserto, neve ou geleira.

As áreas em `primary_area_km2` usam o ângulo sólido real das células cube-sphere. São **estimativas por amostragem central**, não polígonos ambientais exatos. A área `unclassified` soma referências marinhas ainda pendentes e lacunas terrestres; os contadores `land_sample_count` e `unclassified_land_samples` permitem distingui-las. A seed 42 tem área terrestre amostrada estimada em 22.891.276.176 km²; isso não é cobertura vegetal.

### Mosaicos e imagens

Nas três janelas da seed 42 foram observados 1/2/2 principais distintos e 0/16/2 arestas entre classificações terrestres diferentes. Na seed 0, a terceira janela tem cinco principais e 58 arestas; na 12345 a primeira tem oito principais e 55 arestas. As três janelas da seed 7 são uniformes no principal: nenhuma diversidade foi imposta. Nos raios extremos, 1.024 km pode ocupar uma fração minúscula das estruturas C2 e resultar em principal uniforme; detalhes T1/JR1 continuam sendo consultados localmente.

As arestas medidas são vizinhanças da grade de sondagens, não fronteiras vetoriais exatas. Os testes verificam equivalência de coordenadas nas emendas e aproximação dos campos físicos. Fronteiras discretas entre classes podem existir onde a adequação muda; não são uma alteração física de terreno nas bordas de faces.

Imagens offline verificadas visualmente:

- [Planeta seed 42: potencial, temperatura, chuva e relevo](../artifacts/environment-e1/seed-42-r63710000/planet-environments.png).
- [Seed 42, janela 0 uniforme](../artifacts/environment-e1/seed-42-r63710000/region-0-environments.png).
- [Seed 42, janela 1 com transições](../artifacts/environment-e1/seed-42-r63710000/region-1-environments.png).
- [Seed 2026: comparação global](../artifacts/environment-e1/seed-2026-r63710000/planet-environments.png).

As três janelas das seeds 42 e 2026 têm imagens e JSONs disponíveis, inclusive resultados uniformes. O azul marinho global indica referência oceânica, sem confirmação ambiental marinha. As figuras são diagnósticas, não mapas do jogador, e os pixels não são a resolução final do planeta.

## Desempenho e validação

O lote final executou 384 classificações globais por caso em 3,49–4,78 s (aproximadamente 9–12,5 ms por ponto), incluindo consultas T1/JR1. A preparação das autoridades levou 0,17–9,47 s: algumas combinações carregam snapshots disponíveis, outras constroem planos limitados em memória. Portanto não são benchmarks equivalentes de carregamento frio. A regressão estava em execução simultânea; estes tempos são indicativos, não SLA.

O benchmark instrumentado de 64 pontos levou 4,23 s, com pico de **5.818.868 bytes** (5,55 MiB) e 5.730.552 bytes retidos. Inclui consultas E1 e caches T1/JR1, com planos globais já carregados. Não mede RSS nem memória total de preparação; `tracemalloc` adiciona custo. Não houve simulação atmosférica, workers ou processamento de milhões de setores. Os limites explícitos são dois amostradores no serviço, 128 pontos por amostrador, 256 pontos por mosaico e 1 MiB por snapshot persistido; caches das autoridades físicas conservam seus próprios limites anteriores.

Os testes novos cobrem os 15 fixtures corretivos do pacote ativo, distinção desconhecido/falso/zero, ausência de flora, chuva zero, P/PET, PET zero, intervalos configuráveis, datum com nível do mar não zero, declividades extremas, camadas de feições, hierarquia, múltiplos raios, emendas/polos, independência de ordem/processo, versões, persistência/reabertura, alterações posteriores, concorrência SQLite, rollback de falha tardia, episódio P1, independência da extração mineral, reset e migração aditiva em banco temporário. O writer transacional foi validado para SQLite; outros dialetos são recusados explicitamente.

Resultado da regressão final: **752 testes aprovados em 1.021,32 s (17 min 01 s)**, incluindo os 52 novos testes E1 e os 700 da base anterior. Foram selecionados os testes `test_genesis*`, `test_map*`, `test_travel*`, `test_world_gen*`, `test_explor*`, `test_world_time*`, fronteiras/rotas regionais, reset, esqueletos/materialização de regiões e integração/escopo da simulação. Nenhum teste falhou; houve um aviso de depreciação já existente do cliente de testes Starlette/httpx. Compilação Python, verificação de whitespace e consistência dos oito artefatos/24 janelas passaram. Alembic apresenta um único head, `t28t1o2p3q4r`; esse comando apenas inspeciona a cadeia, sem aplicar migração ao banco real.

## Arquivos da fase e reprodução

- `backend/app/game/world/genesis/environment/{catalog,config,classifier,adapter,summary,service,water_audit,preview}.py` e `__init__.py`: entrada ativa, regras, projeção física, mosaicos, persistência e diagnóstico.
- `backend/app/db/models/world_environment.py`: cabeçalho E1 e pontos ambientais; exportados em `models/__init__.py`.
- `backend/alembic/versions/t28t1o2p3q4r_add_environment_e1.py`: duas tabelas novas, sem conversão automática de campanhas.
- `backend/app/game/world/reset.py`: remoção ambiental antes dos pais JR1 no reset já solicitado pelo jogo.
- `backend/scripts/validate_environment.py`: experimentos, estatísticas, prova persistida descartável e imagens.
- `backend/app/tests/test_genesis_environment.py` e `test_genesis_environment_persistence.py`: testes E1.
- Este documento e `artifacts/environment-e1/`: resultados técnicos, [suite consolidada](../artifacts/environment-e1/suite.json) e [prova persistida](../artifacts/environment-e1/persistent-proof.json).

Reproduzir a partir de `backend`: `.venv/Scripts/python.exe -m scripts.validate_environment`. Testes E1: `.venv/Scripts/python.exe -m pytest app/tests/test_genesis_environment.py app/tests/test_genesis_environment_persistence.py -q`. O script usa bancos temporários e não migra o banco real.

## Limites e próximas etapas

E1 entrega uma fundação operacional de **potencial ambiental e classificação física**, não uma superfície completamente povoada nem uma carta contínua de polígonos de biomas. As amostras não provam a presença de todos os ambientes, e os 62 naturais sem candidatos de espécies não bloqueiam a elegibilidade física.

Próximas integrações devem fornecer provas locais persistentes de água, gelo, feições e estruturas conforme cada autoridade seja consolidada; depois, usar os IDs elegíveis no contrato de flora e fauna, mantendo confirmação de vegetação separada. Alterações do mundo vivo precisarão de overlays explícitos. Uma eventual ativação em campanhas reais exige decisão de compatibilidade e migração aplicada deliberadamente. Nesta fase permanecem desativados autogeração, flora/fauna, civilizações, Living Frontiers e Atlas; fontes V4/T1/C2/H1/HR1/W1/W2/P1/J1/JR1 e os datasets não foram recalibrados.
