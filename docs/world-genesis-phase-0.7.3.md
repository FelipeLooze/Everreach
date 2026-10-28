# World Genesis — fase 0.7.3: fechamento hidrográfico prático

## Diagnóstico anterior à implementação

W2 v1 conserva água, mas a política G1 disponível rejeita toda capacidade desconhecida. Além disso, `locations` inicia vazio e não há alocador espacial: mesmo um leito favorável não pode gastar estoques macro. As seções G1 são sondagens pontuais; exigir duas regiões para qualquer passagem interna e uma certificação hidráulica científica excede o necessário para um trecho de RPG. Conservação, geometria de fronteira, identificação da fonte e eventos continuam essenciais.

T1 não tem geomorfologia fluvial imposta. Isso pode exigir T2 para grandes redes, mas não demonstra ausência de todo leito natural. A primeira prova será limitada a terreno T1 real, sem incisão, com busca determinística e orçamento. T2 não será implementada antes de avaliar esse resultado.

Solução mínima proposta: extensão opt-in P1 de W2, com alocação de superfície L1 por área hierárquica e capacidade estimada K1 sobre seções T1 de um trecho curto. Usar somente o compartimento superficial W1; `unresolved`, solo, neve e depósitos de localização desconhecida não serão automaticamente colocados no canal. A hierarquia de quotas e as reivindicações únicas devem impedir dupla utilização, sem concentrar uma célula continental num rio.

A capacidade K1 utilizará área, perímetro molhado, declive e Manning com rugosidade/preset explícitos, redução de incerteza e velocidade limitada. É aproximação de jogo, não certificação científica. O trecho deverá reter o volume geométrico necessário para molhá-lo antes de entregar água a jusante. Excesso não transmitido permanece contabilizado, sem inventar inundação.

P1 terá configuração/persistência próprias, mantendo o ledger, as revisões e o fence transacional W2. Contas locais serão detalhes normalizados de uma conta agregada W2, não quantidades somadas uma segunda vez. Ativação será explícita para mundos sem reconciliação/contas locais anteriores. T1, G1, W1 e saves antigos não serão reescritos.

Manning é uma relação empírica de escoamento uniforme; a escolha de rugosidade é uma estimativa. Referências primárias: [USGS, análise hidráulica](https://pubs.usgs.gov/publication/sir20235145/full), [USBR, limitações do método](https://www.usbr.gov/tsc/techreferences/mands/wmm/chap13_06.html), [FHWA, unidades SI e raio hidráulico](https://www.fhwa.dot.gov/engineering/hydraulics/pubs/hif24001.pdf). A extrapolação a pequenos trechos procedurais será explicitamente tratada como modelo de RPG.

## Resultados

**Houve transferência positiva no pipeline real, sem modificar o terreno:** na seed 42, raio 63.710 km, nó H1 **2717**, uma passagem natural T1 de **2,772 m** entregou **19 L** à conta local a jusante e reteve **11 L** para o molhamento inicial do trecho. O resíduo contábil foi **zero**, tanto no domínio W2 quanto nas contas subordinadas. O commit, a reabertura do SQLite e a repetição idempotente recuperaram o mesmo resultado.

Isso comprova um episódio local fundamentado pelo modelo. Não comprova rio perene, rede continental conectada, lago ou conexão oceânica. O nó 3982 e sua incompatibilidade histórica de 14,068 m continuam pendentes.

## Auditoria dos bloqueios e decisão de escopo

| Componente | Constatação e tratamento nesta fase |
| --- | --- |
| V4 / H1 | Formação, drenagem macro, identidades, áreas e destinos permanecem fontes imutáveis. Nenhuma reconstrução global foi necessária. |
| HR1 | Uma rota macro/regional não garante um leito T1 métrico. Os eventos e as incompatibilidades existentes continuam invalidando usos incompatíveis. |
| C2 | A precipitação sazonal fornece a causa climática histórica; não é um crédito novo que possa ser gasto novamente. |
| W1 | Há saldos finais, mas não posições históricas exatas. L1 estabelece uma hipótese espacial nova e explícita somente para `surface`, debitando a origem uma única vez. |
| T1 | Não impõe geomorfologia fluvial. Uma busca limitada encontrou um trecho natural suficiente para esta prova; portanto **não foi introduzido T2**. Redes extensas ainda podem exigir terreno condicionado versionado. |
| G1 | Perfil descendente verificado não equivale a capacidade hidráulica. P1 exige a verificação G1 e acrescenta cinco seções T1 e K1. Para uma interface interna, duas regiões inteiras são desnecessárias: as duas vistas compartilham ponto, terreno e carga de referência canônicos. |
| W2 | A recusa de capacidade/localização desconhecidas é correta para os contratos antigos. A extensão P1 fornece essas provas no ledger existente; não abre uma permissão genérica para antigas rotas pendentes. |
| Armazenamento / vertedouros | O molhamento geométrico do pequeno trecho é debitado antes da entrega. Excesso fica retido na origem ou a operação é recusada. Lagos, vertedouros e manchas de inundação continuam sem autorização nova. |
| Costa / oceano | P1 não autoriza exportação oceânica nem contorna O1. Falta provar a ligação física costeira caso a caso. |
| Continuação climática | F1 define propostas futuras com identidade e intervalo próprios, sem crédito autorizado. A execução sequencial do balanço local ainda está pendente. |

As seis demonstrações antigas não foram convertidas em sucessos. A combinação de falta de localização e capacidade desconhecida explica por que nem os perfis descendentes podiam mover água. A barreira longitudinal do nó 3982 continua sendo um bloqueio essencial, não uma exigência contábil excessiva.

## Arquitetura entregue: P1, L1 e K1

P1 é uma extensão opcional e versionada de W2. Sua ativação requer inicialização explícita, antes de preparar qualquer domínio W2; um mundo que já possua domínios precisa de uma migração futura específica. Não existe ativação automática em saves existentes.

L1 divide o estoque final superficial W1 por uma árvore de quotas inteiras, ponderadas pelas áreas esféricas existentes. Em cada subdivisão, os quatro filhos somam exatamente o pai, inclusive com inteiros enormes. A folha tem nível fixo por raio/configuração; não se podem reivindicar simultaneamente pai e filho. Na folha, áreas duais dos vértices definem as parcelas locais. A hipótese é uma **lâmina superficial uniforme do novo modelo**, não uma reconstrução da posição histórica da água. Solo, neve, canal, depressão e `unresolved` não são automaticamente colocados no curso.

As contas locais são normalizadas e persistidas. A conta agregada `p1:allocated_surface` do pai W2 é seu resumo, nunca água adicional. Uma localização transfere saldo de `w1:surface` para esse agregado; um fluxo interno muda somente a distribuição entre origem, trecho e receptor. As revisões, transferências, predecessores e exclusão transacional são os mesmos de W2. Consultas carregam apenas as contas necessárias, sem copiar todas as folhas materializadas para cada revisão.

K1 usa cinco seções transversais naturais, área e perímetro molhados, declive/carga disponível e uma aproximação inteira de Manning. Exige perfil longitudinal não ascendente, margens amostradas suficientes, reserva na origem e capacidade/altura disponível no receptor. A estimativa tem velocidade limitada e fator explícito de incerteza. Molhamento e entrega consomem a **mesma** capacidade do episódio. Repetir a operação devolve a revisão existente; outra operação não pode reutilizar a mesma janela nem sobrepor o estado temporal das contas.

Os presets foram estabelecidos antes da busca: grade 16, espaçamento alvo de 4 m, sondas transversais a cada 0,5 m, oito intervalos de cada lado, rugosidade `n=0,075`, velocidade máxima 0,01 m/s, fator de capacidade 10% e episódio de 1.440 minutos. São aproximações conservadoras de RPG, não parâmetros cientificamente calibrados. Não foram reduzidos após as tentativas negativas para produzir uma aprovação.

O envelope das provas contém o tile e todas as seções efetivamente usadas. A extensão interna utiliza esse envelope em lugar da abrangência diagnóstica de 100 m das sondagens G1 antigas; não altera seus registros nem reinterpreta suas recusas. Eventos T1/G1/HR1 correntes invalidam uso futuro. As revisões passadas continuam legíveis. Os dados de geometria são conferidos contra T1 ao registrar a prova; uma prova persistida é relida sem regenerar terreno.

## Seleção real e cadeia de proveniência

A seleção ordena células terrestres elegíveis por estoque superficial por área, escoamento local anual por área e ID. Usa exclusivamente snapshots históricos existentes. O orçamento é de até oito células macro, quatro tiles por célula e 128 arestas por tile, com orçamento de amostras por tentativa; a busca técnica não ocorre a cada tick do jogo.

| Tentativa | Nó | Tile | Arestas examinadas | Amostras T1 | Resultado |
| --- | ---: | --- | ---: | ---: | --- |
| 1 | 3551 | `3/21/2064384/950272` | 128 | 10.659 | Sem passagem demonstrada |
| 2 | 3551 | `3/21/2064385/950272` | 128 | 10.565 | Sem passagem demonstrada |
| 3 | 3551 | `3/21/2064384/950273` | 128 | 10.637 | Sem passagem demonstrada |
| 4 | 3551 | `3/21/2064385/950273` | 128 | 10.885 | Sem passagem demonstrada |
| 5 | 2717 | `2/21/1933312/1343488` | 2 | 456 | Passagem natural encontrada |

Nenhuma entrada foi fabricada e nenhuma seed trocada. O nó 2717 está **fora do manifesto HR1 fixo de W1**: a demonstração não depende só das regiões já escolhidas anteriormente. O modelo utiliza seu estoque final histórico, não seus fluxos sazonais como novos créditos. A precipitação histórica C2/W1 desse nó foi **387, 413, 387 e 355 mm** nos quatro períodos, totalizando 1.542 mm; o JSON registra também o escoamento histórico de referência.

A cadeia efetiva é V4/T1 → C2 histórico → saldo W1 final → quota L1 → geometria real T1 verificada por G1 → capacidade K1 → revisão W2 conservativa. As fontes e suas assinaturas são verificadas durante a preparação. O checksum W1 antes/depois permaneceu `beab3e7f7011314fdc0a019ee939457a90da9044477443999de39eded538edcc`. A prova geométrica P1 fixa o ID `d4194fd1d77749c65f21147b95287eba`.

| Grandeza | Resultado |
| --- | ---: |
| Comprimento natural | 2,772 m |
| Profundidade de projeto | 5 mm |
| Queda de carga do modelo | 203 mm |
| Áreas das cinco seções | 4.455 / 4.236 / 4.131 / 3.100 / 3.100 mm² |
| Larguras molhadas | 1.517 / 1.361 / 1.287 / 1.100 / 1.100 mm |
| Vazão estimada após limites | 0,0031 L/s |
| Capacidade máxima do episódio | 267 L |
| Quota superficial localizada | 121 L |
| Origem antes → depois | 61 → 31 L |
| Receptor antes → depois | 60 → 79 L |
| Água retida para molhar o trecho | 11 L |
| Água entregue a jusante | 19 L |
| Conservação local | **121 = 31 + 79 + 11 L** |
| Resíduo local / macro | **0 / 0 L** |

## Continuação sazonal proposta: F1

`future_forcing_proposal` separa a série histórica W1 dos próximos intervalos lógicos após um corte explícito. Ciclo, trimestre, fonte C2, tile, configuração e instante de corte identificam cada proposta. A duração deriva do ano configurado. Chuva e neve são particionadas separadamente, mantendo `P = chuva + neve`; PET continua uma demanda potencial, não evapotranspiração realizada.

O resultado tem `credit_authorized=False` e **não aplica água ao ledger**. Antes disso, uma fase seguinte deve implementar recibo único por intervalo, predecessor sequencial, estados locais de solo/neve, balanço limitado de ET/infiltração/degelo e entrada externa explícita em W2. Os eventos devem registrar o instante lógico e a fonte. Reexecutar os quatro períodos históricos W1 nunca é um mecanismo de recarga. Esta entrega estabelece a estratégia e a proposta verificável, não uma simulação climática contínua.

## Persistência, desempenho e reprodução

Migração aditiva `q25q8l9m0n1o`, sobre `p24p7k8l9m0n`, cria apenas `genesis_practical_hydrology`, `genesis_local_water_accounts` e `genesis_practical_capacity_use`. O reset elimina os registros subordinados na ordem correta. Migração/downgrade foram testados em SQLite temporário preservando um sentinela W2 antigo. **O banco real `everreach.db` não foi migrado.**

Na execução final local, preparar a prova importada levou **0,591 s**; a revisão real instrumentada levou **0,437 s**, com pico adicional `tracemalloc` de **577.762 bytes (~564 KiB)** e **152.251 bytes** retidos. Esses números excluem a importação das fontes e a busca técnica inicial, não medem RSS e incluem overhead de instrumentação. O caso positivo usa 456 amostras T1 na busca; as quatro tentativas negativas consumiram outras 42.746. Não há geração métrica global, worker novo ou simulação por tick.

O custo por parcela é limitado pela grade, orçamento de sondas e profundidade da árvore de quotas; aumentar o raio aumenta o nível da folha para manter escala local. Os testes cobrem quatro raios, incluindo os extremos suportados, seis faces e polos. O benchmark físico completo foi feito na seed 42 / raio de referência; não constitui validação hidráulica planetária de todas as seeds.

- [Imagem técnica antes/depois](../artifacts/practical-hydrology-p1/practical-passage.png): mesmo T1, com sobreposição do trecho e balanço; não houve condicionamento ou incisão.
- [Busca e prova real](../artifacts/practical-hydrology-p1/probe.json).
- [Resumo e benchmark](../artifacts/practical-hydrology-p1/summary.json).
- [Revisões, prova, saldos e proposta F1](../artifacts/practical-hydrology-p1/result.json).

Comandos a partir de `backend` (as ferramentas usam arquivos históricos do repositório e banco descartável):

```powershell
.venv/Scripts/python.exe -m scripts.probe_practical_hydrology
.venv/Scripts/python.exe -m scripts.preview_practical_hydrology
.venv/Scripts/python.exe -m pytest app/tests/test_genesis_practical_hydrology.py app/tests/test_genesis_practical_hydrology_persistence.py -q
.venv/Scripts/python.exe -m alembic heads
```

## Arquivos desta fase

| Arquivos | Entrega |
| --- | --- |
| `backend/app/game/world/genesis/water_reconciliation/practical/{config,allocation}.py` | Versões, limites e quotas L1 por área esférica. |
| `practical/{hydraulics,proof,interface}.py` | Capacidade K1, busca T1 limitada e interface canônica bilateral. |
| `practical/{service,future,preview,__init__}.py` | Extensão transacional W2, contas locais, proposta F1 e imagem técnica. |
| `water_reconciliation/{ledger,service}.py` | Dispatch explícito P1 e admissão interna L1, mantendo os caminhos anteriores. |
| `backend/app/db/models/world_practical_hydrology.py` | Três modelos adicionais. |
| `backend/app/db/models/__init__.py`, `backend/app/game/world/reset.py` | Registro dos modelos e limpeza. |
| `backend/alembic/versions/q25q8l9m0n1o_add_practical_hydrology_p1.py` | Migração aditiva/downgrade. |
| `backend/app/tests/test_genesis_practical_hydrology*.py` | Testes unitários e pipeline persistente real. |
| `backend/scripts/{probe,preview}_practical_hydrology.py` | Seleção e demonstração reprodutíveis. |
| `artifacts/practical-hydrology-p1/`, este relatório | Imagem, prova, métricas e decisões. |

As alterações de fases anteriores já presentes no workspace foram preservadas. Nenhuma autoridade anterior de terreno, clima ou balanço W1 foi modificada.

## Validação e limites para a próxima fase

Os **27 testes novos passaram**. Cobrem quotas exatas e independência de ordem, áreas em faces/polos e raios extremos, geometria/capacidade, prova determinística real, adulteração de quota/capacidade, identidade de interface em emendas, propostas sazonais sem crédito, versões estritas, conservação pai/filhos, excesso retido, eventos invalidantes, leitura sem regeneração, commit/reabertura/rollback, falha no flush final, duas sessões concorrentes, reset e migração/downgrade com sentinela antigo.

A regressão ampla passou com **620 testes aprovados em 317,89 s**, incluindo os 27 novos e os 593 da seleção anterior: Genesis, exploração, mapa, viagens, fronteiras, materialização, reset e simulação temporal. Os caminhos W2 anteriores permaneceram compatíveis, incluindo o hash de referência `d83edb426f978a7b1fbac6fe954575a37efa62517eeda15a70b6f545664d15b9`. `compileall`, `git diff --check` e head Alembic único (`q25q8l9m0n1o`) passaram. O único aviso foi a depreciação preexistente Starlette/httpx.

**Podemos avançar com geologia que consuma V4/T1 e com consumidores locais que respeitem o episódio P1 comprovado. Ainda não há base para considerar toda a rede hidrográfica um ambiente molhado consolidado.** Restam percursos extensos conectados, fronteiras entre domínios H1, costas/O1, armazenamento/vertedouros, continuação sazonal aplicada e validação de mais trechos/seeds. O sucesso de 2,772 m não elimina uma eventual necessidade de T2 para redes regionais.

A aproximação de Manning em lâmina de poucos milímetros é uma regra de jogo conservadora, não validação científica. A geometria é amostrada, não prova matemática de toda a superfície contínua; o estado é de volumes finitos, não uma inundação 3D. O episódio não resolve evaporação, recarga atmosférica dinâmica ou perenidade durante sua janela. Novas geometrias ou calibrações autoritativas exigem versão explícita. Não foram implementados datasets, ambientes/biomas, materiais, atores, Atlas, mudanças de movimento ou um segundo grafo de exploração.
