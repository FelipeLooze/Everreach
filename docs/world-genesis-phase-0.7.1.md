# World Genesis — fase 0.7.1: hidrografia local G1

## Auditoria e decisões anteriores à implementação

V4/R1 classificam a fonte histórica; H1 condiciona uma árvore macro e cotas; HR1 mantém portas/perfis amostrados sobre V4. C2/W1 fornecem disponibilidade sazonal, sem provar leitos. T1 possui a autoridade local em milímetros e eventos ainda sem aplicação física. A região 3982 demonstra incompatibilidade real entre amostras T1 e cotas históricas: aproximadamente 14 m. Não é permitido trocar o sampler de HR1 e salvar como se ainda fosse HR1.

G1 será uma camada opt-in própria, com pedidos canônicos limitados por tile. Busca minimax sobre perfis T1, com árvore de receptores compartilhada, permite desvios sem escavação. Uma cota fixa abaixo de um endpoint T1 é incompatibilidade demonstrada daquele contrato; fracasso numa malha finita não prova impossibilidade no terreno contínuo. Armazenamento, resolução insuficiente e orçamento esgotado terão estados separados.

Pedidos podem preservar portas HR1 ou propor portas G1 selecionadas em fronteiras compartilhadas. As propostas têm identidades novas e não substituem HR1. Refinamentos locais podem herdar exatamente pontos/IDs de uma prova anterior; não se deve recalcular uma porta herdada com outra resolução. Geometria entre pontos é avaliada em T1, independentemente do chart de origem.

Seções transversais e curvas cota/capacidade são geometria potencial, nunca vazão hidráulica, ocupação ou permanência. Depressões terão saídas e capacidades aproximadas somente no domínio amostrado, sem reconstrução continental. Não haverá W2, incisão, alteração de cotas antigas, mapa público ou dados ambientais.

Persistência separará baseline de eventos, verificará fontes e checksums e não regenerará resultados salvos. Eventos T1/HR1 não interpretados devem invalidar o uso corrente da prova em vez de serem ignorados. Migração aditiva e transações do chamador; nenhum banco real será migrado nesta entrega.

## Entrega e autoridade

`hydro_geometry/` entrega um plano G1 independente e pedidos de evidência canônicos. O descritor fixa configuração G1, assinatura/checksum de T1, assinatura/checksum de H1 e assinatura de configuração HR1. Não depende da visita, do protagonista, da existência de W1 nem da ordem de geração. Nenhuma função das autoridades anteriores foi editada nesta fase.

A superfície utilizada em **todas** as buscas, sondagens longitudinais e seções é `TerrainSampler.sample(...)["height_mm"]`. V4 só é consultada para comparação histórica perto do datum. Nem seus metros inteiros nem seus rótulos são tratados como a superfície corrente T1. C2 continua representando a climatologia macro original; não há recálculo de clima por causa de um caminho G1.

Há dois adaptadores regionais explícitos:

- `hr1_legacy`: conserva pontos/IDs das portas HR1 e a junção existente como referência de transferência, nunca nascente.
- `hr1_t1_candidates`: propõe novas portas G1, selecionando o menor ponto T1 entre sondagens internas de uma borda compartilhada. Registra a porta HR1 anterior e a proposta; não substitui HR1 nem suas cotas. Os dois lados selecionam o mesmo ponto/ID sem precisar materializar um ao outro.

O domínio pode ser qualquer `TerrainTile` no interior de uma célula H1, inclusive níveis superiores a 24. `GeometryRequest` também aceita contratos locais explícitos, com ingresso(s), saída e pontos herdados. `boundary_probe_request` prepara testes de passagem entre bordas indicadas pelo chamador; **não atribui receptores globais nem cria cursos d'água**. Pedidos de maior resolução são novas provas, sem substituir o baseline anterior. Para refinar uma porta existente, deve-se herdar seu ponto/ID literalmente em `Anchor`; escolher outro mínimo é uma nova proposta de fronteira, não continuidade implícita de LOD.

## Busca, trajetórias e estados

Uma malha regular com 4, 8, 16 ou 32 intervalos conecta vizinhos cardinais; cada aresta possui cinco sondagens T1. Pontos obrigatórios fora da grade são inseridos sem criar cruzamentos internos artificiais; mais de um ponto não regular na mesma célula solicita refinamento. O campo T1 não muda com a malha.

A busca determinística minimax parte de uma saída prescrita e cria uma árvore única de receptores, usando também subida acumulada e comprimento para desempate. Permite curvas e desvios; não força a reta entre centros, nem declara a solução globalmente ótima no contínuo. Segmentos comuns são reutilizados, e confluências têm um único receptor. Nenhuma junção adiciona água. Falta de prova vizinha significa pendência, não barreira física.

Cada segmento contém pontos/perfil, queda longitudinal, comprimento aproximado por cordas e declividade racional. A resolução considera a maior distância entre sondagens com limite superior de arco e margem da normalização inteira. Raios de 50 bits fracionários suportam o raio máximo; alturas permanecem em milímetros.

| Estado de rota | Significado |
| --- | --- |
| `verified_at_requested_resolution` | Trajetória longitudinal descendente nas sondagens, dentro da resolução pedida e sem violação de cota de fronteira. Não prova capacidade hidráulica ou rio ativo. |
| `partially_verified_storage_required` | Caminho amostrado exige elevar/armazenar água em alguma parte. Ocupação e escoamento não estão comprovados. |
| `pending_resolution` | Sondagens mais afastadas que a resolução solicitada. A condição geométrica, inclusive armazenamento, continua registrada separadamente. |
| `incompatible_fixed_boundary_head` | Um endpoint T1 está acima da cota fixa declarada. É uma incompatibilidade demonstrada **desse contrato**, não impossibilidade de todas as rotas do planeta. |
| `incompatible_sampled_path_reference_head` | O caminho escolhido ultrapassa a cota de origem declarada. Outra busca/resolução/fronteira pode ser necessária. |
| `pending_budget` | Faltaram amostras ou expansões; não significa bloqueio físico. |
| `coincident_anchors_no_path_demonstrated` | Entradas/saídas coincidentes não demonstram um corredor de extensão positiva. |

O estado global `sampled_geometry_prepared` só informa que a preparação terminou; **não aprova todas as rotas**. Os estados individuais, seções, armazenamento e comparação bilateral são obrigatórios para avaliar uma prova.

O envelope estático mínimo é o máximo acumulado do terreno em direção à saída. É uma geometria potencial de retenção, não um nível d'água aplicado. Alturas acima do solo no envelope são registradas; não há incisão ou pressão inventada para ocultar subidas. Cotas internas históricas HR1 não são herdadas como se fossem válidas em T1: a auditoria antiga permanece disponível, e o envelope G1 é uma proposta independente que exige reconciliação versionada antes de uso por W2.

## Seções e capacidade de passagem

Até oito seções por pedido amostram T1 perpendicularmente ao percurso, por padrão a cada 25 m, até 100 m de cada lado. Esses números definem uma **janela de inspeção**, nunca a largura atribuída a um rio. A aproximação tangente é recusada quando a extensão seria grande demais em relação ao raio.

As cotas amostradas determinam curvas de área transversal, largura conectada e profundidade no eixo para níveis potenciais. A integração é linear por partes e mantém somente o componente ligado ao eixo, quando há contenção nos dois lados. A seção também indica possível escape lateral. Ausência de bancos é registrada como `no_enclosed_section_demonstrated`, não preenchida com dimensões arbitrárias.

`actual_width_mm`, `actual_depth_mm` e `discharge_capacity_m3_s` permanecem desconhecidos. Área transversal não determina sozinha vazão: rugosidade, condição hidráulica, ocupação e continuidade ainda são necessárias. Uma seção favorável em poucos pontos não certifica todo o comprimento do curso.

## Depressões, contornos e saídas

Um segundo flood a partir de toda a borda investiga depressões no mesmo domínio amostrado. Grupos abaixo de uma cota de escape fornecem cotas de fundo, arestas de vertedouro, brackets de contorno e curva aproximada cota/capacidade. A área usa a Jacobiana esférica do cube-sphere em quadratura inteira, com pesos duais dos vértices, em vez de tratar toda célula do atlas como tendo a mesma área física.

A capacidade é a união aproximada de colunas sobre a malha. Cada estágio registra a quantidade de componentes molhados do grafo, pois estágios baixos podem representar bolsões separados. Não é batimetria exata nem capacidade comprovada de um único lago conectado. Contornos são brackets de cruzamento, sem alegação de um polígono fechado exato.

Os IDs são subordinados ao pedido/resolução; não identificam automaticamente um lago global. Provas sobrepostas ou pai/filho não podem ter capacidades somadas sem reconciliação espacial. H1/HR1 continuam referenciados por seus IDs antigos. `water_volume_liters`, inundação efetiva e permanência continuam nulos. Nenhum dos fragmentos de depressão produzidos é uma declaração de lago.

## Costa V4/R1/T1

O contrato costeiro G1 tem versão 1. Para a superfície local, terra/submersão significa altura T1 relativa ao datum. Identidades V4 e referências macro utilizadas por R1 permanecem históricas. Estar abaixo do datum não prova conexão oceânica; estar numa célula H1 marinha não autoriza ignorar terreno T1 acima do datum.

O diagnóstico compara V4 e T1 nas amostras a até 500 m do datum T1 e registra desacordos e a identidade macro de referência. Não é auditoria global da costa nem mudança de IDs R1. `ocean_export_authorized=False` impede interpretar esse diagnóstico como nova saída W1. Conexão marinha e normalização de contornos precisam de evidência costeira versionada, vinculada ao terreno e às fronteiras examinadas.

Uma testemunha real da seed 42 apresentou **289 discordâncias em 289 vértices da janela**. Um exemplo tinha V4 a −5 m e T1 a +5,431 m. Esse valor não é erro global médio: a janela foi procurada deliberadamente para expor a incompatibilidade. Demonstra por que não se pode inferir oceano definitivo da classificação antiga. Nenhuma geografia foi alterada para produzir o exemplo.

## Nó 3982 e comparação das amostras

A auditoria histórica continua mostrando quatro segmentos HR1 acima de suas cotas em T1, com excesso máximo de **14,068 m**. G1 **não resolveu esse conflito** nem deve alegar isso só porque a cota de origem não foi ultrapassada.

Mantendo as portas antigas, G1 produziu um percurso de cerca de **1.216,5 km**, ainda próximo do corredor HR1 na imagem. Encontrou subida entre sondagens de até **9,044 m**, necessidade máxima de elevação no envelope estático de **15,876 m** e lacuna longitudinal máxima de **38,522 km** frente à resolução pedida de 100 m. Logo, o resultado é `pending_resolution`, com condição adicional `storage_geometry_required`. A associação a um fragmento de depressão não resolve o armazenamento entre sondagens: `subedge_storage_unresolved=True` continua explícito.

O pedido de portas candidatas propôs outro ponto na borda, sem modificar a porta antiga. Também permaneceu pendente e necessitando armazenamento. Houve oito seções por pedido, duas com contenção amostrada, e 28 fragmentos de depressão no domínio; não são 28 lagos. A reavaliação de maior resolução deve continuar localmente, preservando pontos de fronteira, antes de tratar esse corredor como fisicamente realizável. Se vier a exigir alterar terreno ou cotas autoritativas, será uma revisão própria.

Foram preparados **24 pedidos** em seis combinações seed/raio: portas antigas, portas candidatas e dois domínios locais adjacentes para cada combinação. São testemunhas técnicas, não um censo planetário.

| Seed / raio (km) / nó | Porta antiga | Porta candidata | Condição observada |
| --- | --- | --- | --- |
| 42 / 63.710 / 3982 | Resolução pendente | Resolução pendente | Armazenamento e cotas internas ainda precisam de reconciliação. |
| 0 / 63.710 / 874 | Fronteira incompatível | Resolução pendente | Uma proposta evita a violação do endpoint antigo; não aprova o percurso inteiro. |
| 2026 / 63.710 / 141 | Duas rotas com fronteira incompatível | Uma pendente e uma incompatível | Casos diferentes coexistem na mesma região. |
| 42 / 6.371 / 136 | Fronteira incompatível | Fronteira incompatível | Perfil descendente não compensa cota fixa incompatível no endpoint. |
| 42 / 637.100 / 37 | Fronteira incompatível | Fronteira incompatível | Busca regional muito grosseira para declarar leito local. |
| 42 / 1.000.000.000 / 37 | Fronteira incompatível | Fronteira incompatível | A escala extrema não força uma passagem. |

Nas duas janelas locais adjacentes do raio máximo houve trajetórias descendentes verificadas na resolução solicitada e porta bilateral coincidente. Nesses dois exemplos, nenhuma seção demonstrou canal confinado: a prova é **longitudinal**, não prova de rio canalizado. Nas demais janelas locais surgiram retenções de 1–5 mm; esses pequenos valores não foram apagados por tolerância implícita. As quantizações e a ausência de ocupação/armazenamento entre sondagens continuam limitações declaradas.

Os hashes de V4, H1, HR1, C2 e W1 foram iguais antes/depois em todas as seis combinações. A prova costeira adicional também conservou V4. Não se estendeu manifesto W1 nem se declarou transferência nova.

## Persistência e eventos

Migração aditiva `o23o6j7k8l9m` sobre T1 cria `genesis_hydro_geometry_plans` e `genesis_hydro_geometry_evidence`. Cada evidência guarda pedido, proveniência, baseline, checksum e `changes` separado. Configuração G1 existente não pode ser substituída silenciosamente. O reset remove evidências/plano G1 antes de suas dependências. As funções não fazem commit.

O registro de preparação regional possui chave determinística própria: ao retornar, nem a seleção de portas candidatas é repetida. Uma prova pendente também é um resultado persistido; só um pedido explícito com outra resolução/orçamento/contrato produz outra prova. Não há retry oculto por exploração. Baselines corrompidos são recusados, não reconstruídos.

Consultas correntes verificam eventos G1, a evidência HR1 referenciada e eventos T1 em toda a cobertura fechada do domínio e das seções, incluindo charts vizinhos e alterações ainda não descarregadas pelo ORM (`autoflush=False`). Não basta checar os pontos de uma linha e ignorar um evento entre sondagens. A busca espacial examina caixas locais por face/nível, sem carregar todos os tiles do planeta. Payloads de tiles T1 não são carregados para testar apenas eventos.

`get_geometry(..., baseline_only=True)` permite diagnóstico histórico, mantendo os eventos separados e sinalizando que não foram aplicados. Não autoriza usar uma prova invalidada como superfície corrente. Alterações físicas e aplicação de eventos precisam de overlay versionado futuro. Reabertura sem sampler, rollback, cache e exclusão por campanha foram testados.

**O banco real `everreach.db` não foi migrado.** Migração e downgrade foram exercitados em SQLite temporário, comparando todos os schemas anteriores e um payload T1 sentinela.

## Contrato para W2

`water_evidence.py` fornece um contrato de versão 1 com ID/hash da prova G1, fonte T1, estado geométrico, comparação bilateral, seções, armazenamento, escapes e referência ao W1. A geometria completa é recuperada pelo ID/hash G1; não se transforma um booleano de preparação em aprovação hidráulica.

Quando W1 existe, a junção verifica H1/HR1 e fornece as quatro quantidades sazonais macro como **referência, sem alocação a qualquer caminho**. Não se devem somar essas referências repetidas em diversos tiles/rotas. `water_allocation_liters=None`, `pending_water_reconciled=False`, `w1_manifest_extended=False` e `active_river_authorized=False` permanecem explícitos.

W2 ainda deverá verificar época/eventos, percurso bilateral, resolução/subgrid, cotas internas antigas, conectividade de armazenamento/vertedouro, capacidade hidráulica e transporte conservativo dos saldos/instantes W1. Toda liberação de água pendente precisa de débito explícito de sua conta original, sem repetir chuva, duplicar estoque ou reescrever eventos anteriores. O ledger imutável e seu manifesto fechado não foram reestruturados nesta fase. Provas G1 podem existir fora desse manifesto; falta de alocação continua pendência hídrica.

## Orçamentos e desempenho

Preset: até 16.384 consultas de altura por pedido, com orçamento solicitado padrão 8.192; limite de configuração 32.768. A contagem inclui o trabalho anterior de seleção de portas de forma conservadora. Cada uma das duas buscas permite até 4.096 expansões. A malha está limitada a 32 intervalos, até 1.089 vértices regulares, mais os anchors. Há até oito seções por pedido (limite configurável 16). Dados excedentes não são truncados como se ainda fossem provas completas.

O baseline serializado tem limite padrão de 2 MiB (teto configurável 8 MiB). Se não couber, persiste-se uma recusa compacta `pending_persistence_budget`; se nem os metadados canônicos couberem, o pedido é recusado antes de inserir uma linha. O cache G1 guarda dois planos puros, nunca todas as evidências visitadas. Usa o cache T1 já limitado. A persistência total cresce com as áreas preparadas; não há despejo de baselines modificados ou cota global fictícia de save.

| Medição | Resultado observado |
| --- | --- |
| Regional 3982 / 16 intervalos / portas antigas | 1,206 s; 1.985 consultas de altura. |
| Mesmo caso / portas candidatas | 1,271 s; 2.000 consultas, incluindo seleção. |
| JSON de referência | 100.587 bytes; carregar/validar ~3,5 ms. |
| `tracemalloc` de referência | Retido 462.506 bytes; pico adicional 2.299.870 bytes (~2,2 MiB). |
| Domínios locais / 8 intervalos | ~0,15–0,20 s; 591 consultas; ~24–34 KiB de JSON. |
| Regionais das seis combinações | ~0,90–1,53 s, sem crescimento proporcional à área total planetária. |
| SQLite descartável / H1 nível 2 / G1 8 intervalos | Gerar + inserir + commit 0,172 s; reabrir 0,0106 s; consulta corrente mediana 8,12 ms. |

As medições em memória excluem criação das fontes, seleção inicial de pedidos, ORM e imagens. `tracemalloc` não mede RSS do jogo. A medição SQLite inclui cabeçalhos, checksums e eventos, mas utiliza H1 nível 2; não deve ser extrapolada como custo de todo save de produção. O principal custo de preparação é amostragem T1/perfis; nenhum serviço/worker ou simulação contínua foi criado.

## Imagens e reprodução

- [3982 com portas antigas](../artifacts/hydro-geometry-g1/seed-42-r63710000-node-3982/legacy-ports/geometry.png) e [portas propostas](../artifacts/hydro-geometry-g1/seed-42-r63710000-node-3982/t1-candidate-ports/geometry.png).
- [Seed 2026 / confluências e incompatibilidades](../artifacts/hydro-geometry-g1/seed-2026-r63710000-node-141/t1-candidate-ports/geometry.png).
- [Passagem local no raio máximo](../artifacts/hydro-geometry-g1/seed-42-r1000000000000-node-37/local-a/geometry.png) e [prova bilateral](../artifacts/hydro-geometry-g1/seed-42-r1000000000000-node-37/local-bilateral.json).
- [Divergência costeira real](../artifacts/hydro-geometry-g1/coast-seed-42/geometry.png) e [diagnóstico](../artifacts/hydro-geometry-g1/coast-seed-42/coast.json).
- [Métricas das 24 provas](../artifacts/hydro-geometry-g1/suite.json) e [benchmark de persistência](../artifacts/hydro-geometry-g1/persistence-benchmark.json).

As figuras mostram fundo T1 interpolado apenas para diagnóstico, referência H1/HR1 em azul/vermelho, caminhos G1 por estado, candidatos de depressão/saída e seção transversal. Não são mapa público nem prova de água ocupando os pixels.

Comandos a partir de `backend`:

```powershell
.venv/Scripts/python.exe -m pytest app/tests/test_genesis_hydro_geometry.py app/tests/test_genesis_hydro_geometry_persistence.py -q
.venv/Scripts/python.exe -m scripts.preview_hydro_geometry --suite
.venv/Scripts/python.exe -m scripts.preview_g1_coast
.venv/Scripts/python.exe -m scripts.benchmark_hydro_geometry_persistence
.venv/Scripts/python.exe -m alembic heads
```

## Arquivos desta fase

| Arquivos | Função |
| --- | --- |
| `backend/app/game/world/genesis/hydro_geometry/{config,plan,spatial}.py` e `__init__.py` | Configuração/pedidos, fontes, endereços, distâncias e áreas. |
| `hydro_geometry/{graph,geometry}.py` | Orçamento, busca, perfis, árvore, proveniência e validação. |
| `hydro_geometry/{sections,depressions}.py` | Seções, curvas geométricas, contornos e escapes potenciais. |
| `hydro_geometry/{regional,service,water_evidence,preview}.py` | Adaptadores, persistência/eventos, contrato W2 e figuras. |
| `backend/app/db/models/world_hydro_geometry.py` | Duas tabelas G1. |
| `backend/app/db/models/__init__.py`, `backend/app/game/world/reset.py` | Registro e exclusão em ordem de dependência. |
| `backend/alembic/versions/o23o6j7k8l9m_add_hydro_geometry_g1.py` | Migração aditiva/downgrade. |
| `backend/app/tests/test_genesis_hydro_geometry{,_persistence}.py` | Provas sintéticas, reais, persistência e compatibilidade. |
| `backend/scripts/{preview_hydro_geometry,preview_g1_coast,benchmark_hydro_geometry_persistence}.py` | Reprodução técnica. |
| `artifacts/hydro-geometry-g1/`, este documento | Provas, imagens, métricas e decisões. |

Os arquivos preexistentes de fases anteriores já estavam modificados/não rastreados no workspace. Essas alterações não foram revertidas nem apresentadas como novas desta entrega. Nenhum módulo autoritativo V4/R1/H1/HR1/C2/W1/T1 foi alterado.

## Validação e limitações

Testes cobrem determinismo entre processos/hash fixo, ordem dos anchors, amostras compartilhadas entre LODs, portas e perfis entre todas as faces incluindo polos, passagem bilateral, desvio de obstáculo, confluência sem receptor duplicado, cotas fixas incompatíveis, insuficiência de resolução/orçamento, depressões e contornos, seção confinada/aberta, distorção de área, costa, preservação W1, persistência sem sampler, eventos T1/HR1/G1, rollback, cache, reset e migração aditiva/downgrade. Casos analíticos controlados são exclusivamente fixtures de teste; não entram na geografia autoritativa dos exemplos reais.

Vetor G1 congelado da prova entre processos: `aa4e213144b6754c51298284fd421eab4243679676a9f5eeb75bba83b949cd70`. Mudanças futuras da geometria ou política de prova exigem versionamento explícito; dados salvos continuam prevalecendo.

**Regressão ampla: 565 aprovados em 230,40 s**, incluindo os **33 testes G1**. A suíte cobre Genesis, mapa, exploração, viagem, fronteiras, materialização, reset e simulação temporal. O único aviso foi a depreciação preexistente Starlette/httpx. `compileall`, `git diff --check` e a verificação de head único Alembic também passaram. A revisão cosmética final das figuras apenas releu os baselines salvos, sem refazer a geometria.

G1 é uma fundação de geometria local, **não uma rede hidrográfica planetária concluída**. As malhas regionais gigantescas continuam grosseiras; ausência de caminho numa malha não prova ausência de passagem estreita no contínuo. Não há refinador adaptativo de corredor continental inteiro, roteamento global de tiles finos ou união automática de depressões sobrepostas. A continuidade demonstrada exige anchors herdados ou portas bilaterais coincidentes; duas propostas independentes de LOD diferente não devem ser assumidas equivalentes.

Seções são pontuais e capacidades aproximadas; não há rugosidade hidráulica, vazão máxima calculada, incisão, alteração de margem ou ocupação permanente. Eventos invalidam provas correntes; ainda não são fisicamente aplicados. Essas limitações não são resolvidas marcando um corredor como rio.

**A fase 0.7.2 pode consumir este contrato G1**, desde que transporte conservativamente W1 e trate cada pendência como pendência. O nó 3982 ainda requer refinamento local de geometria/armazenamento e reconciliação explícita das cotas internas. W2 não deve liberar esse corredor, nem os exemplos de seção não confinada, apenas com base em disponibilidade macro. Mudança necessária de terreno exige contrato próprio, sem ser escondida na hidrografia. Datasets e ambientes continuam fora do escopo.
