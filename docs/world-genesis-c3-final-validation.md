# Fase 0.9.1 — ajuste final e validação do C3

## Recomendação

**Recomendo o perfil C3 R1 com reciclagem limitada a 55% para os futuros mundos**, em vez do C3 original de 45%. A configuração concreta é:

```python
from app.game.world.genesis.climate.v3 import ClimateConfigV3R1
config = ClimateConfigV3R1(land_recycling_ppm=550_000)
```

`climate_version=3`, `condensation_profile="fraction_hazard_r1"` e os parâmetros completos integram a assinatura. O C3 original conserva sua classe, seus defaults, sua serialização e seus resultados. **A recomendação não foi ativada em campanhas reais**, nem libera W1/W2/P1 com outra autoridade climática.

A melhora é concreta, mas moderada: o perfil recupera parte da chuva costeira perdida, aumenta área úmida e habitats florestais elegíveis em relação ao C3 atual nas cinco seeds, e amplia algumas regiões favoráveis na malha. Não faz florestas virarem o principal dominante, não recupera toda a área úmida C2 em todas as seeds e não torna o planeta uniformemente verde. O principal E1 sozinho continua inadequado como medida de variedade física ou cobertura vegetal.

## 1. O que explica os rótulos desérticos de E1

Foram produzidas matrizes ponderadas cruzando simultaneamente **classe P/PET × faixa de precipitação anual × faixa de temperatura × ID principal**. Cada linha contém também número de sondagens e fração da área terrestre. Os 20 CSVs completos estão nas cinco pastas de `artifacts/climate-c3-final/`, um por seed e cenário: `C2-matrix.csv`, `C3-45-matrix.csv`, `R1-45-matrix.csv` e `R1-55-matrix.csv`. As matrizes também constam dos JSONs.

Faixas de chuva: <100, 100–250, 250–500, 500–1.000, 1.000–2.000 e ≥2.000 mm/ano. Temperatura média: <−10, −10–0, 0–10, 10–20 e ≥20 °C. Índices P/PET: hiperárido <0,05, árido 0,05–0,2, semiárido 0,2–0,5, déficit moderado 0,5–1 e úmido ≥1. PET zero fica separado, sem assumir seca.

### Cruzamento condensado: seed 42, C3 atual de 45%

Valores em **pontos percentuais da área terrestre**, não porcentagens internas de cada linha. A matriz completa acrescenta as faixas de chuva e temperatura acima.

| Classe física | Desertos não polares | Deserto polar | Estepe | Outros principais |
|---|---:|---:|---:|---:|
| Hiperárida | 25,70 | 3,41 | 0,00 | 0,00 |
| Árida | 26,18 | 3,71 | 1,47 | 0,00 |
| Semiárida | 3,57 | 4,23 | 6,88 | 1,84 |
| Déficit moderado | 0,00 | 3,02 | 0,81 | 6,88 |
| Úmida por P/PET | 0,00 | 1,88 | 0,00 | 7,96 |
| PET zero | 0,00 | 1,76 | 0,00 | 0,68 |

Os **82,63%** de principais deserto/estepe se decompõem em **60,48 pontos** com P/PET <0,2, **14,68** semiáridos, **3,83** com déficit moderado, **1,88** úmidos e **1,76** com PET zero. Aproximadamente 73% desses rótulos estão, portanto, na classe física árida/hiperárida; os demais não podem ser chamados de aridez forte apenas pelo nome.

Nas outras seeds, a parte árida/hiperárida dentro dos principais secos do C3 atual representa **62,74 / 65,02 / 49,31 / 48,44 pontos percentuais** da terra (seeds 0/7/2026/12345). O restante é principalmente estepe, deserto frio no intervalo semiárido e deserto polar.

### Coerência e sobreposição

- Não apareceu principal inelegível, deserto não polar com P/PET >0,45 ou principal deserto/estepe em ponto quente e úmido (média ≥5 °C e P/PET ≥1), nas sondagens dos quatro cenários e cinco seeds. Isso é uma verificação sobre as amostras, não uma prova de todos os pontos possíveis.
- O catálogo permite deserto polar por frio e precipitação absoluta baixa. PET mínima pode produzir P/PET alto sem tornar o lugar favorável a árvores. A classe polar não exige aridez por P/PET; não deve ser somada à aridez física sem essa ressalva.
- Estepe aceita P/PET até 0,65. Deserto frio aceita até 0,45. Encontrá-los em parte dos índices semiáridos/moderados não viola seus intervalos; não significa que toda essa área ofereça a mesma paisagem de um deserto quente.
- No C3 atual, **10,27–13,59%** da área terrestre tem principal seco e algum perfil florestal elegível. Na seed 42, são **10,82%**. Existe sobreposição real de intervalos; ela não comprova floresta estabelecida.

O mecanismo do principal usa o **menor score normalizado** entre critérios e desempate estável por ID. Perfis com intervalos mais estreitos podem perder para outros elegíveis. Scores de perfis diferentes não são probabilidades calibradas de cobertura, e o principal não exclui os demais habitats. A confirmação de vegetação é um contrato posterior.

Exemplo real no C3 atual, ponto `(32, -15, -25)`: **364 mm/ano**, **691 mm de PET**, P/PET **0,527**, média **7,01 °C**. Estepe recebe score **695.408**, campo de altitude **379.090**, tundra arbustiva **304.629**, pastagem natural **253.904** e pradaria **227.971**. Perfis florestais também podem ser elegíveis, mas não vencem a seleção. O principal estepe é compatível com esses dados; promovê-lo artificialmente a floresta para mudar a cor não seria correção física.

**E1 e EV-ECO não foram alterados.** Os exemplos guardam os candidatos e scores reais, sem bônus florestal. A variedade deve ser analisada com clima, secundários, feições e elegibilidade sobreposta, e não apenas com a cor do vencedor.

## 2. Ajuste físico limitado

O C3 original reaproveita a função de condensação C2, que retorna uma **fração**, como se esse valor já fosse uma **profundidade óptica**. Aplicar `1-exp(-f)` reduz a fração efetiva na exposição de referência: uma referência de 35% vira aproximadamente 29,53%; 15% vira 13,93%. Isso é uma escolha aproximada do C3 anterior, preservada, mas explica parte da perda costeira mesmo sem mudar fontes oceânicas.

O perfil R1 usa a conversão correta entre essas interpretações:

```
tau_base = -ln(1 - fracao_latitudinal_C2)
tau_orografico_por_km = -ln(1 - coeficiente_orografico)
tau = tau_base * distancia / comprimento_condensacao
    + tau_orografico_por_km * subida_m / 1000
fracao_condensada = 1 - exp(-tau)
```

Assim, uma perda de referência de 35% corresponde a 35% na distância de referência. A resposta continua compondo profundidades ópticas por percurso e subida, em vez de aplicar taxas por número de células. A contribuição orográfica é multiplicativa sobre vapor remanescente, não uma tentativa de reproduzir toda a soma linear C2 em qualquer relevo.

A conversão usa uma série inteira fixa de 32 termos, com precisão interna de 10¹² e cache limitado a 4.096 valores. Os testes comparam `-ln(1-f)` em todo o domínio calibrado até 0,85 e verificam composição de subpercursos. Não há `libm` autoritativo, novo campo aleatório ou sistema atmosférico.

Foram testadas apenas duas alternativas novas:

| Configuração | Diferença em relação ao C3 atual |
|---|---|
| C3-45 | Controle original, preservado |
| R1-45 | Conversão fração → profundidade óptica; reciclagem continua 45% |
| **R1-55** | Mesmo ajuste, com teto de reciclagem de 55% para sustentar parte do transporte continental diante da condensação maior |

Não foi alterado o fator de conversão global de chuva, o comprimento de referência do fluxo, a fonte oceânica, os ventos, o relevo, temperatura ou PET. O retorno continua `min(chuva_local * teto, PET_convertida)`, sem estoque inicial, vegetação, rios ou água subterrânea presumidos. Com teto de 55%, pelo menos 45% de cada condensação não retorna imediatamente nessa regra.

A contabilização permanece a do C3: identidades locais exatas em índices de umidade e condição de contorno oceânica prescrita. **Não se declara conservação atmosférica global em litros.** O grafo de médias não resolve volumes de ar; isso continua sendo uma limitação explícita. Não se reutilizou saldo hídrico C2 para criar vapor.

Mais chuva bruta não significa mais água nova. Na quadratura nativa dos nós não oceânicos da seed 42, incluindo depressões desconectadas, o C3-45 tinha aproximadamente **189,93 mm brutos, 71,60 mm reciclados e 118,33 mm de deposição líquida atmosférica**; R1-55 apresenta **208,82 / 94,55 / 114,28 mm**, respectivamente. O aumento de recorrência da precipitação não comprova aumento da disponibilidade superficial líquida global. Esses números não são estoques W1 e usam um domínio diferente dos centros terrestres T1 das tabelas. A futura integração hídrica terá de conciliar retorno potencial e evaporação efetivamente disponível, em vez de contar o retorno como fonte adicional independente.

## 3. Comparação quantitativa nas cinco seeds

Raio de **63.710 km**, mesma geografia V4/T1/J1/JR1, os mesmos **6.144 centros por seed/cenário** e pesos de ângulo sólido esférico. C2 e C3 atuais usam suas amostras congeladas, verificadas por assinatura/replay; os dois candidatos somam **61.440 sondagens globais novas**. Temperatura e PET foram verificadas por igualdade ponto a ponto com C2. Cada candidato também tem relatórios por costa/interior, latitude, altitude, relevo e período.

### Chuva e área úmida

Chuva média terrestre em mm/ano; porcentagens referidas à área terrestre.

| Seed | Chuva C2 / C3-45 / R1-45 / R1-55 | Área úmida C2 / C3-45 / R1-45 / R1-55 |
|---|---:|---:|
| 42 | 157,51 / 179,42 / 188,91 / **198,28** | 10,18 / 9,84 / 10,28 / **10,66%** |
| 0 | 148,30 / 168,02 / 176,82 / **185,63** | 10,71 / 9,55 / 10,14 / **10,47%** |
| 7 | 154,44 / 169,59 / 179,29 / **187,84** | 9,88 / 8,93 / 9,88 / **10,10%** |
| 2026 | 207,83 / 215,46 / 227,90 / **237,69** | 14,52 / 12,52 / 13,36 / **13,90%** |
| 12345 | 219,40 / 237,29 / 250,46 / **261,51** | 15,20 / 12,36 / 13,57 / **14,16%** |

R1-55 supera o C3 atual em área úmida nas cinco seeds, mas continua abaixo de C2 nas seeds 0, 2026 e 12345. Não foi selecionado um percentual-alvo para esconder isso.

### Hiperáridez e potencial florestal

| Seed | Hiperárida C2 / C3-45 / R1-45 / R1-55 | Algum perfil florestal elegível C2 / C3-45 / R1-45 / R1-55 |
|---|---:|---:|
| 42 | 53,29 / 29,11 / 29,30 / **26,92%** | 17,33 / 24,22 / 24,94 / **26,29%** |
| 0 | 57,22 / 35,51 / 35,80 / **32,49%** | 16,74 / 22,70 / 23,60 / **25,28%** |
| 7 | 60,51 / 40,87 / 41,02 / **39,59%** | 16,73 / 24,41 / 24,77 / **26,70%** |
| 2026 | 42,39 / 19,80 / 20,34 / **18,02%** | 21,96 / 29,20 / 30,04 / **31,85%** |
| 12345 | 42,77 / 14,59 / 14,85 / **12,03%** | 22,13 / 29,54 / 30,41 / **32,37%** |

R1-45 recupera parte da chuva costeira, mas **aumenta ligeiramente a hiperáridez** em todas as seeds: a condensação maior retira mais vapor antes do interior. R1-55 compensa essa perda com retorno limitado pela própria chuva/PET e reduz a hiperáridez abaixo do C3 atual nas cinco seeds. Essa combinação, além da distribuição espacial, fundamenta a escolha; não apenas sua média de chuva mais alta.

Somando árido + hiperárido, R1-55 ainda possui **56,90 / 59,21 / 62,73 / 45,65 / 44,17%** de área terrestre com P/PET <0,2. Os desertos continentais não desapareceram.

### Principais do E1

| Seed | Principal deserto/estepe C3-45 → R1-55 | Principal florestal C2 / C3-45 / R1-45 / R1-55 |
|---|---:|---:|
| 42 | 82,63 → **81,08%** | 2,23 / 1,44 / 1,66 / **1,72%** |
| 0 | 83,67 → **82,26%** | 2,32 / 1,44 / 1,82 / **1,86%** |
| 7 | 84,33 → **83,21%** | 2,40 / 1,74 / 1,82 / **1,81%** |
| 2026 | 78,18 → **76,22%** | 3,49 / 1,49 / 1,59 / **1,94%** |
| 12345 | 76,66 → **74,30%** | 2,23 / 1,23 / 1,55 / **1,63%** |

O ganho de principal florestal é pequeno e não recupera C2. Na seed 7, R1-55 tem um pouco menos de principal florestal que R1-45 apesar de mais potencial elegível. Essa divergência é compatível com a competição de scores e sobreposição de intervalos; não foi corrigida com bônus artificiais. A distribuição de **todos os IDs principais**, não apenas florestas/desertos, está em `groups.*.primary_area_fractions` de cada cenário.

## 4. Costa, interior e sazonalidade

Seed 42, médias terrestres ponderadas de precipitação, mm/ano:

| Distância oceânica macro | C2 | C3-45 | R1-45 | R1-55 |
|---|---:|---:|---:|---:|
| 0–1.000 km | 911,00 | 779,05 | 848,73 | 849,09 |
| 1.000–3.000 km | 631,11 | 580,79 | 619,46 | 624,43 |
| 3.000–10.000 km | 191,41 | 218,26 | 229,62 | 240,39 |
| Mais de 10.000 km | 11,22 | 44,56 | 45,12 | 53,95 |

O ajuste óptico recupera a costa sem alterar a fonte oceânica. O retorno adicional beneficia principalmente o interior. Nas outras seeds, o interior além de 10.000 km fica em aproximadamente **50 / 38 / 46 / 78 mm/ano** no R1-55: permanece árido e distinto entre planetas. O bin costeiro tem poucas sondagens e a distância é um proxy macro, não uma praia localizada com precisão métrica.

As médias oceânicas R1-55 nas cinco seeds são **527,81 / 520,96 / 559,55 / 546,68 / 533,62 mm/ano**, ainda inferiores às respectivas C2. A diferença não foi escondida com multiplicador global. R1-45 e R1-55 têm as mesmas regras/fontes oceânicas; diferenças em sondagens interpoladas próximas à costa podem refletir os vértices terrestres vizinhos.

Na seed 42, os quatro totais médios terrestres por período são:

- C3-45: **45,02 / 45,63 / 45,02 / 43,75 mm**.
- R1-45: **47,37 / 48,09 / 47,37 / 46,08 mm**.
- R1-55: **49,60 / 50,55 / 49,60 / 48,53 mm**.

São totais dos períodos de 90 dias, não equivalentes anuais. Temperaturas e PET sazonais permanecem idênticas. Os relatórios incluem seis zonas latitudinais, quatro classes de altitude, contexto montanhoso e as quatro estações. O relevo e o sinal de subida orográfica não foram removidos; a profundidade de ascensão continua aditiva e o teste de composição preserva a causalidade do percurso.

## 5. Extensão favorável e mosaicos

Para medir extensão além das médias, foram usados dois critérios diagnósticos explícitos:

1. **Favorável florestal moderado**: terra, P/PET ≥0,5, média ≥0 °C e algum perfil do grupo florestal elegível.
2. **Quente e úmido**: terra, P/PET ≥1 e média ≥5 °C.

Esses critérios não alteram EV-ECO e não definem toda floresta possível: excluem, por exemplo, parte das formações boreais mais frias. O primeiro permite comparar uma faixa de exploração moderadamente favorável, não apenas uma categoria úmida rara.

### Área e componentes amostrados

| Seed | Área favorável C3-45 → R1-55 | Maior componente favorável na malha, C3-45 → R1-55 (milhões km² estimados) |
|---|---:|---:|
| 42 | 10,35 → **11,37%** | 140,53 → **164,36** |
| 0 | 10,29 → **11,14%** | 302,88 → **345,77** |
| 7 | 10,42 → **11,27%** | 210,38 → **210,92** |
| 2026 | 11,89 → **13,16%** | 177,55 → **338,29** |
| 12345 | 15,30 → **16,82%** | 235,62 → **364,82** |

Os componentes usam vizinhança pelas quatro arestas e atravessam as emendas reais do cube-sphere. A área é a soma dos pesos esféricos das células cujos **centros** satisfazem o critério. **Não são polígonos exatos de floresta nem prova de continuidade em cada metro.** O número de componentes pode aumentar ou diminuir naturalmente; não há quota nem ID geográfico persistente criado por essa análise.

Na seed 42, o maior componente amostrado R1-55 tem extensão geodésica inferior estimada de **38.056 km**, contra 18.839 km do maior componente C3-45. Isso não significa duplicação comprovada de um corredor real: são componentes selecionados por área, e sondagens internas encontram lacunas. Na seed 12345, o maior componente **quente e úmido** da malha cresce de aproximadamente **53,3 para 127,9 milhões de km² estimados**; também está sujeito à mesma limitação de amostragem.

### Corredor fixo e resolução interna

Foi escolhido após a varredura um corredor da maior componente R1-55 da seed 42 e reconsultadas **as mesmas 246 posições**, com espaçamento de até 250 km, nos quatro cenários. Esse testemunho não entra nas estimativas globais.

| Cenário | Sondagens fora do critério favorável | Maior sequência de sondagens favoráveis, extensão acumulada |
|---|---:|---:|
| C2 | 34 | 22.429,5 km |
| C3-45 | 19 | 22.429,5 km |
| R1-45 | 16 | 22.429,5 km |
| R1-55 | 16 | 22.429,5 km |

R1 reduz lacunas amostradas nesse corredor, mas **não aumenta sua maior sequência favorável**. Não se apresenta o aumento de componentes macro como prova de melhora em todo subtrecho. A sequência mede distâncias entre sondagens positivas, não ausência de microbarreiras ou mudanças em todos os pontos intermediários.

### Mosaico de 4.096 km

Na mesma âncora da seed 42, foram comparadas janelas de 4.096 × 4.096 km com 16 × 16 sondagens, respeitando o limite E1 de 256 pontos por mosaico:

| Cenário | Principais distintos | IDs elegíveis | Arestas amostradas com transição de principal |
|---|---:|---:|---:|
| C2 | 13 | 21 | 118 |
| C3-45 | 7 | 20 | 67 |
| R1-45 | 9 | 20 | 86 |
| R1-55 | 9 | 20 | 77 |

R1 restaura parte da diversidade desse mosaico, mas não supera C2 em todos os indicadores. Também foram repetidas, para cada candidato e seed, duas janelas fixas de 1.024 km nas primeiras âncoras terrestres J1: **20 pares de janelas/5.760 sondagens regionais**. Seus principais, secundários e transições constam nos arquivos `R1-*/regional-*`. Não foram escolhidas apenas áreas onde o novo clima ganha.

## 6. Persistência, desempenho e compatibilidade

O perfil R1 acrescenta uma chave de configuração explícita, reconhecida pelo dispatch climático. Não adiciona campos à configuração legada C3; seus dumps e hashes permanecem intactos. C2 e C3 antigos foram reproduzidos, e cada plano R1 foi serializado/recarregado com validação de ledger, PET, perdas e assinatura. E1 continua usando o perfil de origem C3, fixado à assinatura/checksum específica do plano R1.

A prova R1-55 em SQLite temporário materializou **dois pontos** — um seco e outro quente/úmido — e os reabriu sem alteração: **106 incompatíveis, 78 pendentes, 15 elegíveis e uma classificação física confirmada** nas 200 avaliações naturais. A confirmação não é vegetação estabelecida. Não foram criadas espécies, jazidas, rios ou lagos.

W1 continua limitado a C1/C2; W2/P1 continuam vinculados às suas fontes C2. O novo perfil não contorna esses bloqueios. Nenhum saldo hídrico ou save real foi convertido, e não houve migração de banco.

Benchmark da seed 42, três preparos completos por configuração, fontes V4/H1 preexistentes. Inclui reamostragem V4 e solução climática; memória medida separadamente, com geometria quente e cache de logaritmos frio. Não é RSS. Execução coincidiu com validações, portanto não se deve concluir que R1 é mais rápido a partir destas medianas.

| Medida | C3-45 | R1-45 | R1-55 |
|---|---:|---:|---:|
| Mediana de preparo completo | 3,67 s | 3,09 s | 3,26 s |
| Pico de alocações Python | 20.749.324 bytes | 20.924.896 bytes | 20.943.588 bytes |
| Payload compacto | 2.301.599 bytes | 2.300.013 bytes | 2.307.079 bytes |
| Recarga e validação | 0,109 s | 0,114 s | 0,120 s |
| Consulta climática mediana | 0,173 ms | 0,173 ms | 0,176 ms |

O aumento de memória é inferior a 1%; consultas mantêm a ordem de custo anterior. O cache novo tem teto de 4.096 valores. Não há novo worker, simulação contínua, solo global ou geração de setores distantes. Níveis climáticos continuam configurações autoritativas, não LODs intercambiáveis. As limitações de resolução e conservação global já documentadas no C3 continuam válidas.

## 7. Testes, artefatos e reprodução

**801 testes aprovados em 944,75 s (15 min 44 s)** na regressão selecionada, incluindo os 783 anteriores e 18 novos. Abrange World Genesis, C1/C2/C3/E1, geologia, hidrologia/balanços, persistência, mapa, exploração/viagens, fronteiras/rotas, reset e simulação temporal. Apenas o aviso preexistente de depreciação Starlette/httpx. A suíte completa de todo backend/frontend não foi executada.

Novos testes verificam precisão e domínio da conversão óptica, composição de percursos, preservação da semântica legada, dispatch explícito, replay exato do C3, máscaras/componentes em emenda real, pesos sem duplicação, matriz de aridez versus rótulos polares, ausência de água sem fonte/PET, recarga e coexistência de perfis, rejeição hídrica e revisita com geração proibida. As múltiplas construções frias do benchmark também comparam resultados por igualdade integral.

Os 18 testes novos foram repetidos ao final e passaram em 6,30 s. Compilação Python, `git diff --check`, normalização das 20 matrizes, igualdade das autoridades geográficas e prova R1-55 reaberta também foram verificados.

Arquivos modificados/criados nesta etapa:

- `backend/app/game/world/genesis/climate/v3.py`: configuração R1 e conversão fracionária óptica; ramo C3 anterior preservado.
- `backend/app/game/world/genesis/climate/dispatch.py`: seleção explícita do perfil persistido.
- `backend/scripts/recalibrate_climate.py`: rótulos configuráveis na comparação regional offline, sem alterar os defaults anteriores.
- `backend/scripts/finalize_climate_c3.py`: matrizes, dois candidatos, componentes amostrados, percursos, mosaicos, figuras e prova descartável.
- `backend/scripts/benchmark_climate_c3_final.py`: preparo, memória e consultas comparáveis.
- `backend/app/tests/test_genesis_climate_c3_final.py`: 18 novos testes.
- Este documento e `artifacts/climate-c3-final/`.

Reprodução, a partir de `backend`:

```powershell
.venv/Scripts/python.exe -m scripts.finalize_climate_c3
.venv/Scripts/python.exe -m scripts.benchmark_climate_c3_final
.venv/Scripts/python.exe -m pytest app/tests/test_genesis_climate_c3_final.py -q
```

O script reutiliza os controles congelados de `climate-audit-after-e1` e `climate-recalibration-0.9.1`, verificando as autoridades. Amostras de candidatos já disponíveis podem ser reutilizadas somente após igualdade do replay do plano; tempo de consulta fica `null` nesses casos para não apresentar tempo de leitura como benchmark de geração. A prova persistida usa banco temporário. As matrizes são calculadas sobre as mesmas coordenadas em todos os cenários.

Imagens e dados principais:

- [Quatro cenários: extensão favorável, seed 42](../artifacts/climate-c3-final/seed-42/spatial-comparison.png).
- [C3 atual versus R1-55: chuva, temperatura, P/PET e principal](../artifacts/climate-c3-final/seed-42/R1-55-comparison.png).
- [Mosaico C3 atual de 4.096 km](../artifacts/climate-c3-final/seed-42/C3-45-mosaic.png) e [mesma janela R1-55](../artifacts/climate-c3-final/seed-42/R1-55-mosaic.png).
- [Matriz completa C3 atual, seed 42](../artifacts/climate-c3-final/seed-42/C3-45-matrix.csv).
- [Comparação consolidada](../artifacts/climate-c3-final/suite.json), [desempenho](../artifacts/climate-c3-final/performance.json) e [prova persistida](../artifacts/climate-c3-final/seed-42/persistent-proof.json).

As cinco seeds têm mapas e matrizes completos. São ferramentas técnicas offline; não alteram conhecimento do personagem ou mapa público e não constituem Atlas.

## Conclusão

O C3 atual não é a melhor opção entre as configurações avaliadas. **R1-55 apresenta melhora justificável de normalização, costa, área úmida, hiperáridez e extensão favorável amostrada**, preservando causalidade e desertos gigantescos. R1-45 isola a correção óptica, mas aumenta um pouco a hiperáridez; o retorno adicional de R1-55 compensa essa tendência sem fonte terrestre independente de chuva.

A recomendação não significa que o problema visual dos principais E1 esteja resolvido: 74–83% ainda recebem rótulo deserto/estepe, embora só 44–63% estejam fisicamente em P/PET <0,2. Não há fundamento para inflar florestas no ranking. A futura experiência de exploração deve consumir os mosaicos e habitats sobrepostos, mantendo potencial distinto de vegetação real.

O perfil está pronto para revisão/aprovação como clima dos futuros mundos. A ativação real e a compatibilidade hídrica permanecem desligadas. Não foram implementados flora, fauna, civilizações, Atlas ou novos sistemas atmosféricos.
