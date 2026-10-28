# World Genesis WGS2.4: identidade explorável

## Decisão e compatibilidade

O perfil experimental opt-in `world_genesis_ap1_tp1_wgs2_v5` conserva a seleção `natural_formations_wgs2_v2`, os pesos v24, as coberturas, o grafo de `LocationConnection` e a política vegetal canônica V4. Nenhuma campanha antiga é convertida. A mudança versionada é `WGS2_IDENTITY_R1`: cada nova instância V5 persiste fatos de geometria, escala, orientação, variações do catálogo e evidências E1/T1/H1 confirmadas. Indícios por arquétipo substituem a frase genérica somente na V5. Inspeção e investigação devolvem esses fatos e os acessos conhecidos; o narrador recebe os mesmos dados e pode produzir prosa. O fallback sem LLM usa a descrição do registro e suas variações.

O v24 permanece imutável. `observable_visual` preserva a forma do registro, omitindo alegações de plantas, ventos sazonais e efeito térmico que E1/Vg2 não confirmaram. Variações de cobertura arbórea, altura vegetal, exposição ao vento, sazonalidade, duração, número de salas, vias de acesso e acessibilidade não são apresentadas como fatos efetivos sem materialização correspondente. A altura de teto escolhida para a cavidade V5 é incorporada à dimensão vertical da instância. A saída `known_accesses` vem apenas das conexões descobertas pelo personagem no local atual. Os campos `confirmed_physical` excluem valores ausentes; substratos regionais não são declarados minerais expostos nem jazidas. O mapa e os indícios não recebem coordenadas nem nomes de formações ainda desconhecidas.

## Auditoria dos 20 arquétipos

Legenda: C = catalogado, S = selecionável pelo WGS2 v2, A = adaptador implementado, E = elegível com evidência indicada, M = materializável, X = explorável pelo grafo, H = validado por HTTP no perfil V5. `cond.` exige o contexto físico. `—` significa não demonstrado, não impossibilidade. Todos os 20 são C/S/A; nem todos passam E/M em qualquer ponto. O percurso HTTP orgânico não força candidatos; a coluna H identifica separadamente os quatro casos injetados em SQLite de teste com evidência real.

| ID | Família | E / limite principal | M/X | H V5 |
|---|---|---|---|---|
| 0036 | WGS1 relevo | terra, relevo/contexto V2 | cond. | — |
| 0042 | WGS1 vale rochoso | terra, relevo/contexto V2 | cond. | — |
| 0050 | WGS1 cavidade | terra, cavidade local | cond.; interior e retorno | — |
| 0068 | WGS1 nascente local | terra, contexto V2 | cond.; estoque local finito | — |
| 0236 | WGS1 refúgio | terra, contexto V2 | cond.; sombra V4/V5 | — |
| 0020 | aberta | E1 campo de altitude | cond.; acesso externo | — |
| 0021 | aberta | E1 savana | cond.; acesso externo | — |
| 0023 | aberta | E1 pastagem natural | **controlada**; faixa de solo com ida/volta | controlado |
| 0081 | aberta | E1 dunas | cond.; acesso externo | — |
| 0033 | rochosa | T1 declive local | cond.; acesso externo | — |
| 0037 | rochosa | T1 declive local | **controlada**; acesso externo | controlado |
| 0041 | rochosa | E1 encosta instável + T1 declive | cond.; acesso externo | — |
| 0193 | rochosa | T1 declive; eco não simulado | cond.; acesso externo | — |
| 0049 | cavidade | umidade local não confirmada | **bloqueada** | — |
| 0051 | cavidade | terra; geometria da instância | **controlada**; interior e retorno | controlado |
| 0082 | árida | E1 deserto pedregoso | **controlada**; sob o arco com ida/volta | controlado |
| 0084 | árida | E1 terras argilosas erodidas | cond.; acesso externo | — |
| 0086 | árida | E1 deserto pedregoso | cond.; acesso externo | — |
| 0225 | refúgio | E1 bosque aberto **e** pradaria | cond.; acesso externo | — |
| 0226 | refúgio | E1 escarpa rochosa + T1 declive | cond.; acesso externo | — |

`0017` e `0179` continuam pendentes fora da seleção: pedem vegetação persistida. Os 13 novos registros além da cavidade úmida bloqueada e do ecótono condicionado compartilham adaptadores existentes; não constituem 13 mecânicas únicas. Variações de aparência, foco de investigação e fatos físicos mudam a informação obtida. `0051` possui entrada, inspeção interior e retorno. `0023` e `0082` ganham, apenas na V5 e quando o vão amostrado comporta a passagem (300 m e 100 m, respectivamente), uma subárea de superfície curta com ida/volta pelo grafo existente. A primeira acompanha as faixas de solo escuro do registro; a segunda passa sob o arco rochoso. `0037` mantém inspeção externa, sem autorizar escalada. Escalada, abrigo contra vento, mineração e coleta não são ativados por uma descrição do catálogo.

## Demonstração controlada com evidência real

Na seed 42 e raio de referência, o teste força apenas a escolha do candidato em quatro células; a amostra E1/T1/H1 e os gates permanecem reais. Os quatro pontos passaram elegibilidade: `0037` com altitude T1 de 1.072,431 m; `0051` com 1.104,474 m; `0082` com 1.140,220 m; `0023` com 836,641 m. O teste materializou quatro instâncias em quatro famílias, verificou inspeção e investigação com quatro focos distintos, deduplicação, conexões e persistência após commit/reload. Em `0051`, entrada e saída da cavidade foram verificadas. Em `0023`/`0082`, rotas de subárea, retorno e `validate_travel` passaram; a inspeção dentro da subárea trouxe fatos distintos. O teste confirmou que uma conexão não descoberta não aparece em `known_accesses`, e a saída aparece após descoberta explícita. Nenhum local foi descoberto automaticamente pelo teste. A demonstração prova suporte funcional sob evidência real, não frequência orgânica. A V5 conserva o mesmo seletor e a mesma chance por célula da V4.

## Microambientes e limites

Somente a sombra canônica de `0236` modifica Vg2. Declive T1 e o registro `0226` não demonstram por si só abrigo contra vento, redução térmica ou balanço hídrico; não foi criado um segundo modificador. E1 informa habitats potenciais e Vg2 mantém a autoridade de plantas individuais. Não se introduziram recursos, fauna, flora ou novos pontos de água.

Os dados atuais distinguem a forma geométrica e a investigação; o acesso externo ainda é compartilhado por todas as famílias. As duas subáreas V5 são passagens pedestres curtas, com âncoras esféricas e distâncias reais. Elas não têm bônus climático, estoques, risco próprio ou novas regras de viagem. Outras subáreas sugeridas no catálogo permanecem não materializadas. Formações minerais específicas não estão entre os 20 IDs selecionáveis; J1/JR1 oferece apenas contexto regional, sem autorização para extrair ou afirmar afloramento local. Uma expansão futura deveria validar um contrato de exposição de substrato e ações de travessia condicionadas à geometria, antes de apresentá-las como mecânicas.

## Validação e desempenho

Foram aprovados 35 testes direcionados de WGS2, formações locais, microambientes e ecologia canônica (121,35 s). Após a inclusão das subáreas e do filtro de acessos descobertos, os 8 testes WGS2.4 passaram novamente (11,48 s). A versão final dos fatos observáveis passou em 13 testes WGS2.4/canônicos (18,50 s) e em 8 testes WGS2.4 (6,95 s). O teste de interface do perfil V5 aprovou 8 casos. `git diff --check` não encontrou erros de whitespace; Git emitiu avisos de finais de linha já existentes. O teste de backend registrou um aviso de depreciação Starlette/httpx. O Vitest encerrou com código 0 e avisou que o servidor demorou a fechar.

O smoke real usou Uvicorn, LLMs desativadas, seed 42, SQLite temporário e perfil V5. Criação/início, consulta de plantas, movimento TP1, observação, reinício e retomada passaram. O mapa antes/depois permaneceu igual, sem coordenadas ocultas; o banco principal teve hash idêntico antes/depois. O primeiro início levou 33,775 s e o deslocamento 2,182 s. O percurso curto não gerou candidatos nem formações orgânicas. O smoke final, ainda em SQLite temporário, iniciou em 18,653 s e deslocou em 1,394 s; depois materializou quatro formações em pontos da seed 42 com E1/T1/H1 reais, forçando apenas a escolha do candidato na fixture. Via HTTP real, quatro inspeções, quatro investigações e três inspeções de interior/subárea retornaram os IDs e fatos corretos. Uma inspeção adicional após reiniciar o servidor preservou a identidade da última subárea. A rotina sem fixture continua inalterada. Esses tempos não são comparação controlada V4/V5 nem benchmark de inicialização; a variação entre execuções pode refletir aquecimento de SO e cache.

O microbenchmark aquecido `backend/scripts/benchmark_wgs2_identity.py` avaliou 2.000 células e produziu 2.000 payloads de identidade: 105 seleções, 50,688 ms para a seleção v2 inalterada, 11,645 ms para os payloads (aproximadamente 0,006 ms por instância) e pico Python `tracemalloc` de 1,39 MiB para ambos os conjuntos retidos. O adaptador é executado uma vez por materialização; a observação usa o JSON persistido e uma consulta de conexões descobertas. Não medimos isoladamente consulta E1, commits e percepção HTTP em massa; a latência de preparação do mundo continua dominante no smoke. Não se repetiu o benchmark geofísico de bootstrap.

Resultados sanitizados: [`artifacts/wgs2-variety/smoke.json`](../artifacts/wgs2-variety/smoke.json) e [`artifacts/wgs2-variety/controlled-http.json`](../artifacts/wgs2-variety/controlled-http.json). Reproduzir o segundo ensaio com `python scripts/playtest_wgs2_canonical_http.py world_genesis_ap1_tp1_wgs2_v5 controlled-variety` dentro de `backend`.

## Arquivos e próxima expansão

- `backend/app/game/world/genesis/wgs2_identity.py`: apresentação, indícios e fatos estruturados V5.
- `backend/app/game/world/genesis/local_formations.py`: persistência da identidade, duas subáreas com acesso esférico, inspeção e filtragem de conhecimento.
- `backend/app/game/world/genesis/playable.py` e `backend/app/game/world/genesis/vegetation/microhabitat_canonical.py`: perfil V5 com a mesma política ecológica canônica V4.
- `backend/app/api/routes/actions.py`, `backend/app/api/routes/campaigns.py`, `backend/app/game/perception/service.py`, `backend/app/schemas/campaign.py`, `frontend/src/pages/CampaignSetupPage.tsx` e `frontend/src/features/game/GameScreen.tsx`: despacho do perfil, narrativa e interface.
- `backend/app/tests/test_genesis_wgs2_variety.py`, `frontend/src/pages/CampaignSetupPage.test.tsx`, `backend/scripts/playtest_wgs2_canonical_http.py`, `backend/scripts/benchmark_wgs2_identity.py`: testes e ensaios reproduzíveis.

Próxima expansão recomendada: validar evidência local de afloramento e travessias condicionais com regras de risco existentes antes de liberar formações minerais, escalada ou abrigo climático. Manter o seletor e a frequência atuais até existir amostragem orgânica mais ampla.
