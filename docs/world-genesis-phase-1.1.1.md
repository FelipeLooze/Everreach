# World Genesis 1.1.1 — renovação ecológica recorrente L2

L2 complementa L1 com reprodução sazonal recorrente, bancos finitos de propágulos ecológicos e recuperação de vagas por novas gerações. É uma autoridade experimental separada, com ativação explícita. **Não altera o v22, as regras assinadas de L1, Vg1/Vg2/R1, clima, hidrologia ou saves reais.**

O anexo recebido termina na seção 5, em “Não simular diariamente todas as árvores”. Este trabalho implementa os requisitos presentes nesse arquivo, incluindo evolução pelo relógio oficial de 360 dias, sem simulação diária planetária.

## Auditoria e contratos

L1 recuperava partes coletáveis, crescia indivíduos e processava dispersões finitas. Sua colonização automática dependia de morte e candidatos locais, sem produção reprodutiva recorrente. Uma tentativa sem propágulo não recebia nova oportunidade sazonal. Também havia 548 espécies sem órgão bruto de propagação utilizável pelo contrato R1.

L2 mantém esses contratos e adiciona:

- `GenesisVegetationRenewal`: configuração, assinatura, vínculo com L1 e fronteira temporal com checksum.
- `GenesisRenewingPopulation`: capacidade física original, vagas, datas imutáveis de morte dos fundadores, reservas por coorte, proveniência e ledger.
- Eventos de nascimento no ledger existente de `GenesisVegetationLifeEvent`, com assinatura L2, origem e massa explícitas. Não cria outro inventário ou grafo de movimento.

`initialize_renewal(..., experimental=True)` exige L1/R1 válidos. A configuração é `RenewalConfigL2(renewal_version=2)`. A migração x32 é aditiva e deixa todas as campanhas desativadas. Um indivíduo legado sem contrato R1 bloqueia a ativação e exige reconciliação explícita; não é convertido silenciosamente.

Sem uma autoridade L2, os caminhos L1 continuam funcionando como antes. Com L2 ativo, uma morte registra uma vaga e sua origem temporal; os eventos recorrentes assumem a renovação. Dispersões manuais L1 e suas filas existentes continuam sendo processadas. Nada exige a presença do jogador no instante da reprodução.

## O que o v22 permite afirmar

Foram auditadas as estratégias reais, incluindo a observação canônica de que são propostas ecológicas e não prova de fisiologia específica observada no mundo. L2 usa uma **aproximação de gameplay declarada**, baseada em uma alternativa vegetativa ou por esporos explicitamente presente. Não apresenta fertilidade, polinizadores ou vetores desconhecidos como fatos medidos.

As alternativas incluem fragmentos, divisão, estacas, rizomas, rebrotamento e esporos. Estratégias apenas de sementes/polinização ou sementes/mudas continuam pendentes quando não há mecanismo/vetor suficientemente determinado. “Polinização pendente” não significa afirmar dependência obrigatória de animais: o vetor ainda não está comprovado.

| Auditoria | Resultado |
|---|---:|
| Espécies no catálogo | 3.096 |
| Rotas internas declaradas compatíveis com a política L2 | 1.771 |
| Pendentes por polinização/vetor/mecanismo | 1.159 |
| Excepcionais bloqueadas por autorização canônica | 166 |
| Ausências anatômicas identificadas em L1 | 548 |
| Dessas 548, com rota interna declarada em L2 | **221** |
| Dessas 548, ainda pendentes | **327** |

Esses números são contratos de catálogo, **não contagens de espécies materializadas**. Fungos, algas, juncos, trepadeiras, consórcios e extremos mantêm as exigências físicas locais das autoridades anteriores. O mecanismo interno não inventa água, suporte, detrito, energia, micélio ou anomalias para autorizar sua ocorrência.

A maioria das flores permanece pendente: 1.111 das 1.113 espécies florais não recebe reprodução interna autorizada por esta política, por suas dependências ou classe excepcional. Isso é uma limitação explícita dos dados/contratos atuais. Não foi ocultada com sementes fictícias ou fauna implícita. O arquivo `catalog-audit.json` apresenta a divisão completa por tipo e estratégia.

## Produção finita e custo biológico

Os propágulos ecológicos são reservas internas. Não têm ID de item ou de parte coletável e não podem ser extraídos pelo endpoint de coleta. Sua massa é uma estimativa de gameplay derivada do porte adulto R1: aproximadamente 1/10.000 da biomassa para um pacote vegetativo e 1/1.000.000 para um pacote de esporos, com granularidade mínima de 1 mg.

O orçamento anual de referência é 1.000 ppm da biomassa adulta por produtor, com mínimo explícito de 4 mg para a granularidade do modelo. São no máximo dois pacotes por adulto em um período elegível; quatro períodos não excedem o orçamento anual. O banco tem teto de quatro pacotes por adulto. Espaço esgotado impede produção adicional; pacotes expirados não ficam acumulados indefinidamente.

O orçamento representa **nova assimilação modelada reservada à reprodução**, em compartimento separado dos pools R1 de coleta. Não é débito de folhas já coletáveis, reposição de partes exportadas, água W1 disponível ou fotossíntese medida. O ledger é:

`reserva produzida = reserva ainda no banco + dispersada a eventos + expirada + perdida em tentativas`

Cada coorte registra população de origem, época de produção, produtores adultos, fundadores excluídos, descendentes maduros, quota por produtor e alocações já consumidas. Os produtores implícitos permanecem representados pela população estabelecida, sem criar milhões de linhas. Ao alocar um pacote, são registrados o **ID e a posição determinísticos do progenitor**, sua participação na coorte produtora e o débito efetivo. O microsítio do produtor precisa ser elegível.

Uma reserva agregada é potencial modelado da população estabelecida, qualificado na alocação; não se declara que cada fundador virtual teve fertilidade observada individualmente. O total e a quota individual limitam a produção mesmo quando a origem de uma unidade é resolvida sob demanda.

## Calendário, estabelecimento e crescimento

Os eventos ecológicos ocorrem a cada 90 dias, com âncora no dia 30 do calendário de 360 dias. A produção exige maturidade, rota permitida, estação de crescimento e atividade C3/W1/E1 adequada. Jovens não entram na quantidade de reprodutores até atingirem a maturidade L1.

O alcance de referência é 40 m, reduzido para incomuns e raras; a chance de estabelecimento também diminui pela raridade real. Candidatos são amostrados deterministicamente nos slots físicos próximos. Cada tentativa é função da assinatura, população, slot e período, sem sorteios por visita. A chance por tipo é um parâmetro de estabelecimento do modelo, não uma meta de população ou percentual obrigatório de bioma.

O estabelecimento exige vaga sem ocupante/reserva, origem alcançável, pacote viável, habitat elegível e tempo biológico suficiente. Esporos têm viabilidade de referência de 360 dias; pacotes vegetativos, 180 dias. São referências de gameplay para reserva/banco, sem alegar longevidade botânica medida. A espera de estabelecimento é de 14 dias ativos e precisa caber na viabilidade.

O pacote é debitado uma única vez antes de criar o evento. Falhas gastam a reserva correspondente. A capacidade original é somente um teto. Não existe recomposição instantânea, obrigação de preencher todas as vagas ou escalonamento pelo protagonista.

Depois do estabelecimento, L1 determina germinação, juventude, altura, maturidade, recursos e biomassa. O novo indivíduo recebe ID `vgi:l2:...` próprio. O fundador removido conserva seu ID e sua morte, inclusive se seu tombstone só for materializado posteriormente. As posições partem do centro canônico do slot, evitando deriva acumulada entre gerações.

## Evolução sem visitas e extinção

Antes de uma consulta ou ação vegetal, o sistema avança os eventos dos conjuntos registrados até o relógio autoritativo. Todos os eventos vencidos são processados cronologicamente. Nascimentos são resolvidos antes da próxima produção sazonal, permitindo que descendentes maduros participem de ciclos posteriores.

Não há loop diário ou por indivíduo virtual. O custo depende dos períodos ecológicos, populações registradas, vagas perturbadas e participantes efetivamente envolvidos. Uma população intacta continua cheia: pode manter reserva finita, mas não gera indivíduos acima de sua capacidade.

Uma população intacta registrada tardiamente reconstrói seu histórico agregado desde a ativação, incluindo reservas expiradas. Registrar cedo ou visitar tarde produz o mesmo estado biológico. Fontes compatíveis nas bordas são registradas no distúrbio, inclusive através de patches/faces; sua existência não depende de o jogador ter visitado o vizinho.

Avançar de uma vez ou em etapas foi comparado incluindo bancos, perdas, nascimentos, IDs, reservas e corpos. Reconsultar no mesmo instante não produz novos pacotes nem novas tentativas. Replay de ação não avança a biologia; undo restaura as novas tabelas e a fronteira temporal pelo checkpoint existente.

Morte completa não constitui uma autorização de retorno. A origem pode ser um banco realmente produzido anteriormente ou uma população vizinha compatível e alcançável. Remover/esterilizar o banco e não ter fonte alcançável pode manter a extinção indefinidamente. Uma região completamente limpa usa 64 sondagens determinísticas por período, além do estado esparso conhecido, para não enumerar uma capacidade virtual enorme. Esse é um orçamento de tentativas, sem garantir nenhum nascimento.

## Resultados procedurais reais

As cinco provas usam V4/T1, C3 R1-55, W1, E1, Vg2 e R1 reais, no raio de 63.710 km. O distúrbio técnico representa remoções finitas em slots originais; não altera a distribuição baseline para facilitar o resultado. Os bancos SQLite são descartáveis e separados de campanhas reais.

| Seed | Capacidade | Remoções | Sobreviventes | Vivos em 1 / 3 / 5 / 10 anos | Novos indivíduos em 10 anos | Jovens em 10 anos |
|---:|---:|---:|---:|---|---:|---:|
| 42 | 1.037 | 700 | 337 | 375 / 431 / 474 / **561** | 224 | 78 |
| 0 | 322 | 225 | 97 | 116 / 152 / 182 / **243** | 146 | 53 |
| 7 | 820 | 574 | 246 | 308 / 404 / 488 / **646** | 400 | 212 |
| 2026 | 281 | 196 | 85 | 88 / 92 / 95 / **110** | 25 | 9 |
| 12345 | 2.221 | 1.554 | 667 | 777 / 957 / 1.129 / **1.523** | 856 | 191 |

Foram efetivamente estabelecidos **1.651 novos indivíduos** nas cinco provas de referência. Todos esses eventos terminaram com status `established`. Nenhuma das cinco populações foi obrigada a retornar ao teto. A seed 2026 permanece bastante degradada; a existência de condições e fontes elegíveis limita sua recuperação.

Na seed 42, depois de dez anos há 337 fundadores sobreviventes, 146 novos adultos e 78 jovens. Os novos indivíduos têm alturas entre 32 e 1.487 cm e diferentes datas de nascimento. Não foram recriadas 700 árvores adultas. As vagas restantes são 476.

![Recuperação real do patch após 700 remoções](../artifacts/vegetation-renewal-l2-validated/forest-recovery.png)

Este diagnóstico mostra slots e estágios, sem representar cobertura gráfica contínua ou substituir o mapa público. Os arquivos `seed-*.json`, `seed-*.sqlite` e `seed-42-slots.json` guardam estados, datas, eventos, origens, snapshots e posições técnicas.

As provas adicionais em `extra-proofs.json` mostram:

- **Extinção sem fonte alcançável:** EV-FL-1827 foi removida completamente, com esterilização da reserva e alcance controlado de 5 m. Permaneceu com zero indivíduos e zero eventos de nascimento depois de dez anos. Populações externas não foram apagadas: o limite físico de alcance é que impede a contribuição.
- **Banco anterior à morte:** no mesmo alcance controlado, uma reserva real de 4.148 pacotes foi preservada. Após a morte de todos os progenitores, um pacote viável gerou um novo indivíduo. Seu progenitor estava vivo na produção e morto no estabelecimento; o fundador não ressuscitou. Depois de três anos havia somente um indivíduo, não 1.037 restaurados.
- **Rota interna sem órgão coletável:** EV-FL-1463 declara `sementes_ou_divisao`. Não possui órgão bruto de propagação adequado a L1. L2 produziu 122 novos indivíduos por reserva vegetativa interna em três anos, após 300 remoções numa capacidade real de 21.141. Não criou nenhum item de inventário. São 122 eventos reais adicionais, distintos da contagem das cinco referências.

## Desempenho e limitações práticas

Os nascimentos regionais persistem indivíduos e proveniência, mas deixam a preparação geológica/E1 detalhada de seus pontos para a observação local. O teste de observação prepara a evidência física do jovem e verifica que a resposta ao jogador não expõe coordenadas. Ações de coleta continuam exigindo presença, ferramenta, proficiência, maturidade e estoque real.

Foram removidas revalidações de coortes por pacote e gravações por semente. As fontes são validadas sob o mesmo fence transacional, com gravação em lote. Referências de comunidades e participantes e taxas sazonais congeladas são reutilizadas dentro do avanço; o cache não atravessa transações nem substitui os checksums persistidos.

O benchmark copia a prova para RAM e preserva o arquivo original. Na seed 42, avançar mais um ano a partir do décimo ano levou aproximadamente **3,49 s**. A reconstrução fria dos contratos anteriores levou **6,88 s**. Após esse avanço, a população tinha 577 indivíduos vivos. Os vinte registros de população L2 somavam aproximadamente **87,6 KB** de JSON, com máximo de 58,1 KB por população. A etapa medida aumentou o working set de aproximadamente 259,7 MB para 262,3 MB; o processo inclui catálogo, geografia e banco em RAM. O pico de aproximadamente 421 MB inclui o carregamento dessas fontes, não apenas L2.

O perfil aponta consultas ORM, cópias de estruturas, consultas/classificação física e projeção dos participantes como custos relevantes. Não há enumeração diária dos fundadores virtuais, worker ecológico ou processamento de milhões de setores.

**Saltos grandes ainda têm latência perceptível.** Nas validações concorrentes, o maior avanço regional medido levou 54,54 s, num salto de cinco anos com centenas de novos participantes na seed 12345. Esse número não deve ser apresentado como tempo interativo aceitável nem comparado diretamente ao benchmark de um ano. L2 permanece experimental; integração de interface precisa de indicação de preparação e medição em condições representativas antes de ativação em campanhas. Não foi acrescentado outro serviço para esconder esse custo.

As consultas regionais usam adequação sazonal congelada e a aproximação existente de cobertura ponderada pelo porte. Não simulam chuva diária, nutriente medido, competição detalhada, mortalidade natural por idade, polinizadores, sucessão completa, dispersão ilimitada ou alterações físicas dinâmicas sem reconciliação. A amostragem de fontes é finita e conservadora; existência de uma fonte não garante ocupação de todas as vagas. Permanecem pendentes as dependências explícitas do catálogo, sobretudo flores/polinização e micro-habitats ainda não comprovados.

## Validação e compatibilidade

Foram aprovados **202 casos distintos no escopo selecionado desta fase**:

- **180 regressões** de L1, R1, vegetação Vg1/Vg2, persistência, relógio, equipamentos, carga, containers, reset e undo.
- **22 casos L2**, incluindo auditoria das 3.096 estratégias, reserva sem mortes, 700 remoções, novas gerações, semigrupo temporal, extinção, rotas não coletáveis, cinco seeds, corrupção/rollback, reserva anterior à morte, raridade, migração, reinício entre processos, HTTP/replay/undo, legado não migrado, registro tardio, geometria e observação física de jovem.
- Reexecução focal dos casos de 700 perdas, equivalência temporal e reinício após otimização de cache: três aprovados, já incluídos nos 22.

As 180 regressões levaram 671,74 s na execução concorrente. Os primeiros dezoito casos L2 completos passaram em 411,51 s, complementados pelos quatro casos novos de legado, registro tardio e geometria/observação. Logs: `artifacts/renewal-l2-regression.log`, `renewal-l2-final-tests.log`, `renewal-l2-legacy-tests.log`, `renewal-l2-late-registration.log`, `renewal-l2-local-geometry.log` e `renewal-l2-cache-tests.log`.

Este é um escopo de regressão afetado, não uma alegação de que todos os testes do repositório foram executados novamente. Os 843 casos da fase anterior são o histórico informado, não foram somados a esta contagem. As autoridades Vg2/W1 são comparadas antes/depois nas cinco seeds, e a versão assinada L1 permaneceu intacta.

O banco real `backend/everreach.db` conservou 2.027.520 bytes e `LastWriteTimeUtc=2026-10-26 21:53:21`. Nenhuma migração ou ativação foi executada nele. V22 foi apenas lido com validação do hash já existente.

## Arquivos e reprodução

Novos arquivos:

- `backend/app/game/world/genesis/vegetation/renewal.py` — configuração, banco, produção recorrente, alocação finita, recrutamento, distúrbio e consultas.
- `backend/app/db/models/world_vegetation_renewal.py` — autoridade e estados esparsos.
- `backend/alembic/versions/x32x5s6t7u8v_vegetation_renewal_l2.py` — migração aditiva sem ativação.
- `backend/app/tests/test_vegetation_renewal_l2.py` — testes novos.
- `backend/scripts/validate_vegetation_renewal.py` e `benchmark_vegetation_renewal.py` — provas, auditoria, figura, perfil e métricas.
- Este relatório e `artifacts/vegetation-renewal-l2-validated/`.

Integrações alteradas: `vegetation/lifecycle.py`, `vegetation/service.py`, `db/models/__init__.py` e `world/reset.py`. O processamento L1 aceita um corte temporal interno para resolver eventos em ordem, mantendo o comportamento anterior quando L2 está ausente. Nenhum endpoint, dataset, clima, hidrologia ou grafo de viagem foi substituído.

Para reproduzir, a partir de `backend`, usando um novo diretório de provas:

```powershell
.\.venv\Scripts\python.exe -m pytest app/tests/test_vegetation_renewal_l2.py -q
.\.venv\Scripts\python.exe -m scripts.validate_vegetation_renewal --out ../artifacts/l2-reproduction
.\.venv\Scripts\python.exe -m scripts.benchmark_vegetation_renewal --out ../artifacts/l2-reproduction
```

Os scripts usam os preparadores reais da suíte de desenvolvimento, sem LLM ou geografia fabricada. Resultados completos podem ser retomados; não é necessário recalcular os cinco mundos para gerar novamente a imagem. Os comandos não ativam campanhas reais.

L2 entrega renovação recorrente operacional e persistente para as rotas permitidas, com recuperação parcial real e manutenção de extinções legítimas. A próxima integração é apresentar jovens, estágios, indisponibilidades e preparação regional na interface; os contratos pendentes continuam identificados, sem sementes ou organismos fictícios.
