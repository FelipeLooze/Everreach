# World Genesis — fase 0.7.2: reconciliação hídrica W2

## Auditoria e decisões anteriores à implementação

W1 é uma climatologia de quatro períodos com estoques carregados, não quatro contas independentes de água disponível. Seus fluxos já foram distribuídos entre ET, exportação e estoques. Importar precipitação/escoamento novamente duplicaria água. W2 usará explicitamente o último estoque W1 como checkpoint inicial, por célula H1, sem executar o solver global nem reescrever o passado.

O manifesto HR1 de W1 é histórico e imutável. Eventos atuais não podem impedir ler seus saldos históricos, mas devem invalidar o uso corrente de provas G1. W2 separará leitura do baseline selado da verificação das condições atuais. Evidências G1 posteriores serão registradas incrementalmente fora do manifesto W1.

G1 verifica geometria amostrada, mas seus campos `discharge_capacity_m3_s` são desconhecidos e seções não cobrem todo o percurso. O próprio contrato G1 não autoriza rios. O saldo `unresolved` também não tem localização comprovada. Portanto, os exemplos reais existentes não justificam transferências positivas. A infraestrutura deve funcionar e registrar recusas corretas; exemplos positivos controlados serão apenas testes do ledger, claramente identificados.

Cada revisão terá predecessor por domínio, operação idempotente, instante lógico, período, proveniência e ledger exato em litros inteiros. Preparar evidências não moverá água. Batches explícitos normalizados tratarão estados equivalentes independentemente da ordem de preparação; eventos/tempo distintos podem legitimamente mudar o futuro. Nenhuma atualização retroativa será feita.

O relógio WorldTime usa meses de 30 dias; C2/W1 usa 360 dias no preset, configurável. W2 fixará um instante de corte explícito e usará o ano configurado em W1 para rotular os quatro períodos futuros. A referência sazonal não é novo crédito de chuva. Continuação física de precipitação/ET não será inventada nesta reconciliação inicial de estoques.

Evidência costeira versionada verificará uma cadeia amostrada G1 até uma referência oceânica declarada, condições T1 e a continuidade de um patch submerso de referência. V4/R1 serão apenas proveniência histórica. Submersão isolada ou classificação marinha antiga não autorizam exportação. Capacidade e eventos continuam sendo verificações independentes.

Persistência será aditiva, com transações do chamador, compare-and-swap de cabeças locais, operações únicas e proteção de escrita SQLite. O sistema não acrescentará workers, ticks, mapa público ou uma segunda rede de movimento.

## Entrega e resultado físico

Foi implementada a infraestrutura W2: registro incremental de provas, checkpoint por domínio, kernel contábil exato, revisões locais encadeadas, idempotência, transações, verificação corrente de eventos, evidência costeira O1 e consulta de autoridade única. **Nenhum exemplo real foi aprovado para transferência positiva.** Isso atende à alternativa de entrega explicitamente prevista no escopo: as provas disponíveis não demonstram capacidade de passagem suficiente nem localização dos estoques que se pretende liberar.

O caminho de débito/crédito foi exercitado em testes analíticos e de persistência controlados, inclusive com falha no meio de um lote. Esses testes não são exemplos de rios reais aprovados. Não existe opção de produção para forçar aprovação G1: a política de admissão atual permanece fechada enquanto a capacidade não estiver comprovada por um contrato reconhecido.

V4, H1, HR1, C2, W1, T1 e G1 continuam com seus resultados autoritativos intactos. Nenhum mapa público, exploração, movimentação, WorldTime ou grafo de conexões foi substituído. Não há rios/lagos permanentes novos, incisão, datasets ou simulação contínua.

## Checkpoint, autoridade e conservação

O corte inicial associa explicitamente o saldo **final do quarto período W1** ao início lógico de W2. Por padrão, o instante é lido de `WorldTime.total_minutes()`; ferramentas offline podem fornecer o corte explicitamente. Ele fica fixado na assinatura W2. Inicialização e preparação são opt-in, sem migração automática de saves.

Cada célula H1 é um domínio contábil estável. Seus seis compartimentos são importados uma única vez: neve, solo, superfície, depressão aproximada, canal e pendência sem localização. O registro `locations` começa vazio: conhecer a célula macro não prova uma posição local de água. Nem `unresolved` nem um estoque de canal em trânsito se tornam automaticamente um volume num ponto G1.

Para uma revisão e domínio:

```text
estoque_inicial + entradas − saídas = estoque_final
resíduo = 0 L
```

No lote completo, transferências internas se cancelam; exportação oceânica, se futuramente autorizada, é saída registrada, não desaparecimento. As quantidades são inteiros Python em JSON, sem coluna SQL de volume limitada a 64 bits. Os testes incluem valores maiores que 10³⁵ L. PET, precipitação e escoamento históricos não são recarregados como créditos W2.

O kernel faz débitos agregados contra o estoque **anterior** ao lote. Recebimentos desse mesmo lote não podem ser gastos novamente por outro afluente. Sobredemanda de origem ou de uma passagem compartilhada rejeita todo o lote; não escolhe um vencedor pela ordem de exploração. Cada transferência efetivamente aplicada recebe um ID único persistido. Reutilizá-lo numa operação nova é rejeitado.

`query_water_state` estabelece uma única fonte quantitativa por domínio: antes da preparação, retorna a referência de checkpoint W1; depois, retorna o overlay W2. **Os dois valores não devem ser somados.** Para um total composto, substitui-se o checkpoint dos domínios preparados pelo seu saldo W2, mantendo os demais como referência. Uma consulta não prepara domínios automaticamente e não converte saldo em profundidade, lago ou inundação.

## Revisões, independência da ordem e tempo

Uma revisão registra operação canônica, predecessor de cada domínio, instante lógico, período, fontes, evidências/eventos observados, estados antes/depois, movimentos e ledger. Uma operação idêntica repetida retorna a revisão existente, mesmo quando a cabeça já avançou. O mesmo ID com outro conteúdo é rejeitado. Revisões antigas são históricas, nunca autorização corrente de fluxo.

A preparação/inscrição de provas não movimenta água nem avança cabeças locais. IDs de evidência derivam de fontes, pedido G1 e checksum, sem depender do instante ou da ordem de inscrição. Na reconciliação, chaves e intenções são normalizadas. Os testes com preparação em ordem inversa produziram o mesmo payload físico. Já revisões explícitas em instantes/eventos diferentes são história causal diferente; não se promete comutatividade dessa história.

O chamador fornece cabeças esperadas e instante lógico. Cabeça obsoleta ou tempo anterior ao último instante do domínio são recusados. IDs de operação/transferência devem representar uma causa física estável, e não um novo número aleatório por visita.

Os quatro períodos seguem o ano configurado em W1:

```text
período = floor(4 × (minuto_lógico − corte) / (dias_do_ano_W1 × 1440)) mod 4
```

Isso preserva C2 e a duração configurável, sem alterar o calendário WorldTime. **Esses períodos ordenam reconciliações do checkpoint; não constituem uma simulação de um novo ano climático.** Não se projetou automaticamente evolução futura de neve/solo, nova chuva ou ET. A continuação de forçantes locais exigirá operações causais próprias, sem repetir o ano histórico. A demonstração sazonal mantém um único saldo, rotula quatro revisões e conserva as referências W1 separadamente. Não declara perenidade.

## Registro incremental e condições de admissão

O registro W2 não amplia o manifesto W1. Novas provas G1 podem ser inscritas por chave canônica sem um limite global de 32 entradas. O teste de fronteira inscreveu **33 provas G1 válidas** sem criar domínios de água nem alterar o manifesto W1. Outro teste preparou 33 domínios contábeis sob demanda. Os limites de uma revisão são orçamentos locais, não uma quantidade fixa de regiões do planeta.

A política verifica domínio de origem/destino, rota, resolução, cotas, necessidade de armazenamento, seções, fronteiras bilaterais e condições atuais dos eventos. Transferências entre células H1 distintas devem corresponder ao receptor já existente H1; não se cria uma segunda rede de roteamento global. Transferências locais também precisam de prova, sem converter todo caminho potencial em rio.

Provas parciais continuam parciais. Entre as causas registradas:

- resolução insuficiente, rota ausente e preparação inconclusiva;
- cotas incompatíveis e armazenamento/vertedouro ainda não reconciliados;
- seção aberta ou não confinada;
- capacidade hidráulica não demonstrada pelo contrato G1 v1;
- fronteira bilateral não comprovada;
- estoque seco ou sem localização física comprovada;
- eventos que invalidam a geometria;
- conexão costeira ou referência oceânica pendentes.

G1 v1 fornece áreas transversais potenciais, mas não um certificado de capacidade de todo o percurso. Um número acrescentado manualmente a um JSON antigo não vira uma política de capacidade reconhecida. A política de admissão v1, portanto, não autoriza transferências reais positivas com esses dados. O kernel tem um ramo de transferência completo/testado, mas ele só recebe admissões internas; o pedido externo não pode fornecer `status=admitted`.

Também falta um contrato físico de localização/alocação do estoque macro para uma entrada G1. W2 não implementou uma distribuição uniforme arbitrária, não mapeou pendências para depressões por proximidade e não recalculou W1 para resolver o problema. Até existir tal evidência, o saldo permanece na conta de origem.

## Evidência costeira O1

O1 é um contrato independente de versão 1, vinculado a W2/T1/G1 e a uma referência histórica **explicitamente designada**. `ocean_reference_component_ids` inicia vazio. Uma identidade V4 de água não é automaticamente aceita como oceano de referência; a configuração apenas permite nomear referências existentes, não modifica a geografia ou estabelece uma quantidade obrigatória de oceanos.

A prova verifica uma cadeia ordenada de trajetórias G1 com pontos/IDs bilaterais coincidentes até o ponto de referência, resolução suficiente, sondagens T1 submersas e um patch final amostrado submerso, incluindo suas arestas. A identidade histórica e a célula marinha H1 são verificações de proveniência, não substitutos dessa geometria. Referências não designadas, barreiras T1, lacunas, eventos e resolução insuficiente mantêm o resultado pendente.

O escopo de um resultado positivo O1 é **conexão amostrada até o patch de referência nomeado**, não prova de que todo o componente histórico permaneça oceânico em T1. Mesmo nesse resultado, `export_authorized=False`: capacidade hidráulica, origem da água e política de transferência continuam independentes. O teste positivo O1 é um terreno analítico controlado; não foi fabricado um exemplo oceânico real aprovado.

A tentativa costeira real da seed 42 permanece pendente. O ponto que V4/R1 tratava como referência histórica não oferece um patch submerso válido em T1; a cadeia apresenta terreno acima do datum e não há referência oceânica designada. O certificado registra essas causas e não exporta água. Ele utiliza a divergência real mostrada na fase G1, sem corrigir alturas ou classificações antigas.

## Eventos e segurança transacional

W2 lê o baseline W1 selado verificando seus cabeçalhos, assinatura, checksum e ledger, sem aplicar a ele a recusa por eventos HR1 correntes. Isso é necessário para **preservar o passado**: um deslizamento atual não apaga os estoques finais antigos. A checagem de geometria corrente continua obrigatória e ocorre separadamente.

Revisões observam mudanças G1, HR1 e tiles T1 na cobertura local fechada, incluindo emendas e seções, com leitura de estado ainda não descarregado (`autoflush=False`). A proveniência guarda hashes dos eventos e seu instante de observação. Eventos sem timestamp padronizado não têm data física inventada; a revisão registra quando foram observados. W2 não interpreta nem aplica a física desses eventos. Toda alteração não reconciliada invalida a prova para uso corrente, sem editar registros anteriores.

No SQLite, a primeira escrita W2 adquire a proteção de escritor antes do savepoint e permanece na transação externa até commit/rollback do chamador. Isso serializa a validação contra escritores de eventos e evita a particularidade pysqlite de um savepoint de topo se consolidar antes do rollback externo. Depois, um savepoint cobre a revisão, compare-and-swap de todas as cabeças e registros de transferências. Uma falha em qualquer domínio reverte o lote inteiro.

O teste com duas sessões rejeita o predecessor obsoleto. Um trigger de falha **exclusivamente de teste** interrompeu o segundo domínio após a atualização do primeiro: todos os saldos/cabeças, revisão e transferência foram revertidos. Não há trigger ou mecanismo de força-aprovação na implementação de produção.

O contador `write_epoch` é uma proteção de concorrência, não tempo físico nem parte dos IDs das revisões. Pode avançar numa tentativa recusada sem mover água. Não há commit interno. A implementação aceita somente o SQLite testado; outro banco exige protocolo explícito de serialização de eventos, em vez de presumir que um lock numa linha W2 protegeria todos os tiles.

## Persistência e compatibilidade

Migração aditiva `p24p7k8l9m0n`, sobre `o23o6j7k8l9m`, cria cinco tabelas:

| Tabela | Conteúdo |
| --- | --- |
| `genesis_water_reconciliations` | Configuração, fontes e corte W2 explícitos. |
| `genesis_water_domains` | Checkpoint de origem, saldo, checksum, versão e cabeça local. |
| `genesis_water_reconciliation_evidence` | Referências G1 e certificados O1 imutáveis. |
| `genesis_water_revisions` | Operações únicas, predecessores, instante/período e ledger histórico. |
| `genesis_water_transfers` | IDs únicos de transferências efetivamente aplicadas. |

Payloads históricos de revisão são deferidos no ORM; não se carrega toda a cadeia para consultar uma cabeça. Checksum ou origem divergente causa erro, não reconstrução. A consulta corrente de uma cabeça aplicada verifica novamente as provas; uma cabeça com geometria obsoleta exige retenção/revisão futura explícita, sem apagar movimentos já consolidados.

O reset elimina as tabelas W2 antes de G1/W1 e preserva outras campanhas. Migração e downgrade foram testados contra um payload W1 sentinela e todos os schemas anteriores. **O banco real `everreach.db` não foi migrado.** As ferramentas usam SQLite descartável e carregam os snapshots históricos exatos, sem executar novamente os geradores para obter resultados convenientes.

## Demonstração real e métricas

Foram carregadas seis combinações já existentes, com quatro provas G1 principais por combinação e um domínio W2 por caso. As revisões correspondem aos quatro períodos; a tentativa costeira adicional é uma evidência separada, sem alocação.

| Seed | Raio (km) | Nó | Revisões | Transferências reais aplicadas | Maior resíduo |
| --- | ---: | ---: | ---: | ---: | ---: |
| 42 | 63.710 | 3982 | 4 | 0 L | 0 L |
| 0 | 63.710 | 874 | 4 | 0 L | 0 L |
| 2026 | 63.710 | 141 | 4 | 0 L | 0 L |
| 42 | 6.371 | 136 | 4 | 0 L | 0 L |
| 42 | 637.100 | 37 | 4 | 0 L | 0 L |
| 42 | 1.000.000.000 | 37 | 4 | 0 L | 0 L |

O nó 3982 conservou **3.714.083.730.681.525 L** no checkpoint composto dos seis compartimentos. As quatro revisões não mudaram esse valor. Sua incompatibilidade HR1/T1 histórica de 14,068 m e as pendências G1 de resolução/armazenamento não foram forçadas a aprovação. A disponibilidade sazonal W1 é referência; não supera essas falhas geométricas nem permite gastar novamente um fluxo histórico.

Nos outros casos, inclusive nas trajetórias locais descendentes do raio máximo, capacidade de passagem desconhecida e ausência de localização continuam impedindo transferência. Isso distingue uma geometria longitudinal verificada de um movimento hídrico reconciliado. A conservação positiva foi validada nos testes controlados; resíduo zero nos exemplos reais não deve ser anunciado como prova de uma rede ativa.

| Medição | Resultado observado |
| --- | --- |
| Preparação W2 de um domínio e quatro referências, após importar as fontes | ~0,24–0,36 s. |
| Revisão normal, com consulta/validação local SQLite | ~0,069–0,131 s. |
| Revisão de referência instrumentada por `tracemalloc` | ~0,933 s; inclui o custo da instrumentação. |
| Memória adicional da revisão de referência | Pico 1.607.898 bytes (~1,53 MiB), retidos 275.072 bytes. |
| Novos solves globais W1 | 0. |

Esses tempos excluem importação de V4/H1/HR1/C2/W1/G1 e preparação original das geometrias. `tracemalloc` não mede RSS. Os exemplos reais usam H1 nível 5 e G1 já persistido, e abrangem até raio 10¹² m. Não houve crescimento proporcional à área planetária. Os números não são benchmark de renderização ou de simulação climática contínua.

Orçamentos padrão por revisão: oito domínios, 16 evidências incluindo dependências costeiras, 16 intenções e payload de 1 MiB. Cada inspeção de geometria tem até 128 linhas de eventos locais; exceder isso mantém a prova invalidada/pendente. O registro total é incremental, não limitado a 16 ou 32 provas globais. O cache do leitor histórico W1 contém dois planos; W2 não mantém todas as revisões ou domínios num cache global.

## Visualizações e reprodução

- [Nó 3982: saldo preservado e pendências](../artifacts/water-reconciliation-w2/seed-42-r63710000-node-3982/reconciliation.png).
- [Seed 2026](../artifacts/water-reconciliation-w2/seed-2026-r63710000-node-141/reconciliation.png) e [raio máximo](../artifacts/water-reconciliation-w2/seed-42-r1000000000000-node-37/reconciliation.png).
- [Tentativa costeira real O1](../artifacts/water-reconciliation-w2/seed-42-r63710000-node-3982/coast-evidence.json).
- [Métricas completas](../artifacts/water-reconciliation-w2/suite.json) e [revisões da referência](../artifacts/water-reconciliation-w2/seed-42-r63710000-node-3982/revisions.json).

As figuras separam referência W1, geometria G1, estoque antes/depois e transferência W2 aplicada. Zero aprovado é mostrado como zero; não há imagem de um rio real aprovado inexistente. As contas não são áreas molhadas nem profundidades.

Comandos, a partir de `backend`:

```powershell
.venv/Scripts/python.exe -m pytest app/tests/test_genesis_water_reconciliation.py app/tests/test_genesis_water_reconciliation_coast.py app/tests/test_genesis_water_reconciliation_persistence.py -q
.venv/Scripts/python.exe -m scripts.preview_water_reconciliation --suite
.venv/Scripts/python.exe -m alembic heads
```

## Arquivos desta fase

| Arquivos | Entrega |
| --- | --- |
| `backend/app/game/world/genesis/water_reconciliation/{config,ledger}.py`, `__init__.py` | Configuração, intenções e kernel exato. |
| `water_reconciliation/{sources,events,admission}.py` | Histórico W1, eventos locais e admissibilidade sem força-aprovação. |
| `water_reconciliation/{coast,service,preview}.py` | O1, persistência/revisões/CAS, autoridade única e figuras. |
| `backend/app/db/models/world_water_reconciliation.py` | Cinco modelos W2. |
| `backend/app/db/models/__init__.py`, `backend/app/game/world/reset.py` | Registro e exclusão na ordem correta. |
| `backend/alembic/versions/p24p7k8l9m0n_add_water_reconciliation_w2.py` | Migração aditiva e downgrade. |
| `backend/app/tests/test_genesis_water_reconciliation*.py` | Ledger, costas, persistência, regressão e concorrência. |
| `backend/scripts/preview_water_reconciliation.py` | Demonstração descartável com snapshots reais. |
| `artifacts/water-reconciliation-w2/`, este relatório | Revisões, métricas, imagens e decisões. |

As alterações/não rastreados de fases anteriores já existiam no workspace e foram preservados. Os módulos autoritativos anteriores não foram editados nesta fase.

## Testes e estado para as próximas etapas

Os testes específicos cobrem inteiros grandes, conservação de débitos/créditos, afluentes, não reutilização de recebimentos no mesmo lote, sobredemanda atômica, exportação sem prova, pendência sem localização, quatro períodos, idempotência/reuso divergente, ordem inversa de preparação, crescimento além de 32, eventos sobre manifesto W1 fixo, duas sessões com cabeça obsoleta, falha entre atualizações de domínios, rollback após reabertura, consulta de autoridade única, recusa por orçamento, reset e migração/downgrade.

O1 foi testado com conexão controlada, referência não designada, barreira T1, patch sem submersão, evento invalidante e resolução insuficiente. Aprovações de teste são isoladas do fluxo de produção; nenhum bypass foi adicionado à política física. O teste entre processos fixa o hash `d83edb426f978a7b1fbac6fe954575a37efa62517eeda15a70b6f545664d15b9` para uma revisão W2 de referência.

Testes específicos: **28 aprovados**. Regressão ampla: **593 aprovados em 262,37 s**, cobrindo Genesis, exploração, mapa, viagens, fronteiras, reset, materialização e simulação temporal. O único aviso foi a depreciação preexistente Starlette/httpx. `compileall`, `git diff --check` e a verificação de head Alembic único passaram; o head é `p24p7k8l9m0n`.

**A infraestrutura contábil e de revisão está estabelecida; a ocupação hídrica física ainda não está suficientemente resolvida para alimentar integração ambiental dependente de rios/lagos.** Antes disso, faltam localização/alocação comprovada dos estoques, capacidade hidráulica reconhecida de percursos, solução de armazenamento/vertedouros e conexões oceânicas válidas. O nó 3982 continua pendente. Continuação de forçantes locais e aplicação física de eventos também não foram implementadas.

Geologia que consuma apenas a autoridade T1/V4 pode ser desenvolvida independentemente, mas não deve interpretar disponibilidade W1 ou uma rota G1 como ambiente molhado consolidado. Nenhum dataset foi integrado nesta entrega. A próxima etapa hídrica deve preencher essas provas sem abrir mão da conservação e da história W2; não precisa antecipar toda a hidrografia do planeta.
