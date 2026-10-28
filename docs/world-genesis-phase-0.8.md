# World Genesis — fase 0.8: integração D14 v4 + v4.1

## Auditoria antes da implementação

O catálogo v4 é a autoridade dos 120 materiais e permanece byte a byte inalterado. O complemento v4.1 propõe um contrato lógico, não descreve campos já existentes. Ambos e seus guias foram lidos diretamente em `datasets/11_Geologia_Materiais_D14*`.

`formation_tectonics.evaluate` fornece placa dominante, fração continental, parcelas de elevação e estruturas com mecanismos, taxas de fechamento/cisalhamento, distância e contribuição. `Plate` fornece idade, tipo de crosta, eixo e velocidade. Isso é reconstrução cinemática estática, não história litológica completa. `TerrainSampler.sample` fornece altura em mm, detalhe, contexto tectônico e proxy de inclinação; declara explicitamente que não atribui materiais. Não há substratos, fraturas mineralizadas, espessuras estratigráficas, cavidades, impactos, recifes ou autorização canônica mineral. Region não é unidade geológica.

Decisão: criar autoridade geológica **J1**, opt-in e subordinada a V4/T1, sem alterar elevação. Corpos geológicos macro são células de Voronoi esféricas com sítios determinísticos ponderados por área; não são setores de renderização. Seus registros contêm história simplificada de embasamento, bacia antiga, intrusão, metamorfismo e circulação, com regras e parâmetros rastreáveis. Evidências novas são fatos desse modelo procedural versionado, nunca campos atribuídos retrospectivamente a V4 ou inventados pelo adaptador durante uma consulta.

Os 20 descritores serão registrados. Substratos que exigem processos ainda não estabelecidos ficam bloqueados com motivo explícito; não usar clima/hidrologia/ecossistemas atuais para fingir confirmação. Pontes e alternativas são avaliadas genericamente e deduplicadas por unidade/material. Elegibilidade não cria jazida. Calibração separada será apenas experimental, com limites globais/regionais, seleção independente da ordem e zero lendários aleatórios. Nenhuma autogeração será conectada ao fluxo de saves reais.

## Resultados

**J1 está operacional em modo técnico explícito.** Foram produzidos planos físicos de 15 seeds no raio de 63.710 km e três raios adicionais, oportunidades minerais D14 reais e uma jazida experimental finita gravada/reaberta em SQLite descartável. A autogeração em campanhas reais continua desligada. V4, T1, hidrografia, clima, catálogo e movimento não foram alterados.

## Adaptador efetivamente implementado

| Campo lógico v4.1 | Origem implementada |
| --- | --- |
| `world_id` | Assinatura física persistida do plano J1, vinculada ao checksum V4, T1, configuração e hashes D14; não uma visita. A campanha é a chave de isolamento no banco. |
| `region_id` | ID de província geológica agrupada por placa V4, para orçamento. Não é `Region`, continente ou fronteira política. |
| `geological_unit_id` | ID J1 derivado de assinatura e slot do corpo esférico. |
| `lithology_substrate_ids` | Substrato do histórico J1 persistido. V4/T1 não tinham esse campo. |
| `evidence_flags` | Predicados apoiados por registros J1 de formação. Cada registro aponta para uma etapa de história existente; não há fallback em consultas. |
| `event_instance_ids` | Vazio: nenhum impacto, organismo ou evento excepcional é inventado. |
| `source_lineage_ids` | Vazio: não existe cadeia comprovada de transporte mineral neste escopo. |
| `depth_index_0_100` | Proxy geométrico de soterramento/espessura J1, independente de altitude. Continua um índice de acesso, não uma conversão das unidades originais D14 para metros. |
| `canonical_authorizations` | Vazio: sem permissão arcana/lendária implícita. |
| `formation_opportunity_id` | Uma formação por corpo J1. A oportunidade mineral é única por mundo/formação/material, independentemente das rotas satisfeitas. |

O carregador verifica o SHA-256 v4 `1101b05722d85fdc9168d0ed6117e1a3c960343d40a992ada6417e86d92a7eec`, cardinalidades e referências das alternativas. O hash v4.1 também fica fixado no plano. As consultas recebem cópias do catálogo para impedir alteração do cache. Não houve importação de pastas históricas nem sobrescrita dos `MaterialDefinition` preexistentes: o catálogo completo permanece a referência D14 para as oportunidades e depósitos.

O adaptador não traduz `tectonic_context_mm` para “minério”, nem inclinação para fratura confirmada. As fraturas desta fase são estruturas da reconstrução J1 associadas às taxas V4, sem promessa de fissuras visíveis na malha T1. A confirmação dos predicados significa **fato do modelo procedural J1**, não medição geofísica ou evidência que já existisse nas versões anteriores.

## Formação física e distribuição dos 20 substratos

J1 utiliza até 384 sítios candidatos estratificados. A ativação é ponderada pelas áreas esféricas congeladas de V4 e a posição usa seu amostrador esférico, com seed independente. O parâmetro de resolução tem expectativa de 192 corpos de planejamento; não fixa continentes, rochas, oceanos ou jazidas. Os experimentos produziram entre 174 e 209 corpos por seed de referência.

A cobertura é uma partição esférica por sítio mais próximo, com desempate pelo slot. Os limites são contatos entre corpos físicos, não linhas de setores do cube-sphere. O mesmo corpo atravessa setores e faces; um ponto representado em duas faces recebe a mesma identidade. Consultas de LOD não subdividem nem criam corpos ou oportunidades. Este é um planejamento geológico macro limitado, sem gerar malhas métricas do planeta.

Cada sítio lê a placa e os mecanismos V4 reais. Campos espaciais correlacionados definem a variabilidade interna da história, sem consultar altitude, clima ou biomas. As regras J1 são:

- Montagem de embasamento continental granítico e oceânico basáltico/gabróico, considerando idade da crosta.
- Contextos extensionais oceânicos podem estabelecer embasamento ultramáfico; arcos convergentes estabelecem sequências andesíticas ou tufáceas.
- Bacias antigas continentais recebem fácies carbonáticas, arenosas, pelíticas ou conglomeráticas. É uma hipótese histórica nova J1, não a declaração de um lago ou mar atual.
- Colisões transformam precursores registrados em quartzito, mármore, xisto ou gnaisse.
- Intrusão/episódio térmico combinado com rede de fraturas estabelece circulação hidrotermal antiga. Algumas fácies sedimentares antigas estabelecem potencial diagenético. Esses registros tornam elegíveis modelos minerais, sem garantir concentração economicamente extraível.

O índice de profundidade deriva de um proxy de soterramento igual a um terço da espessura do corpo, escalado e limitado. A revisão encontrou e corrigiu um limite inicial que tornava o limiar profundo inalcançável. O teste agora demonstra uma unidade real suficientemente soterrada **e** mineralizante, sem usar altura ou forçar jazida.

| Substrato | Unidades nas 15 seeds de referência | Regra/estado |
| --- | ---: | --- |
| 001 granito | 468 | Embasamento continental |
| 002 basalto | 505 | Crosta oceânica jovem |
| 003 andesito | 168 | Arco convergente |
| 004 gabro | 983 | Embasamento oceânico antigo |
| 005 ultramáfica | 53 | Contexto oceânico extensional |
| 006 calcário | 38 | Fácies antiga carbonática |
| 007 arenito | 160 | Fácies antiga arenosa |
| 008 folhelho | 239 | Fácies antiga pelítica |
| 009 argilito | 156 | Fácies antiga pelítica |
| 010 conglomerado | 30 | Fácies antiga detrítica |
| 011 quartzito | 11 | Metamorfismo de precursor arenoso/detrítico |
| 012 mármore | 3 | Metamorfismo carbonático |
| 013 xisto | 20 | Metamorfismo pelítico |
| 014 gnaisse | 16 | Metamorfismo de embasamento |
| 015 tufo vulcânico | 33 | Sequência de arco |
| 016 sedimento aluvial | 0 | Bloqueado: falta deposição/transporte fluvial consolidado |
| 017 sedimento glacial | 0 | Bloqueado: falta história glacial persistente |
| 018 evaporito | 0 | Bloqueado: falta bacia restrita com evaporação recorrente comprovada |
| 019 sedimento costeiro | 0 | Bloqueado: falta deposição/transporte costeiro rastreável |
| 020 recife carbonático | 0 | Bloqueado: falta bioconstrução física |

Todos os 20 descritores são reconhecidos. Os cinco bloqueios são deliberados; não se usou P1 episódico ou clima potencial para declarar hidrologia/biologia consolidadas. Não foi forçada a presença de todos os tipos em cada seed.

Essas contagens incluem corpos continentais e substrato sob oceanos; não são contagens de afloramentos nem percentuais de área. As métricas também estimam cobertura em 1.536 células de diagnóstico por planeta, ponderadas por ângulo sólido real do cube-sphere. Na média das 15 seeds, gabro ocupa aproximadamente **34,34%**, basalto **17,26%** e granito **15,96%** da área modelada; as demais frações estão nos JSONs. A amostragem é macro e pode perder feições pequenas.

## Pontes, alternativas e oportunidades

As **18 pontes** são avaliadas genericamente: substrato obrigatório compatível, todas as evidências obrigatórias, qualquer evidência adicional exigida, evento/organismo e autorização canônica quando necessários. Ausência retorna inelegibilidade e motivos. As **24 alternativas** exigem a ponte correspondente e seus requisitos próprios. Satisfazer o modelo original e uma alternativa acrescenta proveniências à mesma oportunidade; não duplica chance, slot ou orçamento.

Nas 15 seeds, houve unidades elegíveis para quatro pontes: **402** para `veio_montanhoso`, **289** para `sedimentar`, **201** para `vulcanico` e **6** para `veio_profundo`. Uma unidade pode satisfazer mais de uma ponte; esses números não devem ser somados como corpos distintos.

Alternativas efetivamente elegíveis: **ALT-001 (236)**, ferro sedimentar; **ALT-002 (201)**, cobre vulcânico; **ALT-005 (6)**, prata profunda; **ALT-006 (253)**, ouro em veio primário; **ALT-007 (4)**, ouro profundo; **ALT-008 (22)**, chumbo sedimentar. As demais 18 alternativas estão implementadas e testadas, mas faltam seus processos específicos. Não foram criadas evidências genéricas para liberá-las.

O ouro demonstra a deduplicação em dados reais: as 253 rotas de veio primário e quatro profundas resultam em **253 oportunidades de ouro, não 257**, pois as profundas já pertencem a unidades elegíveis pela outra rota. Não houve ouro aluvial sem fonte e transporte comprovados.

As outras 14 pontes permanecem bloqueadas nos experimentos: aluvião, biomineral, caverna, deserto, escarpa, evaporito, fóssil, glacial, litoral, meteorítico, pântano, recifal, veio anômalo e veio arcano. Os JSONs de métricas discriminam os predicados ausentes por ponte. Em particular, altitude não registra escarpa exposta, perenidade, cavidade ou fonte excepcional.

## Experimentos reais e quantidade efetiva

| Seed | Raio km | Unidades J1 | Oportunidades únicas unidade/material | Candidatos pela calibração de teste |
| --- | ---: | ---: | ---: | ---: |
| 42 | 63.710 | 196 | 652 | 0 |
| 0 | 63.710 | 189 | 624 | 3 |
| 1 | 63.710 | 195 | 697 | 1 |
| 2 | 63.710 | 174 | 705 | 6 |
| 3 | 63.710 | 209 | 633 | 3 |
| 7 | 63.710 | 183 | 697 | 2 |
| 11 | 63.710 | 190 | 594 | 0 |
| 17 | 63.710 | 194 | 655 | 5 |
| 29 | 63.710 | 198 | 704 | 3 |
| 73 | 63.710 | 184 | 585 | 1 |
| 101 | 63.710 | 203 | 753 | 2 |
| 2026 | 63.710 | 193 | 831 | 1 |
| 4096 | 63.710 | 184 | 644 | 3 |
| 12345 | 63.710 | 197 | 472 | 3 |
| 98765 | 63.710 | 194 | 514 | 0 |
| 42 | 6.371 | 196 | 531 | 0 |
| 42 | 637.100 | 196 | 577 | 3 |
| 42 | 1.000.000.000 | 196 | 577 | 2 |

Na referência: **2.883 unidades físicas macro**, **9.760 oportunidades** e **33 candidatos** de orçamento. Nos 18 casos: **3.471 unidades**, **11.445 oportunidades** e **38 candidatos**. Todos os descritores e históricos estão efetivamente gerados nos planos JSON; não são projeções de uma intensidade histórica.

Isso **não significa 38 jazidas criadas em saves**. A demonstração materializou **uma unidade local e uma jazida experimental** em banco descartável; o restante são propostas selecionadas, sem estoque no mundo. Uma seed com zero candidatos permanece com zero. Nenhum save real recebeu unidades ou jazidas.

### Prova finita e persistente

Foi usada a primeira seed do lote cuja calibração original selecionou uma fonte: seed **0**, sem trocar seus parâmetros ou fabricar entradas. O corpo `geo:b19f74a12b90f10481c31e651e97`, slot 66, possui substrato ultramáfico, contexto tectônico, episódio térmico, rede de fraturas e circulação antiga registrados. A oportunidade de ferro usa a ponte `veio_montanhoso`; o nome histórico do modelo não exige montanha atual.

A jazida experimental **`deposit:a2bc2830c985acd9a2288bf722c45d1a`** possui **368 unidades abstratas D14**, posição esférica ancorada ao corpo, índice de profundidade e proveniência. O commit/reopen recuperou ID, estoque e baseline. Não há autorização de acesso, exposição ou coleta. O teste separado esgota o saldo e confirma que revisitar não o restaura; não foi criada extração ou inventário nesta fase.

## Calibração conservadora proposta

As intensidades históricas v4 não são lidas pelo seletor. O preset experimental separado usa taxas por milhão de oportunidades unidade/material: comum **10.000**, incomum **3.000**, raro **500**, muito raro **0**, lendário **0**. Limites globais por material: **4/2/1/0/0**, respectivamente; no máximo uma fonte por material/província geológica. Esses valores são proposta de teste, não parâmetros aprovados para autogeração de campanhas.

A seleção considera o universo macro completo e limitado, usando tickets estáveis e ordenação por hash. Assim, o primeiro local visitado não consome uma quota que mudaria o resultado de outro local. Rotas múltiplas não mudam o ticket. Autorizações excepcionais são recusadas separadamente da raridade.

Sensibilidade nas 15 seeds: taxa zero seleciona **0** fontes; metade do preset, **17**; preset, **33**; dobro, **71**. O preset selecionou **26 comuns e 7 incomuns**, zero raras/muito raras/lendárias; não há quantidade mínima obrigatória. Os limites não aumentam com a área do planeta. A baixa densidade é aceitável para a prova, mas ainda não estabelece disponibilidade prática para exploração/mineração: faltam medidas de área acessível e distância entre fontes. Não recomendo habilitar o preset em saves reais antes desse trabalho.

## Persistência, compatibilidade e desempenho

A migração aditiva **`r26r9m0n1o2p`**, sobre `q25q8l9m0n1o`, cria `genesis_geology_plans`, `genesis_geological_units` e `genesis_mineral_deposits`. Plano, fontes, catálogo, unidades e depósitos possuem hashes/versões fixados. Reabrir usa os registros salvos, sem reconstruir histórias. Divergências são recusadas. Eventos locais são preservados; consultas correntes recusam overlays não interpretados, permitindo baseline diagnóstico explícito.

Há criação opt-in da autoridade, materialização sob demanda das unidades e um método exclusivo de experimento para as fontes selecionadas. Não há chamada automática em save, exploração, mapa, turnos ou visitas. Mudanças de algoritmo/resolução/catalogação futuras exigem uma nova autoridade ou migração explícita, não regeneração de unidades já estabelecidas. O reset remove registros subordinados antes de T1 e preserva outras campanhas. A migração/downgrade foi exercitada com sentinela T1 antigo. **`everreach.db` não foi migrado.**

Preparação J1 com V4/T1 já carregados: **0,053–0,108 s** nos 18 casos; plano serializado de **196.168–231.742 bytes**. Preparação instrumentada da referência: **0,611 s**, pico adicional `tracemalloc` **3.389.842 bytes (~3,23 MiB)**, retidos **1.665.139 bytes**. Não é RSS e exclui formação V4/T1. O custo é limitado a no máximo 384 corpos e seus registros; consulta espacial compara os sítios, sem materializar setores nem executar geologia a cada tick.

A resolução é macro e deliberadamente limitada. No raio extremo, os corpos tornam-se fisicamente enormes; a ausência de crescimento do custo não comprova detalhe geológico local suficiente. Uma eventual subdivisão geológica física deverá ter contrato versionado próprio, separado de LOD e com recalibração; não poderá multiplicar retroativamente as oportunidades J1.

## Arquivos e reprodução

| Arquivos desta fase | Entrega |
| --- | --- |
| `backend/app/game/world/genesis/geology/{catalog,config}.py` | Catálogo ativo imutável, complemento e configuração J1. |
| `geology/{field,adapter}.py` | Unidades físicas/histórias e contrato v4.1, 18 pontes/24 alternativas. |
| `geology/{calibration,service,preview,__init__}.py` | Orçamentos experimentais, persistência e visualização técnica. |
| `backend/app/db/models/world_geology.py` | Três modelos aditivos. |
| `backend/app/db/models/__init__.py`, `backend/app/game/world/reset.py` | Registro e reset na ordem correta. |
| `backend/alembic/versions/r26r9m0n1o2p_add_geology_j1.py` | Migração/downgrade. |
| `backend/app/tests/test_genesis_geology*.py` | Testes reais, contratos, continuidade e persistência. |
| `backend/scripts/validate_geology.py` | 18 experimentos e demonstração SQLite descartável. |
| `artifacts/geology-j1/`, este documento | Planos, métricas, propostas, prova persistente e imagens. |

- [Métricas dos 18 casos e calibração](../artifacts/geology-j1/suite.json).
- [Imagem seed 42](../artifacts/geology-j1/seed-42-r63710000/geology.png), [seed 0](../artifacts/geology-j1/seed-0-r63710000/geology.png), [seed 2026](../artifacts/geology-j1/seed-2026-r63710000/geology.png).
- [Unidade, contrato e depósito persistido](../artifacts/geology-j1/seed-0-r63710000/persistent-proof.json).

As imagens mostram contatos de unidades, substrato primário e número de oportunidades elegíveis nas seis faces. Não representam itens expostos, acessibilidade ou estoque de jazidas em cada pixel. São ferramentas offline de desenvolvimento, não o Atlas nem o mapa público.

Comandos a partir de `backend`:

```powershell
.venv/Scripts/python.exe -u -m scripts.validate_geology
.venv/Scripts/python.exe -m pytest app/tests/test_genesis_geology.py app/tests/test_genesis_geology_persistence.py -q
.venv/Scripts/python.exe -m alembic heads
```

## Testes e próximas etapas

**46 testes novos aprovados**, incluindo comparação entre processos novos; continuidade em todas as emendas, cantos e polos; pontos compartilhados por setores/LODs; quatro raios; independência de ordem; quotas globais/regionais; todas as 24 alternativas sem duplicação; ausência de evidência; bloqueios canônicos, aquáticos e biológicos; profundidade alcançável; persistência, esgotamento sem respawn, rollback, eventos, corrupção, reset e migração/downgrade. O catálogo preserva 120 materiais, 14 propriedades por material e 360 perfis de extração.

A regressão final passou com **666 testes aprovados em 292,90 s**: os 620 anteriores e os 46 novos. A seleção cobre Genesis, exploração, mapa, viagens, fronteiras, materialização, reset e simulação temporal; inclui os hashes de referência das autoridades anteriores. `compileall`, `git diff --check` e head Alembic único (`r26r9m0n1o2p`) passaram. O único aviso foi a depreciação preexistente Starlette/httpx.

**A base geológica pode ser consumida para futuras etapas**, com o significado de cada evidência preservado. Ainda faltam geometria detalhada de corpos/contatos, exposição, acesso e calibração por área explorável, além dos processos hoje bloqueados. Os registros de mineralização são aproximações determinísticas de potencial mineral do RPG, não simulação geoquímica nem garantia de reserva lavrável. Uma unidade tem um hospedeiro primário; não há estratigrafia 3D completa. Não se alteraram materiais, terreno ou sistemas anteriores para fabricar um resultado positivo. Não foram implementados fauna/flora, civilizações, clima/hidrologia novos, fragmentos, extração, inventário ou Atlas.
