# World Genesis — revisão geral de game design

27 de outubro de 2026. Direção: [política AP1](world-genesis-gameplay-policy.md). Primeira alteração operacional: crescimento **GA1**, opt-in sobre L1. G1 continua sendo o nome da hidrografia local; não foi alterado.

## Conclusão da auditoria

A infraestrutura protege propriedades importantes para um RPG: lugares estáveis, recursos finitos, identidade, revisitas, inventário e consequências. O problema está em usar incompletude de um modelo físico como veto permanente à existência de conteúdo e em aplicar um relógio biológico demasiado lento ao ritmo diário da aventura.

Não é necessário refazer o planeta ou aumentar a complexidade climática. A direção passa a ser gerar possibilidades regionais canônicas, com regras de fantasia e consequências persistentes. Nesta entrega, somente o crescimento recebe nova política executável. Clima, hidrologia, E1, Vg2 e o catálogo não foram alterados. Os locais especiais descritos como propostas abaixo **ainda não foram gerados**.

## Auditoria por sistema e impacto no jogador

Prioridades: **P0** impede conteúdo ou ritmo essencial; **P1** compromete diversidade/revisita; **P2** só exige trabalho depois de um caso jogável justificar. Prioridade não significa que o item foi implementado nesta revisão.

| Sistema e código examinado | Problema e impacto no gameplay | Restrição essencial | Simplificação ou parâmetro proposto | Compatibilidade | Prioridade / situação |
|---|---|---|---|---|---|
| Geografia V4 — `formation_v4.py`, `formation_plan.py` | Escala gigantesca favorece extensões continentais homogêneas. Isso não demonstra que cada 50 km contém descobertas. A distribuição por área corrigida não é um excesso de realismo. | Continuidade esférica, seed, IDs macro e geografia estabelecida. | Manter V4; compor interesse regional em escalas de exploração sobre a geografia. Não gerar mais placas para preencher conteúdo. | Recalcular a formação mudaria o mundo; nenhuma alteração aqui. | P2; preservar. |
| Tectônica/T1 — `formation_tectonics.py`, `terrain/field.py` | Relevo contínuo melhora horizontes e navegação, mas oito bandas de ruído e uma declividade não estabelecem cânions, cavernas ou passagens reconhecíveis. Solicitar cada detalhe do relevo a cada organismo repete custo. | Altura autoritativa, emendas, contratos de terreno e modificações locais. | Reutilizar terreno e caches; futuras formações locais com geometria simples e interfaces explícitas. Não exigir erosão científica para um local fantástico. | Uma formação que modifique altura precisa ser um overlay persistente, não uma nova resposta T1 silenciosa. | P1 para locais; sem alteração T1. |
| J1/JR1 — `geology/adapter.py`, `geology/regional/field.py`, `occurrence.py`, `service.py` | Filtros conservadores de profundidade e contato e distinção entre história vulcânica e atividade atual podem impedir recursos/locais sem um próximo produtor de conteúdo. Oportunidade técnica ainda não é achado acessível. | Os 120 materiais, IDs, não duplicação de rotas, estoques e autorização excepcional/lendária. | Parâmetros regionais de acesso/exposição e formações fantásticas autorizadas. Preservar coerência de substratos sem ampliar simulação tectônica. | Novos parâmetros em nova política de ocorrência; nunca reinterpretar jazidas existentes. | P1; propostas. |
| C3 R1-55 — `climate/v3.py`, `water/config.py` | Clima de grade e continentes gigantescos não descrevem cada vale. Usar os mesmos números como veto absoluto de todo microambiente estreita a paisagem. O ledger atmosférico já se declara aproximado, não conservação planetária em litros. | Forçamento, unidades, assinaturas e C2/C3 antigos. | Manter C3 como fundo; exceções ambientais regionais canônicas, contínuas e limitadas espacialmente. Não multiplicar chuva nem impor quotas verdes. | Nenhuma recalibração C3; exceção futura deve declarar sua própria autoridade. | P1; manter clima. |
| W1/W2/P1 — `water/config.py`, `water_reconciliation/practical/allocation.py`, `hydraulics.py`, `service.py` | Quota P1 vem de uma película superficial W1 repartida até folhas de poucos metros. A passagem exige seção molhada, declive, capacidade e volume. Isso protege transferências existentes, mas é um funil inadequado para autorizar todo lago, oásis ou nascente do jogo. | Não duplicar créditos; estoques não negativos, unidades, transferências e identidades persistentes. | Separar conteúdo hídrico regional de solver: apresentação, água utilizável finita e fonte mecânica. Um novo lago canônico pode ter reserva própria explicitamente registrada; não virar um saldo W1 falso. | Nova regra deve declarar origem, estoque e adaptador de consumo; nenhuma edição de comprovantes W2/P1. | P0 para água explorável; proposta, não implementada. |
| E1 — `environment/classifier.py`, `adapter.py` | `FEATURE_GUARDS` mantém floresta nebulosa, gruta inundada, cânion etc. dependentes de evidência que nenhum gerador de conteúdo atual fornece. Requisitos numéricos estritos e `None` propagam pendências. Potencial ambiental não confirma uma paisagem com conteúdo. | Distinguir fato, potencial, desconhecido e ocorrência; snapshots e taxonomia. | Um produtor regional canônico deve estabelecer vales, nevoeiro fantástico e micro-habitats, publicando fatos locais com origem. Não mudar pontuações só para trocar cores. | Perfis locais em nova camada/política, preservando E1 como fundo e as consultas antigas. | P0; proposta. |
| Vg2 `regional_canopy_v2` — `vegetation/v2.py`, `field.py` | Coortes suaves e estratos resolvem mosaico aleatório; preservar. Porém habitat E1, chuva, P/PET, ET, substrato e limites de tipo são portas cumulativas. `_cohort` exclui categorias inteiras antes da verificação local. `extreme_json` recebe pendência incondicional na elegibilidade. | Comunidades reconhecíveis, continuidade, capacidade e indivíduos removidos. | Futuro adaptador regional de tolerância e habitats canônicos; reutilizar a interpolação de coortes e composição. Não relaxar todos os filtros globalmente nem redefinir o teto de cobertura agora. | Novos habitantes/tolerâncias exigem versão ou overlay; baselines Vg2 permanecem. | P0 para bloqueados, P1 para variedade; Vg2 preservado. |
| R1 — `vegetation/resources.py`, inventário e coleta | Massas e pools são estimativas de gameplay já existentes, não ciência medida. Recuperação por raridade, horários, fase e tecidos pode impor esperas adicionais. O principal ganho é impedir coleta infinita e duplicação, não explicar botânica. | Unidade de item, massa positiva, inventário autoritativo, parte permitida e limites compartilhados. | Rever tempos de recuperação separadamente; não manter raridade como único motivo de espera. Não ampliar contabilidade que não protege um limite mecânico. | GA1 não muda partes, massas, caps, recuperação ou itens. | P1; auditar balanceamento por uso antes de nova alteração. |
| L1 — `life_math.py`, `lifecycle.py` | Árvores recebem 600–1.800 dias ativos, frequentemente restringidos por referências v22, estação e taxa local. Maturação passa a anos de calendário. É incompatível com crescimento perceptível durante uma aventura diária. | Tempo autoritativo, determinismo, finitude, morte e IDs distintos para descendentes. | **GA1 implementada**: prazos de calendário com bônus sazonais limitado e variação individual, sem reescrever projeção ou estoques. | Novo descritor e assinatura; L1 antigo permanece exato e não aceita reconfiguração. | **P0 entregue** para maturação. |
| L2 — `renewal.py`, `renewal_batch.py` | `STEP=90 dias`, `OFFSET=30 dias`; produção ainda exige estação e atividade; estabelecimento custa 14 dias ativos. Até uma flor de maturação rápida pode esperar meses para nascer. Bancos/coortes e validação individual repetida dominam saltos longos. | Propágulos/populações finitos, pais vivos na produção, capacidade, tombstones, extinção, ausência de sorteio de visita. | Próximo ajuste pequeno: cadência em dias/semanas e orçamento por tempo, em perfil independente. Depois, coortes agregadas para indivíduos não interagidos, preservando consequências. Não dividir a produção anual por rodadas mais curtas sem recalcular quotas. | Alterar frequência muda probabilidades e IDs: precisa de nova política explícita. Esta entrega mantém L2 e só integra o relógio GA1 à detecção de adultos. | **P0 ainda pendente** para tempo até reposição e latência. |
| S1 — `vegetation/sexual.py` | Já remove a exigência indevida de fauna para rotas sexuais comuns; exigir especialista não especificado não ajudava o jogo. Par conspecífico e registro do parceiro têm função mecânica, mas não precisam evoluir para genética/polinização científica. | Exceções canônicas, parceiro distinto, bancos finitos, seed e idempotência. | Preservar S1; não adicionar NPC polinizador nem simulação genética. Avaliar agregação dos pares junto ao executor futuro, sem trocar as autorizações. | S1 independente continua ligada à assinatura L2. | P2; funcional, preservar. |
| Flora extrema v22 — `catalog.py`, `evidence_audit.py`, `field.py` | As 96 espécies existem no catálogo, mas `extreme_evidence` sempre retorna pendente e `eligibility` não tem ramo de aprovação de extremos. Apenas acrescentar dados físicos não removeria esse veto. Exigir geometria, nutrientes, luz e água completos sem produtor desses locais tornou-se bloqueio estrutural permanente. | Raridade, identidade do local, acesso e autorização de anomalia excepcional específica. | Gerar microambiente e espécies compatíveis como um pacote canônico versionado: fissura de gelo, bolsão vulcânico, cavidade fantástica etc. Energia/água podem ser regras próprias do local. Implementar consumidor dessa autorização, não apenas mais um relatório de evidências. | Não editar v22 nem fingir que uma anomalia foi autorizada. Novas fontes têm IDs e estado próprios. | **P0 de conteúdo**, proposta; nenhuma espécie extrema liberada aqui. |

## O que preservar, simplificar e parametrizar

**Essencial:** determinismo, continuidade, identidade espacial, persistência, independência da visita/LOD, recursos finitos, inventário, descobertas e consequências; ausência de level scaling. Não trocar o grafo de movimento por outro sistema. Não revelar coordenadas desconhecidas ao jogador.

**Simplificável:** detalhe do orçamento biológico interno, demonstração científica de cada formação, exigência de solver planetário para um bolsão local e materialização individual quando coortes representam o mesmo resultado mecânico. Não remover a garantia de estoque ao simplificar a explicação física.

**Parâmetros de jogo:** maturação, recuperação de partes, cadência de reprodução, custo de estabelecimento, tolerância local, frequência regional de locais especiais e dificuldade de acesso. Esses parâmetros não são percentuais obrigatórios de conteúdo global.

**Bloqueios fantásticos:** veto categórico de flora extrema, ausência de produtores de cavernas/água local, E1 aguardando confirmação que ninguém materializa. A solução é um gerador canônico pequeno com contrato consumidor; não um sistema científico adicional.

## GA1 — primeira mudança prática

`LifeConfigGA1` herda apenas o contrato de configuração L1 e acrescenta `growth_policy='adventure_calendar_ga1'`. O descritor recebe `kind='vegetation_life_l1_ga1'` e regras GA1 assinadas. A versão do motor continua L1; a política de ritmo é explícita e diferente. Nenhuma tabela ou migração nova é necessária.

| Classe de ritmo | Dias nominais configuráveis |
|---|---:|
| Flores, ervas e gramíneas | 3–7 |
| Arbustos | 7–15 |
| Árvores comuns | 15–30 |
| Árvores grandes | 30–60 |
| Árvores lentas, designadas explicitamente | 60–120 |
| Outros organismos ordinários | 7–30 |
| Excepcionais | L1 anterior até design canônico específico |

O limite de árvore grande usa a altura madura superior do catálogo, inicialmente 30 m. Sem essa informação, a espécie usa árvore comum; não se inventa uma medição. Existem 51 árvores sem intervalo de altura no catálogo compilado. `tree_pacing` permite revisão explícita por espécie, inclusive manter `legacy`. Não se rotula uma árvore como lenta por raridade, nome evocativo ou pelo intervalo botânico antigo.

Na auditoria de todas as 3.096 espécies, o preset atribui 1.571 à classe flor/erva/gramínea, 280 a arbustos, 191 a árvores comuns, 175 a árvores grandes e 713 a outros organismos. As 166 excepcionais mantêm o perfil anterior. Nenhuma espécie é selecionada automaticamente como lenta; essa classe é configurável e testada com espécie real. **Possuir perfil de crescimento não autoriza ocorrência ou reprodução.**

O relógio usa os dias reais do calendário de jogo, a partir do nascimento estabelecido. A espécie define o prazo nominal determinístico; cada ID acrescenta variação de ±5%. A taxa-base é 0,85, com bônus sazonal de até 0,20 condicionado à atividade ambiental já calculada. As taxas efetivas ficam entre 0,8075 e 1,1025. Assim, um prazo nominal de 30 dias não vira vários anos: sem override, leva no máximo aproximadamente 37,2 dias. Uma grande árvore nominal de 60 dias pode levar até aproximadamente 74,3 dias. Não há sorteio por visita.

A aceleração não é uma alegação de água ou energia adicional mensurada. É a regra de crescimento fantástico autorizada pelo design. Não credita litros em W1/W2/P1, não altera clima, não consome nem duplica um reservatório implícito. O modelo anterior já registra assimilação de tecido de forma abstrata; continuam seus caps e invariantes.

Recuperação de partes mantém a taxa/estação L1 anterior, quotas R1 e fenologia. Crescer rapidamente não significa coletar frutos em qualquer fase, ressuscitar um morto ou restaurar o teto Vg2. A área de copas continua derivada do porte atual pelo VSR1.

O executor em lotes L2 passou a usar o mesmo relógio de maturação GA1 da projeção de indivíduos. Isso evita que o indivíduo apareça adulto na consulta, mas continue sendo tratado como jovem na reprodução. O caminho L1 antigo devolve exatamente as taxas e estações anteriores.

### Ativação e compatibilidade

Em uma campanha experimental nova, após R1 e antes de L2:

```python
from app.game.world.genesis.vegetation.growth_gameplay import LifeConfigGA1
from app.game.world.genesis.vegetation.lifecycle import initialize_life

initialize_life(db, campaign_id, LifeConfigGA1(), experimental=True)
```

O código não faz essa chamada no fluxo de criação de campanhas reais. Se já existir L1 com outra configuração, a chamada é rejeitada. Não converte eventos pendentes, árvores, estoques ou assinaturas antigas. Configurações com política desconhecida falham; regras GA1 corrompidas também. O v22 continua pinado pelo mesmo SHA-256.

## Provas de crescimento — seed 42

Foram criados oito bancos descartáveis, com quatro espécies realmente estabelecidas, comparando L1 e GA1 na mesma geografia. Cada descendente nasceu de evento L2/S1 real: propágulo finito, vaga e microsítio elegível. Nenhuma muda foi fabricada para o gráfico.

Os marcos abaixo são **dias desde o nascimento real**, não desde o corte:

| Espécie real | Política | 7 dias | 15 dias | 30 dias | 60 dias | Calendário nascimento → adulto |
|---|---|---|---|---|---|---:|
| EV-FL-1139, Papoula do Lajeado Inclinado | L1 | 8 cm, jovem | 17 cm, jovem | 26 cm, adulta | 26 cm, adulta | 22,00 d |
| Mesma espécie | GA1 | 26 cm, adulta | 26 cm, adulta | 26 cm, adulta | 26 cm, adulta | **6,59 d** |
| EV-FL-2474, Tanchagem de Raiz Prateada | L1 | 20 cm, jovem | 43 cm, jovem | 78 cm, adulta | 78 cm, adulta | 26,10 d |
| Mesma espécie | GA1 | 78 cm, adulta | 78 cm, adulta | 78 cm, adulta | 78 cm, adulta | **5,77 d** |
| EV-FL-1927, Vassoura da Lua Minguante | L1 | 3 cm, germinação | 8 cm, germinação | 17 cm, jovem | 35 cm, jovem | 260,43 d |
| Mesma espécie | GA1 | 120 cm, jovem | 156 cm, adulta | 156 cm, adulta | 156 cm, adulta | **9,01 d** |
| EV-FL-1827, árvore de grande porte | L1 | 5 cm, germinação | 13 cm, germinação | 29 cm, jovem | 59 cm, jovem | 1.638,95 d |
| Mesma espécie | GA1 | 179 cm, jovem | 392 cm, jovem | 791 cm, jovem | 1.487 cm, adulta | **56,09 d** |

O valor nascimento → adulto é a inversão analítica do relógio congelado, conferida com as projeções reais. A amostra da árvore é classificada como grande pelo intervalo de altura da espécie, não pela raridade. Não representa a classe de 15–30 dias das árvores comuns.

As assinaturas GA1 são diferentes; tentativas e IDs de descendentes também podem diferir dos controles. A comparação preserva geografia e espécies, não força um ID de mundo antigo dentro da nova autoridade.

![Crescimento real L1 e GA1](../artifacts/genesis-gameplay-review/growth-comparison.png)

### Limitação que permanece: tempo até nascer e recuperação da comunidade

No experimento, o primeiro nascimento levou aproximadamente 44,79 dias para a erva, 56,69 dias para arbusto/árvore e **223,67 dias para a flor**, desde a perturbação. Esses atrasos ocorreram nos dois perfis: a cadência/estação/estabelecimento L2 não foi recalibrada. O gráfico de crescimento não esconde essa espera.

Após 700 remoções da população arbórea da seed 42, o caso GA1 tinha 340 vivos nos marcos medidos após o primeiro nascimento: apenas três novos indivíduos sobre os 337 sobreviventes. A nova geração cresce muito mais rápido, mas isso **ainda não é recuperação florestal em semanas**. A próxima intervenção de maior impacto é o perfil de reposição, não mais velocidade de maturação ou chuva.

As JSONs incluem cobertura, estratos, altura e estágios da comunidade em cada marco, mantendo mortos e tombstones. A projeção direta a partir do nascimento foi comparada com cada evolução persistida e validada contra os limites de recursos. Nenhum teste exige retorno ao teto inicial.

## Exploração de 50 km — validação orientada ao jogador

Foram regenerados **25 percursos**, cinco contextos por seed (42, 0, 7, 2026, 12345), com 21 pontos a cada 2,5 km: **525 amostras técnicas**. Centros representam contextos escolhidos, não uma amostragem planetária ponderada por área. Não inferir cobertura global a partir desses números.

As formas encontradas foram floresta densa (105 pontos), floresta aberta (73), bosque (32), arbustal (91), estepe (14) e ausência de comunidade vegetal (210). Os contextos `dry` e `cold` ficaram sem comunidade nos cinco percursos de referência. Isso é um sinal para investigar conteúdo regional e tolerâncias locais, não uma ordem para tornar todo deserto verde.

A seed 42 não trocou de fisionomia ou estrutura acima dos limiares em nenhum de seus cinco percursos de 50 km. Em outras seeds houve até duas trocas de fisionomia por percurso. Coerência regional está presente; surpresa e densidade de descobertas **não estão demonstradas**. Um corredor homogêneo pode ser uma floresta reconhecível, mas não constitui sozinho 50 km de aventura interessante.

Foram encontradas populações com quatro espécies raras do catálogo: EV-FL-1136, EV-FL-1507, EV-FL-1519 e EV-FL-1606. Isso confirma a possibilidade procedural nesses pontos, não uma descoberta de personagem, acessibilidade ou distribuição de recompensas já integrada.

Todos os pontos foram consultados em ordem inversa e devolveram amostras idênticas. Não há exportação para mapa público nem alteração do conhecimento do personagem.

![Percursos por estrutura visual](../artifacts/genesis-gameplay-review/exploration-50km.png)

| Pergunta de experiência | Resposta verificável nesta revisão |
|---|---|
| Explorar 50 km oferece lugares interessantes? | **Ainda não comprovado.** Há identidade de paisagem; a contagem de locais canônicos/recompensas não foi implementada. Os percursos mostram trechos muito homogêneos. |
| Uma floresta é variada e parece viva? | Vg2 tem comunidades e estratos reconhecíveis; GA1 permite crescimento perceptível. Sem renderização/integração de locais, não se declara aprovação visual final. |
| Existem rios, lagos e especiais recompensadores? | Há infraestrutura e provas hídricas; ela não equivale a distribuição de corpos hídricos visitáveis. Não foram criados novos rios/lagos nesta revisão. |
| Uma planta rara pode existir de verdade? | Sim, quatro IDs raros em populações reais dos percursos; não se afirma descoberta pelo jogador. As 96 extremas continuam bloqueadas. |
| O crescimento aparece em dias/semanas? | **Sim, após nascimento**, nos quatro casos GA1. A espera para nascer continua sendo um problema separado. |
| Uma floresta destruída recupera em tempo razoável? | **Ainda não.** Poucos novos indivíduos no intervalo; é preciso ajustar reposição L2, preservando finitude e extinção. |
| A revisita preserva consequências? | Sim nos contratos/testes afetados e nas amostras em ordem inversa; GA1 não apaga mortos nem troca baseline. |
| A geração é rápida para jogar? | Amostragem vegetal é barata nestes percursos; reconciliação ecológica longa continua inadequada para bloquear exploração. Não confundir os dois custos. |

## Desempenho e limites de simplicidade

As 525 amostras de Vg2 consumiram aproximadamente **4,49 s** somadas, e as revisitas inversas com cache aproximadamente **0,037 s**. São medições técnicas de amostragem, com preparação dos contextos registrada separadamente em cada seed; não incluem materialização completa, rede ou renderização.

O caso de referência anterior de vinte anos levou **38,97 s** no executor otimizado contra 103,68 s no original. É um resultado da entrega 1.1.2, não um novo benchmark GA1. Não há alegação de que GA1 resolveu a latência de décadas. A maturação acelerada pode criar mais produtores cedo; portanto, o perfil de reprodução seguinte deve medir seu custo real antes de ativação.

GA1 reaproveita a integral sazonal analítica e sua inversão; não faz ticks diários. Congela quatro taxas por indivíduo e só adiciona trabalho constante na vinculação do perfil. Continua o limite real do L2: eventos individuais de estabelecimento, geração/validação de microsítios, serialização e atualizações de ocupação. A otimização 1.1.2 de coortes e cache de E1 deve ser preservada, mas não precisa impor eternamente os mesmos detalhes internos a uma política futura.

**Próximo desenho de desempenho:** coortes de jovens não interagidos, com contagem, nascimento, espécie, estágios e ocupação determinística; materialização de identidade individual ao interagir, com registros de exceção para mortos/coletados. Antes de implementar, definir quais posições/IDs já expostos precisam continuar exatos e como dividir coortes sem duplicação. Isso é uma proposta limitada para substituir custo relevante, não um novo simulador ecológico.

## Ordem recomendada de pequenas entregas

1. **GA1, entregue:** maturação em dias de calendário e provas persistidas de 7/15/30/60 dias. Manter experimental.
2. **Reposição perceptível:** novo perfil sobre L2/S1 com tentativas em dias/semanas, orçamentos por tempo e estabelecimento configurável. Testar primeiro surgimento de jovens, cobertura, extinção, ações, visitas fragmentadas e custo. Não multiplicar quotas anuais involuntariamente nem restaurar todos os indivíduos.
3. **Um local hídrico canônico utilizável:** validar primeiro lago/oásis com identidade, dimensões, água cenográfica separada de estoque mecânico, origem explícita e retirada finita; integrar ao consumo sem falsificar W1/P1. Não exigir simulação de bacia inteira para um protótipo de local.
4. **Um microambiente fantástico e suas espécies:** escolher poucos contratos v22, gerar local + autorização + consumidor e provar ocorrência persistente. Não liberar todas as 96 espécies nem anomalias excepcionais sem autorização exata.
5. **Paisagem regional e custo de revisita:** tolerâncias locais em camada versionada, preservando coortes Vg2; agregar jovens não interagidos se os benchmarks confirmarem benefício. Avaliar corredores e locais, não só cores ou médias físicas.

Não iniciar fauna ou Atlas dentro desses ajustes. Essas são tarefas pequenas ordenadas por impacto, não uma autorização para reescrever World Genesis nem novos números de fase impostos ao projeto.

## Arquivos e reprodução

Alterados nesta revisão:

- `README.md`: referência à direção AP1.
- `vegetation/growth_gameplay.py`: configuração, validação, classes e regras GA1.
- `vegetation/life_math.py`: acesso ao relógio de crescimento e instante de maturidade com fallback L1 exato.
- `vegetation/lifecycle.py`: dispatch de configuração, descritor assinado e projeção do relógio GA1; recuperação de partes anterior preservada.
- `vegetation/renewal_batch.py`: verificação de adulto usa o mesmo relógio da projeção.
- `app/tests/test_vegetation_growth_ga1.py`: contratos, espécies reais, persistência, ordem/tempo, invariantes, rollback, replay e undo.
- `scripts/review_genesis_gameplay.py`: provas reais comparativas e imagens de crescimento, somente bancos descartáveis.
- `scripts/audit_genesis_exploration.py`: percursos técnicos nas cinco seeds e revisita inversa.
- Este relatório e `world-genesis-gameplay-policy.md`.

Artefatos reproduzíveis em `artifacts/genesis-gameplay-review/`: JSON/SQLite por espécie/política, `species-pacing.json`, `catalog-pacing-audit.json`, `exploration-50km.json` e duas imagens técnicas. O histórico experimental de prototipagem não autoriza ativação em campanhas.

Em `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.review_genesis_gameplay --seeds 42
.\.venv\Scripts\python.exe -m scripts.audit_genesis_exploration
.\.venv\Scripts\python.exe -m pytest app/tests/test_vegetation_growth_ga1.py app/tests/test_vegetation_lifecycle_l1.py app/tests/test_vegetation_renewal_l2.py app/tests/test_vegetation_stabilization_s1.py -q
```

O script de crescimento retoma JSONs já concluídas. Para uma execução nova, fornecer `--out` com um diretório novo. As SQLite são campanhas experimentais isoladas. Nenhum comando acima migra o banco de jogo.

## Validação final

Foram aprovados **88 casos distintos**: 14 de GA1 e 74 de L1/L2/S1. A execução conjunta aprovou 86 casos em 504,76 s; dois casos adicionais de GA1 (HTTP/replay/undo e rejeição de atribuição inválida) passaram separadamente em 19,82 s. Reexecuções de protótipos não entram nessa soma. A cobertura inclui determinismo, projeção fragmentada, reinício/sessões independentes, persistência de nascimentos reais, invariantes de massa e capacidade, visitas, corrupção, recusa de migração implícita, rollback, coleta, replay e undo.

Resultados consolidados em `artifacts/genesis-gameplay-review/validation.json` e logs de regressão em `artifacts/genesis-gameplay-*.log`. Não se afirma execução de todos os testes do repositório. As duas imagens foram abertas e conferidas visualmente.

O banco real `backend/everreach.db` preservou 2.027.520 bytes e `LastWriteTimeUtc=2026-10-26 21:53:21`; a conferência final abriu o banco apenas em modo de leitura e verificou ausência de ativação GA1. O catálogo v22 manteve SHA-256 `a2d177f65e96ac90b572a6acc78c1513e9a01db40032257a3bbe3d58cf0acb38`.

A direção mudou: possibilidades fantásticas passam a ser conteúdo gerável por regras explícitas; realismo deixa de ser justificativa suficiente para veto. A primeira recalibração de maturação está operacional. A recuperação populacional rápida e a distribuição de locais especiais continuam como lacunas concretas, sem confundi-las com problemas climáticos ou declarar entregas inexistentes.
