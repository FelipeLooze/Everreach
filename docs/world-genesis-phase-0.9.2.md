# Fase 0.9.2 — compatibilidade hídrica C3 R1-55

## Auditoria e decisão anterior à implementação

C3 fornece precipitação bruta climatológica, retorno atmosférico potencial derivado dessa precipitação e PET. Seu ledger fecha identidades locais em índices de umidade, não massa atmosférica global em litros. O retorno não é um saque já realizado em estoques W1. A deposição líquida P−retorno é um diagnóstico atmosférico, não a chuva que necessariamente deve alimentar o balanço de superfície.

W1 recebe quatro períodos de chuva/PET/neve/temperatura, começa seco, executa aquecimento limitado e evapora somente água líquida/solo/reservatório acessível. Seu balanço de litros é conservativo. A adaptação mínima escolhida é um **contrato de forçamento explícito W1/C3-R1-55 v1**: chuva bruta entra uma vez; PET total permanece demanda; retorno e deposição atmosférica ficam como diagnósticos separados, sem créditos ou débitos adicionais. Subtrair o retorno e ainda consumir PET total duplicaria a retirada hipotética. Adicioná-lo à chuva duplicaria a entrada.

W2 abre somente os estoques finais W1 uma vez, sem recreditar seus fluxos históricos. P1 subdivide contas existentes e exige prova T1/G1, capacidade e débito real. Seus kernels não dependem de uma fórmula climática C2; o bloqueio está no leitor de fontes e nos identificadores de proveniência. A implementação manterá os formatos/fontes C2 intactos e criará fontes explícitas C3 para novas autoridades, sem copiar balanços.

## Resultados

**Implementada a extensão explícita W1/C3-R1-55 v1 e adaptadas as fontes W2/P1.** A demonstração materializou uma prova natural nova sob o saldo C3, transferiu água real entre contas finitas e confirmou commit/reabertura/idempotência. Não houve alteração de C3 R1-55, V4/T1/JR1, taxonomia, campanhas reais ou esquema de banco.

## Contratos e significado das grandezas

| Grandeza | Significado e unidade | Uso nesta integração |
|---|---|---|
| Precipitação bruta C3 | Total climatológico do período, mm; inclui chuva que pode ter origem reciclada | Entrada **única** de precipitação W1, com partição de neve existente |
| Retorno atmosférico C3 | Hipótese potencial de evaporação/retorno ao ar, limitada no solver climático por chuva e PET nativas | Diagnóstico projetado na malha H1, sem crédito ou débito de estoque |
| Deposição atmosférica líquida | Precipitação bruta menos retorno projetado, mm | Diagnóstico; não substitui automaticamente a precipitação de superfície |
| PET W1 | Demanda evaporativa potencial do período, mm × área = litros | Demanda **total**, não reduzida pelo retorno atmosférico |
| ET efetiva W1 | Água efetivamente removida de líquido superficial, solo e reservatório acessíveis, em litros | Perda conservativa única no balanço de superfície; neve não é fonte direta de ET |
| Água armazenável/roteável | Resultado após partição de neve, fusão, infiltração, ET, liberação do solo, capacidades e abertura física das rotas | Estoques/fluxos dos seis compartimentos W1 existentes; não é uma nova água adicionada por C3 |

A identidade global W1 permanece:

```
estoque_final = estoque_inicial + precipitação_bruta
             - ET_efetiva - exportação_oceânica
```

Em cada nó/período, incluem-se também entrada/saída lateral. PET é demanda, não perda automática. Retorno atmosférico não é uma segunda perda nem uma segunda entrada. `local_runoff`, entradas laterais e saídas internas são transferências intermediárias: **não devem ser somados novamente como fontes globais**.

Exemplo de teste controlado: P=100, PET=60 e retorno atmosférico hipotético de 40. W1 recebe 100 e demanda 60, deixando 40. Usar P−retorno e ainda PET total deixaria zero; somar o retorno a P deixaria 80. O teste verifica essas diferenças e a ausência de água quando precipitação e estoques iniciais são zero.

Usar deposição líquida com demanda residual poderia coincidir algebricamente em um caso completamente líquido e acessível, mas não é uma transformação geral dos compartimentos de neve, solo e reservatório. O retorno climático não foi pago previamente por esses estoques. Por isso foi adotado o contrato simples de **P bruta + PET total**, sem alterar o kernel de balanço.

### Projeção e rastreabilidade

O novo `WaterConfigC3R155` mantém `water_version=1` do algoritmo de buckets e introduz o contrato versionado `C3_R1_55_gross_precipitation_total_PET_v1`, com `source_climate_version=3`. O `WaterConfig` antigo continua aceitando somente C1/C2, com default C2. Não se infere a extensão por tentativa, nem se muda o default.

Somente `ClimateConfigV3R1` com reciclagem de 550.000 ppm é aceito pela extensão. C3 original de 55% e R1 de 45% são recusados. Os demais parâmetros climáticos permanecem pinados na configuração/assinatura da autoridade; os experimentos desta fase usam exatamente os snapshots R1-55 adotados, sem recalibração.

O retorno é convertido do ledger C3 nativo para mm por período usando a mesma referência de fluxo/comprimento/tempo da precipitação e interpolado com os mesmos pesos bilineares. A deposição diagnóstica é calculada como P bruta menos esse retorno arredondado. Todos os termos são não negativos; arredondamentos em mm não equivalem à precisão do ledger atmosférico em índices.

W1 conserva sua consulta de temperatura/PET na altura **V4/H1 do mesmo raio**; não troca silenciosamente por T1. Já o limite de PET do retorno atmosférico foi calculado nas colunas nativas C3. A projeção do retorno **não é ET real na coluna H1**, e pode divergir dela. O snapshot guarda essa distinção e o checksum do payload climático completo.

`WaterPlanC3` acrescenta somente checksum e duas matrizes diagnósticas. Os estoques e fluxos conservativos continuam os mesmos; não foi criado um compartimento de “água reciclada”. A recarga verifica o contrato, o checksum, o diagnóstico projetado e P/PET/neve/temperatura contra a fonte C3, além de validar o balanço. Não executa novamente o solver hídrico. Trocar apenas assinaturas/configuração de um W1-C2 não torna seus saldos válidos em C3.

## W2 e P1

W2 continua na versão local 2 e P1 na versão prática 1, com os mesmos kernels de contas, débito, capacidade e admissão física. A extensão altera a proveniência, não a matemática de transferência:

- Autoridades W2/C2 conservam exatamente o descriptor anterior com `c2_signature`.
- Novas autoridades W2/C3 usam `climate_signature`, `climate_version=3` e `climate_forcing_contract`, além dos checksums W1/G1/T1/H1/HR1 existentes.
- A nova configuração W1 e as novas fontes produzem assinaturas distintas. P1 deriva sua assinatura do W2 e exige prova vinculada ao **novo** W1.
- A abertura W2 continua copiando apenas estoques finais uma vez. Nenhum fluxo histórico de precipitação, retorno ou ET é recreditado.
- P1 continua exigindo uma autoridade W2 nova, ainda sem domínios preparados. Não é instalado silenciosamente em autoridades antigas.

O contrato F1 de forçamento futuro permanece **proposta sem autorização de crédito**. Para C3, identifica o contrato climático e explicita que não há crédito de reciclagem e que PET é demanda total. Não foram implementados novos intervalos de chuva em runtime, simulação diária ou repetição de fluxos W1 na exploração. Créditos futuros ainda exigem recibos de intervalo únicos, sequência temporal e estado local de solo/neve já previstos pelo contrato existente.

## Comparação nas cinco seeds

Seeds **42, 0, 7, 2026 e 12345**, raio de **63.710 km**. Cada balanço cobre os 6.144 nós H1, quatro períodos de 90 dias e os mesmos dois anos de aquecimento limitado antes do ano reportado. A condição inicial anterior ao aquecimento é seca, sem estoque inventado.

Geografia, grafo H1, capacidades, política HR1, parâmetros de infiltração/solo/fusão/ET e critérios de rota são iguais no par C2/C3. Nas seeds 42/0/2026 foi reutilizado o manifesto regional C2 congelado, com 30/31/30 regiões. Os três balanços C2 foram reproduzidos por igualdade completa com os arquivos anteriores. Nas seeds 7/12345, sem snapshot W1 anterior, foram preparados 32 nós geográficos por ordem determinística de queda de cabeça H1, sem consultar chuva ou escoamento; C2/C3 usam exatamente as mesmas provas.

As médias seguintes são ponderadas pelas áreas esféricas inteiras H1 sobre terra acima do datum, não por contagem de pontos. Podem diferir ligeiramente das médias E1/T1 por máscara de terra e altura. Isso não indica mudança no clima.

| Seed | P bruta C2 → C3 (mm/ano) | PET total, igual nas duas | ET efetiva C2 → C3 | Escoamento local C2 → C3 |
|---|---:|---:|---:|---:|
| 42 | 157,51 → 198,28 | 691,00 | 127,76 → 168,71 | 19,45 → 19,63 |
| 0 | 148,44 → 185,82 | 730,27 | 119,05 → 160,36 | 21,16 → 17,34 |
| 7 | 154,69 → 188,12 | 697,62 | 121,85 → 160,35 | 20,86 → 15,85 |
| 2026 | 207,83 → 237,70 | 657,93 | 162,51 → 200,20 | 26,03 → 19,47 |
| 12345 | 219,40 → 261,51 | 669,91 | 172,04 → 221,27 | 29,62 → 23,24 |

**Todos os resíduos globais, por período e por nó são zero litro.** Temperaturas e PET são preservadas; a chuva muda conforme a autoridade adotada. O escoamento diminui em quatro seeds porque a redistribuição alimenta mais ET em áreas antes muito secas e reduz parte das concentrações chuvosas. Não se alterou a hidrologia para forçar mais rios.

As saídas laterais macro só ocorrem em provas HR1 bilaterais válidas. Na seed 42, seu total anual passou de aproximadamente 3,236×10¹⁵ para 2,719×10¹⁵ L. Nas demais, o conjunto limitado de provas não resultou em saídas positivas. A exportação oceânica validada foi zero nos cinco pares. Isso **não significa que os planetas não tenham drenagem**: rotas não comprovadas permanecem pendentes e seus volumes ficam em contas não localizadas, sem inventar rios ou barragens físicas.

### Regiões úmidas e áridas

Além das classes de cada clima, o relatório mantém grupos pela classificação **C2 fixa** para comparar as mesmas regiões geográficas. Na seed 42:

| Grupo geográfico fixo C2 | Chuva C2 → C3 | ET C2 → C3 | Escoamento local C2 → C3 |
|---|---:|---:|---:|
| Úmido, P ≥ PET >0 | 678,92 → 651,98 | 439,22 → 423,82 | 187,62 → 181,10 |
| Árido, P/PET <0,2 | 22,66 → 76,94 | 22,57 → 76,66 | ~0,01 → ~0,00 |

Água adicional no interior pode ser quase toda consumida por demanda evaporativa, sem gerar um rio. Sob a classificação úmida do próprio C3, **24,57 / 27,57 / 34,95 / 37,51 / 32,19%** da área úmida das cinco seeds não apresenta escoamento local no ano modelado. Os testes verificam que essa situação é permitida, em vez de exigir um resultado positivo.

### Armazenamento

Os seis estoques são preservados: neve, solo, superfície, depressão, canal e não localizado. Exemplo das profundidades finais médias terrestres C3, mm:

| Seed | Solo | Superfície | Neve |
|---|---:|---:|---:|
| 42 | 8,61 | 0,67 | 36,50 |
| 0 | 7,91 | 0,66 | 28,64 |
| 7 | 6,51 | 0,59 | 39,01 |
| 2026 | 9,73 | 0,80 | 59,99 |
| 12345 | 10,52 | 0,88 | 57,06 |

Os relatórios incluem volumes exatos de abertura/final de todos os compartimentos, balanços por bacia e períodos. Estoque final não deve ser somado ao escoamento como outra fonte. Neve acumulada durante o aquecimento finito não significa geleira real; “depressão” continua uma coluna H1 aproximada, e “não localizado” é contabilidade, não área inundada mapeada.

## Coerência entre hipótese atmosférica e ET superficial

O clima é um forçamento unidirecional; não foi criado um solver acoplado atmosfera/solo. Foram medidos tanto o retorno projetado quanto a lacuna positiva `max(0, retorno_potencial − ET_W1)` em cada nó/período, sem usar essa lacuna para criar ou retirar água.

Médias terrestres anuais C3 em mm, na malha H1:

| Seed | Retorno atmosférico potencial | Deposição atmosférica diagnóstica P−retorno | Lacuna positiva de suporte por ET W1 |
|---|---:|---:|---:|
| 42 | 75,74 | 122,54 | 2,80 |
| 0 | 73,03 | 112,79 | 2,27 |
| 7 | 73,15 | 114,97 | 2,52 |
| 2026 | 88,19 | 149,50 | 2,98 |
| 12345 | 99,56 | 161,95 | 3,16 |

Essa divergência é real e não foi ocultada por ajuste de clima, clipping do diagnóstico ou débito obrigatório. As colunas climáticas, a altura H1, a partição de neve e a água acessível podem diferir. ET total global maior que o retorno não garante suporte em cada nó/estação. Os valores não devem ser comparados como se fossem a mesma quadratura dos relatórios atmosféricos nativos anteriores.

O fechamento em litros W1 é rigoroso **dentro de seu domínio e de seu forçamento**, mas não comprova conservação global do modelo atmosférico nem igualdade entre ET W1 e retorno C3. O contrato operacional é claro: clima fornece P bruta; W1 decide a ET possível; o retorno C3 permanece uma hipótese diagnóstica. Fechar esse feedback exigiria outro acoplamento, que não é necessário nem foi alegado nesta etapa.

## Reconciliação real e persistente C3

A prova anterior não teve sua assinatura trocada. A mesma parcela geográfica foi novamente inspecionada com T1 real, cotas calculadas dos **novos** estoques W1-C3, perfis transversais, interface bilateral e capacidade P1. A busca limitada encontrou passagem natural no nó H1 **2717** sem alterar relevo.

Em SQLite descartável:

1. Criaram-se fontes V4/H1/HR1/T1/G1/C3 e W1 novos, com checksums consistentes.
2. W2 abriu somente os estoques finais desse W1; P1 foi inicializado antes de preparar domínios.
3. Uma alocação L1 debitou **121 L** da conta superficial W1 e normalizou duas contas locais de **61 e 60 L**.
4. O episódio K1 debitou **30 L** da origem: **19 L entregues** ao destino e **11 L retidos** no trecho para umedecimento. Origem: 61 → **31 L**; destino: 60 → **79 L**; trecho: 0 → **11 L**.
5. O total local permaneceu 121 L, com resíduos pai/filhos zero. O snapshot W1 não mudou.
6. Commit, reabertura e repetição idempotente preservaram a revisão e os valores, sem novo crédito. Os testes também fazem rollback e proíbem re-solve/regen de terreno durante a revisita.

É uma passagem interna de aproximadamente **2,772 m**, em um episódio de até 1.440 minutos, com capacidade conservadora já existente. Não prova perenidade, rio inteiro, lago ou vegetação. A reconciliação medida, com as autoridades já carregadas, levou aproximadamente **0,037 s**.

## Desempenho

Benchmark pareado da seed 42: mesmo manifesto HR1, três preparos por versão com ordem alternada. Exclui preparo das autoridades V4/H1/C2/C3, mede memória separadamente e não é RSS. Pode coincidir com regressões; tempos são indicativos.

| Medida | W1-C2 | W1-C3 R1-55 |
|---|---:|---:|
| Mediana de preparo | 1,477 s | 1,714 s |
| Pico de alocações Python | 11.136.953 bytes | 15.097.598 bytes |
| Payload compacto | 2.099.764 bytes | 2.351.076 bytes |
| Recarga e validação | 0,097 s | 1,484 s |
| Consulta mediana de nó em memória | 0,0098 ms | 0,0118 ms |

A recarga C3 é mais cara porque verifica também a projeção climática e os campos de forçamento, impedindo relabel de C2 por troca de cabeçalho. Não é um novo solve. Os caches existentes de dois planos limitam o custo de revisitas; não foi criado cache ilimitado ou worker. A geração continua limitada aos 6.144 nós macro e à evidência local explicitamente pedida, sem milhões de setores.

## Testes e compatibilidade

**818 testes aprovados em 940,79 s (15 min 40 s)** na regressão selecionada: os 801 anteriores e 17 novos. Abrange World Genesis, C1/C2/C3/E1, geologia, hidrologia/balanços, persistência, mapa, exploração/viagens, fronteiras/rotas, reset e simulação temporal. Apenas o aviso preexistente de depreciação Starlette/httpx. A suíte completa de todo backend/frontend não foi executada.

Os 17 testes da extensão foram repetidos ao final e passaram em 20,25 s, incluindo a lacuna de suporte de ET e a ausência de escoamento obrigatório em região úmida. Compilação, `git diff --check`, não negatividade dos estoques dos dez balanços, resíduos dos cinco pares e reabertura da prova C3 também passaram.

Os testes novos cobrem contrato explícito/versões inválidas, orçamento sem dupla subtração/crédito, ausência de água com fonte seca, forçamento C3 real, ET limitada à PET/estoque, diagnóstico de lacuna, região úmida sem escoamento, replay/recarga sem solver, corrupção, tentativa de relabel C2, rejeição de C3 não adotado, opt-in, coexistência C2/C3, W2/P1 positivos, idempotência, duplicação de cota/episódio, rollback, revisita e proposta futura sem crédito.

Os formatos e defaults C2 não recebem campos C3. A configuração antiga `WaterConfig(source_climate_version=3)` continua inválida; é necessário `WaterConfigC3R155()`. O namespace W1 permanece porque seu algoritmo é o mesmo, mas o contrato v1 extra e a assinatura tornam a nova autoridade independente. W2 preserva seu descriptor C2 anterior; C3 usa chaves próprias, e P1 continua derivando a fonte W2. Nenhuma migração foi criada ou aplicada.

## Arquivos e reprodução

- `backend/app/game/world/genesis/water/config.py`: perfil de forçamento C3-R1-55 v1, parser e admissão de fonte.
- `.../water/c3_forcing.py`: projeção/validação dos diagnósticos e snapshot C3, sem alterar clima.
- `.../water/plan.py`, `service.py`, `query.py`: opt-in, recarga pinada e diagnósticos read-only.
- `.../water_reconciliation/sources.py`, `service.py`: fontes W2 compatíveis com o novo contrato, preservando C2.
- `.../water_reconciliation/practical/future.py`: proveniência explícita da proposta C3 futura, ainda sem crédito.
- `backend/scripts/validate_water_c3.py`: cinco seeds, comparação com a mesma evidência e prova persistida descartável.
- `backend/scripts/benchmark_water_c3.py`: benchmark pareado.
- `backend/app/tests/test_genesis_water_c3.py`: 17 casos novos.
- Este documento e `artifacts/water-c3-compatibility/`.

Reproduzir a partir de `backend`:

```powershell
.venv/Scripts/python.exe -m scripts.validate_water_c3
.venv/Scripts/python.exe -m scripts.benchmark_water_c3
.venv/Scripts/python.exe -m pytest app/tests/test_genesis_water_c3.py -q
```

O validador lê os snapshots climáticos R1-55 já aprovados; não os recalibra. Os bancos da demonstração são temporários. Dados principais:

- [Comparação das cinco seeds](../artifacts/water-c3-compatibility/suite.json).
- [Reconciliação persistida com C3](../artifacts/water-c3-compatibility/seed-42/persistent-proof.json) e [prova natural reinspecionada](../artifacts/water-c3-compatibility/seed-42/natural-proof.json).
- [Desempenho](../artifacts/water-c3-compatibility/performance.json).
- [Escoamento local C2](../artifacts/water-c3-compatibility/seed-42/C2/annual_runoff.png) e [C3](../artifacts/water-c3-compatibility/seed-42/C3/annual_runoff.png), na mesma escala técnica.

Os mapas são diagnósticos offline, não Atlas nem novas localizações conhecidas do jogador. Não representam água permanente ou ocupação exata dos estoques.

## Recomendação de ativação

A infraestrutura está operacional para preparar **novas autoridades experimentais C3 R1-55 → W1 → W2 → P1**, com forçamento explícito, conservação dos estoques em litros e proveniência persistida. Podemos avançar aos contratos de vegetação sem reabrir a calibração climática, consumindo disponibilidade/solo/temperatura com seus estados de evidência e limites espaciais.

A ativação em campanhas reais permanece desligada. Para futuros mundos, o bootstrap deverá escolher explicitamente `ClimateConfigV3R1(land_recycling_ppm=550_000)` e `WaterConfigC3R155()`, preparar a evidência HR1 desejada e criar W2/P1 antes de abrir domínios locais. Campanhas C2 continuam lendo suas autoridades antigas; não existe migração por troca de assinatura.

Não se deve promover disponibilidade macro a rio, lago, solo saturado local ou floresta estabelecida. O clima e os buckets continuam aproximados e unidirecionais; crédito climático temporal F1 permanece não implementado. Essas limitações estão explícitas e não foram contornadas inventando água ou objetos físicos.
