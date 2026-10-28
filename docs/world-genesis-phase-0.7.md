# World Genesis — fase 0.7: terreno local T1

## Auditoria e decisões

V4 (`formation_tectonics.evaluate`) possui relevo inteiro em metros e direções de 30 bits. Aplicar esse campo diretamente em consultas centimétricas produz degraus e, em raios extremos, perde detalhe angular. Alterá-lo quebraria V4, R1, H1, HR1, C2 e W1. T1 será uma camada opt-in independente: reconstrói V4 numa malha canônica esparsa sob demanda e aplica detalhe contínuo em coordenadas ambiente 3D com precisão própria. Nada é convertido automaticamente.

Os setores físicos existentes usam `CellKey` até nível 24. Isso não alcança exploração métrica no raio máximo. T1 terá endereço subordinado de tile até nível 46, sem ampliar ou reinterpretar `CellKey`. Tiles finos continuam associados a ancestrais físicos existentes. Não há alocação global de tiles.

Alternativas rejeitadas: ruído sem vínculo entre setores; deslocamentos aleatórios de vértices; erosão global; geração local de cada continente; truncar oitavas conforme LOD e assim mudar a altura da mesma coordenada. O LOD controla amostragem e cobertura, enquanto a consulta autoritativa sempre avalia o mesmo campo completo. Interpolação de visualização não é altitude autoritativa.

HR1 e H1 são condições macro, não leitos. Seus perfis foram calculados em V4. W1 fixa até 32 provas HR1 e não pode ganhar transferências durante exploração. T1 somente auditará perfis, cotas e disponibilidades existentes; incompatibilidades exigirão revisão/overlay explícito. Não haverá alteração de estoques ou criação de rios/lagos nesta fase.

Exploração, `Region`/`Subregion`/`Location`, grafo de movimento, descobertas e mapa público não consultam terreno T1 automaticamente. Nenhum endpoint público ou coordenada descoberta é acrescentado. Persistência e reset terão tabelas aditivas e transações do chamador.

## Fundação entregue

`terrain/field.py` define `TerrainPlan`, `TerrainSampler` e a autoridade de altura T1. O plano contém um descritor pequeno, a configuração e o hash de toda a autoridade V4 persistida. Não contém um mapa global refinado. `TerrainConfig` é estrita, congelada e versionada; parâmetros e fonte fazem parte da assinatura.

O descritor escolhe a malha de reconstrução da V4 a partir de `detail_wavelength_m`, com pelo menos 16 amostras nominais por comprimento característico, limitado ao nível 24 histórico. Só os quatro vértices necessários a uma consulta são avaliados. A interpolação bilinear usa milímetros e raios exatos. Seus vértices coincidem com V4; entre eles há aproximação explícita, não uma alegação de igualdade à V4. A base é contínua em altura nas emendas; derivadas normais podem ter mudanças entre células/charts. A altura inteira final possui quantização de milímetro, não continuidade matemática submilimétrica.

O detalhe usa oito campos globais 3D, independentes de setor/ordem/LOD, com direções normalizadas em 64 bits fracionários. Os comprimentos físicos padrão vão de 128 km a aproximadamente 7 m, divididos por quatro a cada oitava. As amplitudes máximas nominais são 120, 55, 25, 12, 5, 2, 0,8 e 0,3 m, moduladas pelo contexto tectônico V4 interpolado e por `relief_scale_ppm`. O relevo base conserva seus gradientes continentais; o detalhe estático dá formas multiescala de encostas, colinas, sulcos e depressões, sem declarar erosão ou drenagem física resolvida. Não há grão diferente por setor nem identidade política envolvida.

A interpolação do campo aleatório mantém precisão adicional até a soma das contribuições; não quantiza cada campo em centésimos de amplitude antes da soma. O envelope costeiro reduz o detalhe continuamente a zero no datum da **base reconstruída**, preservando seu sinal terra/água. Isso não garante que todas as classificações costeiras V4/R1 originais coincidam com T1: a reconstrução da própria base pode deslocar um cruzamento próximo do nível do mar. R1 e seus IDs continuam intactos como evidências da fonte antiga.

`terrain/geometry.py` consulta o mesmo campo em quatro sondagens tangentes e fornece gradiente e declive em escala física. A distância das sondagens aproxima um arco local, e o resultado identifica o espaçamento usado. Contexto tectônico, assinatura, ponto, resolução e geometria formam um contrato para futuros solos/rochas/afloramentos. Nenhum material ou jazida é atribuído.

## Endereços, LOD e autoridade

`TerrainTile(face, level, x, y)` aceita níveis 0–46 e índices inteiros de 64 bits na persistência. Seus vértices utilizam raios de até 51 bits, dentro do contrato `SurfacePoint`. `CellKey` não foi alterado. `physical_ancestor(sector_level)` relaciona o tile fino a um setor físico; um tile mais amplo que um setor retorna associação não singular no snapshot, em vez de inventar um único setor.

`level_for_spacing(radius_m, spacing_m, intervals)` calcula o nível necessário usando o limite conservador de espaçamento `2R/(intervals*2**level)`. A maior escala não elimina a resolução local. No raio de referência, a amostra técnica local usa L21 com 32 intervalos e espaçamento máximo de 2 m; no raio máximo, usa L35. Não há uma quantidade preestabelecida de tiles ou continentes.

Todos os LODs amostram o campo completo. Vértices comuns de pai/filho, tiles vizinhos e charts diferentes têm a mesma altura inteira. A malha visual interpolada entre amostras **não** é autoridade de colisão/navegação. Bordas com resoluções diferentes podem exigir costura geométrica de malha em um futuro renderer; esta fase garante altura em pontos comuns e convergência do campo, não implementa uma malha sem T-junctions.

API de preparação/consulta, com transação pertencendo ao chamador:

```python
initialize_terrain(db, campaign_id, TerrainConfig())
tile = tile_at(point, level_for_spacing(radius_m, spacing_m=2))
materialize_terrain_tile(db, campaign_id, tile)
height = query_altitude(db, campaign_id, point)  # height_mm, versão e assinatura
query_hydrology_constraints(db, campaign_id, h1_node)  # somente HR1 já salvo
```

Não existe fallback silencioso de `query_altitude` para V4. Mundos sem T1 mantêm seus contratos anteriores; mundos T1 devem utilizar essa consulta para altitude local. `TerrainSampler.sample` é a implementação pura da **base gerada**, utilizada por ferramentas e auditorias, não um interpretador de eventos vivos. Os snapshots V4 e planos H1/HR1/C2/W1 continuam descrevendo sua fonte histórica; não passam a representar alturas atuais T1. Nenhum consumidor de gameplay foi trocado nesta fase.

A ativação T1 é explícita e recusa mundos que já possuam setores físicos V4 materializados: esses territórios precisam de uma migração de autoridade específica, ainda não implementada. Isso impede reinterpretar silenciosamente alturas e modificações antigas. Mundo V4 sem setores físicos pode receber T1 explicitamente, inclusive com os planos macro hidroclimáticos existentes, que permanecem como restrições históricas.

## Persistência e alterações vivas

Migração aditiva `n22n5i6j7k8l`, sobre `m21m4h5i6j7k`, cria `genesis_terrain_plans` e `genesis_terrain_tiles`. Não altera dados de tabelas antigas nem ativa T1. A migração foi exercitada somente em banco temporário; **`everreach.db` não foi migrado**.

Cada tile guarda baseline, checksum e `changes` separadamente. O retorno a um tile salvo verifica endereço, dimensões, termos e checksum e reutiliza o baseline; corrupção causa erro, nunca reconstrução silenciosa. A consulta usa amostras persistidas quando o ponto coincide com elas. Sobreposições de LOD que discordarem são rejeitadas. Outros pontos usam o campo completo versionado.

Eventos de escavação/deslizamento/construção podem ser conservados em `changes`, mas sua aplicação física ainda não é implementada. Uma consulta corrente que intersecte um tile com alterações não interpretadas falha de forma explícita. `baseline_only=True` permite diagnóstico da base, sem fingir que o evento foi aplicado. A cobertura consultada é fechada: considera os dois lados de divisões internas e todos os charts incidentes em emendas/vértices. Assim, a propriedade canônica de um ponto não esconde um evento no tile vizinho. A materialização de outro LOD não apaga o evento anterior.

As rotinas não fazem commit. Rollback, reabertura, payload deferido, conservação de alterações, cache sem tiles fantasmas e reset por campanha são testados. O reset remove tiles e plano T1 antes da fonte V4. O cache contém somente objetos puros, sem autoridade associada ao sucesso de uma transação.

## Integração hidrográfica e incompatibilidades

`terrain/hydrology.py` lê H1, HR1 e, quando fornecido, W1. Inspeciona cinco pontos por segmento regional antigo, suas cotas e portas. Relata excesso de terreno T1 acima da cota HR1, subidas amostradas, perfis e contexto sazonal W1. A prova identifica hashes de T1/HR1/W1 e o conjunto efetivamente inspecionado. É diagnóstico da **base** T1, não validação contínua, batimetria, condutância ou aplicação de eventos.

`query_hydrology_constraints` não cria HR1 ausente e não acrescenta evidência ao W1. Pode inspecionar um HR1 preparado posteriormente e indicar `in_w1_fixed_manifest=False`, preservando toda a contabilidade antiga. HR1 modificado exige overlay consciente de eventos, em vez de ser tratado como baseline.

Na referência seed 42, raio 63.710 km, a inspeção do nó W1 alimentado **3982** encontrou quatro segmentos, todos com algum excesso sobre a cota histórica; o maior excesso amostrado foi **14.068 mm**. Portanto, alimentação calculada não prova que a água cabe ou segue esses leitos em T1. O relatório mantém `bed_validated=False`, capacidade de armazenamento/passagem desconhecida e o ledger W1 inalterado. Não houve incisão para encaixar uma trajetória antiga. Os hashes W1 antes/depois foram iguais em todas as seis amostras.

Os demais relatórios incluem regiões sem transferência confirmada. A escolha de até duas testemunhas por planeta não é um censo de rios nem uma estimativa estatística de incompatibilidades planetárias. Não há volume atribuído a lago permanente, largura de rio, nível de água local ou descarte de água pendente.

### Contrato para a futura revisão/overlay de água

O limite de até 32 regiões pertence ao **baseline W1 imutável**, não pode se tornar o limite permanente de exploração. O próximo estágio deve manter esse baseline e acrescentar revisões localizadas com as seguintes invariantes:

1. Uma evidência geométrica deve identificar T1/configuração/resolução/amostragem, hashes H1/HR1, portas canônicas compartilhadas, limites do domínio, estado de eventos e condições de fronteira. A chave de evidência deriva desses dados físicos, nunca da visita ou da sequência de chamadas.
2. Provas puras podem ser calculadas em qualquer ordem. Bilateralidade deve depender dos mesmos dados canônicos dos dois lados; vizinho ausente significa pendência, não aprovação nem bloqueio físico definitivo. Nenhuma visita pode criar água ou mudar a seed da solução.
3. Uma revisão deve listar baseline W1, revisão anterior, domínio e vizinhos afetados, instante lógico, condições sazonais, evidências e IDs dos eventos já aplicados. Uma chave canônica de operação impede aplicar duas vezes a mesma transferência.
4. Entrada = saída + variação de estoques deve fechar em litros inteiros por período/domínio. A pendência W1 é uma obrigação contabilizada, não um reservatório com posição conhecida: sua alocação precisa de um vínculo explícito, limitado pelo saldo original, sem duplicar chuva, escoamento ou estoque.
5. Evidências adicionais não reescrevem o passado. O planejamento geométrico pode ser independente da ordem de preparação; a evolução física depende legitimamente de eventos e tempo. Para estados equivalentes, a ordem incidental de materialização deve produzir a mesma revisão normalizada. Conflitos em fronteiras precisam de resolução transacional determinística, não de “primeiro explorador vence”.
6. Um overlay só pode ativar um trajeto com alimentação, continuidade, armazenamento/vertedouro e capacidade de passagem comprovados no domínio declarado. Eventos que invalidem a prova devem suspender sua utilização futura sem apagar a água ou seus registros.

Este é um contrato de projeto, **não um overlay implementado**. É necessária uma versão explícita de reconciliação hidrográfica que resolva domínios, saldos e eventos antes de abrir novas rotas autoritativas. Não basta aumentar o limite 32, refazer W1 a cada visita ou recalcular um plano sem transportar seus estoques.

## Orçamentos e desempenho

Por padrão, um tile possui 16 intervalos (289 amostras). O limite configurável permite até 32 intervalos (1.089 amostras), no máximo 131.072 bytes serializados por patch no preset padrão, com teto de configuração de 262.144 bytes. A verificação de amostras e extensão ocorre antes da geração; o tamanho persistido é verificado antes de inserir a linha. Um pedido excedente falha e deve ser dividido pelo chamador. Não há fila ou subdivisão automática oculta.

Extensão máxima conservadora por patch: 1.000 km, configurável. Auditoria hidrográfica: até 4.096 sondagens por chamada no preset. Cache: dois samplers, cada um com até 2.048 vértices V4; não retém grades globais ou todos os tiles visitados. Na consulta persistente, há no máximo 47 níveis de cobertura local por chart, incluindo tiles incidentes nas bordas. O custo depende da consulta local e dos LODs sobrepostos, não do total de tiles do mundo. Baselines de tiles ficam deferidos no ORM.

Não há cota total do save: a persistência cresce com o território materializado, devendo ser gerida futuramente com política explícita. Tiles modificados não podem ser descartados por uma política de cache. O custo é limitado por trabalho/amostras, sem uma promessa de prazo rígido em milissegundos.

Benchmarks de 1.089 amostras, sem criação da fonte V4 nem ORM/imagens:

| Seed | Raio (km) | Tile frio (s) | Consulta T1 mediana (ms) | V4 direta (ms) | JSON do tile (bytes) | Pico adicional (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 63.710 | 0,266 | 0,238 | 0,073 | 23.383 | 958.100 |
| 42 | 63.710 | 0,267 | 0,235 | 0,075 | 23.382 | 962.330 |
| 2026 | 63.710 | 0,306 | 0,241 | 0,077 | 26.650 | 942.822 |
| 42 | 6.371 | 0,274 | 0,232 | 0,058 | 23.377 | 988.404 |
| 42 | 637.100 | 0,269 | 0,232 | 0,099 | 22.473 | 925.484 |
| 42 | 1.000.000.000 | 0,280 | 0,238 | 0,103 | 24.488 | 933.838 |

`tracemalloc` mede alocações Python adicionais durante um patch frio, não RSS nem memória total do jogo. O resultado não cresce com o raio. Tile quente é semelhante ao frio (~0,26–0,29 s): o custo principal já é o detalhe local/hash, e não seus quatro vértices V4. O descritor T1 levou ~0,1–1,1 ms nas seis fontes carregadas.

Benchmark separado SQLite/ORM, descartável, com um tile padrão de 289 amostras: geração + inserção + commit **0,082 s**; reabertura fria do tile salvo **0,0027 s**; consulta autoritativa com procura de cobertura/eventos **4,74 ms** mediana. Não comparar essa consulta diretamente à consulta puramente em memória sem considerar validação e acesso ao banco.

## Visualizações e métricas

Cada figura compara V4 original, base reconstruída T1, morfologia regional e campo completo, em três extensões físicas. Os pixels interpolados são apenas visualização. As mesmas escalas de cor são usadas por linha; não se afirma um levantamento mundial a partir dessas janelas.

- [Seed 42 / raio de referência](../artifacts/terrain-t1/seed-42-r63710000/terrain-comparison.png).
- [Seed 0](../artifacts/terrain-t1/seed-0-r63710000/terrain-comparison.png) e [seed 2026](../artifacts/terrain-t1/seed-2026-r63710000/terrain-comparison.png).
- [Raio terrestre](../artifacts/terrain-t1/seed-42-r6371000/terrain-comparison.png), [raio 637.100 km](../artifacts/terrain-t1/seed-42-r637100000/terrain-comparison.png) e [raio máximo](../artifacts/terrain-t1/seed-42-r1000000000000/terrain-comparison.png).
- [Métricas completas](../artifacts/terrain-t1/suite.json), [benchmark ORM](../artifacts/terrain-t1/persistence-benchmark.json) e [incompatibilidades de referência](../artifacts/terrain-t1/seed-42-r63710000/hydrology-constraints.json).

Nas janelas examinadas, o maior erro da reconstrução em relação à V4 inteira foi **2,688 m**; na janela macro de referência foi **1,625 m**. Isso é medição de testemunhas, não limite global provado. O detalhe da janela macro de referência variou aproximadamente de −6,6 a +30,6 m; o campo local variou cerca de 17 cm na janela de aproximadamente dezenas de metros. Outras testemunhas incluem fundo oceânico, sem obrigar que toda seed/posição gere montanhas ou obstáculos.

## Arquivos desta fase

| Arquivos | Entrega |
| --- | --- |
| `backend/app/game/world/genesis/terrain/{config,address,field}.py` | Configuração, endereços finos, plano, campo determinístico e cache. |
| `terrain/{patch,service}.py` | Tiles progressivos, validação, consulta autoritativa, persistência e diagnóstico de HR1 já salvo. |
| `terrain/{geometry,hydrology,preview}.py` e `__init__.py` | Gradientes, restrições hidrográficas e figuras técnicas. |
| `backend/app/db/models/world_terrain.py` | Plano e tiles; mudanças separadas. |
| `backend/app/db/models/__init__.py` | Registro dos dois modelos. |
| `backend/alembic/versions/n22n5i6j7k8l_add_terrain_t1.py` | Migração aditiva e downgrade. |
| `backend/app/game/world/reset.py` | Exclusão T1 por campanha em ordem de dependência. |
| `backend/app/tests/test_genesis_terrain*.py` | Campo, orçamento, geometrias, persistência, migração e hidrologia. |
| `backend/scripts/{preview_terrain,benchmark_terrain_persistence}.py` | Reprodução das figuras e medições. |
| `artifacts/terrain-t1/` e este documento | Seis comparações, JSONs, evidências e decisões. |

Os arquivos de fases anteriores já estavam modificados/não rastreados no workspace. Não foram revertidos nem incluídos como mudanças novas desta fase. V4/R1/H1/HR1/C2/W1 não foram editados nesta implementação.

## Validação

Testes T1 verificam determinismo entre processos e hash fixo; ordem inversa; amostras comuns pai/filho; bordas vizinhas; aproximação dos dois lados de todas as emendas e de todos os vértices, incluindo faces polares; coincidência dos vértices da base com V4; detalhe métrico em raios diferentes; gradientes; recusa de versão/configuração inválida; orçamento; expulsão de cache sem mudança de resultado; imagens; conservação do baseline/eventos; cobertura de eventos em emendas; reabertura sem gerador; rollback; reset e migração aditiva/downgrade.

A auditoria hidrográfica verifica imutabilidade V4/H1/HR1/C2/W1, incompatibilidade construída deliberadamente e preparação posterior de HR1 sem estender/recalcular W1. O teste da migração compara todos os schemas anteriores e um payload legado sentinela antes/depois, em SQLite temporário.

Comandos executados a partir de `backend`:

```powershell
.venv/Scripts/python.exe -m pytest app/tests/test_genesis_terrain.py app/tests/test_genesis_terrain_persistence.py app/tests/test_genesis_terrain_hydrology.py -q
.venv/Scripts/python.exe -m scripts.preview_terrain --suite
.venv/Scripts/python.exe -m scripts.benchmark_terrain_persistence
.venv/Scripts/python.exe -m alembic heads
```

Regressão ampla: arquivos `test_genesis*`, `test_map*`, `test_travel*`, `test_world_gen*`, `test_explor*`, `test_world_time*`, além de fronteiras, rotas regionais, reset, materialização e simulação temporal: **531 aprovados em 210,31 s**. Verificação final específica T1, incluindo a proteção adicional contra ativação sobre territórios V4 já materializados: **29 aprovados em 14,27 s**. A suíte ampla foi coletada antes da inclusão desse último caso; os dois números não devem ser somados. O único aviso foi a depreciação preexistente Starlette/httpx. `compileall`, `git diff --check` e a verificação de head único Alembic também passaram.

## Limitações e próximo estágio

T1 entrega terreno base, não um renderer ou sistema de colisão/locomoção. A continuidade garantida é de altura até a quantização; não garante derivadas C1, ausência de todos os artefatos visuais de triangulação ou detalhe adequado a toda resolução de tela. A morfologia local é estática, condicionada à tectônica, sem erosão dinâmica, sedimentos, substratos ou causalidade geológica científica. A amostragem espacial pode omitir uma passagem estreita em um LOD grosso: deve-se consultar/preparar uma escala física menor, não inferir uma barreira permanente.

O próximo estágio prioritário é a **reconciliação hidrográfica local versionada**: trajetórias compatíveis com T1, seções de passagem, depressões conectadas, capacidades/vertedouros, condições bilaterais e overlay conservativo dos saldos W1. O caso 3982 demonstra por que não se deve pular essa etapa. Só depois será apropriado consumir essa geometria/água em ambientes e datasets. Nenhum rio ou lago permanente foi criado, nenhum sistema público de mapa/exploração foi alterado e o Atlas Interativo não foi iniciado.
