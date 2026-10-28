# World Genesis — fase 0.3.2: distribuição tectônica por área

## Auditoria e decisão antes da implementação

Revisados nucleação, configuração, plano/carregamento, dispatch, materialização, área esférica, diagnóstico e refinamento R1. V3 ativa candidatos uniformemente nas coordenadas das faces e restringe o jitter ao centro de cada célula. Isso concentra sites por área perto dos cantos; corrigir só os pixels do relatório não corrige a nucleação. Há também um limite importante: ponderar probabilidades por área e depois truncá-las individualmente em 100% recriaria viés nos raios gigantescos.

Decisão: criar configuração/gerador **V4**, mantendo o modelo cinemático e os campos de relevo da V3 como implementação compartilhada congelada. Mudar somente a política de sites: probabilidade proporcional à área real de cada candidato e amostragem proporcional ao jacobiano esférico dentro de toda a célula. Se a intensidade solicitada ultrapassar a capacidade da grade, reduzir a intensidade **globalmente**, preservando a proporcionalidade, em vez de saturar regiões específicas. O número de placas continuará variável.

Os pesos das 64 células geométricas de uma face serão calculados com `cell_solid_angle`, quantizados e fixados no contrato V4. A tabela versionada evita depender de diferenças de libm entre máquinas durante a geração autoritativa. Testes compararão a tabela com a função de área existente. A rejeição dentro de célula usará aritmética inteira e orçamento fixo; não haverá fallback para jitter plano que reintroduza o viés.

Planos V3, hashes, configuração, snapshots e R1 V3 devem continuar idênticos. V4 opt-in compartilhará persistência e topologia; não haverá conversão de saves, novas simulações, hidrologia, clima ou alterações do mapa público.

## Implementação entregue

### Configuração e composição de versões

`FormationConfigV4` fixa `config_version=4` e `generator_version=4`, herdando os parâmetros e a calibração espacial existentes. O raio inicial continua **63.710 km**, configurável até 10^12 m. V3 continua sendo `FormationConfig`; validar uma configuração V4 como V3 é erro, não conversão.

V4 troca a política de **nucleação e posição dos sites**. Propriedades geológicas por slot — crosta, idade, eixo e velocidade — foram extraídas para um helper com a fórmula V3 congelada, compartilhado pelas duas versões. Os campos de ruído/relevo e a reconstrução cinemática também permanecem no modelo V3 compartilhado. As fontes novas de ativação, posição e aceitação usam namespace de aleatoriedade **4**, independente por slot, tentativa e subsistema. Esse arranjo isola a correção sem acrescentar física nova.

Planos têm `kind=plate_formation_v4`, configuração completa, assinatura própria e seus sites efetivos persistidos. Os caminhos V3 continuam produzindo `plate_formation_v3` e os mesmos dados anteriores. `load_plan` verifica espécie de plano, seed, configuração e assinatura. Snapshots esféricos guardam `generator_version=4` para mundos novos V4; a tabela existente é suficiente, pois a versão é fixada no mundo por campanha.

### Probabilidades proporcionais à área, sem saturação regional

Há os mesmos **384 candidatos potenciais**, em nível 3, como limite de planejamento. Isso não fixa a quantidade de placas nem de continentes. Para cada candidato, Wᵢ é a área esférica quantizada de sua célula, calculada a partir de `sphere_area.cell_solid_angle` e congelada em uma tabela simétrica de **16 inteiros**. Os testes verificam as 384 células contra a função original; o erro absoluto de quantização é menor que 0,51×10⁻¹² esterradianos por célula.

A intensidade solicitada ainda deriva de área planetária/escala física de placas. Em termos conceituais:

```text
λ = min(quantidade esperada / soma(W), 0,95 / maior(W))
probabilidade da célula i = λ × Wᵢ
```

O código aplica a fórmula com inteiros de 63 bits para os sorteios, com arredondamento inferior a uma unidade da distribuição. O teto de 95% é aplicado à **intensidade global**, não a cada probabilidade já calculada. Portanto, mesmo nos raios extremos, a razão probabilidade/área continua uniforme. Um teto individual de `min(pᵢ,1)` teria subamostrado os centros das faces novamente.

Essa escolha mantém a quantidade esperada em ~106 placas no raio de referência. Quando a densidade desejada não cabe na grade com essa margem de ativação, a expectativa global cai para ~203, em vez de saturar regiões específicas. Não foi imposto um número efetivo; a quantidade continua variando com a seed.

O mínimo estrutural de dois sites, já necessário ao modelo de placas, permanece. Se faltarem sites, a escolha adicional usa CDF ponderada por área entre candidatos ainda disponíveis, com namespace próprio. Não se exige terra, oceano, arquipélago ou qualquer quantidade de massas continentais.

### Posição proporcional à área dentro da célula

Ponderar apenas a ativação deixa um viés residual se o jitter interno continuar plano. V4 usa toda a célula e aceita posições proporcionalmente ao jacobiano radial:

```text
J(u,v) = (1 + u² + v²)^(-3/2)
aceitação = J(u,v) / máximo de J dentro da célula
```

Posições são geradas numa malha fixa de 2²⁰ subdivisões por eixo, em centros de intervalos. A comparação de aceitação usa quadrados, cubos e raiz quadrada inteira: **nenhuma função transcendental de ponto flutuante participa da geração autoritativa**. A tabela de pesos também elimina dependência de libm na ativação. A aproximação discreta e a quantização são fixadas pelo gerador V4.

O orçamento é de **128 tentativas por site**, com probabilidade de aceitação por tentativa >1/2 nessa grade. Um esgotamento resulta em erro explícito, sem jitter plano de fallback, seed substituta ou resultado enviesado. Sob o modelo pseudoaleatório, o limite conservador de probabilidade de esgotamento é inferior a 2⁻¹²⁸ por site; isso não é uma prova sobre todo o espaço de seeds. O teste força o esgotamento e verifica a parada. Nenhum dos casos estatísticos/visuais testados esgotou o orçamento.

O pior custo continua limitado por 384 candidatos e pelo orçamento fixo de sites. Nenhum setor do planeta é enumerado para distribuir placas.

## Validação por área

### Mesmas 15 seeds, raio de 63.710 km

As seeds `0, 1, 2, 3, 4, 5, 7, 11, 17, 23, 42, 73, 101, 2026, 8675309` foram avaliadas nas duas versões, com a mesma resolução diagnóstica L6, 24.576 pontos por mundo e os pesos de área da fase anterior.

| Zona do cube-sphere | Densidade relativa V3 | Densidade relativa V4 |
| --- | --- | --- |
| Centro das faces | 0,659 | 1,000 |
| Bordas | 1,081 | 1,001 |
| Cantos | 1,604 | 0,997 |

Valor 1 significa sites por área iguais à média da superfície. As zonas são as mesmas da auditoria anterior: centro com `max(|u|,|v|)<0,5`, cantos com ambas as coordenadas ≥0,5 em módulo, bordas restantes. A área dessas zonas é calculada pela projeção esférica, não por contagem de células.

Não se exige uniformidade em uma seed isolada. A seed 42, por exemplo, ainda pode apresentar concentração casual em uma zona. A correção é a **distribuição probabilística por área**, não um mecanismo que reposiciona placas para preencher cotas.

### Estatística ampliada: 512 seeds por raio

Foi amostrada somente a nucleação das seeds **0..511**, em quatro raios, nas duas versões: **4.096 inventários de placas**. Esse estudo não gerou milhares de planetas em alta resolução. O script percorre os inventários em sequência, mantendo apenas contagens agregadas.

| Raio km | V3 centro / borda / canto | V4 centro / borda / canto | Média de placas V3 → V4 |
| --- | --- | --- | --- |
| 6.371 | 0,634 / 1,111 / 1,579 | 1,028 / 0,985 / 0,975 | 10,60 → 10,66 |
| 63.710 | 0,645 / 1,093 / 1,604 | 0,993 / 1,006 / 1,001 | 105,90 → 106,88 |
| 637.100 | 0,647 / 1,089 / 1,611 | 0,998 / 1,001 / 1,001 | 268,16 → 203,54 |
| 10⁹ | 0,647 / 1,089 / 1,611 | 0,998 / 1,001 / 1,001 | 268,16 → 203,54 |

No raio de referência, a quantidade V4 variou de **82 a 137 placas** entre essas 512 seeds; nos maiores raios, de **164 a 232**. A uniformidade por área foi mantida no regime de teto global. A variação maior nas estatísticas do planeta menor é compatível com seu número muito menor de sites.

Arquivos: `density-statistics.json`, `density-comparison.png` e `v3/site-density.json` / `v4/site-density.json`, em `artifacts/tectonic-distribution-0.3.2/`. O teste de distribuição condicional dentro de uma célula também compara 4.096 posições com a área exata de uma subdivisão, distinguindo o resultado de jitter uniforme nas coordenadas da face.

## Comparação da geografia e continuidade

Foram refeitas as **22 combinações seed/raio da fase anterior em cada versão**, totalizando 44 planos e amostragens globais diagnósticas. São 15 seeds no raio de referência, três delas em 6.371 km e 637.100 km, e a seed 42 no limite de 10⁹ km. As comparações visuais usam a mesma seed, o mesmo raio e L6, lado a lado.

| Métrica nas 15 seeds de referência | V3 | V4 |
| --- | --- | --- |
| Cobertura terrestre ponderada | 32,88%–45,69% | 30,53%–50,04% |
| Componentes terrestres diagnósticos L6 | 34–97 | 26–79 |
| Placas nas 15 seeds | 83–121 | 88–110 |
| Discordância macro/local ponderada | 3,39%–4,35% | 3,38%–4,43% |
| Faixa de altura amostrada | −7.327 a 11.745 m | −7.334 a 12.833 m |

Nenhuma das 44 amostras ficou sem terra ou sem água. Os atlas inspecionados mantiveram variedade de massas, oceanos e estruturas, sem resultados sistematicamente planos ou preenchidos por um único tipo de superfície. Essas observações não garantem diversidade obrigatória em toda seed possível.

As contagens de componentes são diagnósticas e continuam dependentes da resolução. A correção de sites **não resolve** a conectividade de ilhas, estreitos ou rios locais identificada na fase 0.3.1. Os campos cinemáticos continuam globais; não há elevação independente por face, e os testes verificaram igualdade de geologia/IDs nas 24 orientações de emenda, interiores de setores e perturbações nos polos/vértices.

Imagens principais:

- `paired-reference.png`: V3/V4, mesmas 15 seeds, em pares adjacentes.
- `paired-radii.png`: comparações dos sete casos de outros raios.
- `density-comparison.png`: distribuição por área nas quatro escalas.
- `benchmarks-v4/coast-r-63710000/coast.png`: exemplo de R1 aplicado a um mundo V4.

Tabelas completas estão em `version-comparison.md`, `v3/comparison.*` e `v4/comparison.*`. Não foram alterados mundos V3 para torná-los visualmente parecidos com os novos.

## Persistência, compatibilidade e R1

- Os **22 planos V3** reproduzidos nesta fase foram comparados integralmente com as exportações congeladas da fase 0.3.1: **todos idênticos**, incluindo placas, configuração, labels e componentes. Evidência: `v3-compatibility.json`.
- O vetor SHA-256 anterior do plano V3 e a elevação conhecida continuam iguais. O SHA-256 de um patch R1 V3 completo também foi congelado e conferido: formato, IDs, relações e valores anteriores foram mantidos.
- Configuração V4 é explícita; um save V3 não pode ser reinicializado como V4. Configuração omitida mantém o contrato genérico anterior, sem mudança dos defaults públicos. Usar V4 em novo mundo requer `FormationConfigV4()`.
- `materialize_sector` recupera snapshots antes de gerar, e setores novos usam o plano persistido da versão correta. Testes proíbem a reconstrução do plano/nucleação durante recarga e preservam `changes` nas duas versões.
- V4 usa o mesmo esquema de persistência esférica, âncoras e coberturas. **Não houve migração de esquema ou conversão de coordenadas.** O banco real não foi aberto para gravação.
- R1 continua com `refinement_version=1`, mesmo algoritmo, limites, portas e garantia local/amostrada. `source_generator_version` passa a aceitar 4 além de 3. A assinatura do plano já separa os IDs de mundos diferentes. Nenhum ID macro antigo é substituído ou fundido.
- R1 continua `baseline_only`: não aplica ou apaga acontecimentos de terreno, não autoriza travessias e não modifica o grafo de movimento ou o mapa público.

## Desempenho e memória

Microbenchmarks das duas versões, seed 42, com 12 setores dispersos por raio:

| Raio km | Plano frio V3 → V4 | Setor, mediana V3 → V4 | Pico Python de patch R1 V4 |
| --- | --- | --- | --- |
| 6.371 | 0,043 → 0,045 s | 1,52 → 1,60 ms | ~3,00 MB |
| 63.710 | 1,568 → 1,583 s | 4,21 → 4,17 ms | ~3,08 MB |
| 637.100 | 2,253 → 2,095 s | 6,14 → 5,63 ms | ~3,17 MB |
| 10⁹ | 2,241 → 2,119 s | 5,92 → 5,72 ms | ~2,98 MB |

Os custos permaneceram na mesma ordem. Não atribuir pequenas diferenças exclusivamente ao algoritmo: as versões foram medidas em processos de desenvolvimento paralelos, os mundos têm quantidades/posições diferentes de placas e não houve isolamento de CPU. Memória é pico de alocações Python rastreadas na operação, não RSS ou memória total do jogo. Arquivos completos com profiling: `benchmarks-v3/benchmarks.json` e `benchmarks-v4/benchmarks.json`.

Os limites permanecem: até 384 placas, plano macro até 6.144 células, até 33×33 amostras por setor, caches já limitados e R1 com orçamento próprio. A correção não exige gerar setores distantes. Os tempos de patches ainda não são apropriados para execução a cada frame; nenhum worker ou serviço contínuo foi adicionado.

## Ferramentas e reprodução

Executar em `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_planets --formation-version 3 --level 6 --compare-radii --output ../artifacts/tectonic-distribution-0.3.2/v3
.\.venv\Scripts\python.exe -m scripts.validate_planets --formation-version 4 --level 6 --compare-radii --output ../artifacts/tectonic-distribution-0.3.2/v4
.\.venv\Scripts\python.exe -m scripts.compare_tectonic_versions --root ../artifacts/tectonic-distribution-0.3.2 --v3-baseline ../artifacts/planet-validation-0.3.1 --density-seeds 512
.\.venv\Scripts\python.exe -m scripts.benchmark_planets --formation-version 4 --output ../artifacts/tectonic-distribution-0.3.2/benchmarks-v4
.\.venv\Scripts\python.exe -m scripts.preview_planet --formation-version 4 --seed 42 --output ../artifacts/preview-v4
```

Os viewers agora carregam planos V3/V4 pelo dispatch validado e mostram a versão correta nas legendas. As ferramentas e exportações continuam offline, sem acesso ao banco ou exposição ao jogador.

Uso interno de um novo mundo:

```python
from app.game.world.genesis.formation_v4 import FormationConfigV4
from app.game.world.genesis.service import initialize_world

world = initialize_world(db, new_campaign_id, FormationConfigV4(radius_m=63_710_000))
# Chamador mantém o controle de commit/rollback e da materialização inicial.
```

## Arquivos desta fase

| Arquivo | Mudança |
| --- | --- |
| Novo `backend/app/game/world/genesis/formation_v4.py` | Configuração V4, pesos geométricos congelados, ativação por área e sampler condicional inteiro. |
| `.../genesis/formation_plates.py` | Extração das marcas V3 para helper compartilhado, sem mudança de valores V3. |
| `.../genesis/formation_plan.py` | Seleção da política V4 e kind/carregamento explicitamente versionados. |
| `.../genesis/formation_geography.py` | Tag de snapshot derivada da configuração fixada, preservando o valor 3 em V3. |
| `.../genesis/sphere_config.py` | Dispatch explícito de configuração 4. |
| `.../genesis/coast_refinement.py` | R1 aceita fonte V4 e mantém a fonte V3/garantias anteriores. |
| `.../genesis/formation_preview.py`, `coast_preview.py`, `validation_report.py` | Legendas/metadados versionados e carregamento correto de ambas as versões. |
| `backend/scripts/validate_planets.py`, `preview_planet.py`, `benchmark_planets.py` | Opção `--formation-version`, mantendo default 3 e fluxos anteriores. |
| Novo `backend/scripts/compare_tectonic_versions.py` | Atlas pareado, estatística de distribuição em sequência e conferência de planos V3 congelados. |
| Novo `backend/app/tests/test_genesis_formation_v4.py` | Testes V4, estatística, compatibilidade, orçamento, ferramentas e R1. |
| `backend/app/tests/test_genesis_sphere_topology.py` | Versão desconhecida do teste mudou de 4 para 5, porque 4 passou a existir. |
| Novo `docs/world-genesis-phase-0.3.2.md` | Decisões, resultados, garantias, limites e parecer. |
| Novo `artifacts/tectonic-distribution-0.3.2/` | Auditorias V3/V4, comparação visual, estatísticas, compatibilidade e benchmarks. |

Arquivos e resultados anteriores da fase 0.3.1 foram preservados. Não houve alteração de exploração, movimento, rotas públicas, frontend ou qualquer dataset.

## Testes executados

**345 testes selecionados passaram: 301 anteriores e 44 novos.** Incluem v1/v2/v3/v4, mapas, descoberta, viagens, fronteiras, materialização, tempo, escopo de simulação e exclusão de campanha. Não foi executada a suíte inteira do backend ou frontend.

Os novos testes verificam: tabela contra área real; probabilidade proporcional sem saturação regional em cinco raios; distribuição interna de célula; orçamento de rejeição e mínimo estrutural; 256 seeds em quatro raios; vetores congelados V3 e R1; vetor V4 e processos com PYTHONHASHSEED diferente; ordem de geração; igualdade nas 24 orientações de emenda e em setores interiores; polos/vértices; R1 V4 e suas portas; persistência/alterações V3+V4; recarga sem reconstrução; rejeição de conversão de versão; escala extrema; viewers, exportações e comparador offline.

`compileall`, `git diff --check` e cadeia Alembic foram verificados. A cabeça segue única, `i17i1d2e3f4g`. Permanece apenas o aviso de depreciação Starlette/httpx preexistente nos testes.

## Limitações e parecer

A correção remove o viés de **densidade por área** identificado. O processo ainda é estratificado em candidatos finitos, com no máximo um site por célula; não é um processo de Poisson contínuo nem promete uniformidade perfeita em cada seed. A quantização de pesos/posições é explícita e inferior à variabilidade estatística observada. O orçamento de rejeição tem falha explícita extremamente improvável, não fallback enviesado.

As limitações anteriores de escala angular em raios extremos, precisão macro de costa e conectividade amostrada continuam. V4 não acrescenta microformas ausentes, erosão, água, clima ou física geológica adicional. Corrigir distribuição de sites não transforma IDs macro em limites físicos exatos.

**Parecer: V4 está estável para encerrar esta correção da formação planetária e avançar para hidrologia e clima.** Recomenda-se V4 explicitamente para novos mundos, mantendo a leitura/reprodução completa da V3 nos existentes. A próxima fase deve planejar bacias e validar saídas/conectividade com resolução própria, reaproveitando R1, sem usar somente IDs macro como prova de que águas ou passagens estão conectadas.
