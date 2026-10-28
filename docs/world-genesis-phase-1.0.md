# World Genesis 1.0 — Flora e vegetação Vg1

Data: 26/10/2026. Estado: fundação operacional **experimental**, com comunidades, indivíduos, coleta finita e persistência demonstrados. Ativação em campanhas reais continua desabilitada por padrão.

## Decisões e auditoria do código existente

E1 classifica ambientes potenciais; não havia uma autoridade de populações vegetais nem coleta botânica executável. A coleta de criaturas e o inventário já possuem autoridade própria. Vg1 acrescenta uma camada subordinada, reutiliza `ItemDefinition`, `ItemInstance`, ferramentas, `CharacterSkill`, relógio e `LocationSpatialAnchor`, e não altera o grafo de movimento ou o mapa público.

Fontes reais usadas: geografia V4, campo completo T1, substratos/formações JR1, E1-C3 e W1 preparado com `WaterConfigC3R155()`. Clima de referência: `ClimateConfigV3R1(land_recycling_ppm=550_000)`. Assinaturas e checksums dessas autoridades entram na identidade de Vg1. C2 não é aceito por troca de cabeçalho. W2/P1 não são reinterpretados como rios permanentes, solo saturado ou vegetação.

O repositório recebeu o ZIP v22, mas as pastas extraídas anteriores e o ZIP v20 já não estavam disponíveis. Foram extraídos **bytes originais** das pastas de taxonomia, flora e D14 do v22. Os três hashes E1 e o hash D14 v4 permanecem iguais aos anteriores. O diagnóstico histórico `Everreach_EV_ECO_1_1_Auditoria_Habitats.json` não consta desse pacote: E1 agora informa sua ausência, sem inventar a auditoria antiga ou alterar regras físicas. O teste histórico compara o ZIP disponível e continua exigindo os hashes originais.

Não foram modificados arquivos dentro do ZIP ou registros do catálogo. v21 não é uma segunda autoridade.

## Catálogo ativo e integridade

Leitura obrigatória realizada: `02_Flora/LEIA_PRIMEIRO.md`, guia WorldGenesis v7.2, índice e validação v7.2. Fonte autoritativa: `Everreach_Flora_3096_Extremos_Ecologia_v7_2.json`.

- SHA-256: `a2d177f65e96ac90b572a6acc78c1513e9a01db40032257a3bbe3d58cf0acb38`.
- 3.096 espécies, 3.096 perfis, 6.192 partes e 6.192 itens; IDs e nomes de itens conferidos.
- Índice compilado por habitat, derivado dos perfis. Nenhum índice autoriza ocorrência.
- 96 registros extremos, incluindo 34 `consorcio_simbiotico`, preservados como tipos próprios.
- Oito overlays legados preservados separadamente, condicionais ao micro-habitat; não expandem o perfil para toda uma geleira/caverna.
- Estruturas compiladas imutáveis; o grande documento JSON transitório é descartado. Partes são retornadas por cópia.

1.500 perfis não informam altura: Vg1 usa faixas de porte por tipo, declaradas como **parâmetros de arquitetura de jogo**, não como medidas recuperadas do dataset. 1.596 espécies não têm estoque sugerido: podem formar comunidades se elegíveis, mas seus indivíduos não recebem estoque coletável automático.

## Fundação e continuidade

Pipeline: habitat E1 elegível → filtros físicos → distribuição biogeográfica → população fundadora finita → comunidade estabelecida → indivíduo materializado → ações persistentes.

`pre_player_biogeographic_history_v1` representa uma história ecológica anterior ao protagonista. A geração não depende de sementes previamente registradas pelo jogador. Ela não simula crescimento instantâneo: o adulto fundador é parte do estado inicial definido pela seed e pelas autoridades.

As populações pertencem a patches físicos fixos com espaçamento máximo configurado de 1 km. O nível do endereço adapta-se ao raio: 14 para 6.371 km, 17 para 63.710 km, 19 para 254.840 km e 31 para 1 bilhão de km. São endereços T1 subordinados; não mudam o contrato `CellKey` legado. Visitas, LOD de desenho, ordem de consulta e nível do personagem não entram no endereço.

Campos 3D sobre a esfera definem distribuição biogeográfica, composição e arquitetura, atravessando faces sem reseeding. Regiões de distribuição usam escala de 640 km; o preset dirigido acrescenta composição em escala de 4 km e arquitetura de copa em 8 km. A representação da comunidade é discreta em patches; isso não significa continuidade analítica de todos os rótulos em cada fronteira de patch. Aliases da mesma emenda geram o mesmo endereço/resultado.

Área física é integrada pelo ângulo sólido esférico. Cobertura, altura e área determinam um número **finito de slots de organismos/colônias-modelo**. Não se trata de um censo botânico. O refinamento verifica o micro-local de um slot; um local incompatível não é substituído por outro sorteio. O orçamento configurável de 12 espécies por descritor limita a representação local, não a biodiversidade global.

Identidades de comunidade, população e indivíduo derivam da autoridade e dos endereços físicos; não usam UUID de campanha, horário de materialização ou IDs de entidades políticas.

## Adequação e limites das evidências

Os filtros exigem habitat efetivamente elegível no E1, referências térmicas/pluviométricas conhecidas, P/PET conhecido no clima, substrato JR1 disponível, superfície terrestre aberta, condições sazonais e ciclo de água acessível no W1. Ausência de escoamento superficial não bloqueia plantas: o teste verifica esse caso explicitamente.

Um intervalo específico de P/PET ausente no perfil **não é uma fisiologia confirmada ou tolerância ilimitada**: a espécie continua limitada pelo habitat E1 efetivamente elegível e pelos limites funcionais versionados de Vg1. Falta de referências indispensáveis de temperatura/chuva mantém pendência. Porte legado é uma regra explícita de jogo; não resolve nutrição, química ou energia desconhecidas.

Substrato terrestre genérico é validado contra JR1. O modelo de fundação admite micro-sítios expostos sobre essa superfície; não afirma espessura real de solo, nutrientes medidos, química específica ou profundidade de raízes. ET/umidade de solo W1 são **adequação regional**, não um novo estoque local nem uma autorização para consumir água do W2. A fundação não credita água reciclada ao solo e não modifica ET, clima ou ledger hídrico.

Condições sem evidência continuam bloqueadas. `pending-species.json` enumera os IDs e motivos: 808 registros têm ao menos um bloqueio estrutural no adaptador atual, com motivos sobrepostos:

| Exigência ausente | Registros |
|---|---:|
| Referência climática indispensável | 391 |
| Perfil sem hospedeiro natural | 184 |
| Suporte local para trepadeiras | 78 |
| Energia detrítica localizada para fungos | 140 |
| Coluna d'água/energia especializada | 191 |
| Anomalia exata autorizada e fonte persistida | 166 |
| Geometria, substrato e energia de micro-habitat extremo | 96 |

As 96 espécies novas extremas e os oito overlays **não foram forçados a aparecer**. Os contratos atuais não fornecem as provas locais completas. Consórcios não viram plantas fotossintéticas. A autoridade Vg1 não cria anomalias, fontes hidrotermais, cavernas iluminadas ou corpos d'água para liberar espécies. Musgos/líquens terrestres legados podem formar cobertura polar/alpina nos locais adequados; isso não libera automaticamente espécies especializadas de gelo, cavernas ou abismos.

## Calibração de variedade

Primeiro foi executado `ecological_v1`. Na região moderada da seed 42, percursos de 5 e 20 km mantiveram a mesma dominante, com variação inferior a 0,3 ponto percentual de cobertura. O problema era escala de composição, não falta de chuva nessa região.

Foi implementado `exploration_mosaic_v1`: campos determinísticos adicionais alteram seleção/dominância entre espécies já elegíveis, fração ocupada e distribuição de copa/sub-bosque. A cobertura dirigida nunca ultrapassa o teto ecológico original. Não há multiplicador de chuva, mudança de E1, novas permissões mágicas ou quota de biomas. Regiões sem fonte hídrica/condições essenciais permanecem vazias.

**Recomendação experimental:** usar explicitamente `VegetationConfig(policy="exploration_mosaic_v1")` em futuros mundos de teste. O preset ecológico permanece como controle reproduzível; a escolha é parte da assinatura e não pode ser trocada em uma campanha já inicializada.

## Resultados nas cinco seeds

Raio 63.710 km. Por seed: 384 sondas globais e percursos/janelas contrastantes úmidos, moderados, áridos, muito secos e muito frios. Não são amostras regionais aleatórias: sua riqueza não estima prevalência no planeta.

| Seed | Espécies ecológico → dirigido | Dominantes ecológico → dirigido | Patches com comunidade / avaliados | Cobertura média terrestre global dirigida |
|---|---:|---:|---:|---:|
| 42 | 545 → 921 | 108 → 199 | 1.119 / 1.985 | 16,95% |
| 0 | 462 → 791 | 86 → 181 | 1.079 / 1.966 | 14,64% |
| 7 | 479 → 699 | 92 → 159 | 1.078 / 1.987 | 12,69% |
| 2026 | 484 → 868 | 85 → 176 | 1.056 / 1.977 | 19,09% |
| 12345 | 446 → 887 | 86 → 210 | 1.030 / 1.944 | 18,77% |

Total dirigido: **5.362 comunidades estabelecidas**, 9.859 patches avaliados, **1.376 espécies distintas** no conjunto das regiões. A estatística não instancia indivíduos interativos. Os descritores com populações finitas estão persistidos nos snapshots JSON de cada autoridade experimental; a materialização em banco e a coleta são provas separadas.

A cobertura global usa ponderação por ângulo sólido do cube-sphere e referência terrestre W1. Essa resolução não é um inventário exato de litorais locais. Não se deve usar a média global para descrever uma floresta específica. Na janela úmida da seed 42 a cobertura média dirigida foi 60,5%; na moderada, 47,2%; na árida, 21,5%. Regiões extremas secas/frias sem suporte continuaram vazias.

Foram geradas florestas densas/abertas, bosques, mosaicos de savana, campos de ervas/gramíneas, estepes, arbustais, cobertura desértica esparsa e cobertura polar/alpina. A densidade representada varia de 0 a 7.830 organismos/colônias por hectare na seed 42. Densidade herbácea e densidade arbórea não são equivalentes: alturas, tipos e estratos estão nos descritores.

Mudanças de dominante no percurso moderado, ecológico → dirigido:

| Seed | 5 km | 20 km | 50 km | 100 km | 500 km |
|---|---:|---:|---:|---:|---:|
| 42 | 0 → 4 | 0 → 10 | 1 → 15 | 3 → 20 | 11 → 19 |
| 0 | 0 → 4 | 1 → 13 | 2 → 17 | 4 → 20 | 10 → 19 |
| 7 | 0 → 2 | 0 → 13 | 3 → 17 | 2 → 20 | 10 → 20 |
| 2026 | 0 → 5 | 0 → 10 | 0 → 17 | 2 → 20 | 12 → 18 |
| 12345 | 0 → 3 | 1 → 12 | 3 → 18 | 4 → 20 | 9 → 19 |

Cada percurso tem 21 amostras; passos de 250 m a 25 km. Os percursos grandes demonstram diferenças entre amostras, não a distância exata entre todas as transições. Trocar dominante vegetal não significa trocar de bioma a cada quilômetro. Os mapas mostram o mosaico e o restante da estrutura.

Raios adicionais, seed 42: 6.371 km, 254.840 km e 1.000.000.000 km, 96 sondas por planeta, respectivamente 204, 137 e 124 espécies estabelecidas. Esses ensaios usam C3 R1-55 realmente resolvido em nível climático 3, mais grosseiro que os mundos de referência. Validam funcionamento/endereçamento/custo, não qualidade climática comparável entre resoluções.

## Coleta e persistência reais

Tabelas novas: planos Vg1, comunidades, indivíduos, ações e certificados botânicos de ferramentas. Migração `u29u2p3q4r5s` preparada; **não executada no banco real**. O reset de campanha remove filhos Vg1 antes dos pais e preserva outras campanhas.

O materializador não instancia todas as plantas do patch. Um slot observado/interativo recebe posição exata, estágio fundador, fenologia inicial e estoque finito. O estoque total não ultrapassa a sugestão não nula do catálogo, limites da parte e maturidade. Sementes/frutos exigem fase reprodutiva adequada. Estoque desconhecido permanece zero coletável/pending; não recebe um valor arbitrário.

Coleta exige personagem vivo, localização ancorada a até 5 m do indivíduo, janela sazonal/horária do calendário existente, proficiência principal persistida e ferramenta efetivamente possuída. Capacidade genérica `CUTTING` não comprova precisão/corte fino: essas operações dependem de certificação botânica explícita de teste. As proficiências não são concedidas ao jogador pelo importador; o operador da demonstração recebeu treino explícito somente no banco descartável. Procedimento insuficiente não cria itens nem XP.

A transferência usa o ledger existente de itens e preserva o ID canônico `IT-EVR-FL-*`. Cada lote tem recibo de origem, parte, indivíduo, quantidade, horário, ferramenta, revisão e conservação inicial. Não aplica preços históricos, potência medicinal/mágica ou XP automático. A massa dos materiais ainda não possui calibração própria nesta fase; a definição usa o padrão legado de massa zero, restrito ao experimento, e isso deve ser resolvido antes da ativação comercial/coleta em campanhas reais.

Parte destrutiva/raiz mata o indivíduo. Remoção de árvore exige serra; não inventa um novo item de madeira fora das partes do catálogo. A população e a cobertura atuais descontam indivíduos removidos. IDs de ação idempotentes não produzem um segundo lote. Savepoints e fence SQLite deixam commit/rollback sob controle do chamador.

Prova real em `persistent-proof-final.sqlite` e `persistent-proof.json`: espécie **EV-FL-0296**, indivíduo `vgi:6137a214d294e2baf5b2ab03ed2dd854`, parte `EV-FL-0296-P01`, item `IT-EVR-FL-0296-P01`. Transferido **1** item ao inventário. Repetir a mesma ação devolveu o recibo existente. O indivíduo foi removido, o banco fechado/reaberto e a revisita manteve `alive=false`, estoques zero e quantidade de inventário **1**. Autoridades de campanhas reais não foram tocadas.

## Desempenho

Ensaio completo sem tracemalloc, em processos concorrentes: aproximadamente 2–10 s para carregar as fontes congeladas e 34–38 s por seed no preset ecológico, 44–53 s no dirigido, para cerca de 2.000 patches distintos com classificação E1/T1/JR1 completa. A interpretação é preparação sob demanda, não uso por frame de renderização.

Benchmark com tracemalloc, processo novo: catálogo retido **17,17 MiB**, pico transitório de parsing **249,50 MiB**, importação instrumentada 1,80 s. Cache máximo de 128 patches por sampler e dois contextos Vg1. Instrumentação aumenta muito o custo: 160 consultas novas levaram 81,57 s no ecológico e 112,37 s no dirigido; consulta em cache ~0,18 ms. Alocações retidas das consultas ~10–13 MiB, sem enumerar populações planetárias ou criar indivíduos.

Na prova SQLite: preparar/importar fontes 2,46 s; comunidade + indivíduo 0,69 s; coleta 0,36 s; revisita 0,37 s. O gargalo das operações persistentes inclui verificação de checksums e fontes E1/T1/JR1/W1. Ainda não é uma API de renderização de alta frequência. Não foram adicionados workers ou simulação contínua.

## Artefatos e reprodução

Dentro de `backend`, com o ambiente virtual existente:

```powershell
.venv/Scripts/python.exe -m scripts.validate_vegetation
.venv/Scripts/python.exe -m scripts.validate_vegetation --policy exploration_mosaic_v1
.venv/Scripts/python.exe -m scripts.report_vegetation
.venv/Scripts/python.exe -m scripts.preview_vegetation
.venv/Scripts/python.exe -m scripts.benchmark_vegetation
.venv/Scripts/python.exe -m scripts.validate_vegetation_radii
.venv/Scripts/python.exe -m scripts.prove_vegetation --database another-isolated-proof.sqlite
.venv/Scripts/python.exe -m pytest app/tests/test_genesis_vegetation.py app/tests/test_genesis_vegetation_persistence.py app/tests/test_campaign_reset.py -q
```

O script da prova recusa sobrescrever um banco já existente e restringe o caminho à pasta de artefatos isolada. Os validadores usam snapshots climáticos/hídricos das fases anteriores; faltas nesses arquivos são erros explícitos.

Artefatos em `artifacts/vegetation-vg1/`:

- `comparison.json`, `established-species.json`, `pending-species.json`.
- `seed-*/ecological_v1/` e `seed-*/exploration_mosaic_v1/`: autoridade, comunidades, métricas, janelas e sondas globais.
- `seed-*/vegetation-mosaics.png`: forma, dominante, cobertura, densidade, riqueza representada e estratos.
- `seed-*/ecological-vs-directed.png`: comparação na mesma geografia.
- `seed-*/planet-established-vegetation.png` e `exploration-routes-comparison.png`.
- `benchmark.json`, `additional-radii.json` e prova SQLite/JSON.

São ferramentas técnicas e snapshots de comunidades efetivamente fundadas pelo modelo. Não são mapas públicos nem simples mapas de elegibilidade E1. Imagens inspecionadas visualmente.

## Testes e arquivos

**825 testes distintos aprovados:** 670 World Genesis/auditoria climática, 96 de mapa/exploração/viagem/relógio/loot/ferramentas e 59 Vg1/reset. Estes 59 foram executados em três lotes sem sobreposição (56 + 2 + 1). A suíte adicional cobre integridade, nulidade, extremos, cinco seeds reais, ordem/LOD/processos, emendas/cantos, raios extremos, fundação, direção procedural, ausência de mutação do clima/água, persistência, idempotência, estoque desconhecido/finito, corrupção, rollback, remoção de uma árvore fundadora real e migração em SQLite temporário. Escopo selecionado, não toda a suíte do repositório. Manifesto `artifacts/vegetation-vg1/validation.json` contém resultados e hashes de código/logs. Aviso existente: depreciação Starlette/httpx do ambiente de teste.

Arquivos de código desta fase:

- `backend/app/game/world/genesis/vegetation/{__init__,catalog,config,field,service}.py`.
- `backend/app/db/models/world_vegetation.py`, registro em `models/__init__.py`, migração `u29u2p3q4r5s`.
- Integração de exclusão em `backend/app/game/world/reset.py`.
- Compatibilidade de diagnóstico auxiliar em `environment/catalog.py` e `test_genesis_environment.py`; regras/hashes E1 inalterados.
- `test_genesis_vegetation.py`, `test_genesis_vegetation_persistence.py`.
- Scripts `validate_vegetation`, `validate_vegetation_radii`, `report_vegetation`, `preview_vegetation`, `benchmark_vegetation`, `prove_vegetation`.
- Este documento, artefatos e cópias originais extraídas do v22.

O workspace já continha implementações e alterações das fases anteriores. Esta lista não atribui à Fase 1.0 todas as alterações preexistentes do repositório.

## Limitações e recomendação

Vg1 entrega paisagens fundadas, variadas e persistentes, além de uma prova concreta de recursos finitos. A recomendação é adotar **o preset dirigido como referência experimental**, mantendo ativação explícita e autoridades antigas intactas.

Continuam necessários antes de ampliar a ativação: calibrar estoque/massa das espécies sem parâmetros, registrar evidências locais para organismos aquáticos/subterrâneos/extremos, energia orgânica e suportes, e decidir o acoplamento observacional ao fluxo público de ações. Não foi implementado crescimento, rebrote, reprodução contínua, sucessão ou retroalimentação de vegetação sobre clima/hidrologia; seus contratos exigem eventos futuros explícitos. A classificação E1 persistida não é reescrita para fingir que sempre continha vegetação.

Fauna, civilizações e Atlas não fazem parte desta implementação.
