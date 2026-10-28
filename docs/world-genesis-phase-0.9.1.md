# World Genesis 0.9.1 — recalibração climática C3 experimental

## Entrega e decisão

Foi implementada **C3**, com transporte normalizado por distância física, reciclagem terrestre limitada à própria precipitação e à PET, e contabilização atmosférica local persistida. É uma melhoria integrada ao grafo existente, sem vegetação de entrada, reservatórios inventados, multiplicador global de chuva, ruído ambiental, novos serviços ou simulação diária.

O candidato selecionado para avaliação experimental usa **até 45% da chuva local reciclável**, ainda limitado pela demanda evaporativa do período. Não foi escolhido o candidato que produz mais chuva. O objetivo atingido foi reduzir hiperáridez e ampliar gradientes e habitats elegíveis no interior, mantendo desertos extensos. A participação de principais desérticos do E1 quase não mudou, e a área de principal florestal diminuiu: esses resultados estão explicitados abaixo, sem recalibrar o classificador para fazê-los desaparecer.

**C1/C2, seus defaults e seus snapshots permanecem reproduzíveis. C3 não foi ativada em campanhas reais.** A nova configuração é experimental e opt-in; não houve migração. W1/W2/P1 de C2 não são aceitos como saldos derivados de C3. A compatibilidade hídrica permanece bloqueada até uma revisão explícita, não foi simulada como se já existisse.

## Auditoria do código antes da alteração

Foram examinados `climate/{physics,plan,v2,query,dispatch,service,calibration}.py`, E1 e os leitores de fontes W1/W2/P1. C2 usa uma média síncrona dos vizinhos a montante, fonte oceânica prescrita, retenção `L/(L+passo)` e condensação por aresta. A chuva anual e a PET já tinham unidades e agregação corretas. Não houve correção aritmética dessas grandezas.

Limitações relevantes: a fração de condensação de fundo não distinguia uma aresta de 1.000 km de uma de 4.000 km; o transporte não incluía retorno de água precipitada à atmosfera; a média dos vizinhos não é um fluxo conservativo de massa atmosférica. Uma simples multiplicação da chuva não resolveria essas causas. E1 também fixava explicitamente a origem C2; seria incorreto passar C3 por esse contrato sem um perfil distinto.

Alternativas avaliadas:

| Alternativa | Tratamento |
|---|---|
| Multiplicar chuva globalmente | Descartada: altera escala sem melhorar transporte ou causalidade |
| Aumentar apenas o alcance de umidade C2 | Auditoria anterior mostrou ganho limitado; não resolve perdas por número de células |
| Normalizar distância sem reciclagem | Implementada como controle; não selecionada isoladamente por ganho climático insuficiente |
| Reciclagem com armazenamento/vegetação presumidos | Descartada: não há essa autoridade local consolidada |
| Normalização + retorno limitado à chuva do período e PET | Implementada; candidatos de 35%, 45% e 65% comparados |
| CFD, circulação diária ou novo simulador hidrológico | Fora do escopo; não implementados |

## Modelo C3 e suas garantias

### Distância e precipitação

A retenção de umidade em um percurso de comprimento `d` é `exp(-d/L_umidade)`. A profundidade óptica de condensação é:

```
tau = taxa_latitudinal_C2 * d / L_condensacao
    + max(0, subida_m) * coeficiente_orografico_por_km / 1000
fracao_condensada = 1 - exp(-tau)
```

As taxas latitudinais reaproveitam a convecção tropical e a ascensão extratropical de C2; oceanos, ventos, relevo, temperatura, insolação, PET e sazonalidade são preservados. A perda orográfica depende de subida física, não de acrescentar uma taxa plana por célula. As exponenciais autoritativas usam aritmética inteira com aproximação Padé e quadraturas sucessivas; não dependem do `libm` da plataforma. Os testes comparam a aproximação e a composição de percursos com tolerância inferior a 60 ppm.

O índice condensado por percurso é convertido em **taxa** usando `L_referencia_fluxo/d`, antes da conversão diária/sazonal já existente. Portanto subdividir um percurso não simplesmente duplica chuva por contar duas células. Esse fator varia com distância física e exposição, não é um multiplicador global escolhido para atingir cobertura ambiental. A solução não é numericamente idêntica entre resoluções: há quadratura e diferenças de terreno/costas, analisadas separadamente.

Os comprimentos padrão são derivados da política física de escala V4: `L_umidade=2*comprimento_placa`, `L_maritimo=comprimento_placa/3`, `L_condensacao=L_referencia_fluxo=comprimento_placa/4`. Os dois últimos também podem ser configurados explicitamente em metros e ficam na assinatura. No planeta de referência, são aproximadamente 25.298 / 4.216 / 3.162 / 3.162 km. A política cresce com raiz do raio e, em raios extremos, proporcionalmente ao raio, conforme a política já existente de placas.

### Água reciclada e contabilização

Em cada nó não oceânico e período:

```
disponivel = entrada * retencao_distancia
chuva_bruta = disponivel * fracao_condensada
retorno = min(chuva_bruta * fracao_reciclagem, limite_PET_convertido_para_o_percurso)
saida = disponivel - chuva_bruta + retorno
```

Não existe fonte terrestre independente de chuva. Não há água inicial ou estoque persistente criado, carry-over entre períodos, floresta presumida ou reutilização de W1. O retorno representa evaporação/evapotranspiração climatológica potencial de superfície recebendo chuva, limitada pela água e energia disponíveis na aproximação. Não afirma evapotranspiração real de uma espécie ou um solo específico.

Cada registro persiste sete inteiros: **entrada, perda por distância, disponível, chuva bruta, retorno, saída, limite PET**. Nos nós não oceânicos, as identidades são exatas no domínio de índices:

```
entrada = perda_distancia + disponivel
disponivel + retorno = chuva_bruta + saida
0 <= retorno <= min(chuva_bruta * r, limite_PET)
```

O limite aceito é `r<=0,65`; o candidato escolhido usa `r=0,45`, portanto pelo menos 55% de cada condensação não retorna imediatamente nessa regra. O mesmo vapor pode precipitar e evaporar em locais diferentes; isso é recorrência de fluxo bruto, não criação de um novo estoque. O ledger separa chuva bruta e deposição atmosférica líquida. Sem fonte oceânica, a inicialização seca e todos os retornos permanecem zero. Com PET zero, não há retorno local. A atualização é síncrona, determinística e limitada a 64 iterações por período no preset selecionado.

**Não se declara conservação global de água em litros.** O grafo continua calculando médias de vizinhos, sem resolver volumes de ar ou divergência de fluxos por área; os oceanos são condições de contorno prescritas. As identidades são locais em índices de umidade, e as conversões para mm têm arredondamentos inteiros. Chuva bruta do clima não é saldo de água superficial.

Na seed 42, sobre o conjunto de nós não oceânicos nativos, incluindo depressões abaixo do datum desconectadas, o diagnóstico contínuo ponderado dá aproximadamente **189,93 mm de precipitação bruta**, **71,60 mm de retorno** e **118,33 mm de deposição atmosférica líquida**. Esse domínio e sua quadratura diferem da amostra terrestre T1 da tabela principal. Esses valores não foram injetados em W1 como se fossem estoques reconciliados.

## Calibração: controles e candidatos

Foram avaliadas as seeds **42, 0, 7, 2026 e 12345**, raio de **63.710 km**. Cada candidato teve diagnóstico em **6.146 vértices nativos**, com ponderação esférica. Para o candidato de 45%, foram feitas **6.144 consultas T1/C3/E1 por seed** nos mesmos centros e pesos das 6.144 sondagens C2 congeladas da auditoria anterior. As assinaturas foram verificadas e o C2 foi reconstruído por igualdade completa em todas as seeds antes da comparação. Os dados C2 não foram trocados por uma nova geografia.

Além das 30.720 sondagens C3, houve 2.880 consultas regionais pareadas C2/C3: duas janelas de 1.024 km por seed, ancoradas nas duas primeiras unidades terrestres J1 em ordem determinística, com 144 pontos por janela/versão. A seed 42 também repetiu duas janelas nos testemunhos úmido/seco da auditoria anterior. Essas janelas extras não foram escolhidas para alterar a estatística global.

### Comparação entre candidatos — chuva terrestre nativa

Valores em mm/ano, quadratura dos vértices. Não confundir com a quadratura T1 dos centros da tabela seguinte.

| Seed | C3 sem reciclagem | C3 retorno até 35% | **C3 retorno até 45%** | C3 retorno até 65% |
|---|---:|---:|---:|---:|
| 42 | 158,40 | 184,11 | **192,34** | 210,22 |
| 0 | 148,13 | 173,90 | **182,23** | 199,19 |
| 7 | 148,20 | 173,35 | **181,38** | 197,81 |
| 2026 | 200,03 | 227,67 | **236,74** | 255,50 |
| 12345 | 209,79 | 243,11 | **253,80** | 275,13 |

O controle sem reciclagem corrige a dependência de percurso, mas isoladamente não entregou a redistribuição desejada e foi rejeitado como preset final. A alternativa de 35% melhora o interior, com retorno menor. A de 65% entrega mais chuva, mas permite quase dois terços de cada precipitação retornarem imediatamente; preferiu-se o limite intermediário, que já produz ganho forte nos índices hiperáridos sem assumir tanta reevaporação de superfície não caracterizada. Não se trata de um limite empírico universal da natureza; é uma escolha conservadora e versionada do modelo de RPG.

### Resultado C2 → C3 selecionado — 6.144 centros por seed

Médias e frações ponderadas por área esférica; denominador terrestre T1, salvo a coluna oceânica.

| Seed | Chuva terrestre C2 → C3 (mm/ano) | Chuva oceânica C2 → C3 (mm/ano) | Hiperárida C2 → C3 | Algum perfil florestal elegível C2 → C3 |
|---|---:|---:|---:|---:|
| 42 | 157,51 → 179,42 | 544,70 → 477,06 | 53,29% → 29,11% | 17,33% → 24,22% |
| 0 | 148,30 → 168,02 | 531,81 → 471,57 | 57,22% → 35,51% | 16,74% → 22,70% |
| 7 | 154,44 → 169,59 | 573,13 → 506,29 | 60,51% → 40,87% | 16,73% → 24,41% |
| 2026 | 207,83 → 215,46 | 559,98 → 494,01 | 42,39% → 19,80% | 21,96% → 29,20% |
| 12345 | 219,40 → 237,29 | 538,59 → 481,61 | 42,77% → 14,59% | 22,13% → 29,54% |

As temperaturas, amplitudes sazonais e PET são **idênticas ponto a ponto**, não apenas semelhantes em média. Houve redução de chuva oceânica e em parte das costas junto ao aumento no interior, evidência de redistribuição. O oceano permanece fonte prescrita; a mudança de taxa por exposição altera sua chuva diagnóstica, sem multiplicar seu índice de vapor.

Classes por P/PET: hiperárida <0,05; árida 0,05–0,2; semiárida 0,2–0,5; déficit moderado 0,5–1; úmida ≥1. PET zero é categoria energética separada. As frações não são biomas ou água líquida comprovada.

| Seed | Árida C2 → C3 | Semiárida C2 → C3 | Déficit moderado C2 → C3 | Úmida C2 → C3 |
|---|---:|---:|---:|---:|
| 42 | 17,16% → 31,37% | 8,57% → 16,53% | 8,36% → 10,72% | 10,18% → 9,84% |
| 0 | 14,43% → 27,23% | 8,59% → 15,98% | 7,38% → 10,05% | 10,71% → 9,55% |
| 7 | 11,76% → 24,15% | 7,24% → 13,31% | 7,73% → 9,86% | 9,88% → 8,93% |
| 2026 | 18,17% → 29,51% | 11,49% → 21,07% | 10,62% → 14,28% | 14,52% → 12,52% |
| 12345 | 18,08% → 33,84% | 10,94% → 21,05% | 11,33% → 16,47% | 15,20% → 12,36% |

O principal ganho é transformar extensões hiperáridas em regimes áridos, semiáridos e de déficit moderado, **não expandir a classe P/PET ≥1**. A elegibilidade de bosques/florestas pode aumentar também em regimes com déficit sazonal; não equivale à classe úmida nem à presença de árvores.

### Continentalidade, latitude e barreiras

Na seed 42, a chuva terrestre média por distância oceânica passa de:

| Distância macro C2 | C2 | C3 |
|---|---:|---:|
| 0–1.000 km | 911,00 | 779,05 |
| 1.000–3.000 km | 631,11 | 580,79 |
| 3.000–10.000 km | 191,41 | 218,26 |
| Mais de 10.000 km | 11,22 | 44,56 |

Os interiores mais distantes das outras seeds passam a aproximadamente 40,92 / 31,37 / 38,15 / 66,33 mm/ano. Portanto permanecem muito secos e distintos entre si. A seed 42 tem mediana terrestre de chuva **20 → 70 mm/ano**, mas P95 **906 → 807 mm/ano**. Não houve aumento uniforme de extremos.

Os relatórios `before`/`after` separam terra/referência oceânica/depressões desconectadas, seis faixas de latitude absoluta, quatro distâncias oceânicas, altitudes e contexto montanhoso. Os quatro períodos possuem médias de precipitação e temperatura próprias. Distância oceânica é o campo macro interpolado, não costa local medida em metros; o bin costeiro tem poucas sondagens. Latitude, relevo e vento impedem exigir monotonicidade perfeita entre bins.

Na quadratura nativa da seed 42, período 0, os nós terrestres a barlavento com subida acima de 300 m têm média de **131,77 → 123,50 mm no período**; a sotavento com descida maior que 300 m, **4,61 → 14,68 mm**. O contraste persiste, com maior umidade alcançando o lado protegido. As médias de grupos geográficos não isolam causalidade; o teste controlado de crista C3 verifica diretamente aumento de chuva na barreira e redução a jusante mesmo com reciclagem.

## Impacto real em E1

E1 não foi recalibrado para favorecer florestas. Foi adicionado somente um perfil de fonte explícito, `EV-ECO-1.1.1_C3_P_over_PET`, que aceita C3 e produz outra assinatura. O perfil C2 anterior, seus campos e sua serialização permanecem intactos. Nos novos snapshots, os campos de proveniência são rotulados C3, não apresentados como evidência C2.

| Seed | Principal deserto/estepe C2 → C3 | Principal do grupo de florestas C2 → C3 |
|---|---:|---:|
| 42 | 82,35% → 82,63% | 2,23% → 1,44% |
| 0 | 83,70% → 83,67% | 2,32% → 1,44% |
| 7 | 84,11% → 84,33% | 2,40% → 1,74% |
| 2026 | 77,14% → 78,18% | 3,49% → 1,49% |
| 12345 | 76,46% → 76,66% | 2,23% → 1,23% |

**A C3 não resolve a predominância gráfica dos rótulos desérticos.** Reduz o déficit mais extremo e amplia habitats florestais elegíveis, mas a seleção de um único principal continua dominada pelos intervalos/adequação E1, frio e precipitação absoluta. Parte das áreas costeiras perdeu chuva; por isso a área de principal florestal e a fração climaticamente úmida podem cair. Não se ocultou isso escolhendo uma quota ou alterando scores E1.

Os mosaicos pareados confirmam efeitos regionais sem exigir que todas as janelas mudem. Na segunda janela da seed 42, a diversidade de principais é **2 → 3**, com **8 → 7** IDs distintos em posições secundárias; na primeira da seed 0, **1 → 2**, secundários **4 → 6**; na primeira da seed 12345, principais **8 → 8**, secundários **16 → 17**. Algumas janelas da seed 7 permanecem uniformes. Os números são contagens de perfis/sondagens regionais, não percentuais globais de cobertura. Todos os pontos e secundários constam dos JSONs `regional-*-C2/C3`.

Nos testemunhos úmido/seco já definidos da seed 42, a janela úmida C3 contém sete principais e 16 IDs elegíveis, e a seca permanece com um principal e um ID elegível. Dois pontos C3 foram materializados em banco temporário, commitados e reabertos: 200 avaliações naturais, **122 incompatíveis, 73 pendentes e 5 elegíveis**, sem cobertura vegetal confirmada. Nenhuma espécie, jazida ou corpo hídrico foi criado.

## Escala, resolução e custo

### Sensibilidade

Na seed 42, mantendo a mesma autoridade geográfica V4 e H1 e reamostrando seus campos em cada nível:

| Nível climático | Vértices | Chuva terrestre C3 nativa (mm/ano) |
|---|---:|---:|
| 3 | 386 | 128,88 |
| 4 | 1.538 | 168,82 |
| 5 | 6.146 | 192,34 |

Esses níveis **não são LODs intercambiáveis**. Além da discretização do transporte, mudam as amostras de costas, montanhas e máscara oceânica. Ainda existe sensibilidade relevante, cerca de 14% do nível 4 para 5. Não se declara invariância à resolução. Os testes de subdivisão isolam a parte corrigida: retenção e profundidade óptica de um mesmo percurso/soma de subidas compõem aproximadamente, sem aplicar uma fração fixa por célula. O preset autoritativo selecionado permanece no nível 5.

Outros raios foram exercitados com mundos reais da seed 42, cada qual preservando sua geografia configurada:

| Raio (km) | Chuva terrestre C2 nativa | C3 nativa |
|---|---:|---:|
| 6.371 | 60,63 | 174,69 |
| 63.710 | 173,28 | 192,34 |
| 637.100 | 196,01 | 144,11 |
| 1.000.000.000 | 196,01 | 144,11 |

Não houve ganho universal de chuva em todos os raios. O C3 normaliza perdas e taxas pelo percurso; isso muda a calibração anterior especialmente onde a relação entre resolução, escala de placas e distâncias era diferente. Os planetas gigantescos continuam funcionais e determinísticos, mas presets de raio distintos devem ser avaliados como configurações próprias. Esta seleção prioriza 63.710 km, sem alegar que todas as escalas resultem igualmente povoadas ou úmidas.

Na referência, o residual do candidato selecionado é de 2–4 ppm nas cinco seeds. Na seed 42, aumentar 64 para 128 iterações muda a média nativa em apenas **0,000303 mm/ano**. No raio terrestre, o residual é maior, 319 ppm, e a mesma mudança leva de **174,687 para 174,928 mm/ano** (~0,14%). Isso permite limitar o custo, sem declarar solução analítica exata.

### Benchmark

Seed 42 de referência, três preparos completos por versão, com as fontes V4/H1 previamente preparadas. Os tempos incluem as avaliações V4 do campo climático; memória instrumentada separadamente, com geometria reutilizada. Não são RSS nem benchmark isolado do sistema operacional; parte da execução coincidiu com validações offline.

| Medida | C2 | C3 |
|---|---:|---:|
| Mediana do preparo completo | 2,008 s | 2,875 s |
| Pico de alocações Python do preparo medido | 14.568.556 bytes | 20.749.324 bytes |
| Payload compacto | 1.091.034 bytes | 2.301.599 bytes |
| Recarga + validação | 0,044 s | 0,118 s |
| Mediana de consulta climática em memória | 0,167 ms | 0,169 ms |

O preparo aumentou aproximadamente 43%, e o ledger ampliou payload/memória. O custo continua limitado a quatro períodos e 6.146 vértices no preset, sem gerar setores locais distantes. As consultas continuam interpolando quatro vértices. Caches C1/C2/C3 compartilham o limite anterior de dois planos; o ambiente mantém os limites E1 existentes. Não há worker ou processo climático contínuo.

## Versionamento, saves e hidrologia

- `climate_version=3`, configuração e assinatura próprias; dispatch explícito. O solver C1/C2 não foi reescrito.
- A subclasse de plano C3 persiste comprimentos resolvidos, passos e ledger; a recarga verifica dimensões, não negatividade, orçamentos, identidades e correspondência entre ledger e chuva, sem solver.
- O serviço climático mantém seu default anterior e rejeita reconfiguração silenciosa de um cabeçalho C2 para C3.
- E1-C3 exige configuração explícita e fica fixado à assinatura/checksum C3. E1-C2 não é reinterpretado como C3 e preserva sua assinatura.
- W1 aceita fontes C1/C2; `source_climate_version=3` é recusado. Um balanço W1-C2 carregado com C3 falha por proveniência. W2/P1 têm cabeçalhos/assinaturas C2 explícitos e continuam bloqueados para essa troca.
- O teste de coexistência cria campanhas C2 e C3 descartáveis no mesmo banco, confirma recarga e revisita sem chamar gerador climático ou amostrador ambiental novamente.

Antes de usar C3 em uma campanha com hidrologia, será necessário preparar **novos** balanços e revisar a correspondência entre chuva bruta, retorno atmosférico potencial e evaporação efetivamente limitada por W1. Não é seguro copiar saldos, apenas trocar uma assinatura ou afirmar que o ledger atmosférico já reconcilia os litros de W1/W2/P1. Nenhum desses sistemas foi alterado para contornar o bloqueio nesta etapa.

## Testes e imagens

**783 testes aprovados em 927,50 s (15 min 27 s)** na regressão selecionada: World Genesis, clima/ambientes, hidrologia/balanços, geologia, mapa, movimento/viagem/exploração, fronteiras/rotas, reset e integração temporal. Inclui os 752 da entrega E1, os sete da auditoria posterior e os 24 C3. Apenas o aviso preexistente Starlette/httpx. Também passaram compilação e verificações de whitespace, identidade das fontes e recarga/ledger dos cinco planos C3 exportados. A suíte completa de todo backend/frontend não foi executada.

Os **24 testes novos C3** passaram na execução específica, incluindo exponencial/subdivisão, origem e limites de reciclagem, ausência de água sem fonte, extremos frios/PET, não negatividade, sombra de chuva, emendas/cantos/polos, raios, ordem síncrona, hashes de processo, ledger e rejeição de corrupção, dispatch, C2 intacto, perfil E1 explícito, coexistência/persistência e bloqueio de saldos hídricos de outra versão. A revisita persistida foi testada com funções de geração substituídas por falha obrigatória para detectar regeneração inadvertida.

Após o endurecimento final da validação do ledger e da mensagem de perfil de origem, **76 testes C3/E1 foram repetidos e passaram em 90,38 s**. A cadeia Alembic continua com o único head anterior `t28t1o2p3q4r`; nenhuma migração nova foi criada ou aplicada.

Imagens técnicas offline, com as mesmas escalas antes/depois:

- [Seed 42: precipitação, temperatura, P/PET e principal E1](../artifacts/climate-recalibration-0.9.1/seed-42/comparison.png).
- [Seed 42: classes de aridez e potencial florestal sobreposto](../artifacts/climate-recalibration-0.9.1/seed-42/potential-comparison.png).
- [Seed 42: perfil de distância oceânica](../artifacts/climate-recalibration-0.9.1/seed-42/distance-profile.png).
- [Seed 2026: comparação](../artifacts/climate-recalibration-0.9.1/seed-2026/comparison.png).
- [Comparação completa das cinco seeds](../artifacts/climate-recalibration-0.9.1/suite.json) e [desempenho/sensibilidades](../artifacts/climate-recalibration-0.9.1/performance-sensitivity.json).

As cinco pastas têm os mesmos mapas, amostras, relatório e plano C3. Verde na figura de potencial significa elegibilidade física, não árvores instanciadas. Azul marinho é referência oceânica, não habitat aquático confirmado. As figuras não alteram conhecimento do jogador ou o mapa público.

## Arquivos e reprodução

| Arquivo | Mudança |
|---|---|
| `backend/app/game/world/genesis/climate/v3.py` | Configuração/solver C3, exponencial inteira, reciclagem e ledger, validação/recarga |
| `.../climate/plan.py`, `dispatch.py` | Dispatch e carga C3 explícitos, preservando caminhos C1/C2 |
| `.../climate/calibration.py` | Diagnóstico de transporte com a física correta de C3 |
| `.../environment/config.py`, `adapter.py`, `service.py` | Perfil E1-C3 opt-in e proveniência correta, sem mudar a classificação E1-C2 |
| `backend/scripts/validate_environment.py` | Importador descartável usa a versão climática real, sem hardcode C2 |
| `backend/scripts/audit_climate_after_e1.py` | Rótulo climático opcional em figuras e checagem sazonal por versão |
| `backend/scripts/recalibrate_climate.py` | Candidatos, cinco seeds, 6.144 centros, mosaicos/secundários, figuras e prova persistida |
| `backend/scripts/benchmark_climate_recalibration.py` | Preparo, memória, raio, resolução e horizonte iterativo |
| `backend/app/tests/test_genesis_climate_v3.py` | 24 casos C3 |
| `backend/app/tests/test_genesis_climate_v2.py` | Versão inválida passa de 3 para 4, pois 3 agora é suportada explicitamente |
| Este documento e `artifacts/climate-recalibration-0.9.1/` | Resultados reproduzíveis e limitações |

Em `backend`:

```powershell
.venv/Scripts/python.exe -m scripts.recalibrate_climate
.venv/Scripts/python.exe -m scripts.benchmark_climate_recalibration
.venv/Scripts/python.exe -m pytest app/tests/test_genesis_climate_v3.py -q
```

O primeiro script reutiliza as 6.144 amostras C2 congeladas da auditoria anterior, verificando assinatura e replay; os arquivos necessários permanecem em `artifacts/climate-audit-after-e1/`. Não lê o banco de campanha. A prova persistida usa arquivo SQLite temporário. V4, T1, J1/JR1, D14 e EV-ECO não foram recalibrados ou substituídos.

## Limitações e recomendação

C3 entrega uma melhoria física pequena e versionada do transporte, com queda relevante de hiperáridez e aumento de habitats florestais potenciais nos cinco planetas de referência. Não elimina regiões inóspitas nem resolve todos os limites de um modelo de circulação prescrito. A fração úmida e os principais florestais não aumentaram; isso é uma limitação/resultante desta escolha, não evidência de conversão errada de E1.

Persistem ausência de conservação atmosférica global rigorosa, fonte oceânica parametrizada, resolução costeira/microclimática limitada, sensibilidade à malha e falta de feedback de estoques/solos reais. O retorno é climatológico e não um saque de estoques de gameplay. Não existe acúmulo sazonal de solo ou neve nesse novo fechamento.

Recomendação: **aceitar C3 de 45% como preset experimental para revisão**, mantendo C2 em saves antigos e a ativação real desligada. A aprovação para novos mundos deve considerar os mapas e a alteração dos balanços hídricos; até lá, a compatibilidade W1/W2/P1 continua bloqueada. Não há autorização implícita para migrar campanhas ou gerar flora/fauna nesta entrega.
