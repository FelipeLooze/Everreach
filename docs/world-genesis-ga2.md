# GA2 — reprodução e recuperação vegetal em ritmo de RPG

27 de outubro de 2026. Política experimental `adventure_renewal_ga2`, revisão 1. Implementação da direção AP1 sobre L2/S1, usando o crescimento GA1 existente. Nenhuma campanha real foi ativada.

## Resultado

Nas cinco seeds 42, 0, 7, 2026 e 12345, no raio de 63.710 km, foram executadas **60 campanhas isoladas**: seis categorias reais, cada uma sob GA1+L2 e GA1+GA2. GA2 estabeleceu **3.767 descendentes reais** até o dia 360 nos trinta casos, contra 1.040 nos controles. Esses números somam campanhas independentes, não espécies novas nem percentuais planetários.

Cada par usa a mesma geografia, a mesma autoridade GA1 e **exatamente as mesmas posições removidas**, verificadas nos bancos iniciais. A ferramenta histórica sorteava a seleção da perturbação usando a assinatura L2; a nova opção interna de seleção explícita permitiu repetir a intervenção física no controle e em GA2. O comportamento histórico sem essa opção permanece inalterado. Amostras anteriores com remoções não pareadas foram arquivadas fora dos resultados finais.

| Categoria | Primeiro nascimento com GA1+L2 | Com GA1+GA2 |
|---|---:|---:|
| Flores | 133,67–250,13 dias | **2–6 dias** |
| Ervas | 43,67–229,00 dias | **2–8 dias** |
| Gramíneas | 43,67–133,67 dias | **3–6 dias** |
| Arbustos | 43,67–133,67 dias | **5–11 dias** |
| Árvores comuns | 43,67–133,67 dias | **8–10 dias** |
| Árvores grandes | 43,67–133,67 dias | **4–9 dias** |

As condições vieram das autoridades existentes e os progenitores das populações reais. Os espaços foram abertos por remoções experimentais explícitas, e não inventados no gerador para forçar sucesso. São cenários favoráveis de recuperação, não uma garantia universal de nascimento.

O [relatório de métricas](../artifacts/vegetation-ga2/results.md) lista espécie, primeira oportunidade, primeiro propágulo, primeiro nascimento e primeira maturidade em cada seed/categoria. As JSONs e SQLite correspondentes contêm os eventos, reservas e ocupações persistidos.

## Ritmo configurável

| Classe | Intervalo entre oportunidades | Estabelecimento após reserva | Teto de produção por adulto maduro em 360 dias | Chance-base por vaga/oportunidade |
|---|---:|---:|---:|---:|
| Flor, erva e gramínea | 3–5 dias | 1–3 dias | 60 propágulos | 35% |
| Arbusto | 5–10 dias | 2–5 dias | 36 | 25% |
| Árvore comum | 7–14 dias | 3–7 dias | 24 | 18% |
| Árvore grande | 10–15 dias | 3–7 dias | 18 | 12% |
| Árvore lenta explicitamente designada em GA1 | 10–15 dias | 3–7 dias | 18 | 12% |
| Outros organismos ordinários | 5–12 dias | 2–5 dias | 30 | 20% |
| Excepcionais/legado sem revisão | Não recebem produção automática | — | 0 | 0 |

Esses são parâmetros de gameplay, não fertilidade botânica medida. O intervalo e o estabelecimento são escolhidos deterministicamente por espécie dentro da faixa assinada. O tipo/porte acompanha a classificação GA1 existente; não é derivado de nível do protagonista ou raridade. “Árvore comum” nessa tabela identifica a classe de porte/ritmo padrão, não uma garantia de raridade `comum` no catálogo.

A primeira oportunidade possui uma fase determinística por população, entre um dia e o intervalo completo, ancorada na ativação. As seguintes respeitam o intervalo da espécie. Por isso um primeiro nascimento pode anteceder um intervalo inteiro — por exemplo, fase de um dia mais três de estabelecimento. Não existe tentativa extra ao observar ou revisitar.

Estações favoráveis creditam taxa integral; fora delas, a taxa padrão é 75%. Não há bloqueio trimestral nem necessidade de aguardar verão para toda reprodução comum. O marcador canônico de atividade anual é reconhecido. O habitat continua elegível segundo os contratos existentes: GA2 não libera gelo, cavernas ou ecossistemas ausentes.

Raridade reduz a chance de sucesso para 100%, 85%, 70% ou 55% da chance-base, conforme a classe ordinária. O alcance de dispersão e os requisitos canônicos continuam vindo dos contratos existentes. Raridade não converte o intervalo de poucos dias em meses.

## Produção, reserva e estabelecimento são processos distintos

O orçamento GA2 é proporcional ao tempo de progenitores maduros ainda presentes na oportunidade de produção. Integra taxas sazonais e a maturidade GA1 dos descendentes; um recém-nascido não recebe crédito como se fosse adulto durante todo o intervalo anterior.

Em termos mecânicos:

```text
crédito = integral de minutos maduros × taxa sazonal × propágulos anuais / ano
```

O resto fracionário é persistido em inteiros. Tokens inteiros sem espaço no banco são descartados, sem formar um crédito crescente que explodiria após anos. Os bancos mantêm o limite configurável L2, inicialmente quatro propágulos por adulto, e viabilidade GA2 de trinta dias. Propágulos expirados são imediatamente inelegíveis para consumo; a contabilização de expiração é consolidada nas oportunidades seguintes.

Uma oportunidade não reutiliza a quota trimestral L2 inteira. Os novos tetos são uma recalibração **explícita**: por exemplo, dezoito propágulos por adulto/ano para uma árvore grande. A produção é dividida pelo tempo decorrido, não multiplicada pelo número de consultas ou pelo número de rodadas.

O banco representa um orçamento interno abstrato, não itens de sementes. A seleção do progenitor possui quota por banco, consumo único e limite global de tokens. O débito ocorre ao reservar um nascimento. Uma reserva cancelada por devastação não é devolvida como um segundo recurso. Capacidade cheia impede novas reservas.

A contabilidade de massa interna L2 continua verificável, usando o tamanho de unidade herdado, mas não financia GA2 por retirada de R1. Os campos antigos de referência de massa não determinam sua produção. O parâmetro legado `annual_reserve_ppm` não é um ajuste GA2: valores diferentes do padrão são rejeitados, indicando usar `annual_packets_per_adult`.

GA2 não muda estoques, massas ou inventário R1. Uma planta pode amadurecer rapidamente sem possuir folhas/frutos coletáveis fora da estação ou antes da recuperação L1 dessas partes. A validação de coleta usou a janela real do catálogo e passagem de tempo; não concedeu estoque para facilitar o teste.

## Recuperação real da floresta da seed 42

População EV-FL-1827, capacidade original de 1.037 árvores. Foram removidas 700 posições; permaneceram **337 fundadores**, que não foram recriados nem renomeados. O primeiro propágulo surgiu na primeira oportunidade, e o primeiro nascimento ocorreu no quarto dia.

| Dia | Vivos GA1+L2 | Vivos GA1+GA2 | Novos adultos GA2 | Jovens | Germinando | Vagas restantes |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 337 | 337 | 0 | 0 | 0 | 700 |
| 7 | 337 | 353 | 0 | 0 | 16 | 684 |
| 15 | 337 | 353 | 0 | 16 | 0 | 684 |
| 30 | 337 | 377 | 0 | 40 | 0 | 660 |
| 60 | 344 | 420 | 0 | 79 | 4 | 617 |
| 90 | 344 | 426 | 43 | 43 | 3 | 611 |
| 180 | 356 | 438 | 95 | 6 | 0 | 599 |

Os 337 adultos fundadores sobreviventes permanecem em todas as linhas. Novos adultos são apenas descendentes que completaram GA1. Não há obrigação de preencher as vagas.

### Cobertura e altura

A cobertura original da população-alvo representava 14,4766% da área do patch, que também contém outras espécies. Após a remoção, caiu para 4,7045%. No GA2 evoluiu para:

| Dia | Cobertura da população na área do patch | Altura média dos vivos |
|---|---:|---:|
| 7 | 4,7050% | 14,22 m |
| 15 | 4,7112% | 14,31 m |
| 30 | 4,7543% | 13,73 m |
| 60 | 5,1135% | 13,52 m |
| 90 | 5,7287% | 14,49 m |
| 180 | 6,0709% | 14,79 m |

A queda inicial da altura média resulta da entrada de jovens, não do encolhimento dos fundadores. O VSR1 conserva a área de copas proporcional ao quadrado do porte relativo. Uma pequena muda conta como indivíduo e contribui muito menos que uma árvore adulta para a cobertura.

A cobertura de **todo o patch** passou de 73,0535% após a perturbação para 74,4199% no dia 180. Esse total inclui as outras populações preservadas; não deve ser confundido com restauração da população-alvo ou do teto Vg2.

![Floresta real após remoções](../artifacts/vegetation-ga2/large_tree-comparison.png)

### Flores e comunidades pequenas

Na seed 42, a população de flores EV-FL-1139 tinha capacidade de 3.299 e perdeu 150 indivíduos. GA2 produziu 3.230 vivos no dia 7, 3.270 no dia 15, 3.294 no dia 30 e 3.299 no dia 60. Os fundadores restantes forneceram origem válida e orçamentos finitos para cada descendente. No controle GA1+L2, os 3.149 sobreviventes permaneceram sem reposição até depois do dia 180; o primeiro nascimento ocorreu aproximadamente no dia 223,67.

Uma população herbácea com muitas plantas maduras e poucas vagas pode recompor contagem rapidamente. Isso não impõe o mesmo resultado à floresta de grande porte: número, estágio, cobertura e disponibilidade coletável são medidas separadas.

![Comparação da população de flores](../artifacts/vegetation-ga2/flor-comparison.png)

## Origem, reprodução sexual e situações negativas

Os contratos L2/S1 continuam autorizando rotas para **2.930 espécies ordinárias**. As 166 excepcionais sem autorização específica permanecem bloqueadas. GA2 não torna qualquer uma dessas espécies automaticamente elegível em um habitat inexistente.

Na rota sexual, continuam necessários dois progenitores maduros distintos da mesma espécie, com a compatibilidade simplificada S1 e origem rastreável. Nenhum NPC polinizador, sexo botânico ou genética detalhada foi introduzido. As rotas vegetativas e por esporos também são preservadas.

Foi demonstrada recolonização de uma população totalmente removida e com banco esterilizado. O primeiro nascimento teve origem em uma população vizinha real. Descendentes imigrantes posteriormente amadureceram e tornaram-se progenitores locais; as datas de produção foram comparadas com suas maturidades GA1.

Também foi demonstrada extinção persistente quando todas as fontes conspecíficas registradas ao alcance do experimento foram destruídas. Uma população sexual isolada com apenas um fundador maduro não se autofecunda. Banco esgotado/expirado, falta de origem, ausência de parceiro, dispersão insuficiente, capacidade preenchida, habitat inelegível e autorização excepcional ausente continuam impedindo nascimentos.

## Persistência compacta e integração com o jogo

GA2 é um novo descritor e assinatura na infraestrutura L2 existente. Não há um segundo grafo de movimento, nova simulação global, tabela planetária ou worker.

Um nascimento registra no evento e na ocupação nativa: ID do novo indivíduo; ID do pai e, quando aplicável, parceiro S1; população de origem e banco consumido; posição canônica; nascimento; perfil GA1 congelado; instante de maturidade; orçamento consumido; assinaturas e checksums.

Enquanto não encontrado, esse indivíduo mantém um **registro compacto de fenótipo/ocupação**, com crescimento consultado analiticamente. Sua existência não depende de materializar um corpo R1. Não é apenas uma contagem fungível: ID, posição, origem e data já estão estabelecidos.

Ao encontrá-lo, o fluxo existente de ocupante atual hidrata um único corpo autoritativo, preservando exatamente ID, posição, porte, estágio e histórico. Estoques R1/L1 são derivados pelas regras anteriores. Mortos, remoções e eventos permanecem registrados. Indivíduos já encontrados continuam com seus corpos e consequências individuais.

As trinta campanhas GA2 mantiveram **uma linha de corpo individual por campanha** — o fundador inicialmente materializado — enquanto os descendentes permaneciam compactos. As contagens não representam milhares de corpos ORM escondidos em outra etapa. O teste de encontro percorreu o fluxo de fundador morto → ocupante atual → corpo GA2 → coleta finita com replay idempotente.

Populações intactas sem participação ficam implícitas. Quando registradas mais tarde, seu histórico de produção cheia é reconstruído nos mesmos instantes determinísticos. Registro e reconstrução são transacionais: uma falha não deixa uma população vazia que perderia o histórico na tentativa seguinte. Os testes comparam registro antecipado e tardio com igualdade completa de populações, bancos, eventos e fronteira temporal, e comprovam a retomada após uma falha injetada.

## Tempo, determinismo e desempenho

As oportunidades usam o calendário oficial de 360 dias e a fronteira temporal persistida. Processam-se apenas populações participantes, fontes reais ao redor da perturbação e eventos esparsos. Não há ticks diários planetários. Abrir mapa, observar ou revisitar não cria novas oportunidades.

Avançar sessenta dias de uma vez e em seis intervalos de dez produziu consultas e estados autoritativos completos iguais. A hidratação também preservou contagem, estágios e assinatura de medição VSR1. Rollback e undo restauraram reservas, eventos, corpos e ocupações. Uma falha por evento corrompido deixou a fronteira anterior intacta; após reparo explícito no teste, a repetição criou uma única ocupação.

### Benchmarks independentes

Cada linha parte da mesma cópia inicial da floresta perturbada, e não de um estado já avançado pelo benchmark anterior. Preparação do contexto, consulta/atualização, VSR1 e revisita sem avanço são medidos separadamente em `benchmark.json`.

| Salto | GA1+L2: atualização e consulta | GA1+GA2: atualização e consulta |
|---|---:|---:|
| 30 dias | 3,45 s | 1,05 s |
| 60 dias | 0,53 s | 1,63 s |
| 90 dias | 0,62 s | 2,00 s |
| 180 dias | 0,93 s | 2,73 s |
| 360 dias | 1,26 s | 3,47 s |
| 5 anos | 4,18 s | 4,89 s |
| 10 anos | 6,15 s | 6,62 s |

GA2 faz mais trabalho e estabelece mais plantas nos primeiros meses. A frequência maior **não é gratuita**: o salto independente de sessenta dias ficou perceptível. As revisitas sem avanço GA2 ficaram em torno de 0,3–0,4 s nestes ensaios. A linha inicial de trinta dias inclui efeitos de aquecimento de caches; não deve ser usada isoladamente para alegar que GA2 é mais rápida. Preparação de contexto é registrada à parte, incluindo a primeira preparação de vários segundos.

As consultas incrementais das provas nas cinco seeds e as revisitas estão nos artefatos; não se declara latência de frame nem aprovação para ativação automática em campanhas.

O custo de dez anos não cresceu dezenas de vezes com a frequência: continuou limitado neste cenário, sem expansão de corpos. Não se promete esse tempo para uma região arbitrariamente grande, nem para uma devastação total de milhões de posições.

O primeiro protótipo registrava também populações intactas sem participação; GA2 foi restringida a participantes e fontes necessárias. Os demais custos relevantes são seleção de progenitor/banco, verificação de habitat, serialização/checksums de ocupação e operações ORM por instante de oportunidade.

Foram reutilizados o writer fence, savepoints, staging/checksums e memoização E1 da entrega 1.1.2. GA2 acrescenta cache transacional de coortes e de validação de registros compactos, invalidado por mudanças na ocupação e maturidade. A execução com cache foi comparada à execução sem cache com igualdade de estado completo. O cenário de dez anos precisou reconstruir apenas dezenas de coortes, em vez de revalidar cada descendente em cada oportunidade.

Os ensaios preliminares estão arquivados em subdiretórios de protótipo e não entram na tabela pareada final. Nenhuma latência foi escondida em um serviço ou worker; gerar contexto e medir estrutura possuem tempos próprios.

## Ativação e compatibilidade

Depois de inicializar R1 e GA1 explicitamente em uma campanha experimental:

```python
from app.game.world.genesis.vegetation.renewal_gameplay import initialize_ga2, RenewalConfigGA2

initialize_ga2(db, campaign_id, RenewalConfigGA2(), experimental=True)
```

A chamada assina uma autoridade GA2 e inicializa S1 explicitamente dentro da mesma transação. Não deve haver autoridade L2 anterior com outra configuração, evento L1 legado pendente ou descendente L1 legado que exigiria conversão. Esses casos são rejeitados com motivo, sem migração implícita. Uma configuração já persistida não é alterada por uma segunda chamada.

As regras e assinaturas de L2, S1 e GA1 antigos permanecem disponíveis. V4, T1, J1/JR1, C3 R1-55, W1/W2/P1, E1, Vg2, v22 e R1 não foram recalibrados. VSR1 conserva suas fórmulas e passa a ler também o fenótipo compacto da ocupação GA2.

Não há migração de schema nesta entrega: GA2 utiliza descritores e registros JSON versionados existentes. Não foi implementado fluxo de ativação para campanhas reais.

## Testes, artefatos e arquivos

Foram aprovados **113 casos distintos** no escopo afetado: 25 de GA2 e 88 de L1/L2/S1/GA1. A suíte anterior passou em 496,51 s. Os novos casos foram executados em lotes focais; reexecuções, o caso S1 das 224 árvores e o teste de registro tardio repetidos não foram somados duas vezes. Não se afirma execução de todos os testes do repositório.

Os resultados finais e a verificação do banco real estão em `artifacts/vegetation-ga2/validation.json`. A suíte inclui seis categorias reais, orçamento, expiração, capacidade, persistência, visitas fragmentadas, registro tardio, S1, exceções, extinção, recolonização, corrupção, rollback, encontro, coleta, replay e undo. As duas imagens foram abertas e conferidas visualmente.

O banco real manteve 2.027.520 bytes e `LastWriteTimeUtc=2026-10-26 21:53:21`. A conferência em modo somente leitura não encontrou ativação GA2. O v22 manteve SHA-256 `a2d177f65e96ac90b572a6acc78c1513e9a01db40032257a3bbe3d58cf0acb38`.

Arquivos desta entrega:

- `vegetation/renewal_gameplay.py`: política, orçamento por tempo, scheduler, executor e ocupantes compactos.
- `vegetation/renewal.py`: dispatch explícito, perfil GA2, validação do orçamento, seleção de participantes e integração de perturbações.
- `vegetation/lifecycle.py`: leitura/hidratação de ocupantes e registro de remoções compactas, preservando o caminho anterior.
- `vegetation/sexual.py`: reutilização transacional de coortes para S1 em GA2; mesma autorização/compatibilidade.
- `vegetation/recovery_structure.py`: leitura do fenótipo compacto pela mesma medição VSR1.
- `app/tests/test_vegetation_renewal_ga2.py`: testes da política e integração.
- `scripts/validate_adventure_renewal.py`, `benchmark_adventure_renewal.py`, `report_adventure_renewal.py`: campanhas, comparações, bancos, imagens e conferência dos resultados.
- `docs/world-genesis-gameplay-policy.md` e este relatório.

Em `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_adventure_renewal
.\.venv\Scripts\python.exe -m scripts.benchmark_adventure_renewal
.\.venv\Scripts\python.exe -m scripts.report_adventure_renewal
.\.venv\Scripts\python.exe -m pytest app/tests/test_vegetation_renewal_ga2.py -q
.\.venv\Scripts\python.exe -m pytest app/tests/test_vegetation_growth_ga1.py app/tests/test_vegetation_lifecycle_l1.py app/tests/test_vegetation_renewal_l2.py app/tests/test_vegetation_stabilization_s1.py -q
```

Os scripts retomam resultados concluídos. Um novo `--out` nas ferramentas permite refazer as provas sem reutilizar JSONs. Para executar apenas GA2 na ferramenta de comparação, gere antes os controles L2 no mesmo diretório: eles fornecem as posições reais removidas. Isso é uma exigência do experimento pareado, não da ativação GA2 em um mundo novo. Benchmark e relatório usam o mesmo `--out` da validação. Todas as SQLite dessas ferramentas são experimentais isoladas; não apontam para `everreach.db`.

## Limitações e recomendação

GA2 demonstra a resposta desejada em dias/semanas: nascimentos reais, crescimento GA1 e recomposição estrutural progressiva, com extinção e consequências preservadas. Está pronta para avaliação experimental de gameplay.

A dispersão e a busca local de progenitores continuam conservadoras e limitadas aos candidatos espaciais do contrato existente. Isso pode deixar vagas duradouras mesmo havendo outras árvores mais longe; não é imposta restauração integral. Na comparação pareada de dez anos, L2 chegou a 549 vivos e GA2 a 458: GA2 entrega uma resposta inicial mais rápida, mas não garante maior contagem em todos os horizontes. As políticas diferem em quota por banco, calendário, vida do banco e sequência determinística de sucesso. Esse resultado e a estabilização em patamares incompletos permanecem documentados para avaliação de gameplay.

As amostras são cenários selecionados favoráveis, não prova de frequência de recuperação por área de todo o planeta.

As reservas e os registros de nascimento são finitos, mas o histórico persistido cresce com eventos reais. A ocupação compacta evita corpos remotos em massa; não transforma uma região de tamanho arbitrário em custo constante. Saltos longos e regiões muito perturbadas ainda exigem preparação perceptível.

Nenhuma fauna, hidrografia fantástica, microambiente ou Atlas foi adicionado. A próxima decisão pode avaliar o ritmo experimental entregue; não é necessário reabrir o clima ou uma simulação botânica para explicar os nascimentos.
