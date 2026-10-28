# Auditoria climática após E1

## Parecer

**Preservar C2 e E1. Não foi encontrado erro de unidade, agregação anual, conversão P/PET ou truncamento do solver que justifique uma nova versão autoritativa.** A aridez é forte e sistemática no modelo, mas a estimativa anterior a exagerava por amostragem esparsa. A malha refinada contém áreas úmidas e potencial florestal extenso; não há um bloqueio geral de E1 contra florestas quando as condições climáticas são adequadas.

Podemos iniciar a integração **controlada** de flora e fauna sobre os contratos atuais, usando todos os habitats elegíveis e suas sobreposições, não somente o rótulo principal. Isso não libera autogeração em saves reais nem confirma vegetação, água permanente ou habitats ainda pendentes. Não há justificativa técnica nesta auditoria para aumentar chuva apenas para tornar o mapa verde.

O parecer é de coerência interna para o RPG, não validação científica de um planeta de 63.710 km de raio. O C2 é uma parametrização estacionária com viés seco, sem reciclagem terrestre ou balanço atmosférico conservativo. Não é possível provar com esse modelo que a atmosfera de um planeta real teria exatamente estas chuvas. Essa limitação não deve ser confundida com um erro de conversão.

## Escopo e procedimento

Foram auditados `climate/{plan,physics,v2,query,geometry,calibration,dispatch,service}.py`, o adaptador/classificador/configuração E1 e os contratos reais de consulta T1. Nenhum desses arquivos autoritativos foi alterado nesta auditoria. Os arquivos novos são uma ferramenta offline, seus testes, este relatório e os artefatos. Não foram abertos saves reais nem adicionados serviços, migrações, flora, fauna, rios, lagos ou Atlas.

Seeds: **42, 0, 7, 2026 e 12345**, todas com raio de **63.710.000 m**. Foram usados os mesmos planos congelados/procedimentos de carga da entrega E1. As cinco assinaturas E1 coincidem com as da Fase 0.9. Para cada seed:

- Malha anterior reexecutada: 384 centros, 8 × 8 por face.
- Malha refinada: 6.144 centros, 32 × 32 por face, **16 vezes mais sondagens**.
- Peso de cada centro: ângulo sólido exato de sua célula cube-sphere, reaproveitando `cell_solid_angle`. Os pesos somam 4π; não se usa área plana do cubo.
- Auditoria adicional dos 6.146 vértices nativos do C2, com a quadratura esférica preexistente, para analisar solver, fontes, exposição aos ventos e sensibilidade dos parâmetros.

São **32.640 consultas ambientais reais**, incluindo T1/JR1, nas duas malhas das cinco seeds. Em cada consulta foi verificada a correspondência exata de precipitação, temperatura, quatro períodos, PET e P/PET entre C2 e E1. **Zero divergências.** Terra é determinada pela altura T1 relativa ao datum configurado; referência oceânica e áreas abaixo do datum desconectadas são separadas. A máscara H1 não é prova de um habitat aquático local.

Área estimada por centro de célula continua sendo quadratura, não um levantamento exato de costas. O nível 5 é a resolução climática do plano, não uma precisão costeira de metros. Os resultados refinados melhoram o diagnóstico, mas não demonstram convergência de todos os polígonos ambientais possíveis.

## Unidades e agregação

| Etapa | Fórmula/contrato verificado | Resultado |
|---|---|---|
| Fonte oceânica | Índice de vapor entre zero e 1.000.000; depende da temperatura e máscara oceânica | É disponibilidade prescrita, não evaporação medida em mm |
| Chuva de um período | `rain_index * rain_scale_milli_mm_per_day * year_days // (1_000_000 * 4000)` | Converte índice × milímetros/dia × um quarto do ano; milésimos removidos corretamente |
| Chuva anual | Soma dos quatro `precipitation_mm` | Não é média nem soma multiplicada por quatro |
| Temperatura | Centésimos de °C no C2; divisão por 100 no E1 | Sem confusão °C/centésimos |
| Relevo | T1 fornece mm; altura passada ao C2 é `height_mm // 1000`, em metros | Gradiente de 6 °C/km, não 6 °C/m |
| PET de um período | `pet_milli_mm_day(...) * year_days // 4000` | Demanda potencial; anual também é soma de quatro períodos |
| P/PET | `annual_rain * 1_000_000 // annual_pet`, depois divisão por 1.000.000 no E1 | Correspondência exata com `clima.indice_aridez` do catálogo |
| Déficit | `(PET-P)/PET`, limitado inferiormente em zero | Campo diferente, não consumido como P/PET |
| PET zero | P/PET desconhecido, estado energético limitado | Não vira P/PET zero ou deserto automaticamente |
| Escoamento | `runoff_mm`, vazão e água permanente permanecem indeterminados | Não participam da decisão de aridez |

O preset usa ano de 360 dias e quatro períodos de 90 dias. Os períodos 0 e 2 usam a mesma declinação equinocial e podem ser iguais; isso é simetria da climatologia prescrita, não duplicação acidental no somatório. Não há tempo diário ou atraso térmico orbital explícito.

As duas etapas de truncamento de chuva — construção e interpolação — podem perder menos de 8 mm anuais em relação aos respectivos cálculos contínuos, não centenas de milímetros. Na PET, o truncamento diário e dos quatro períodos tem ordem de poucos milímetros anuais. Isso pode importar em regimes quase sem energia, mas não explica a aridez geral. O teste oceânico controlado calcula a chuva a partir do índice de fonte e da condensação, verificando numericamente o divisor 4000 e a soma anual.

## Resultados ponderados por área

Todas as porcentagens desta seção usam **área terrestre amostrada como denominador**, não número de pontos nem área total do planeta. Classes de índice são diagnósticas; não geram biomas. “Úmido” significa P/PET ≥ 1, com PET definida; não significa necessariamente água líquida disponível ou floresta.

| Seed | Pontos terrestres na malha refinada | Chuva anual média (mm) | Chuva P50 / P95 (mm) | Temperatura média (°C) | PET média (mm/ano) | Principal deserto/estepe | P/PET ≥ 1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 42 | 2.753 | 157,51 | 20 / 906 | 4,07 | 691,14 | 82,35% | 10,18% |
| 0 | 2.475 | 148,30 | 18 / 835 | 4,79 | 730,23 | 83,70% | 10,71% |
| 7 | 3.048 | 154,44 | 14 / 873 | 3,86 | 697,38 | 84,11% | 9,88% |
| 2026 | 1.854 | 207,83 | 41 / 1.070 | 2,85 | 658,05 | 77,14% | 14,52% |
| 12345 | 2.126 | 219,40 | 42 / 1.156 | 4,20 | 670,12 | 76,46% | 15,20% |

A faixa observada anteriormente de 125–195 mm veio de poucos pontos terrestres sem ponderação. A nova faixa é **148–219 mm/ano**, ainda seca. Na seed 42, a própria malha anterior, agora ponderada, dá 124,26 mm e 88,17% de principais secos; a refinada dá 157,51 mm e 82,35%. A mudança decorre da amostragem, **sem modificar clima ou classificação**. A malha anterior não tinha sequer um ponto terrestre no bin oceânico 0–1.000 km da seed 42; a refinada tem 14.

Referências oceânicas têm médias de precipitação de 544,70 / 531,81 / 573,13 / 559,98 / 538,59 mm/ano, respectivamente. Não existe falta completa de produção de umidade oceânica. Áreas abaixo do datum desconectadas não são contadas como terra nem interpretadas como lagos; têm grupo separado nos JSONs.

A média das razões não equivale à razão das médias. Na seed 42: média ponderada de P/PET onde definida = 0,590; P médio / PET média = 0,228; mediana ponderada de P/PET = 0,039. Poucos locais frios com PET pequena elevam a média das razões. As frações de área são mais informativas: 53,29% hiperárida (P/PET < 0,05), 17,16% árida (0,05–0,2), 8,57% semiárida (0,2–0,5), 8,36% com déficit moderado (0,5–1), 10,18% úmida e 2,44% com PET zero. Os nomes são índices climáticos, sem pressupor solo, vegetação ou escoamento.

### Latitude, oceano e relevo

| Seed | Chuva em terra a 0–1.000 km do oceano | 1.000–3.000 km | 3.000–10.000 km | Mais de 10.000 km |
|---|---:|---:|---:|---:|
| 42 | 911 | 631 | 191 | 11 |
| 0 | 631 | 621 | 183 | 8 |
| 7 | 836 | 712 | 217 | 8 |
| 2026 | 969 | 591 | 211 | 9 |
| 12345 | 631 | 697 | 207 | 16 |

Valores em mm/ano, ponderados por área. A distância é o campo **macro C2 interpolado**, não distância exata a uma costa T1. O primeiro bin possui somente 8–20 pontos terrestres por seed e não sustenta afirmações sobre todas as praias. Em particular, a seed 12345 não apresenta monotonicidade estrita entre os dois primeiros bins; latitude, vento e relevo também variam.

Na seed 42, 42,66% da área terrestre amostrada fica além de 10.000 km do oceano; apenas 9,45% fica abaixo de 3.000 km. Na seed 7, o interior além de 10.000 km ocupa 48,20%; nas seeds 2026/12345, aproximadamente 26%. Essa diferença acompanha suas maiores médias terrestres de chuva. É correlação geográfica plausível, não uma quota de cobertura úmida.

Na seed 42, as médias de chuva por latitude absoluta 0–15 / 15–30 / 30–45 / 45–60 / 60–75 / 75–90° são **267 / 162 / 144 / 101 / 50 / 100 mm/ano**. As temperaturas médias correspondentes são aproximadamente **15,64 / 11,48 / 3,41 / −5,87 / −17,50 / −21,63 °C**. Os demais planetas e contagens por bin estão na figura comparativa e nos relatórios. Bins polares têm pouca terra amostrada, sobretudo a seed 12345, com quatro pontos terrestres acima de 75°; sua média não representa todos os polos possíveis.

O contexto montanhoso T1 recebe, em média, **355 / 345 / 237 / 386 / 553 mm/ano** nas cinco seeds; o restante terrestre recebe **148 / 141 / 151 / 198 / 203 mm/ano**. Portanto a orografia não foi simplesmente desativada ou convertida com unidade errada. Isso não significa que toda montanha seja úmida: o relatório nativo também separa subidas a barlavento, descidas a sotavento e gradiente baixo em cada período. O teste existente de transporte conserva a relação causal: elevação de condensação na crista aumenta chuva ali e reduz a jusante.

As alturas terrestres médias T1 são aproximadamente 1.441 / 1.327 / 1.457 / 1.363 / 1.526 m. O resfriamento orográfico é relevante para a abundância de perfis frios e PET baixa, sem um erro mm→m.

## Causas e experimentos controlados

O kernel recebe vapor do oceano e transporta uma média ponderada dos vizinhos a montante. Em terra, a retenção por distância é `L/(L+passo)`, e parte do vapor disponível condensa. O resto segue para o próximo passo. Na seed 42:

- Comprimento de umidade automático: **25.298 km**; influência marítima: **4.216 km**.
- Passo atmosférico médio terrestre: aproximadamente **2.990 km**.
- Retenção média por distância: aproximadamente **0,895**.
- Fração média condensada por passo: aproximadamente **0,276**, variando com latitude, período e relevo.
- Fonte oceânica média: aproximadamente **0,57–0,58** do índice máximo, com supressão prescrita em temperaturas negativas.

Como ilustração, 0,895 × (1−0,276) ≈ 0,648 de vapor remanescente por passo; dez passos com esses valores médios deixariam aproximadamente 1,3%. Isso não substitui o solver, pois médias de produtos e trajetórias reais diferem, mas explica por que `moisture_length=25.298 km` **não** significa que o vapor chegue quase intacto a essa distância. Condensação, mistura de fluxos e distância agem em conjunto. Não há reciclagem de evapotranspiração terrestre que reponha o transporte nos interiores.

As seguintes ablações usam **os mesmos vértices, alturas e máscara oceânica C2 da seed 42**, sem reamostrar terreno. São experiências diagnósticas, não novos presets ou snapshots de campanha. Seus números são da quadratura nativa e não devem ser comparados como se fossem exatamente a mesma quadratura dos centros T1 da tabela anterior.

| Experimento | Chuva média terrestre nativa (mm/ano) | Interpretação |
|---|---:|---|
| Replay C2, 40 iterações | 173,280532 | Igualdade completa com o plano congelado |
| 64 iterações | 173,280960 | Diferença de 0,000428 mm/ano; horizonte insuficiente não explica a seca |
| Sem condensação orográfica | 110,057145 | A orografia concentra chuva; removê-la não é correção para “chover mais” |
| Dobrar comprimento de umidade | 189,033854 | Aumenta a média em cerca de 9%; não elimina o regime seco |
| Perda de distância desprezível (`L=10¹² m`) | 209,300330 | Mesmo esse limite continua seco; condensação/mistura seguem atuando |
| Sem ascensão extratropical C2 | 167,221357 | O mecanismo C2 aumenta chuva total e redistribui umidade; sua remoção não corrige o problema |

No plano de referência da seed 42, nenhuma área terrestre fica inacessível a uma fonte oceânica no grafo prescrito, e nenhuma exige mais passos que o orçamento de 40. Os maiores caminhos mínimos sazonais têm 16–22 passos. O residual após 40 iterações é 5–12 ppm e cai a 0–1 após 64. A convergência e a acessibilidade de outras seeds também estão registradas, sem deduzir delas que haja umidade suficiente em todo interior.

### Escala do raio

Não se pode atribuir toda a seca simplesmente ao tamanho do planeta. O próprio fechamento do modelo é seco. Há dois controles diferentes nos artefatos:

1. Mundos reais existentes da seed 42 com outros raios: suas geografias mudam com a política V4, então não isolam o efeito do raio.
2. Experimento que mantém **as mesmas alturas e máscara oceânica angulares**, alterando somente distâncias de arestas e a política automática de comprimentos. É um contrafactual do grafo, não um mundo que possa ser salvo com a mesma proveniência.

No segundo controle, as médias nativas são **195,82 / 173,28 / 158,41 / 158,41 mm/ano**, para raios 6.371 / 63.710 / 637.100 / 1.000.000.000 km. O comprimento de umidade cresce conforme a política existente: inicialmente com raiz do raio e depois com o piso proporcional ao raio. Por isso há redução e depois um patamar, não uma queda ilimitada da chuva em planetas gigantescos. Não existe aqui erro de km/m ou parâmetro totalmente independente do raio.

A condensação é uma fração por **aresta**, e os ventos selecionam/ponderam vizinhos principalmente pela direção. O módulo do vento não é uma velocidade de advecção integrada no tempo; o fallback sem direção usa vizinhos, não ausência completa de transporte. O nível climático faz parte da autoridade, não é LOD intercambiável. Essas são limitações concretas da aproximação C2, já insuficientes para alegar invariância física a qualquer resolução ou simulação atmosférica científica. Não foram escondidas nem “corrigidas” multiplicando precipitação.

## E1: elegibilidade não é o rótulo principal

| Seed | Área com algum perfil do grupo de florestas elegível | Principal do grupo de florestas | P/PET ≥ 1 e média ≥ 5 °C | Pontos nessa última condição sem perfil florestal elegível |
|---|---:|---:|---:|---:|
| 42 | 17,33% | 2,23% | 2,83% | 0 / 64 |
| 0 | 16,74% | 2,32% | 3,86% | 0 / 81 |
| 7 | 16,73% | 2,40% | 3,74% | 0 / 94 |
| 2026 | 21,96% | 3,49% | 3,63% | 0 / 49 |
| 12345 | 22,13% | 2,23% | 5,33% | 0 / 91 |

Os 379 pontos terrestres quentes/úmidos examinados possuem pelo menos um perfil florestal elegível. Isso testa um subconjunto claro de condições favoráveis; não estabelece que seja a definição universal de floresta. Perfis boreais e bosques secos também podem ser elegíveis fora desse subconjunto. A área com potencial florestal é sobreposta e não deve ser somada às demais coberturas como uma partição.

Um único principal não representa todos os habitats permitidos. Entre **4,13% e 6,16%** da área terrestre tem principal desértico/estepe e algum perfil florestal elegível nos intervalos de sobreposição. Alterar a classificação apenas para que florestas ganhem a disputa gráfica não seria correção climática. A futura integração deve consultar `eligible_habitat_ids`, secundários e adequação física, preservando requisitos de confirmação.

Além disso, deserto **polar** tem regra de frio e baixa precipitação absoluta; não exige P/PET baixo no catálogo. PET quase zero permite P/PET alto em um local extremamente frio. Na seed 42, por exemplo, `(−7, −23, −32)` tem −17,98 °C, 76 mm/ano e PET de 3 mm/ano, resultando em P/PET ≈ 25,33, com principal polar. Isso não é uma floresta tropical escondida nem um erro no quociente. Somar todos os IDs contendo “deserto” não equivale a medir área de déficit hídrico.

As evidências hídricas de E1 não foram usadas como substituto de precipitação. Rio permanente, inundação, solo saturado e lago continuam desconhecidos sem prova correspondente; essa prudência reduz **confirmações de habitats hídricos**, não a chuva do C2 nem a elegibilidade básica das florestas. A janela de crescimento florestal, altitude e substrato mantêm seus contratos versionados; a auditoria não encontrou bloqueio sistemático que justifique relaxá-los.

### Exemplos reais sem criar vegetação ou água

Seed 42, sondagem `(-27, 32, 9)`: altura T1 de 2.990,912 m, distância oceânica macro de 2.244 km, temperatura média de 5,43 °C, **1.542 mm/ano**, PET de 609 mm e P/PET de 2,532. Precipitações dos quatro períodos: **387 / 413 / 387 / 355 mm**. E1 permite floresta temperada úmida e subalpina, além de outras camadas; principal potencial subalpino. Nada disso confirma árvores.

Seed 42, `(-32, -27, -1)`: altura de 18,065 m, distância oceânica macro de 19.595 km, 24,22 °C, **zero mm/ano**, PET de 1.709 mm. E1 permite deserto pedregoso. As duas sondagens vêm da mesma varredura sistemática; foram selecionadas depois apenas para ilustrar os extremos, e não para estimar sua frequência.

## Resolução regional e visualizações

No raio de referência, as arestas atmosféricas têm aproximadamente 3.000 km. Uma janela de 1.024 km pode estar inteiramente no mesmo regime climático amplo. Sua baixa diversidade não prova erro: os perfis principais são discretos, enquanto as grandezas interpoladas variam continuamente. T1 ainda ajusta altitude/temperatura/PET localmente; a chuva não recebe uma segunda simulação orográfica de vales. Canais estreitos, nevoeiro local e sombras de chuva de escala pequena não são resolvidos pelo C2. Essa é uma limitação espacial, não autorização para inventar microclimas.

Foram gerados mapas offline nas cinco seeds, com precipitação, temperatura, P/PET e potencial E1 na mesma grade. A imagem comparativa mostra médias por latitude e distância oceânica, incluindo número de sondagens por bin. As cores de potencial não representam vegetação estabelecida ou um mapa público.

- [Seed 42: clima e ambientes](../artifacts/climate-audit-after-e1/seed-42/climate-environments.png).
- [Seed 2026: clima e ambientes](../artifacts/climate-audit-after-e1/seed-2026/climate-environments.png).
- [Comparação entre latitudes e distâncias nas cinco seeds](../artifacts/climate-audit-after-e1/latitude-distance.png).
- [Dados consolidados](../artifacts/climate-audit-after-e1/suite.json); cada pasta contém relatório e as duas malhas completas, permitindo localizar também regiões secas ou uniformes.

## Testes e reprodução

**118 testes aprovados em 157,48 s**, incluindo sete novos testes da auditoria e os testes existentes de clima C1/C2 e ambiente E1, com persistência. Houve somente o aviso preexistente de depreciação Starlette/httpx. A compilação Python, os checks de whitespace e a verificação dos artefatos passaram. A regressão completa de 752 testes da entrega E1 não foi repetida: esta auditoria não modificou código autoritativo e executou os 118 testes diretamente relacionados. As assinaturas congeladas e os planos das cinco seeds foram preservados.

Os testes adicionais verificam ponderação esférica, quantis, diferença entre média das razões e razão das médias, exclusão de PET indefinida do denominador, distâncias desconhecidas, conversão diária/sazonal/anual a partir de uma fonte oceânica controlada e igualdade C2/E1 real. Os testes existentes de C1/C2/E1 exercitam determinismo, snapshots congelados, emendas/polos, sombra de chuva, ordem, persistência e incompatibilidade de versões. O caso oceânico de teste precisa estar abaixo do datum; usar altura igual ao nível do mar com `marine=True` é corretamente recusado pelo validador.

A partir de `backend`:

```powershell
.venv/Scripts/python.exe -m scripts.audit_climate_after_e1
$auditTests = Get-ChildItem app/tests -File | Where-Object { $_.Name -like 'test_genesis_climate*.py' -or $_.Name -like 'test_genesis_environment*.py' -or $_.Name -eq 'test_climate_after_e1_audit.py' }
.venv/Scripts/python.exe -m pytest @($auditTests.FullName) -q
```

O comando de testes acima usa expansão explícita de caminhos no PowerShell. O script aceita `--output`, `--seeds` e `--fine-level 4|5`; os números publicados usam as cinco seeds padrão e nível 5. Não requer migração ou acesso ao banco do jogo.

Arquivos entregues: `backend/scripts/audit_climate_after_e1.py`, `backend/app/tests/test_climate_after_e1_audit.py`, este documento e `artifacts/climate-audit-after-e1/`. **Não foi criada C3**, nem alterado silenciosamente qualquer snapshot C2/E1. Qualquer mudança futura do transporte ou de seus parâmetros autoritativos deverá ter versão explícita, com nova comparação; os experimentos presentes não ativam tais mudanças.

## Recomendação prática

O clima atual suporta uma integração ambiental de RPG com interiores muito secos, zonas frias extensas e áreas naturalmente úmidas. Não é necessário impor percentuais de florestas ou corrigir unidades que já estão certas. A maior correção necessária nesta auditoria foi **na interpretação dos números**: ponderar área, aumentar sondagens, separar índices de água de rótulos ambientais e considerar os habitats sobrepostos.

Avançar usando os potenciais físicos atuais é razoável, mantendo pendentes os habitats que exigem água, gelo ou feições ainda não comprovadas. A distribuição de espécies deve respeitar esses contratos e não tratar um principal regional como exclusão dos demais elegíveis. O presente parecer não autoriza preenchimento global, vegetação automática em todo ponto úmido ou fauna sem habitat confirmado. Se a direção de jogo desejar interiores úmidos muito mais extensos que os atuais, isso será uma decisão explícita de calibração do modelo, não uma correção aritmética demonstrada por esta auditoria.
