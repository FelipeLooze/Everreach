# Everreach World Genesis WGS2.1: desempenho

## Diagnostico

Os tempos de 48,8-80,6 s nao foram causados pela selecao WGS2. A selecao/materializacao de formacoes ocorre durante observacao/viagem, depois do bootstrap. No benchmark controlado, AP1 base, WGS1 v2 e WGS2 tiveram tempos proximos; o custo dominante comum e a preparacao autoritativa AP1 (H1, C3, W1, W2) e a procura do local inicial.

O perfil encontrou recomputacao de validacao dentro do mesmo request. `find_start` e `encounter` ja carregavam um `VegetationSampler` validado, mas materializacao de comunidades e individuos voltava a chamar `context()`. Isso recalculava checagens de assinatura/checksum de ambiente, clima, hidrologia e agua por cada candidato. Tambem havia consultas ambientais repetindo a validacao do sampler. As chamadas SQL somavam milissegundos, nao dezenas de segundos.

## Correcao

- Adicionado parametro privado `_sampler` nas funcoes internas de materializacao/consulta de comunidade e ambiente, preservando os caminhos publicos: sem sampler fornecido, continuam validando e carregando a autoridade como antes.
- `find_start`, `encounter` e o ciclo de vida do individuo reutilizam o sampler validado do request ao chamar essas funcoes.
- Nenhuma regra de elegibilidade, seed, resultado geografico, materializacao antecipada, perfil de campanha, peso do seletor WGS2 ou dataset foi alterado. Nenhum cross-campaign cache foi introduzido.
- Uma regressao WGS1 v2 revelou que a direcao de pista persistida continha caracteres de substituicao apesar de o contrato/teste esperar “indicio proximo”. Corrigida a grafia, sem mudar descoberta ou conectividade.

## Ambiente e protocolo

Windows x64, Python 3.12, SQLite temporario, aplicacao FastAPI via TestClient in-process, sem chamadas externas (provedores LLM desativados). Perfis AP1 base, WGS1 v2 e WGS2 v1; seeds 42, 7 e 2026; execucao sequencial, nao concorrente. A primeira campanha do processo mede runtime frio; as seguintes medem processo aquecido, mas cada seed continua usando uma autoridade geofisica propria. Um ensaio WGS2 dedicado em processo isolado repetiu as tres seeds. SQLAlchemy mediu quantidade e tempo total de execucao dos statements. O consumo de memoria foi obtido pelo working set do processo Windows, sem tracemalloc durante os cronometros.

Os valores historicos de WGS1 (17-28 s) vieram de outra carga/ambiente e nao sao comparaveis a este protocolo.

## Benchmark matched antes/depois

Tempos totais de `/start`, em segundos, na ordem das seeds 42 / 7 / 2026:

| Perfil | Antes | Depois |
|---|---:|---:|
| AP1 base | 63,3 / 44,5 / 50,6 | 45,4 / 36,6 / 36,7 |
| WGS1 v2 | 68,7 / 44,9 / 51,9 | 43,3 / 37,7 / 34,4 |
| WGS2 v1 | 67,4 / 44,6 / 51,2 | 39,4 / 31,5 / 30,9 |

Os tempos absolutos variam entre repeticoes e posicao na sequencia; o perfil e a seed permaneceram iguais. A matriz mostra que WGS2 nao adicionava custo consistente sobre WGS1/AP1. A queda aparece nos tres perfis apos a reutilizacao interna, indicando correcao de custo comum do fluxo vegetal.

Ensaio WGS2 dedicado, com instrumentacao detalhada identica antes/depois (segundos):

| Seed | `/start` antes -> depois | `find_start` antes -> depois | `encounter` antes -> depois |
|---|---:|---:|---:|
| 42 | 72,880 -> 51,177 | 25,147 -> 5,197 | 7,830 -> 1,973 |
| 7 | 45,173 -> 40,879 | 2,178 -> 0,881 | 7,859 -> 1,834 |
| 2026 | 51,846 -> 42,112 | 12,683 -> 2,401 | 5,002 -> 1,217 |

O ganho de `find_start` e `encounter` se repetiu nas tres seeds. O tempo total e mais variavel porque inclui a preparacao global e o primeiro carregamento. A selecao WGS2 nao ocorre durante `/start`.

## Subsistemas e recursos

No perfil WGS2 pos-correcao, as faixas observadas nas tres seeds foram:

| Subsistema | Tempo observado |
|---|---:|
| V4 / plano planetario | 1,9-2,4 s |
| H1 hidrologia global | 13,4-14,9 s |
| Clima C3 | 7,5-8,6 s |
| W1 balanco | 4,6-5,0 s |
| W2 reconciliacao | 3,8-4,0 s |
| Terreno T1 e HR1 regional | abaixo de 0,02 s cada |
| Geologia J1/JR1 | abaixo de 0,42 s combinados |
| E1 | abaixo de 0,46 s |
| Vg1/R1/L1/GA2 init | 1,4-6,7 s combinados |
| Territorio TP1 | 0,7-1,2 s; bootstrap AP1 tambem inclui os planos listados |
| Selecionar local inicial | 0,9-5,2 s pos-correcao |
| Persistencia/SQL | 1.871-3.518 statements; 0,14-0,23 s de execucao SQLite |

O tempo de CPU do processo no ensaio WGS2 dedicado foi 34,8-43,4 s por start (media 37,7 s), diante de 40,9-51,2 s de tempo decorrido. Com chamadas externas desativadas e SQL abaixo de 0,23 s, o custo restante e essencialmente CPU local de calculos/validacoes dos planos globais. O bootstrap serializa e valida H1/C3/W1/W2 de forma eager; deixa-los lazy exige um contrato de autoridade/assinaturas e transacoes sob demanda e nao foi feito aqui.

Working set apos cada start: 292 MB, 308 MB e 309 MB. O pico de working set do processo que executou os tres starts foi 475 MB. E uma medicao do processo/test harness, incluindo catalogos e caches residentes; nao equivale ao incremento isolado por campanha nem a RSS de um servidor com carga real.

## Observacao e viagem HTTP

Smoke executado apos a correcao em Uvicorn real e SQLite temporario, seed 7:

- Criou e iniciou a campanha WGS2 em 47,234 s.
- Explorou 5,209 km em oito celulas visitadas; percorreu arestas TP1 ativas.
- Avaliou tres candidatos, rejeitou dois sem as evidencias exigidas e materializou/descobriu/inspecionou `EV-LOC-0050` (selecao-base compativel).
- Completou visita/interacao/retorno e reiniciou o servidor; localizacao, mapa publico e reinspecao persistiram.
- Nenhum vazamento de coordenadas ocultas foi detectado.
- Latencia media observada: geracao/observacao 2,573 s; viagem 2,579 s. No playtest anterior da seed 7, os valores eram 2,170 s e 2,643 s; a diferenca pequena e variavel nao prova ganho no caminho HTTP de exploracao.

Relatorios completos: [`matched.json`](../artifacts/wgs2-performance/matched.json), [`matched-after.json`](../artifacts/wgs2-performance/matched-after.json), [`wgs2-instrumented.json`](../artifacts/wgs2-performance/wgs2-instrumented.json), [`wgs2-cpu.json`](../artifacts/wgs2-performance/wgs2-cpu.json) e [`http-smoke-seed-7.json`](../artifacts/wgs2-performance/http-smoke-seed-7.json). O harness reproduzivel esta em [`benchmark_wgs2_performance.py`](../backend/scripts/benchmark_wgs2_performance.py).

## Testes

- `test_look_is_lazy_local_and_repeated_observation_does_not_restock` e `test_genesis_wgs2_families.py`: 5 passaram.
- Persistencia ambiental e integracao espacial: 21 passaram. Seletores/contexto WGS1 direcionados: 4 passaram.
- WGS1 HTTP exploration cave/water/revisit: passou.
- WGS1 v2 persistencia e decisao de contexto falhou inicialmente por divergencia textual preexistente; apos corrigir o texto para o valor esperado, o caso passou junto dos quatro testes WGS2: 5 passaram.
- `/start` HTTP nos tres perfis e tres seeds: 9 respostas 200.
- Smoke HTTP WGS2 seed 7 passou, incluindo reinicio e retomada.
- `compileall` e `git diff --check` passaram. A suite completa nao foi executada.

## Limitacoes e proxima etapa

WGS2 nao e a causa do aumento inicial historico. A correcao remove custo repetido no seletor de local inicial e na observacao vegetal, com SQL reduzido em aproximadamente 23-36% no ensaio dedicado e sem diferencas de elegibilidade ou identidade. Ainda restam aproximadamente 26-33 s de calculos globais AP1/H1/C3/W1/W2 conforme a seed e a carga. O bootstrap de ambiente tem custo CPU alto e working set de processo significativo; a proxima otimizacao deve perfilar os planos globais em separado e provar que qualquer adiamento preserva assinaturas, inicializacao atomica e compatibilidade dos saves.

Esta etapa nao alterou configuracoes climatica/hidrologica/geologica, datasets, versoes WGS1/WGS2, conexoes de viagem nem saves reais. Nenhuma migracao foi executada no banco principal. O trabalho nao implementa cobertura multissetorial nem microambientes.
