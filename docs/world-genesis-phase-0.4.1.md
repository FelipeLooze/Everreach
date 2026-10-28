# World Genesis — fase 0.4.1: refinamento regional HR1

## Auditoria e decisão antes da implementação

Foram revisados H1 (`geometry`, `plan`, `sectors`, `service`), o avaliador V4 e sua calibração, R1 e persistência/exclusão. H1 fixa uma árvore macro e condições potenciais de transbordamento, não leitos. Suas cinco amostras por ligação podem omitir barreiras. R1 demonstra consultas limitadas e portas compartilhadas, mas não oferece roteamento hidráulico. V4 usa relevo inteiro em metros; na referência sua menor escala de ruído é da ordem de centenas de quilômetros. Mais amostras não criam canais de metros.

| Alternativa | Avaliação |
| --- | --- |
| Recortar linhas H1 e chamá-las de rios | Rejeitada: não verifica obstáculos regionais. |
| Recalcular bacias globais em alta resolução | Rejeitada: rompe orçamento e geração progressiva. |
| Esculpir canais novos no V4 | Rejeitada nesta fase: exigiria outra fonte de altitude/versionamento de terreno. |
| Refinar células H1 canônicas, com busca limitada e portas bilaterais | Escolhida: identidades subordinadas, rotas contra V4 e falhas explícitas. |

HR1 é opt-in, separado de H1 e R1, sem alterar dados anteriores. Cada região corresponde a uma célula H1. Um grafo regular amostrado tem orçamento fixo; escolher uma porta examina apenas as duas células incidentes. A seleção é calculada dos dois lados com a mesma regra, sem depender da exploração. O refinamento pode deslocar o ponto representativo H1 dentro da mesma borda; a ligação macro continua a mesma.

As cotas das junções macro permanecem fixas. A busca minimax tenta satisfazê-las sem incisão; se a menor barreira amostrada exceder a cota H1, devolve incompatibilidade, nunca uma linha atravessando a montanha. A rede interna é acíclica e confluente, com um único receptor por vértice usado. Cotas acima do terreno indicam armazenamento potencial necessário, sem afirmar que o caminho tenha água.

## Contrato e algoritmo implementados

`RegionalHydrologyConfig` fixa `refinement_version=1`, `hydrology_version=1` e profundidade de amostragem 2–4, padrão 3. A assinatura HR1 inclui a assinatura H1 e todos os parâmetros. O namespace HR1 não renomeia bacias, reaches, junções ou depressões H1. Cada baseline registra fonte V4, H1, configuração, endereço canônico, contexto da bacia H1, referência ao armazenamento macro quando houver, portas, rotas, segmentos, candidatos a depressão, incompatibilidades e orçamento.

Cada célula H1 recebe uma grade de vértices dyádicos no cube-sphere. No padrão são 77 vértices e 112 arestas por grafo; na profundidade máxima, 285 e 480. Cantos são excluídos e vértices da borda são folhas, evitando sair por um terceiro território ou usar a borda inteira como leito. Cada aresta possui cinco alturas V4: extremidades e quartos intermediários. As coordenadas, alturas, custos, desempates e cotas usadas em decisões são inteiros ou frações exatas. Não há ruído novo.

### Portas bilaterais

Para cada ligação H1 já existente, os dois grafos incidentes oferecem os mesmos 7 pontos de borda no padrão, ou 3/15 nas outras profundidades. Uma busca minimax em cada lado calcula as barreiras até sua junção macro. A escolha minimiza a maior barreira das duas metades, depois prefere proximidade do meio da borda e o raio inteiro em ordem lexicográfica. Portanto, há tentativa de desvio e escolha entre alternativas; a posição H1 não é imposta como leito.

A cota da porta é a menor cabeça amostrada necessária para atingir a junção a jusante, cuja cabeça H1 é fixa. A maior barreira bilateral precisa caber na cabeça da junção a montante. O contrato contém direção, IDs H1/HR1, ponto escolhido, ponto representativo H1, cotas, terreno, número de candidatos, cabeça mínima requerida e estado de compatibilidade. O mesmo contrato é calculado antes de qualquer vizinho ser materializado, inclusive entre faces.

Uma falha não prova que inexista caminho na superfície contínua: significa incompatibilidade **neste domínio, nesta resolução e nestas amostras**. Não se aumenta a cota H1 nem se altera o terreno para obter aprovação. A pendência sugere refinamento mais fino ou domínio canônico maior, futuramente versionado.

### Rede interna e confluências

Primeiro é roteada a saída junção → porta. Depois, uma única árvore minimax até a junção roteia as entradas, reservando o caminho de saída para impedir retornos e cruzamentos contraditórios. Entradas que se encontram compartilham segmentos e receptor. Cada vértice usado tem no máximo um receptor; cada caminho preserva a identidade da ligação/reach H1. O centro macro é ponto de transferência ou terminal, **não uma nascente nova**. Não são criados afluentes para preencher uma região sem ligações H1.

Se uma entrada não conseguir atingir a junção com a cabeça fixada sem conflitar com a saída reservada, resulta em `local_confluence_conflict`, sem segmento inventado. A política não faz busca combinatória de todas as árvores de confluência nem tenta deslocar a junção macro. É uma limitação deliberada do orçamento inicial. Uma saída incompatível também deixa as entradas como pendentes a jusante, em vez de terminar um rio artificialmente ali.

Cada segmento registra cinco alturas de terreno e cinco cabeças potenciais, não crescentes a jusante. Um envelope de máximos a jusante explica qualquer cota acima do terreno como armazenamento potencial; `storage_raise_m` expõe a diferença. A cabeça nas junções e portas é exata no grafo amostrado. O algoritmo não garante monotonicidade da superfície contínua entre todas as amostras.

### Continuidade não é apenas igualdade de porta

`compare_regional_connection(a, b, port_id)` confere as duas metades persistidas, seus contratos e seus estados locais. Só retorna `connected_sampled_potential` quando ambas as rotas locais existem e são compatíveis. Se um lado estiver bloqueado, retorna `refinement_incompatible`, mesmo que a porta isolada seja bilateralmente viável. Uma rota isolada sempre declara `peer_validation_pending`; não pode ser consumida como rio conectado e ativo sem essa conferência.

A continuidade global decorre da árvore H1 e das árvores locais sem ciclos, sem adicionar ligações entre bacias. Isso vale para o subconjunto bilateralmente compatível, não é uma promessa de realização de todos os corredores H1. Lacunas ficam como pendências explícitas, nunca como rios físicos que desaparecem.

## Consultas locais e persistência progressiva

O recorte de um segmento salvo usa `CellKey` e frações exatas da carta cúbica. Setores adjacentes compartilham IDs de corte e condições de cabeça; nas bordas regionais/faces, recebem o ID e a cabeça da porta bilateral. Vértices de confluência e a junção macro possuem identidade comum. Em cortes dentro de uma aresta, o contrato informa limites de cabeça até um refinamento menor, sem fingir uma cota local já resolvida. Foram testados setores nos níveis 5, 13 e 24.

O detalhe local entregue é **consulta/recorte de trajetórias regionais amostradas**, não um leito de metros. A consulta comum não reexecuta o planejamento H1 nem o roteador regional quando já existe baseline. Não é calculada uma bacia inteira ao movimentar o personagem.

API interna, explicitamente habilitada após V4 e H1:

```python
from app.game.world.genesis.hydrology.regional_service import (
    initialize_regional_hydrology, materialize_hydrology_region, query_hydrology_sector,
)

initialize_regional_hydrology(db, campaign_id)  # somente configuração fixada
region = materialize_hydrology_region(db, campaign_id, h1_node_index)
sector = query_hydrology_sector(db, campaign_id, sector_key)
# O chamador controla commit/rollback.
```

A consulta por setor prepara apenas sua região canônica se ainda não existir. Para mundos cujo nível de setor seja menor que o H1, essa API recusa a consulta agregada; a preparação por índice regional continua disponível. Não se tenta enumerar silenciosamente grandes coberturas.

Persistência aditiva:

- `genesis_hydrology_refinements`: opt-in e configuração fixada, com assinatura/checksum H1 de origem.
- `genesis_hydrology_regions`: região preparada, assinatura, checksum do baseline e `changes` separado.

A migração **`k19k2f3g4h5i`**, posterior a `j18j1e2f3g4h`, somente cria tabelas. Saves V1–V4/H1 existentes não recebem HR1 automaticamente. A exclusão de campanha remove regiões/configuração HR1 antes dos pais H1. Os testes exercitam upgrade/downgrade em banco temporário preservando linhas V4, H1 e snapshots H1. **O banco real não foi migrado.** A ativação em execução requer a migração pelo fluxo habitual e o opt-in acima.

Ao retornar, o serviço confere proveniência, checksum e invariantes do baseline salvo. Não reamostra terreno nem recria rotas. Alterações futuras são preservadas em `changes`; a consulta devolve baseline e changes separadamente. HR1 não interpreta ainda eventos fictícios de barragens ou alterações de terreno: preservar esses dados não equivale a simular seus efeitos. Como nos modelos existentes, é necessário atribuir um novo dicionário para persistir JSON alterado pelo ORM.

Os grafos e amostras são compartilhados apenas durante uma preparação e descartados ao final: no máximo cinco grafos e 12.000 amostras. Na configuração máxima, o limite estrutural é `5 × (285 + 3 × 480) = 8.625` posições antes de deduplicar bordas. A margem do orçamento permite falha explícita se um futuro código ultrapassar o contrato. Não há cache global HR1 sem limite; são reutilizados o cache H1 existente e as linhas persistidas, com identidade de sessão do ORM. Não há workers, filas, ticks de água ou geração de regiões distantes.

## Depressões, clima futuro e suficiência do terreno

Os candidatos regionais a depressão são mínimos fechados no grafo de amostras interiores, com barreiras de quarto de aresta. A extensão é `unresolved_open_patch_candidate`: eles não representam componentes globais de lago nem uma capacidade de armazenamento já medida. São identidades subordinadas; o vínculo com a bacia e o candidato macro H1 permanece separado.

Todos os estados de água real são desconhecidos. O contrato reserva precipitação, evaporação, volume disponível e sazonalidade como `None`; vazão e perenidade das portas também são desconhecidas. Não há vazão inferida de área geométrica, lago permanente ou volume preenchido automaticamente. Cotas de transbordamento são condições potenciais, não uma fonte de água.

Na referência de 63.710 km, o menor comprimento de ruído V4 é **316.227 m (~316 km)**. A célula H1 tem escala média próxima de 2.881 km; a grade HR1 padrão divide sua extensão em oito, com escala característica de ~360 km e sondas intermediárias menores. Essa resolução encontra desvios e barreiras regionais; não suporta afirmar a existência de um canal estreito, cachoeira ou desfiladeiro específico. A precisão dos endereços não acrescenta relevo ausente. Em raios extremos, a resolução física fica ainda mais grosseira, mantendo o orçamento.

Para detalhe de exploração em metros será necessário um contrato explícito de terreno, por exemplo T1, que ainda **não foi implementado**. Ele deverá fixar fonte V4, seed independente de exploração, versão e escala física, continuidade entre tiles/faces, interface canônica de consulta de altitude e proveniência nos snapshots hidrográficos. A hierarquia deverá escolher uma única altitude autoritativa para cada versão/cobertura; não se deve somar um ruído de rios por fora do avaliador. Mundos/regiões antigos manterão suas altitudes e dados salvos, sem conversão automática. HR1 não antecipa essa alteração de terreno nem garante que todo conflito atual exija T1: uma grade mais fina ou outra política regional pode bastar.

## Visualizações, amostras e métricas

Executar a partir de `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.preview_regional_hydrology --suite --measure-memory --output ../artifacts/hydrology-regional-hr1
```

Também aceita `--seed`, `--radius-m`, `--depth` e até 16 `--nodes` explicitamente selecionados por planeta. A seleção padrão inclui vizinhos em emendas e confluências; não percorre todos os nós buscando casos favoráveis. A ferramenta não abre banco. Exporta cada baseline regional, imagem comparativa e resumo, além de conferir portas bilaterais que aparecem nos dois lados selecionados.

As imagens comparam o corredor H1 em branco com o candidato HR1. Ciano indica perfil amostrado sem represamento; laranja exige cabeça acima do terreno em alguma amostra. Marcadores vermelhos identificam incompatibilidade de cota; a legenda declara água desconhecida. O fundo é um diagnóstico discreto dos vértices V4, não um campo novo de altitude.

Artefatos: [comparação estruturada](../artifacts/hydrology-regional-hr1/comparison.json), [desvio regional, seed 42/nó 2176](../artifacts/hydrology-regional-hr1/seed-42-r63710000/node-2176/regional.png), [confluência, seed 42/nó 11](../artifacts/hydrology-regional-hr1/seed-42-r63710000/node-11/regional.png), [conflito local, nó 159](../artifacts/hydrology-regional-hr1/seed-42-r63710000/node-159/regional.png), [saída incompatível, seed 0/nó 3487](../artifacts/hydrology-regional-hr1/seed-0-r63710000/node-3487/regional.png).

| Seed | Raio (km) | Regiões selecionadas | Metades de rota compatíveis / avaliadas | Observação |
| --- | ---: | ---: | ---: | --- |
| 42 | 63.710 | 7 | 17 / 18 | Um conflito na entrada de uma confluência. |
| 0 | 63.710 | 8 | 16 / 18 | Uma saída incompatível e uma entrada pendente por essa saída. |
| 2026 | 6.371 | 8 | 24 / 24 | Sem incompatibilidades nas regiões selecionadas. |

São **23 regiões selecionadas**, não estatística de aprovação de todo o planeta. Foram comparadas 12 ligações com as duas regiões presentes: 11 conectadas no grafo amostrado e uma incompatível. O conflito de confluência da seed 42 afeta outra ligação, cujo segundo lado não foi incluído nessa seleção.

Problemas concretos:

- Na seed 0, nó 3487 → 3486, a cabeça H1 de montante é 1.073 m, mas a menor barreira bilateral encontrada exige 1.083 m. O serviço preserva os 1.073 m e não cria a rota, nem a entrada que dependeria dessa saída.
- Na seed 42, nó 159, uma entrada exige 1.645 m na árvore local reservada, excedendo a condição compartilhada compatível de 1.621 m. A entrada é marcada como conflito local; a saída restante conserva seu contrato.

Não se corrigiram esses casos com terreno fictício. As correções arquiteturais são a busca de alternativas de porta/percurso, a recusa explícita e a conferência bilateral antes de declarar conectividade. Resolver todas as pendências exige uma política posterior de domínio/resolução/confluência com versão própria.

No benchmark final das regiões selecionadas, preparação HR1 levou **0,143–0,345 s**, com **819–2.037 amostras** e 2–5 grafos no padrão. Consultas de recorte em memória tiveram medianas por região aproximadamente **0,15–0,60 ms**. Isso exclui acesso ORM, checksum e validação de linha persistida; não é latência medida de uma ação do jogador. O baseline JSON ficou aproximadamente entre 4,8 e 12,5 KB.

Uma preparação separada instrumentada por planeta apresentou pico Python de aproximadamente **0,51 MiB**, excluindo fonte V4 e H1 já existentes, imagens e ORM. A medida inclui grafos/amostras transitórios e baseline; não é RSS total do processo. Os tempos normais não incluem a instrumentação. Testes adicionais usam profundidade máxima e raio de 10¹² m, conferindo orçamento estrutural e pico abaixo de 64 MiB, sem limite rígido de tempo de CPU.

## Arquivos desta fase

| Arquivo | Mudança |
| --- | --- |
| `backend/app/game/world/genesis/hydrology/regional_graph.py` | Grafos V4 limitados, perfis compartilhados e busca minimax inteira. |
| `.../hydrology/regional.py` | Configuração HR1, portas, confluências, cotas, recortes, validação e conferência bilateral. |
| `.../hydrology/regional_service.py` | Opt-in, preparação progressiva, recarga sem regeneração e consultas. |
| `.../hydrology/regional_preview.py` | Imagens técnicas H1 × HR1. |
| `backend/app/db/models/world_hydrology_regional.py` | Configuração e regiões com baseline/changes separados. |
| `backend/app/db/models/__init__.py`, `backend/app/game/world/reset.py` | Registro dos modelos e exclusão por dependências. |
| `backend/alembic/versions/k19k2f3g4h5i_add_regional_hydrology_hr1.py` | Migração aditiva, sem conversões. |
| `backend/app/tests/test_genesis_hydrology_regional.py` | Determinismo, portas, confluências, obstáculos, validação, recursos e viewer. |
| `backend/app/tests/test_genesis_hydrology_regional_persistence.py` | Opt-in, persistência, ordem, alterações, rollback, migração e exclusão. |
| `backend/scripts/preview_regional_hydrology.py` | Seleção técnica, comparação entre seeds/raios e benchmarks. |
| `docs/world-genesis-phase-0.4.1.md`, `artifacts/hydrology-regional-hr1/` | Decisões, resultados e imagens reproduzíveis. |

As alterações das fases anteriores já presentes no workspace foram preservadas. Não foram editados algoritmos/configurações/snapshots H1, V4 ou R1, mapa público, exploração, grafo de movimento ou datasets.

## Testes executados

**409 testes da regressão selecionada passaram em 203,62 s.** Depois, a checagem de configuração foi executada novamente com sete casos aprovados, incluindo um novo caso de rejeição de versão booleana. Isso cobre **410 casos distintos**, dos quais 31 são novos HR1. O tempo da regressão inclui concorrência com a geração dos artefatos técnicos e não é benchmark isolado. Não foi executada a suíte completa do backend/frontend. Permanece apenas o aviso preexistente de depreciação Starlette/httpx.

A seleção inclui `test_genesis*.py`, `test_map*.py`, `test_travel*.py`, `test_world_gen*.py`, `test_regional_boundaries.py`, `test_cross_region_routes.py`, `test_explor*.py`, `test_campaign_reset.py`, `test_region_skeleton.py`, `test_neighbor_region_materialization.py`, `test_world_simulation_integration.py`, `test_simulation_scope.py` e `test_world_time*.py`.

Os novos testes verificam: limites/versionamento; determinismo e ordem; replay em processos com `PYTHONHASHSEED` diferente; preservação da fonte V4/H1; portas/cotas entre faces em níveis 5/13/24; árvore confluente de receptor único; recusa de barreiras acima de H1; busca que desvia uma crista amostrada; armazenamento sem permanência; rejeição de ciclos/cotas/endereços inválidos; ausência de recomputação H1; raio de 10¹² m; orçamento de grafos/amostras/memória; região vazia sem nascentes inventadas; inspeção bilateral de metades pendentes; exportação visual; opt-in; persistência em ambas as ordens; recarga sem reamostrar ou rerotear; alterações conservadas; checksum/proveniência; rollback; exclusão por campanha; upgrade/downgrade preservando V4/H1 e snapshots anteriores.

Também passaram `compileall`, `git diff --check` e a conferência da cadeia Alembic com cabeça única `k19k2f3g4h5i`. As imagens de desvio, confluência e incompatibilidade foram inspecionadas; todos os 23 baselines exportados foram validados pelo gerador, com 12 comparações bilaterais de ligação. Nenhuma migração foi aplicada ao banco real.

## Limitações e próximas etapas

HR1 entrega uma fundação regional funcional e testável, com consultas locais, persistência e incompatibilidades visíveis. **Não entrega leitos locais definitivos nem realiza todos os corredores H1.** Portas coincidentes não dispensam a conferência das duas metades. A grade e suas cinco amostras por aresta não provam a ausência de barreiras entre amostras, e a política fixa de junção/saída pode recusar uma confluência realizável por outro arranjo.

Antes de usar esses caminhos como geografia jogável, a próxima etapa deverá escolher uma política versionada para pendências, validar cotas/trajetos em escala de exploração e definir a fonte única de terreno detalhado onde V4 não tiver suporte. O futuro balanço climático poderá então determinar alimentação, armazenamento efetivo, vazão, sazonalidade e permanência de lagos. Nenhum curso deve ser marcado como perene ou revelado ao jogador apenas por existir um candidato HR1.
