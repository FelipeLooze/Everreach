# World Genesis 1.0.1 — Calibração visual e contratos de recursos

26/10/2026. Resultado: **Vg2 `regional_canopy_v2`**, independente de Vg1, recomendado como referência visual experimental nos ensaios descritos abaixo. Não há ativação automática, migração de campanhas ou nova aprovação de estoque/massa de espécies reais.

## Diagnóstico e decisões

O preset anterior somava 25% do ranking de composição de 128 km a 75% de um campo por espécie de 4 km. Com centenas de candidatas sobrepostas e um orçamento local de 12 espécies, pequenas diferenças entre esses campos trocavam frequentemente a composição e a dominante. A cor por ID tornava cada troca semelhante a uma mudança de bioma. Contudo, **nem todas eram somente cosméticas**: os dados também mostram saltos de altura e de ocupação de copa.

Além disso, a cobertura era multiplicada por `750_000 + 25 * noise`, com `noise` entre −10.000 e +10.000. O fator fica entre 0,5 e 1,0, centrado em 0,75: o preset reduzia a ocupação por construção. Não havia fundamento para vincular toda a diversidade à retirada sistemática de vegetação.

Decisões:

1. Preservar fórmulas, configuração, snapshots e resultados de Vg1. Uma verificação de entrada impede usar configuração Vg2 acidentalmente no algoritmo Vg1; as fórmulas antigas não mudaram.
2. Criar `VegetationConfigV2` e dispatch explícito. Planos existentes continuam usando sua versão; inicializar outra configuração em uma campanha já fundada é recusado.
3. Modelar conjuntos regionais de espécies, com líderes e associadas, interpolados no espaço 3D da esfera. Separar composição de cobertura e arquitetura.
4. Usar o teto ecológico anterior, sem alterar clima, água ou elegibilidade. Fazer diagnósticos por fisionomia, altura, densidade e estratos; IDs continuam sendo informação botânica separada.
5. Preparar calibração de recursos por parte com orçamento de tecido e massa positivos. Não preencher os valores ausentes dos 1.596 registros com números genéricos.

O caminho informado corresponde ao pacote v22 disponível como ZIP no repositório. As 23 fontes necessárias foram novamente disponibilizadas como cópias dos bytes originais do ZIP, pois as pastas extraídas anteriores não estavam presentes. Nenhum registro do dataset foi reescrito; v21 não é carregado.

## Vg2: continuidade e cobertura

O espaço ambiente da esfera recebe uma malha de referência de 32 km. Cada referência mantém conjuntos potenciais de árvores e cobertura inferior, com liderança estável e espécies secundárias. O ponto consulta oito referências vizinhas com interpolação suave; as candidatas ainda passam pelos filtros físicos locais e pelos campos biogeográficos de raridade. Não há reseeding em faces ou setores. Os conjuntos potenciais não são populações materializadas nas referências da malha.

Caso os conjuntos regionais não forneçam nenhuma espécie adequada, o gerador consulta as candidatas locais já elegíveis; não cria uma condição física ou uma exceção mágica para preencher o local. O fallback também é determinístico.

A arquitetura regional varia em escala de 48 km; um campo mais fraco de 8 km varia ocupação de copa/clareiras. Uma abertura no dossel pode possuir ervas ou arbustos adequados, em vez de significar necessariamente solo nu. Alturas continuam usando os parâmetros do catálogo e a arquitetura de jogo declarada para os registros legados incompletos.

A cobertura parte da base ecológica sem a multiplicação redutora anterior. Um preenchimento adicional pequeno só ocupa a margem até o teto heurístico existente, quando P/PET ≥ 0,5, ET W1 positiva e pelo menos um período com água de solo regional modelada. Onde essas condições faltam, não há preenchimento adicional. Isso é uma hipótese de ocupação inicial, não uma simulação de produtividade, consumo de água ou crescimento. Não credita litros, não muda W1/C3 e não declara a umidade macro como profundidade de água local.

O descritor local permanece em patches físicos de até 1 km. As interpolações e os endereços canônicos são independentes de visitas, ordem, LOD e face. Rótulos de patches não são uma malha de renderização contínua; não foi construído um renderizador.

## Antes/depois: cobertura nas mesmas janelas de 20 km

Raio: 63.710 km. Mesmas geografias, pontos e autoridades das cinco seeds de referência. Valores em porcentagem de cobertura:

| Seed | Úmida: Vg1 → Vg2 | Moderada: Vg1 → Vg2 | Árida: Vg1 → Vg2 |
|---|---:|---:|---:|
| 42 | 60,46 → 82,41 | 47,15 → 61,87 | 21,50 → 28,99 |
| 0 | 61,16 → 80,28 | 44,68 → 61,93 | 22,81 → 28,95 |
| 7 | 57,59 → 80,90 | 47,11 → 61,95 | 22,31 → 28,92 |
| 2026 | 56,35 → 78,63 | 46,43 → 61,84 | 23,11 → 29,30 |
| 12345 | 57,80 → 79,93 | 45,51 → 61,88 | 22,36 → 28,94 |

Na seed 42, as bases ecológicas anteriormente demonstradas eram aproximadamente 82,3%, 61,9% e 29,0%. Vg2 recupera essas coberturas sem tornar a região árida uma floresta. A maior parte da recuperação é a remoção da penalidade de 25%, e não uma nova fonte de água. As janelas extremamente secas e frias sem suporte continuam sem população estabelecida.

## Continuidade, identidade e estrutura visual

Cada janela tem 16 × 16 sondas. Componentes são agrupamentos de amostras com adjacência de quatro vizinhos, não um censo exato de manchas geográficas. Na seed 42:

| Região | Componentes por dominante Vg1 → Vg2 | Componentes por fisionomia Vg1 → Vg2 |
|---|---:|---:|
| Úmida | 69 → 5 | 14 → 1 |
| Moderada | 99 → 16 | 29 → 1 |
| Árida | 49 → 1 | 4 → 1 |

Uma floresta aberta reconhecível pode ocupar 20 km sem mudar de classe, mantendo diferentes espécies e gradientes de altura/copa. Isso é diferente de um campo homogêneo sem estrutura. Nos mapas de 100 km da seed 42:

- A janela úmida mantém floresta densa nas 256 sondas, com altura média ponderada variando entre aproximadamente **10,8 e 23,1 m**, além de variação de densidade e estratos.
- A janela moderada contém **201 sondas de floresta aberta e 55 de bosque**, organizadas em manchas maiores; altura média de **4,1 a 11,2 m**.
- A janela árida contém **169 sondas de arbustal e 87 de estepe**, com altura média de **0,3 a 2,2 m**. A cobertura média fica perto de 29%.

As cores principais representam fisionomias. Há painéis independentes de cobertura, altura média, densidade e estratos. O mapa antigo por ID não é utilizado como evidência suficiente de diversidade visual.

O diagnóstico longitudinal registra separadamente mudança de dominante, mudança de fisionomia e mudança estrutural apreciável. O último é um limiar técnico explícito: mudança de forma, 10 pontos percentuais de cobertura/copa, diferença relevante de altura ponderada ou grande diferença de densidade. Não é uma avaliação perceptiva de cenas renderizadas. No percurso moderado antigo de 20 km, por exemplo, **11 das 13 trocas de dominante da seed 0 não ultrapassavam esses limiares estruturais**. Em outros casos havia mudanças estruturais reais; não classificamos todas as trocas como cosméticas.

Trocas de dominante nos percursos moderados, antes → depois:

| Seed | 5 km | 20 km | 50 km | 100 km | 500 km |
|---|---:|---:|---:|---:|---:|
| 42 | 4 → 0 | 10 → 3 | 15 → 4 | 20 → 7 | 19 → 12 |
| 0 | 4 → 0 | 13 → 4 | 17 → 6 | 20 → 6 | 19 → 19 |
| 7 | 2 → 0 | 13 → 1 | 17 → 3 | 20 → 4 | 20 → 18 |
| 2026 | 5 → 1 | 10 → 1 | 17 → 2 | 20 → 8 | 18 → 13 |
| 12345 | 3 → 0 | 12 → 3 | 18 → 2 | 20 → 5 | 19 → 13 |

Todos os percursos têm 21 sondas: passos de 250 m a 25 km. Não interpretamos 19 mudanças em 500 km como uma dominante mudando a cada metro; nem afirmamos ausência de transições entre sondas distantes. Os percursos incluem também regiões úmidas, áridas, muito frias e muito secas. Matriz completa de IDs, formas e estrutura em `seed-*/routes.json` e `report.json`.

Vg2 não tenta preservar a riqueza inflada por troca frequente de composição: as amostras regionais ampliadas registraram 345, 336, 257, 395 e 362 espécies distintas respectivamente. O número menor de IDs não significa regressão visual. Não é a contagem planetária de espécies, e não há quota global de biodiversidade.

Para verificar paisagens fora das cinco janelas contrastantes, 384 sondas planetárias da seed 42 produziram: **8 florestas densas, 8 abertas, 3 bosques, 14 savanas, 7 campos, 16 estepes, 57 arbustais, 19 coberturas desérticas esparsas, 18 polares/alpinas e 1 de musgos/líquens**, além de 233 sondas sem vegetação. Estas últimas incluem a referência oceânica e regiões terrestres inviáveis; essa contagem bruta não é uma porcentagem de aridez terrestre. Não foi imposta nenhuma dessas quantidades. Os exemplos e seus parâmetros completos estão na galeria e no JSON do piloto.

## Auditoria das 96 espécies extremas

Foram auditados os 96 registros, seus 16 habitats, energia, micro-habitat específico, dependências hídricas e anomalia exata. A inspeção usa 15 contextos reais de montanha, frio e área úmida nas cinco seeds, com coordenadas, T1, JR1, C3 e W1 registrados. A tabela por espécie preserva a exigência original; não substitui uma prova por um rótulo de ambiente.

**Nenhuma das 96 possui ainda prova local completa que autorize materialização legítima.** Isso é um resultado da auditoria, não uma nova ocorrência fabricada ou uma alteração da taxonomia.

| Família de ambiente | Evidência integrável agora | Evidência que continua faltando |
|---|---|---|
| Montanha vulcânica | Relevo T1, substrato e história vulcânica JR1 | Atividade atual, emissão/energia/nutrientes locais e superfície específica segura |
| Pico nevado | Altitude, contexto montanhoso e sazonalidade C3 | Microfissura exposta e realmente sem gelo; nutrientes locais |
| Geleira/banquisa | Frio, neve potencial e estoques macro W1 | Geometria efetiva de gelo, morena/bolsa exposta ou camada subglacial iluminada |
| Deserto polar | Superfície e regime climático frio | Bolsa de degelo, substrato e água/energia no micro-local |
| Cavernas, rios subterrâneos e túneis de lava | Contexto geológico e relevo de superfície | Cavidade/acesso, temperatura local, luz real ou energia química/detrítica |
| Talude, mesopelágico, abismo e fossa | Geografia/referência marinha e substratos macro | Coluna d'água efetiva, profundidade/pressão e aporte trófico localizado |
| Dorsal oceânica | Contexto geológico compatível | Gradiente químico ou fonte hidrotermal efetiva se exigida |
| Oceano polar sazonal | Clima e referência oceânica | Camada fótica local, água e aporte trófico confirmados |
| Espécies excepcionais | ID exato requerido pelo catálogo | Autorização e fonte anômala persistida e colocalizada |

Ruído de relevo T1 não é uma fissura sem gelo comprovada. Neve W1 por célula não é uma geleira local. História vulcânica não é emissão geotérmica ativa. Uma transferência P1 temporária não é uma gruta iluminada ou um rio permanente. Portanto não foi seguro cumprir a parte condicional de materializar alguns extremos nesta correção. Integração legítima dessas ocorrências depende de evidências futuras de microgeometria, criosfera, cavernas, coluna d'água e energia/anomalias; não de recalibração de probabilidades. As coberturas polares comuns demonstradas usam espécies legadas elegíveis e não liberam as especializadas.

Artefatos: `evidence-audit.json`, `extreme-species-evidence.json`. Os oito overlays legados permanecem condicionais e inalterados.

## Estoques, massa e inventário

Os 1.596 estoques ausentes são majoritariamente conteúdo proposto v7.1/v7.2, não um erro que removeu quantidades no importador. Foram inventariadas **3.192 partes**, com IDs e campos originais. Há 350 árvores, 251 arbustos, 252 gramíneas e os demais tipos, incluindo 34 consórcios; contagem completa no relatório.

A nova estratégia é `PartCalibrationV1`, uma configuração revisada e imutável por espécie/parte/tipo, vinculada à autoridade Vg2. Exige:

- Massa unitária positiva em mg, tecido disponível medido ou explicitamente estimado com método documentado, fração removível e máximo de unidades maduras.
- `max_units × unit_mass ≤ available_tissue_mass × removable_fraction`. Partes do mesmo pool de tecido não podem alocar a mesma massa duas vezes.
- Proveniência e método de medição/revisão explícitos. Tipo e IDs precisam existir no v22. Quando o catálogo já estabelece um máximo da parte, ele não pode ser ultrapassado.
- Estágio/fenologia e janela de coleta existentes; estoque finito, sem recuperação por visita ou tempo automático.

Altura e tipo ajudam a planejar a amostragem, mas não bastam para inventar biomassa ou rendimento. Propostas por espécie/parte foram geradas com valores desconhecidos **null**, não com uma reserva universal. **Zero calibrações reais foram autoaprovadas.** O importador não transforma raridade em estoque.

O inventário existente soma `base_weight × quantity` e trabalha com unidades genéricas de peso, sem impor quilogramas no contrato. Por isso a calibração exige também uma conversão explícita `inventory_mg_per_weight_unit`, uniforme dentro da autoridade. Não redefinimos globalmente as unidades do inventário.

**Vg2 impede coleta sem massa e rendimento revisados**, inclusive para registros legados com sugestão de estoque. Sua referência visual pode existir sem autorizar os recursos. Um item canônico que já existe com massa zero não é alterado: a tentativa exige uma migração explícita futura e não retira estoque. Vg1 continua reproduzindo seus resultados antigos, sem reescrever itens ou saves.

Testes transacionais usaram uma **fixture sintética**, claramente identificada como teste: massa de 5.000 mg, uma unidade, pool de 20.000 mg, remoção de até 50% e conversão experimental de 1.000.000 mg por unidade de peso. Isso verifica os limites e o ledger, não aprova uma massa física para uma espécie real. O item entrou com peso 0,005 e foi contabilizado pela função existente do inventário; repetir a ação não duplicou o lote, revisitar não restaurou estoque e a colisão com item legado de massa zero foi recusada.

## Desempenho e persistência

Benchmark pareado em uma rota de 160 patches novos, mesmas fontes e processo:

| Consulta | Vg1 | Vg2 |
|---|---:|---:|
| Tempo total | 15,93 s | 2,04 s |
| Média por patch | 99,53 ms | 12,76 ms |
| Consulta em cache | 0,103 ms | 0,098 ms |

É uma amostra de rota com reaproveitamento regional, não garantia de latência no primeiro acesso isolado ou em qualquer hardware. Há cache máximo de 128 patches e 256 conjuntos regionais por sampler. Em 64 consultas instrumentadas Vg2: 4,14 MiB retidos e 4,22 MiB de pico, excluindo catálogo e fontes pré-carregadas. O catálogo continua o mesmo da Fase 1.0; esses números não são a memória total do processo.

A comparação completa por seed, incluindo ambos os geradores, perfis e janelas de 100 km, levou aproximadamente 57–66 s por seed. Não são materializados indivíduos ou populações planetárias inteiras para essas estatísticas.

Vg2 usa as tabelas de persistência existentes com novo descritor/versionamento JSON. Não é necessária alteração destrutiva de schema. Coleta mantém fence SQLite, savepoints, recibos idempotentes, estoques e remoção autoritativos. Um save Vg1 não troca para Vg2 no retorno à região. Crescimento, respawn, fauna e simulação contínua não foram implementados.

## Validação, reprodução e arquivos

**855 testes distintos aprovados:** 724 World Genesis/auditoria climática/Vg1; 91 de mapas, exploração, viagens, relógio e loot; 40 de Vg2, peso, ferramentas e reset. Os lotes não se sobrepõem; é um escopo selecionado de regressão, não toda a suíte do repositório. Resultados e hashes estão em `artifacts/vegetation-1.0.1/validation.json`; logs independentes em `artifacts/vegetation-1.0.1-*.log`. Os novos testes verificam dispatch, snapshots Vg1, nulidade, elegibilidade, cobertura, continuidade de emendas/polos, ordem, processos, caches, auditoria extrema, pools compartilhados, massa, conversão, persistência e coleta. O único aviso conhecido é a depreciação Starlette/httpx já existente no ambiente.

Dentro de `backend`:

```powershell
.venv/Scripts/python.exe -m scripts.calibrate_vegetation
.venv/Scripts/python.exe -m scripts.audit_vegetation_evidence
.venv/Scripts/python.exe -m scripts.preview_vegetation_calibration
.venv/Scripts/python.exe -m scripts.benchmark_vegetation_calibration
.venv/Scripts/python.exe -m pytest app/tests/test_vegetation_calibration_v2.py -q
```

Os validadores dependem dos snapshots anteriores de C3/W1 e Vg1; ausência de autoridade é um erro explícito. Para regenerar também o piloto planetário e sua galeria, executar `scripts.pilot_vegetation_structure` antes do preview.

Arquivos desta etapa:

- Novos: `vegetation/v2.py`, `vegetation/diagnostics.py`, `vegetation/evidence_audit.py`.
- Alterados: `vegetation/config.py` (configuração/contratos/dispatch), `vegetation/service.py` (persistência e coleta versionadas), `vegetation/field.py` (somente guarda de versão).
- Novo teste: `backend/app/tests/test_vegetation_calibration_v2.py`.
- Scripts: `calibrate_vegetation.py`, `audit_vegetation_evidence.py`, `preview_vegetation_calibration.py`, `benchmark_vegetation_calibration.py`, `pilot_vegetation_structure.py`.
- Documento atual e artefatos em `artifacts/vegetation-1.0.1/`, separados dos snapshots Vg1.

Há alterações preexistentes de outras fases no workspace; não foram revertidas nem atribuídas a esta etapa.

## Recomendação

**Aprovar `regional_canopy_v2` como referência visual experimental dos futuros mundos.** As janelas demonstram florestas extensas com variação interna, paisagens intermediárias e regiões áridas reconhecíveis. A troca frequente de IDs deixou de ser o principal mecanismo de variedade, e a cobertura não sofre uma penalidade sistemática para produzir diversidade.

Essa recomendação é sobre a fundação visual e seus diagnósticos, não uma aprovação de renderização 3D inexistente nem autorização para estoque/massa desconhecidos. Antes de ativar coleta Vg2 em campanhas, revisar os parâmetros por parte e a conversão de peso. As 96 espécies extremas aguardam provas físicas locais, explicitamente identificadas. Não é necessário reabrir clima ou hidrologia para resolver essas pendências.
