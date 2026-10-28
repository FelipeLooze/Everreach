# World Genesis 1.1.2 — estabilização da renovação vegetal

A reprodução sexual abstrata **S1** amplia L2 por uma autorização explícita e assinada. O executor em lotes preserva as regras ecológicas L2 e o resultado de 224 novos indivíduos na seed 42. O contrato derivado **VSR1** mede cobertura e estratos a partir dos ocupantes persistidos, distinguindo recuperação da população e da copa.

V22, Vg2, C3, W1 e E1 não foram recalibrados nem editados. L1/L2 mantêm seus descritores, seeds e executor de referência. Não há fauna, NPC polinizador, novo item de semente, migração automática de campanha, simulação diária global ou Atlas.

**Limite restante:** grandes avanços ainda exigem preparação perceptível. A reprodução e a persistência estão estabilizadas; os números desta entrega não autorizam tratar um salto regional de vinte anos como operação instantânea de interface.

## Auditoria dos requisitos originais

O arquivo original `342f270b-c1b7-4ea0-baff-3af76536ce19/Pasted text.txt` foi relido. Termina efetivamente na seção 5, em “Não simular diariamente todas as árvores”. A busca por outra cópia da Fase 1.1.1 nos anexos disponíveis encontrou somente esse arquivo. Não foi presumido que existia uma parte final recebida.

Os requisitos completos desta solicitação 1.1.2 foram aplicados explicitamente:

| Área | Verificação realizada |
|---|---|
| Compatibilidade | L1/L2 preservados, S1 opt-in, migração aditiva, descritores antigos intactos, nenhuma ativação real |
| Persistência | IDs, tombstones, bancos finitos, reinício, revisitas, rollback, replay e undo |
| Desempenho | Mesmo snapshot inicial, horizontes independentes de 1/5/10/20 anos e igualdade do estado completo |
| Visualização | Original, devastada, 1/5/10/20 anos; copas, altura, densidade e estratos; sem mapa público |
| Condições negativas | Excepcionais, agente especializado obrigatório, ausência de par maduro, fora de estação e extinção sem fonte |

## Reprodução sexual S1

### O bloqueio encontrado

No v22, 1.108 espécies declaram `sementes_e_polinização` e 51 declaram `sementes_ou_mudas`. L2 conservadoramente mantinha essas 1.159 estratégias pendentes por falta de mecanismo/vetor determinado. A ausência de especificação não comprova dependência obrigatória de um animal especializado.

A leitura integral do catálogo encontrou a cautela genérica de cultivo “podem impedir” em 1.500 perfis, mas **nenhuma exigência reprodutiva explícita de agente especializado específico** nos campos auditados. A cautela não foi transformada em autorização de ocorrência nem em obrigação universal de fauna. Condições físicas especiais e autorizações canônicas continuam sob os contratos anteriores.

S1 interpreta a estratégia sexual declarada como uma oportunidade abstrata e determinística de reprodução, sem afirmar que um polinizador foi observado ou criado. A autorização é uma regra versionada de gameplay, não uma medição de fertilidade ou genética.

| Contratos de catálogo | Antes | Depois de S1 |
|---|---:|---:|
| Rotas já autorizadas por L2 | 1.771 | 1.771 preservadas |
| Rotas sexuais antes pendentes | 1.159 | **1.159 autorizadas por S1** |
| Total com contrato reprodutivo | 1.771 | **2.930** |
| Excepcionais sem autorização canônica | 166 | **166 bloqueadas** |
| Flores com contrato | 2 de 1.113 | **1.110 de 1.113** |

As 1.108 flores adicionais possuem contrato autorizado, não ocorrência garantida. As três flores restantes são excepcionais. `species-authorization.json` lista todas as 3.096 espécies, nome, tipo, raridade, situação anterior/nova e motivo de bloqueio. `authorization-audit.json` contém os totais e a divisão por tipo.

Fungos, algas, juncos, trepadeiras, consórcios e extremos mantêm os bloqueios locais de suporte, água, energia, substrato, micélio, geometria e anomalia das autoridades existentes. **Contrato reprodutivo não cria um habitat elegível.** Um requisito especializado explicitamente obrigatório continua impedindo S1; os testes exercitam essa rejeição sem modificar o v22.

### Requisitos físicos e finitude

S1 exige dois indivíduos maduros distintos da mesma espécie. O modelo não presume autofecundação, sexo botânico observado, ploidia ou compatibilidade genética medida. A compatibilidade simplificada é registrada como `conspecific_mature_pair_S1`.

Os progenitores precisam pertencer à coorte produtora, ter microsítio elegível e estar dentro do alcance configurado. O evento registra progenitor, parceiro, posições técnicas, assinatura S1 e `pollinator_entity=null`. Não nasce nenhum NPC ou entidade animal.

A produção conserva os orçamentos L2: reserva biológica modelada limitada por adulto/período, quota individual, teto do banco, viabilidade, débito único, estação, condições C3/W1/E1, dispersão e vaga. Os pacotes sexuais internos têm referência de viabilidade de 180 dias e não possuem item ou parte coletável. A janela trimestral existente permanece; não foi introduzida meteorologia diária.

Somente as estratégias anteriormente pendentes recebem o novo perfil. Rotas clonais e por esporos não são substituídas. A assinatura L2 continua sendo usada nos hashes existentes; a assinatura S1 é uma autorização adicional. Por isso, habilitar S1 não troca os IDs ou as probabilidades dos povoamentos arbóreos ABI já autorizados por L2.

`initialize_sexual_policy(..., experimental=True)` é explícito e prospectivo. Antes da ativação, os períodos antigos continuam seguindo L2; não há crédito retroativo de sementes. O vínculo com L2, o hash v22 e a auditoria de obrigações entram no descritor assinado. Corrupção, ausência ou incompatibilidade da autorização bloqueia seu uso.

## Resultados reais nas cinco seeds

Foram usados V4/T1, C3 R1-55, W1, E1, Vg2, R1 e L1/L2 existentes, no raio de 63.710 km. Os cenários foram criados em bancos isolados com populações reais. Nenhum baseline foi remodelado para facilitar os resultados.

### Flores e campos — dois anos

Cada cenário removeu 150 ocupantes de sua população, preservando os sobreviventes. O limite original não é uma meta de restauração.

| Seed | Flores: capacidade / vivos finais / novos | Campo de gramíneas: capacidade / vivos finais / novos |
|---:|---|---|
| 42 | 3.299 / 3.225 / **76** | 2.849 / 2.785 / **86** |
| 0 | 32.306 / 32.194 / **38** | 7.675 / 7.624 / **99** |
| 7 | 10.947 / 10.871 / **74** | 8.313 / 8.272 / **109** |
| 2026 | 4.371 / 4.260 / **39** | 3.549 / 3.487 / **88** |
| 12345 | 13.412 / 13.358 / **96** | 4.822 / 4.752 / **80** |

São **323 novos indivíduos por reprodução sexual S1** e 462 por rotas existentes de gramíneas. Os eventos sexuais possuem parceiros distintos e proveniência, com zero criação de itens de inventário. Não é uma alegação de que todas as 1.108 flores passaram a ocorrer nesses cinco locais.

### Árvores — resultado anterior preservado

| Seed | Capacidade | Após remoções | Vivos em 10 anos | Vivos em 20 anos |
|---:|---:|---:|---:|---:|
| 42 | 1.037 | 337 | **561** | 669 |
| 0 | 322 | 97 | **243** | 293 |
| 7 | 820 | 246 | **646** | 766 |
| 2026 | 281 | 85 | **110** | 126 |
| 12345 | 2.221 | 667 | **1.523** | 1.960 |

Na seed 42 continuam os mesmos **224 novos indivíduos aos dez anos**, com 78 jovens e 483 adultos no total. Não houve alteração silenciosa da formação, dos slots ou dos mortos. Os cinco cenários arbóreos totalizam 2.382 novos indivíduos aos vinte anos. Somados aos cenários de flores/campos, foram efetivamente estabelecidos **3.167 indivíduos** nos quinze experimentos, em horizontes explicitamente diferentes.

Os arquivos `flor-seed-*.json`, `graminea-seed-*.json`, `arvore-seed-*.json` e seus SQLite guardam os resultados persistidos. `quality-summary.json` resume os estabelecimentos, sem confundi-los com o total de contratos do catálogo.

## Cobertura e estrutura VSR1

Os 1.037 indivíduos da referência são a capacidade **da população arbórea alvo**. O patch contém outras populações. As 700 remoções não eliminaram 70% de todas as árvores da região. A comparação mostra a população afetada e o patch completo para evitar exagerar a devastação ou a recuperação.

VSR1 deriva a estrutura de slots ocupados, alturas, maturidade, densidade e arquitetura Vg2 já existente. Cada fundador sobrevivente contribui com seu porte adulto original; cada descendente contribui proporcionalmente à área de copa estimada pelo **quadrado do porte relativo**. Uma vaga contribui zero. Os estratos seguem os limiares existentes de altura: solo, arbustivo e dossel.

O footprint adulto usa a referência existente — altura ao quadrado para árvores e referência unitária para os demais tipos — e é normalizado à cobertura baseline da população. Não se multiplica a vegetação para atingir o teto, nem se deduz uma floresta adulta a partir do número de jovens.

VSR1 é uma medida estrutural derivada versionada, disponível em `measure_community`. Os campos antigos de cobertura linear L1/L2 não foram reinterpretados silenciosamente. O contrato não substitui E1, não cria biomas, não simula arquitetura botânica detalhada e não promete união exata de copas sobrepostas numa renderização.

### Seed 42, mesma população e mesmo patch

| Momento | Vivos | Jovens / adultos | Altura média presente | Copas da população no patch | Copas vs. original | Cobertura total do patch |
|---|---:|---|---:|---:|---:|---:|
| Original | 1.037 | 0 / 1.037 | 14,87 m | 14,48% | 100% | 82,83% |
| Após 700 remoções | 337 | 0 / 337 | 14,87 m | 4,70% | 32,5% | 73,05% |
| 1 ano | 375 | 38 / 337 | 13,55 m | 4,72% | 32,6% | 73,06% |
| 5 anos | 474 | 115 / 359 | 13,24 m | 5,63% | 38,9% | 73,98% |
| 10 anos | 561 | 78 / 483 | 13,80 m | 7,07% | **48,8%** | 75,42% |
| 20 anos | 669 | 32 / 637 | 14,53 m | 9,05% | 62,5% | 77,40% |

A densidade inteira da população alvo vai de 26/ha para 8/ha após as remoções e 16/ha aos vinte anos. A altura média dos sobreviventes continua inicialmente alta porque eles eram adultos; quando jovens entram na população, a média cai antes de voltar a crescer. Isso não significa perda adicional de cobertura.

Aos dez anos, a população recupera **54,1% da contagem original, mas 48,8% das copas originais**. A diferença responde diretamente ao problema identificado: contar árvores não equivale a recuperar a floresta.

![Cobertura e estrutura em seis momentos da mesma região](../artifacts/vegetation-stabilization-1.1.2/forest-structure-recovery.png)

Todas as cinco seeds possuem snapshots de estrutura original, devastada e após 1/5/10/20 anos. Os resultados incluem cobertura por população/estrato, densidade, altura média e assinatura de medição baseada no estado biológico, sem depender da frequência de observação. Nenhuma coordenada desconhecida foi acrescentada ao mapa do jogador.

## Gargalos e otimizações

O perfil real encontrou consultas ORM repetidas, rehash/cópia de estados amplos por propágulo, projeção completa de indivíduos usada apenas para decidir maturidade e custo importante de avaliação/classificação física.

As intervenções foram limitadas a execução/leitura:

1. Carregamento e validação dos participantes sob um mesmo fence SQLite, com reservas e ocupação em lote. Checksums são finalizados antes de cada flush.
2. Compartilhamento transitório de metadados imutáveis e cópia somente das partes mutáveis. Nenhuma estrutura transitória escapa para o save; exceções limpam o runtime e o savepoint restaura o estado.
3. Maturidade reprodutiva determinada pela mesma inversão analítica do relógio L1, reutilizada por participante, sem recalcular estoques só para obter um booleano.
4. Cache limitado de candidatos/posições físicas e conjuntos de coorte, sem alterar raio, candidato, ordenação ou chance.
5. Leitura agregada dos ocupantes na consulta regional, sem reabrir a autoridade para cada filho.
6. Visão privada de E1 que executa os métodos originais `evaluate`/`classify` e reutiliza seus resultados para as mesmas evidências. Chaves preservam tipos e todas as dependências. Faixas topográficas com pontuação constante usam a mesma classe de intervalo inclusivo, validada nos limites. Resultados internos são imutáveis; os fatos e o E1 público não são modificados.
7. Memoização da função pura de posição milimétrica de sites geológicos, que repetia a conversão das mesmas posições imutáveis em cada halo. O valor inteiro original permanece idêntico, com raio incluído na chave.

Os limites são 8.192 avaliações E1 na visão de leitura, 4.096 entradas geométricas no executor e 32.768 conversões de posição na função pura. Coortes expiradas são descartadas do cache operacional. Não há worker planetário, serviço distribuído, processamento diário global ou alteração dos campos C3/W1/E1.

### Comparação controlada: mesmo snapshot e mesmo horizonte

Cada horizonte começa de uma cópia independente do mesmo banco inicial devastado, sem reaproveitar a evolução de outro horizonte. O tempo inclui atualização ecológica e consulta final. A reconstrução do contexto foi medida separadamente. A nova medição de estrutura também foi cronometrada separadamente e somada no JSON; não recebeu trabalho ecológico deslocado artificialmente.

| Seed | Salto | Referência L2 | Executor otimizado | Ganho |
|---:|---:|---:|---:|---:|
| 42 | 1 ano | 2,43 s | 1,73 s | 1,40× |
| 42 | 5 anos | 7,78 s | 5,43 s | 1,43× |
| 42 | 10 anos | 15,40 s | 8,83 s | 1,74× |
| 42 | 20 anos | 26,66 s | 13,41 s | 1,99× |
| 12345 | 1 ano | 6,95 s | 4,24 s | 1,64× |
| 12345 | 5 anos | 30,01 s | 14,81 s | 2,03× |
| 12345 | 10 anos | 63,29 s | 26,66 s | 2,37× |
| 12345 | 20 anos | 103,68 s | **38,97 s** | **2,66×** |

Os oito hashes do estado autoritativo completo coincidiram, incluindo bancos, quotas individuais, perdas, eventos, payloads, IDs, baselines, corpos e estoques. Não foi aceita apenas a igualdade de contagens. As assinaturas L2 permaneceram iguais.

Também foi reproduzido o cenário de uma região já no quinto ano retornando no décimo. Partindo da mesma cópia já evoluída, a referência levou **17,51 s** e o executor **5,41 s**, com estado completo idêntico: ganho de **3,24×**. A preparação comum até o quinto ano levou 18,58 s e está registrada. Essa é uma comparação pareada atual; não é uma afirmação de que os antigos 54,54 s foram medidos no mesmo estado térmico/caches/hardware.

No maior caso, a visão de leitura produziu 872 avaliações E1 originais e reutilizou 363.828 avaliações equivalentes, sem mudar seus valores. O diagnóstico de estrutura acrescentou até aproximadamente 0,38 s nos cenários medidos. `performance-comparison.json`, `reference-performance.json`, `fast-performance.json` e `late-jump-comparison.json` permitem reproduzir os números e conferir os hashes.

### Memória e latência residual

Uma medição adicional isolada do caso de vinte anos/seed 12345 levou 16,29 s mais 2,75 s de carregamento frio do contexto. O working set do processo passou de 253,3 MB para 275,8 MB, com pico de aproximadamente 418 MB durante carregamento. Inclui catálogo, geografia e SQLite em RAM; não é uma alegação de heap L2 isolado. O estado final manteve 1.960 vivos e 1.293 descendentes.

Os tempos variam com caches e concorrência. A tabela conserva as medições da série comparativa, sem substituir o pior número por uma repetição mais favorável. **38,97 s para um salto de vinte anos ainda exige uma etapa de preparação visível**, e não cabe num frame de exploração. A melhoria foi medida; não foi escondida em geração antecipada, outra thread ou serviço. Antes de ativação em campanhas reais, a interface precisa tratar saltos excepcionais com preparação explícita e limites de interação. Não há promessa de latência instantânea para milhares de estabelecimentos físicos.

## Testes e persistência

Foram aprovados **260 casos distintos no escopo afetado**:

- 180 regressões de L1/R1, Vg1/Vg2, relógio, persistência, coleta, inventário, carga, containers, equipamentos, reset e undo.
- 22 regressões L2, incluindo extinção sem fonte, recuperação, conservação, ordem temporal, reinício e HTTP/undo.
- 34 testes de geologia regional/persistência após a memoização pura de coordenadas.
- 24 testes desta estabilização: auditoria, cinco seeds florais, parceiro maduro, estação, exceções obrigatórias, preservação das 224 árvores, comparação completa com referência, frequência de visita, cobertura, assinaturas, ativação prospectiva, corrupção, rollback, ausência de duplicação, reinício S1, HTTP/replay/undo, migração, reset, caches exatos, limites topográficos e fila L1 pendente anterior a L2.

O arquivo principal passou em 23 casos; o caso adicional da fila L1 antiga passou separadamente e confirmou igualdade completa com a referência. Reexecuções focais não foram somadas novamente. Não se afirma que todos os testes do repositório foram executados. Logs e contagem consolidada ficam em `validation.json`.

Os nove cenários de benchmark — oito horizontes mais o salto tardio — são provas diferenciais adicionais, separados da contagem pytest. Os quinze cenários de qualidade mantêm bancos SQLite reais de teste. Fonte v22 e autoridades físicas permanecem preservadas.

O banco real `backend/everreach.db` continuou com 2.027.520 bytes e `LastWriteTimeUtc=2026-10-26 21:53:21`. A migração y33 foi testada em SQLite descartável e não foi aplicada a esse banco. S1 exige ativação explícita; não há migração de campanhas por visita ou atualização de código.

## Arquivos e reprodução

Novos módulos: `vegetation/sexual.py`, `renewal_batch.py`, `renewal_readview.py` e `recovery_structure.py`. Nova persistência: `db/models/world_vegetation_sexual.py` e migração `y33y6t7u8v9w_vegetation_sexual_s1.py`. Novos testes: `test_vegetation_stabilization_s1.py`.

As integrações em `vegetation/renewal.py` mantêm o executor de referência e adicionam dispatch/autorizações opcionais. `vegetation/lifecycle.py` apenas permite gravação agrupada da ocupação durante esse runtime. `geology/regional/spatial.py` recebe o cache da função pura. `db/models/__init__.py` e `world/reset.py` registram/removem a autorização na ordem correta. Nenhum arquivo de E1, C3, W1, Vg2 ou dataset foi alterado nesta fase.

Ferramentas: `scripts/stabilize_vegetation.py`, `validate_vegetation_stabilization.py`, `compare_late_vegetation_jump.py` e `measure_vegetation_stabilization_memory.py`. Artefatos em `artifacts/vegetation-stabilization-1.1.2/`.

Em `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest app/tests/test_vegetation_stabilization_s1.py -q
.\.venv\Scripts\python.exe -m scripts.stabilize_vegetation --mode reference
.\.venv\Scripts\python.exe -m scripts.stabilize_vegetation --mode fast
.\.venv\Scripts\python.exe -m scripts.validate_vegetation_stabilization
.\.venv\Scripts\python.exe -m scripts.compare_late_vegetation_jump
.\.venv\Scripts\python.exe -m scripts.measure_vegetation_stabilization_memory
```

Os scripts retomam artefatos completos; um novo `--out` nos dois primeiros validadores executa os cenários desde o início. A ativação real não faz parte desses comandos.

## Recomendação

Os contratos de reprodução e estrutura estão suficientemente estabilizados para os sistemas consumidores e para a integração visual futura: flores comuns conseguem renovar populações, árvores mantêm várias idades, campos se recuperam e extinções legítimas permanecem possíveis. Não é necessário adicionar fauna para resolver a ausência genérica de vetor.

L1/L2 e o resultado satisfatório foram preservados. A política S1 é uma decisão explícita para mundos experimentais, com limites ecológicos e de capacidade intactos. O custo de saltos regionais muito grandes continua sendo um limite operacional mensurado; a ativação em campanhas e a experiência de preparação precisam considerar esses tempos, sem declarar o processamento instantâneo ou esconder essa limitação.
