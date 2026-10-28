# World Genesis 0.8.1 — refinamento regional JR1

## Auditoria e decisões anteriores à implementação

J1 preserva aproximadamente 192 corpos macro e sua história. Seu adaptador não tem formação regional e o preset experimental limita o planeta inteiro. Não se deve modificar o campo J1 nem aumentar sua chance por visita. V4/T1 e D14 permanecem imutáveis.

JR1 será uma extensão opt-in de J1. Uma malha espacial cartesiana de 8 km intersectada com a esfera define sítios físicos; a formação usa o sítio esférico mais próximo, com busca local de orçamento fixo. Os contatos são esféricos, sem emendas do cube-sphere. IDs incluem autoridade, província J1 e endereço físico; nenhum LOD ou visita. As formações são recortadas pelos contatos J1. Fragmentos cujo sítio fica fora da província não ganham fontes: ficam explicitamente pendentes, sem mover sua âncora conforme a exploração.

As histórias JR1 registrarão fácies, intrusões compatíveis, estratos, fraturas e processos mineralizantes antes da adaptação. Não haverá processos fluviais, biológicos, glaciais ou canônicos inventados. Substrato, afloramento modelado, oportunidade, jazida e acesso terão estados distintos. O afloramento será apenas uma hipótese geométrica sobre T1 baseline; não uma autorização de mineração.

A seleção experimental usará intensidade por comprimento de estrutura elegível, com uma oportunidade por formação/material e nenhum cap global fixo. Todas as rotas D14 de um material compartilham a mesma oportunidade. Fontes finitas reutilizarão `GenesisMineralDeposit`; tabelas aditivas guardarão a autoridade regional, formações e vínculos. Não haverá autogeração em campanhas reais nem migração do banco real.

Experimentos usarão seeds predefinidas e janelas terrestres escolhidas por geografia, antes de avaliar minerais, inclusive casos sem fontes. Mediremos área, densidade, distâncias, exposição, custo e persistência. Não extrapolaremos o total de jazidas planetárias a partir de poucas janelas.

## Resultados

**JR1 está operacional como extensão regional de J1, com ativação explícita e fontes experimentais finitas.** A limitação de aproximadamente 200 oportunidades para o planeta inteiro foi removida do caminho regional: uma única janela terrestre da seed 42 contém 245 formações físicas e 1.474 oportunidades locais. Nenhuma fonte foi criada em saves reais.

## Hierarquia, resolução e continuidade

J1 continua determinando província, hospedeiro macro e história fundamental. JR1 acrescenta formações de escala quilométrica a essa autoridade; não refaz placas, continentes, terreno ou clima.

Alternativas consideradas: subdividir os tiles gráficos faria a geração depender de LOD; pré-computar uma tesselação fina planetária teria custo proibitivo; criar pontos aleatórios conforme a visita alteraria o mundo pela ordem de exploração. Foi escolhida uma função espacial local sobre uma malha cartesiana tridimensional, intersectada com a mesma esfera existente.

A escala padrão é **8.000 m**, independente do raio e dos setores de renderização. Cada caixa que intersecta uma porção de área positiva da esfera possui um sítio determinístico no seu interior. A formação pertence ao sítio mais próximo; a busca examina exatamente um halo de **343 caixas**, com desempate canônico pelo endereço. A comparação é inteira, com raios exatos de até 53 bits do contrato existente. A quantização dos sítios fica abaixo de 1 mm até o raio máximo. O teste compara esse halo com um halo maior, incluindo polos, emendas e planetas pequenos/grandes.

O próprio sítio da caixa que contém um ponto fornece um limite de distância de aproximadamente `sqrt(3) × espaçamento`; isso permite uma busca finita, sem índice planetário de alta resolução. O espaçamento é uma escala de planejamento, não a promessa de diâmetro ou área idênticos para todos os corpos. Para planetas menores que quatro espaçamentos, há um limite explícito de `R/4`; os raios dos experimentos principais usam integralmente 8 km.

O ID é derivado de assinatura JR1, província J1 e endereço físico. Uma formação pode cruzar setores e faces e ser consultada em qualquer LOD. Janelas de estudo não participam dos IDs. Duas janelas sobrepostas retornam os mesmos corpos, oportunidades e fontes. Não há um contador global de formações: outras áreas possuem seus próprios endereços, preparados apenas quando necessários.

Os corpos são recortados pelo domínio J1. Perto de um contato macro, um fragmento pode ter o sítio do outro lado da província. Esse fragmento mantém a identidade e o contexto corretos, mas **não gera fontes enquanto não tiver âncora interior certificada**. Não se desloca a âncora conforme a visita. A recusa é um bloqueio de geração mineral, não uma barreira à movimentação. O comportamento é testado numa fronteira J1 real.

## História física, substrato e evidências

As formações registram hospedeiro, espessura, cobertura relativa, índice de profundidade, comprimento agregado de estrutura e proveniência. As variações dependem do hospedeiro e das etapas existentes em J1:

- Bacias antigas recebem fácies compatíveis e pacotes estratigráficos explícitos: por exemplo, arenito/argilito/conglomerado ou folhelho/argilito/arenito.
- Contextos metamórficos mantêm famílias compatíveis, sem converter arbitrariamente uma província em bacia ou arco vulcânico.
- Embasamentos/episódios térmicos compatíveis podem conter corpos intrusivos subordinados; a primeira janela da seed 42 contém 173 formações graníticas e 72 gabróicas.
- Redes de fraturas provêm de estruturas herdadas ou contração térmica registrada. Circulação mineralizante requer hospedeiro térmico e permeabilidade. Horizontes diagenéticos exigem bacia/fácies/idade compatíveis.

Esses são processos novos do modelo estático **JR1**, persistidos antes da adaptação. Não são fatos atribuídos retroativamente a V4/T1, nem simulação dinâmica. O adaptador só lê os registros e confere a existência dos processos referenciados. Ausência de evidência não ganha fallback em consultas.

Continuam proibidas inferências de rios permanentes, transporte aluvial, recifes, geleiras, cavernas completas, organismos, impactos ou fontes arcanas a partir de altitude/clima. As 18 pontes e 24 alternativas D14 são reutilizadas sem alteração. As alternativas compartilham uma oportunidade por formação/material. Um filtro conservador de profundidade usa o intervalo de referência individual D14; o índice não é convertido implicitamente em metros. As demais restrições canônicas são verificadas antes de selecionar fontes.

## O que cada estado significa

| Estado | Significado implementado |
| --- | --- |
| Substrato | Hospedeiro da formação, inclusive enterrado; não um item ou afloramento confirmado. |
| Afloramento modelado | Cobertura geométrica JR1 não positiva e âncora acima do nível do mar T1 baseline. É hipótese estática registrada, sem erosão/clima atuais inventados. |
| Oportunidade | Formação, processo e material compatíveis; ainda não há reserva criada. |
| Fonte selecionada | Proposta da política experimental, com ID, posição e volume finito; pode ainda não estar no banco. |
| Jazida persistida | Instância em `GenesisMineralDeposit`, com saldo inicial e remanescente. Voltar não faz uma nova seleção nem repõe o saldo. |
| Acesso | **Não autorizado** nesta fase. Inclinação regional e afloramento são diagnósticos, não prova de caminho, segurança ou capacidade de extração. |

A cobertura relativa é um parâmetro geológico JR1, não uma escavação em T1. As figuras distinguem hospedeiro enterrado, afloramento modelado, oportunidade e fonte candidata. Nenhuma altura T1 foi modificada.

## Calibração por extensão física

O preset experimental usa intensidade por quilômetro de estrutura elegível: comum **0,035**, incomum **0,008**, raro **0,001**, muito raro **0,00005**, lendário **0**. O comprimento registrado varia com a escala física da formação, e não com o número de visitas, pixels ou consultas. Na escala padrão, o comprimento agregado fica entre aproximadamente 1,6 e 6,4 km; não representa uma rota reta de mineração.

A regra versionada é `p = λL / (1 + λL)`, calculada com inteiros e ticket estável por oportunidade/material. É uma aproximação de ocorrência de RPG, não uma lei geofísica. Os parâmetros foram definidos como proposta antes das medições e mantidos nos casos positivos e vazios. Não são as intensidades históricas v4. Não há cap global 4/2/1 nem quota consumida pelo primeiro território visitado. Só há uma fonte por formação/material, independentemente do número de rotas elegíveis.

O ticket não usa o fator de sensibilidade; assim, comparar metade/preset/dobro mede a mesma população física. No lote de referência, foram selecionadas **514 / 957 / 1.684** fontes, respectivamente. Taxa zero seleciona zero. O preset é conservador entre as alternativas testadas e continua exclusivamente experimental; não há ativação automática no jogo.

## Experimentos reais, sem escolha de seeds favoráveis

Seeds predefinidas: **42, 0, 7, 2026 e 12345**. Para cada uma, as três primeiras âncoras J1 terrestres na ordem dos slots foram escolhidas **antes** de avaliar minerais. Cada janela mede **96 × 96 km**. A enumeração encontra todos os sítios ancorados dentro da janela por um volume local limitado; não depende da resolução da imagem. A área terrestre é medida separadamente em quadratura esférica de 24 × 24 células, considerando a área real dos quadriláteros.

| Seed | Janela | Formações | Oportunidades | Fontes selecionadas | Comuns terrestres | Comuns com afloramento modelado | Ferro: fontes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 42 | 0 | 245 | 1.474 | 71 | 57 | 8 | 12 |
| 42 | 1 | 205 | 1.306 | 72 | 62 | 5 | 15 |
| 42 | 2 | 237 | 777 | 50 | 37 | 3 | 20 |
| 0 | 0 | 234 | 1.507 | 87 | 74 | 13 | 17 |
| 0 | 1 | 228 | 804 | 61 | 49 | 6 | 23 |
| 0 | 2 | 216 | 644 | 43 | 35 | 4 | 20 |
| 7 | 0 | 203 | 1.420 | 90 | 76 | 5 | 28 |
| 7 | 1 | 238 | 1.427 | 79 | 65 | 14 | 16 |
| 7 | 2 | 247 | 853 | 47 | 30 | 1 | 19 |
| 2026 | 0 | 240 | 1.380 | 82 | 66 | 13 | 16 |
| 2026 | 1 | 234 | 1.576 | 70 | 57 | 8 | 6 |
| 2026 | 2 | 190 | **0** | **0** | **0** | **0** | **0** |
| 12345 | 0 | 234 | 3.712 | 134 | 111 | 20 | 20 |
| 12345 | 1 | 233 | 420 | 25 | 20 | 1 | 14 |
| 12345 | 2 | 219 | 764 | 46 | 36 | 7 | 17 |

O caso vazio não foi substituído: seu hospedeiro/história não fornece os processos mineralizantes necessários. A variação de litologia e história explica resultados muito diferentes sem obrigar cada região a ter recursos.

No raio de referência, foram geradas **3.403 formações**, **18.064 oportunidades**, **957 propostas de fontes**, sendo **775 comuns**, **159 incomuns** e **23 raras**. Muito raras e lendárias: **zero selecionadas**. As 23 raras distribuem-se por nove materiais, sem tornar cada material raro abundante.

As janelas somam aproximadamente **138.239,92 km² terrestres**. A média ponderada é de **5,61 fontes comuns por 1.000 km²**; entre janelas, **0–12,04**. Há **108** fontes comuns em afloramento modelado. Fontes enterradas continuam sendo reservas, não itens disponíveis no chão.

Na janela 0 da seed 42, o ferro possui **12 fontes**, com mediana local de vizinho mais próximo de **11,47 km**. Nas janelas com ferro, essa mediana varia aproximadamente de **11,24 a 18,60 km**. Entre sítios distintos com algum recurso comum, as medianas locais variam de **6,30 a 12,84 km**. Materiais diferentes podem coexistir na mesma formação; distâncias agregadas deduplicam essas posições para não produzir zeros artificiais. Não se convertem essas medidas para as unidades legadas de viagem.

### Outros raios, mesma escala regional

| Seed 42 / janela 0 | Formações | Oportunidades | Selecionadas | Comuns terrestres | Ferro |
| --- | ---: | ---: | ---: | ---: | ---: |
| Raio 6.371 km | 233 | 3.665 | 129 | 103 | 22 |
| Raio 63.710 km | 245 | 1.474 | 71 | 57 | 12 |
| Raio 637.100 km | 240 | 1.315 | 65 | 53 | 13 |
| Raio 1.000.000.000 km | 238 | 1.623 | 84 | 71 | 15 |

As histórias macro e as posições escolhidas variam com o planeta; não se exige a mesma quantidade de fontes. O espaçamento local permanece 8 km. Nos **18 casos**, há **4.114 formações únicas**, **24.667 oportunidades** e **1.235 propostas únicas**. Os snapshots foram efetivamente produzidos; não são projeções baseadas na área planetária. Somente essas janelas foram detalhadas.

## Persistência real e estoque compartilhado

A prova usa a seed 42/janela 0 e um SQLite descartável. A autoridade JR1 é vinculada a checksum J1, T1, configuração e política fixados. A janela é materializada em ordem inversa, confirmada e reaberta. Os IDs e volumes são comparados às propostas físicas originais.

O exemplo de continuidade é a formação **`jr1:a09f099e4eb1b07d2e95d486b2039f80`**, que atravessa os setores físicos **`0/13/2255/607`** e **`0/13/2255/608`**. Nos dois lados, a fonte de quartzo **`deposit-jr1:0420c23a17f82b27b71b42a5f65b8b60`** mantém **148 unidades abstratas D14**, com mesmo ID e saldo após reabrir o banco. Os pontos exatos e os estoques estão no arquivo da prova.

A demonstração completa materializa **245 formações e 71 jazidas experimentais finitas** da primeira janela. As demais **1.164 propostas** do lote permanecem propostas, sem estoque criado em saves. Os testes também esgotam um saldo e confirmam que revisitas por outro setor não o recompõem. Não existe mineração, item ou inventário gerado por esse teste.

As reservas reutilizam **`genesis_mineral_deposits`**. Uma tabela de vínculo aplica unicidade por campanha/formação/material; não há um estoque paralelo somado a J1. A ativação recusa campanhas com jazidas macro experimentais já alocadas, exigindo migração explícita. Na direção inversa, uma campanha JR1 não pode voltar a criar jazidas pelo experimento macro antigo. Saves J1 sem tabelas JR1 continuam funcionando, verificado em teste.

A migração **`s27s0n1o2p3q`**, sobre `r26r9m0n1o2p`, é aditiva: cria autoridade regional, formações e vínculos, sem alterar os dados anteriores. Baseline e mudanças posteriores são separados. Eventos geológicos não interpretados bloqueiam novo uso corrente; o histórico permanece acessível em diagnóstico explícito. Eventos T1 na âncora impedem novas fontes; exposição e acesso atuais nunca são declarados confirmados para toda a formação.

O escritor SQLite adquire proteção antes do savepoint, e a transação externa continua sob controle do chamador. Uma falha no vínculo reverte formação/fontes do lote. Duas sessões preparando a mesma formação não duplicam reservas. Não há commits internos. Reset e downgrade foram testados com sentinela J1 antigo e outras campanhas preservadas. **O banco real `everreach.db` não foi migrado.**

## Custo e geração sob demanda

Preparar os descritores de uma janela levou aproximadamente **0,194–0,325 s**, com J1/V4/T1 já carregados. A referência instrumentada por `tracemalloc` levou **2,29 s**, pico adicional **2.908.064 bytes (~2,77 MiB)** e **2.891.482 bytes retidos**, incluindo 245 descritores e caches locais. Não mede RSS nem inclui a construção das autoridades macro.

O cache de sítios é limitado a **4.096** entradas e o de formações a **256**. Cada consulta espacial tem halo fixo; cada materialização persiste uma formação e suas fontes, não uma janela inteira obrigatoriamente. O enumerador de experimentos tem limite de **16.000 caixas** e janela máxima de 128 km; ele não faz parte da exploração ou de um loop por tick. A persistência de uma janela inteira é um teste mais caro, não o mínimo necessário para iniciar uma campanha.

Materializar e validar deliberadamente as **245 formações/71 fontes no SQLite temporário levou 19,38 s**, aproximadamente 79 ms por formação nesse lote. Isso inclui repetidas leituras/validações de autoridade, catálogo, verificações T1, SQL e registros de estoque; não se deve anunciar o tempo dos descritores puros como custo completo de salvar. O lote rodou junto dos testes locais, não é medição de frame ou streaming isolado. Há margem para otimizar a reutilização de contexto em lotes, sem mudar a autoridade ou adicionar workers.

## Arquivos e reprodução

| Arquivos desta fase | Entrega |
| --- | --- |
| `backend/app/game/world/genesis/geology/regional/{config,spatial}.py` | Versões, escala física e sítios locais na esfera. |
| `regional/{field,occurrence}.py` | Histórias, estratos, adaptação D14 e ocorrência por extensão. |
| `regional/{service,experiment,preview,__init__}.py` | Persistência, janelas métricas e figuras offline. |
| `backend/app/game/world/genesis/geology/service.py` | Proteção contra misturar fontes macro J1 e JR1; geografia J1 inalterada. |
| `backend/app/db/models/world_geology_regional.py` | Três modelos de autoridade/formação/vínculo. |
| `backend/app/db/models/__init__.py`, `backend/app/game/world/reset.py` | Registro e reset na ordem correta. |
| `backend/alembic/versions/s27s0n1o2p3q_add_regional_geology_jr1.py` | Migração aditiva/downgrade. |
| `backend/app/tests/test_genesis_geology_regional*.py` | Testes da extensão e da persistência. |
| `backend/scripts/validate_regional_geology.py` | Experimentos predefinidos e prova SQLite descartável. |
| `artifacts/geology-jr1/`, este documento | Descritores reais, métricas, propostas, prova e imagens. |

- [Lote completo e desempenho](../artifacts/geology-jr1/suite.json).
- [J1/JR1/fontes na seed 42](../artifacts/geology-jr1/seed-42-r63710000-w0/regional-geology.png).
- [Variação sedimentar](../artifacts/geology-jr1/seed-42-r63710000-w2/regional-geology.png) e [controle vazio 2026](../artifacts/geology-jr1/seed-2026-r63710000-w2/regional-geology.png).
- [Formações reais da referência](../artifacts/geology-jr1/seed-42-r63710000-w0/formations.json), [fontes selecionadas](../artifacts/geology-jr1/seed-42-r63710000-w0/selected-test-sources.json) e [estoques persistidos](../artifacts/geology-jr1/seed-42-r63710000-w0/persistent-proof.json).

Comandos a partir de `backend`:

```powershell
.venv/Scripts/python.exe -u -m scripts.validate_regional_geology
.venv/Scripts/python.exe -m pytest app/tests/test_genesis_geology_regional.py app/tests/test_genesis_geology_regional_persistence.py -q
.venv/Scripts/python.exe -m alembic heads
```

## Validação e conclusão

Os **34 testes novos** cobrem: cobertura e busca inteira confrontada com halo maior; continuidade de emendas/polos em vários raios; múltiplas formações na mesma província; setores e LODs compartilhando fontes; janelas sobrepostas; ordem inversa e expulsão dos caches; contato J1 pendente; caso real vazio; D14/raridade/profundidade; processos ausentes; determinismo entre processos; commit/reopen, saldo esgotado, corrupção, eventos, rollback atômico, duas sessões, migração/downgrade, reset e incompatibilidade de alocação macro/regional.

A regressão final passou com **700 testes aprovados em 323,07 s**: os 666 anteriores e os 34 novos. A seleção cobre Genesis, exploração, mapa, viagens, fronteiras, materialização, reset e simulação temporal, incluindo os hashes de referência anteriores. `compileall`, `git diff --check` e head Alembic único (`s27s0n1o2p3q`) passaram. O único aviso foi a depreciação preexistente Starlette/httpx.

**A limitação estrutural de escala foi resolvida:** recursos comuns agora aparecem em escalas regionais mensuráveis, com fontes raras esparsas e regiões legitimamente vazias. A base está apta a preparar geologia e reservas continentais progressivamente. A autogeração real permanece desligada conforme solicitado.

Limites: corpos e estruturas ainda são aproximações estáticas, sem estratigrafia 3D completa; a malha cartesiana produz áreas variáveis conforme orientação, e o preset não garante densidade planetária uniforme. A calibração usa área física medida e comprimentos registrados, mas as 15 janelas terrestres não são uma amostra estatística de todo o planeta. Contatos macro com âncora externa continuam pendentes. Afloramento é modelado, acesso real não foi calculado, e reservas não provam minério lavrável ou economia balanceada. Há base de disponibilidade para futuras mineração/crafting/economia, mas sua funcionalidade e custos exigirão as respectivas integrações, proibidas nesta fase. Não foram implementados cavernas completas, Atlas, biomas, fauna, hidrologia/clima novos ou geração dependente do nível do protagonista.
