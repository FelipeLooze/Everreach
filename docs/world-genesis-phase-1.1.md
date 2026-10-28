# World Genesis 1.1 — crescimento, recuperação e reprodução L1

L1 é uma autoridade **experimental, opt-in**, sobre Vg2/R1. Implementa recuperação gradual, nascimento, crescimento e colonização com propágulos finitos. Não ativa campanhas reais e não altera o v22, C3 R1-55, W1, E1 ou os descritores Vg1/Vg2/R1.

## Auditoria e decisões

O R1 anterior tem estoques finitos, massa positiva, recibos e inventário autoritativo, mas nenhuma regeneração ativa. A fenologia dos fundadores é estática; algumas flags `colheita_preserva_individuo=false` tornam a coleta de ramos fatal. O intervalo sugerido em `future_recovery` usava o índice ecológico numérico. Esse campo histórico permanece intacto e inativo; **L1 não o usa**.

O catálogo possui 1.904 espécies `comum`, 797 `incomum` e 395 `raro`. Das raras, 166 têm classe mágica excepcional: recebem a restrição excepcional, sem autorizar ocorrência. Não existem rótulos reais `muito_raro` nesta edição. As 96 espécies extremas e os requisitos canônicos continuam sujeitos aos bloqueios anteriores.

L1 acrescenta somente metadados canônicos de raridade e ciclo de vida ao catálogo compacto. O SHA-256 do arquivo v22 continua `a2d177f65e96ac90b572a6acc78c1513e9a01db40032257a3bbe3d58cf0acb38`. IDs, partes, itens e conteúdos originais são preservados.

| Categoria L1 | Recuperação de um estoque completo, em dias ativos |
|---|---:|
| Comum | 5–7 |
| Incomum | 10–14 |
| Rara | 20–30 |
| Muito rara, caso uma fonte futura a declare | 45–60 |
| Excepcional | 90–120, além das condições canônicas obrigatórias |

O intervalo exato é um hash estável da espécie, parte e tipo. Exceções exigem configuração versionada e justificativa. Uma unidade de um estoque de vinte pode voltar antes do prazo de recuperação integral; não é necessário esperar o estoque inteiro renascer. Coletas parciais preservam o progresso fracionário já acumulado. Não há crédito bancado quando o estoque está cheio.

## Tempo biológico e disponibilidade

O relógio oficial possui ano de 360 dias. L1 integra analiticamente seus quatro períodos, incluindo a passagem dezembro/janeiro; não itera dias nem minutos. Resto inteiro por parte preserva a equivalência entre projeções fragmentadas e contínuas. O estado registra assinatura, última atualização, estágio, altura e frações de recuperação.

A adequação é calculada com E1, temperaturas sazonais C3 e presença de ET positiva em W1. Inadequação conhecida suspende a atividade; temperaturas entre 0 e 5 °C reduzem a taxa, e acima disso a referência é plena. As estações de crescimento do catálogo restringem o crescimento dos jovens. As estações de disponibilidade de cada parte restringem sua produção. Flores e frutos usam janelas simplificadas de 45 dias por período permitido, distintas da fenologia estática antiga. Horários canônicos continuam restringindo **a coleta**, sem impor que uma planta só cresça enquanto o jogador pode colhê-la.

Essas taxas são aproximações de adequação e gameplay. Não representam fotossíntese medida, chuva diária, nutrientes locais ou conservação hídrica diária. Nenhum estoque W1 congelado é debitado. A ausência de escoamento superficial não é tratada como ausência obrigatória de atividade biológica. Mudança de uma autoridade física persistida continua exigindo reconciliação explícita.

Fundadores ainda não consultados partem da mesma época de ativação L1. Materializá-los mais tarde não reinicia sua recuperação. Indivíduos R1 já persistidos são incorporados explicitamente no instante de ativação, preservando baselines, IDs, estoques coletados e mortes. Indivíduos anteriores sem R1 continuam sem migração automática.

## Mortalidade, crescimento e massa

A política `partial_tissue_l1` interpreta folhas, flores, frutos, sementes, poda de ramos, pequenas porções de casca e outros tecidos parciais como removíveis com sobrevivência. É uma interpretação explícita de gameplay, aplicada somente em L1. Não modifica a flag v22 nem o comportamento fatal antigo de R1. Retirada de raízes inteiras, arrancamento, derrubada, tecidos integrais e remoção de colônias continuam fatais. A ação `remove` não cria madeira ou produtos ausentes do catálogo.

A auditoria encontrou 2.088 partes com flag histórica explicitamente falsa: 1.723 pertencem às classes parciais reinterpretadas por L1; 365 permanecem conservadoramente fatais. A lista exata faz parte da assinatura da autoridade, sem alterar esses registros do catálogo.

Novos indivíduos passam por germinação, juventude e maturidade. Os tempos dependem do tipo, da espécie e do intervalo canônico de referência quando disponível. Árvores têm referência de 600–1.800 dias ativos, muito diferente da recuperação semanal de ramos de uma árvore adulta. A altura cresce até o porte do slot; a biomassa acompanha o quadrado da fração de porte, coerente com a aproximação R1. Jovens não disponibilizam estoques adultos. Tecidos não renováveis tornam-se disponíveis uma única vez na maturidade; sua extração permanece destrutiva.

Os tetos de partes, porção por ação, massa unitária e pools anatômicos continuam vindo de R1. L1 registra assimilação de biomassa modelada, sem declará-la uma medição de água ou nutrientes. O invariante por indivíduo é:

`massa inicial + assimilada = tecidos restantes + exportada ao inventário + descartada + dispersada`

Uma unidade produzida não pode reservar duas vezes tecido compartilhado. O inventário só recebe a massa realmente removida pelo caminho de coleta existente. Propágulos transferidos para eventos não criam itens de inventário. No nascimento, sua massa é carregada para o novo corpo; eventual excedente ao compartimento inicial fica explicitamente descartado no estado do novo indivíduo.

## Reprodução, capacidade e extinção

Cada população mantém a capacidade finita de slots de fundadores de Vg2. Uma morte libera seu slot e mantém o indivíduo original como tombstone. Não se inventa capacidade adicional. Um novo ocupante recebe ID distinto e posição determinística próxima do centro **canônico** do slot; gerações sucessivas não acumulam deslocamento.

A dispersão exige progenitor real vivo e maduro, órgão reprodutivo ou fragmento clonal permitido pela estratégia canônica, estoque positivo, estação/fase adequadas, alcance geográfico, habitat elegível e vaga sem ocupante ou reserva. Uma unidade e sua massa são debitadas imediatamente, antes de agendar o estabelecimento. O padrão é 40 m de alcance e 14 dias ativos para estabelecimento. Trata-se de dispersão abiótica simplificada, sem pressupor fauna ou converter órgãos inexistentes em sementes.

Uma morte explícita pode procurar progenitores nas comunidades físicas próximas, inclusive através de bordas de patches e faces. A busca usa endereços inversos finitos: até nove patches e nove candidatos por população compatível, sem enumerar seus milhares de indivíduos. A escolha é ordenada e independente de quais candidatos já haviam sido visitados. A visita processa o evento previamente determinado; não sorteia uma nova chance de reprodução.

Eventos persistidos reservam um único slot. Sua ordem de execução é `(due_minute, event_id)`. Chaves são idempotentes e têm escopo de campanha. Um propágulo já disperso pode sobreviver à morte posterior do progenitor. Falha de habitat ou distúrbio cancela seu estabelecimento com estado explícito; não há reembolso oculto nem repetição por visita.

A ferramenta experimental `clear_population` registra extinção local esparsa, incluindo fundadores virtuais e filas de propágulos, sem materializar toda a população. Ela não tem endpoint público. Posteriormente, uma dispersão explícita de uma população vizinha pode recolonizar uma vaga. O morto original permanece morto. Não existe ciclo planetário contínuo de reprodução: além da renovação ligada à morte, novas dispersões dependem de eventos ecológicos explícitos.

## Resultados reais — cinco seeds, raio de 63.710 km

Cada prova esgota um estoque renovável usando coletas reais, produzindo lotes positivos no inventário. Depois compara atualizações acumuladas com projeção direta em 7, 30, 90 e 365 dias. Ao final remove o indivíduo e verifica outro ano sem recuperação.

| Seed | Espécie | Categoria | Dias ativos | Teto R1 | Estoque em 7 / 30 / 90 / 365 dias |
|---:|---|---|---:|---:|---|
| 42 | EV-FL-1827 | comum, árvore | 7 | 14 | 14 / 14 / 14 / 14 |
| 42 | EV-FL-2789 | raro, líquen | 27 | 3 | 0 / 3 / 3 / 3 |
| 0 | EV-FL-1628 | comum, árvore | 5 | 30 | 30 / 30 / 30 / 30 |
| 0 | EV-FL-1996 | raro, arbusto | 27 | 17 | 4 / 17 / 17 / 17 |
| 7 | EV-FL-1580 | comum, árvore | 5 | 14 | 14 / 14 / 14 / 14 |
| 7 | EV-FL-2034 | raro, arbusto | 28 | 25 | 6 / 25 / 25 / 25 |
| 2026 | EV-FL-1840 | comum, árvore | 6 | 22 | 22 / 22 / 22 / 22 |
| 2026 | EV-FL-2041 | raro, arbusto | 25 | 12 | 3 / 12 / 12 / 12 |
| 12345 | EV-FL-1574 | comum, árvore | 7 | 15 | 15 / 15 / 15 / 15 |
| 12345 | EV-FL-0343 | raro, erva | 26 | 13 | 3 / 13 / 13 / 13 |

O líquen ilustra a granularidade de um estoque pequeno: sete dias ainda não completam uma unidade. O teste separado de estoque maior verifica produção positiva parcial antes do prazo integral. Ausência de líquen raro elegível na janela da seed 0 levou à seleção de um **arbusto raro realmente presente**, sem fabricar ocorrência.

Foram persistidos três estabelecimentos reais na seed 42:

| Caso | Origem debitada | Capacidade / vivos após estabelecimento | 7 dias | 365 dias |
|---|---:|---:|---|---|
| Erva EV-FL-2474 | 630 mg de sementes | 3.131 / 3.131 | jovem, 21 cm, sem partes maduras | adulta, 78 cm |
| Árvore EV-FL-1827 | 16.964 mg de ramo clonal | 1.037 / 1.037 | germinando, 7 cm, sem partes maduras | jovem, 326 cm |
| Recolonização externa de EV-FL-1827 | 17.193 mg de ramo clonal | 1.037 / **1** | germinando, 7 cm | jovem, 326 cm |

A árvore de referência mede 1.487 cm na maturidade e exige 1.464 dias ativos. Seu corpo novo tem aproximadamente 19 g aos sete dias e 7,14 kg após um ano; não recebe antecipadamente o corpo adulto. A população extinta fica em zero até o evento externo e passa a um indivíduo, sem restaurar os outros 1.036 fundadores.

Não foi materializada espécie excepcional. Sua ausência de evidência canônica continua sendo um bloqueio legítimo, não uma falha a contornar.

![Recuperação de estoques e crescimento de indivíduos reais](../artifacts/vegetation-life-l1-validated/recovery-and-growth.png)

Os segmentos ligam amostras, sem afirmar uma taxa diária constante entre elas. Os arquivos [recovery.json](../artifacts/vegetation-life-l1-validated/recovery.json), [births.json](../artifacts/vegetation-life-l1-validated/births.json) e os onze bancos SQLite isolados guardam IDs, baselines, recibos, eventos, estados e inventários. Há dez campanhas de recuperação e três de nascimento no banco compartilhado de provas de nascimento; nenhum banco é um save real.

## Desempenho e verificações

O benchmark usa cópia em RAM de `births.sqlite`, preservando a prova original. Foram materializados apenas dez participantes nas três campanhas de nascimento, diante de capacidades populacionais de milhares. A projeção pura de um indivíduo por 365 dias ficou em até 0,102 ms nas provas, com pico rastreado de 17.725 bytes. Na prova específica de árvore jovem, 1.000 projeções de cem anos tiveram média de 0,284 ms, pico de 15.766 bytes e 32 bytes retidos.

A sincronização persistente de um jovem por mais 365 dias levou aproximadamente 139 ms, incluindo validação física e fences SQLite. A reconstrução fria dos contratos anteriores levou 5,43 s. Esses números são medições locais com outras validações em execução, não garantias de frame time. A leitura fria dos planos anteriores e os checkpoints integrais de undo merecem acompanhamento na futura interface; não justificam um worker planetário.

Testes executados:

- World Genesis e calibração Vg2: **736 aprovados**, 1.393 s.
- R1: **25 aprovados**, 187 s, preservando comportamento antigo, massas, inventário, recibos e undo.
- Relógio, simulação temporal, equipamentos, containers, carga, reset e undo: **54 aprovados**, 45 s.
- L1: **28 aprovados**, 199 s. Cobrem catálogo completo, calendário e virada do ano, cinco seeds, recuperação gradual, congelamento, semigrupo temporal, árvore viva/morta, raízes, nascimento, crescimento, reserva finita, extinção/recolonização, opt-in, corrupção, reinício entre processos, migração aditiva, sessão desatualizada, rollback, HTTP/replay/undo e progresso parcial. Resultado registrado em `artifacts/plant-life-l1-complete-tests.log`.
- Reexecução focal de dispersão após o ajuste de seleção sazonal: `artifacts/plant-life-propagation-final.log`.
- Compilação Python dos módulos e scripts alterados.

As autoridades C3/W1 são comparadas antes/depois nos testes das cinco seeds. A migração L1 é aditiva, testada em SQLite descartável e **não aplicada a `backend/everreach.db`**. O banco real conservou tamanho de 2.027.520 bytes e `LastWriteTimeUtc=2026-10-26 21:53:21` nesta execução.

As quatro suítes acima totalizam **843 casos aprovados**, sem contar reexecuções focais. A seleção sazonal final de propágulos passou em quatro reexecuções de nascimento, colonização automática, recolonização e reinício.

## Arquivos e reprodução

Novos arquivos:

- `backend/app/game/world/genesis/vegetation/life_math.py`: perfis, política e integração sazonal inteira.
- `backend/app/game/world/genesis/vegetation/lifecycle.py`: autoridade L1, projeção, mortalidade, capacidade, dispersão e eventos.
- `backend/app/db/models/world_vegetation_lifecycle.py`: plano, população esparsa e eventos.
- `backend/alembic/versions/w31w4r5s6t7u_vegetation_life_l1.py`: migração aditiva, sem ativação.
- `backend/app/tests/test_vegetation_lifecycle_l1.py`: testes novos.
- `backend/scripts/validate_vegetation_life.py` e `benchmark_vegetation_life.py`: provas, imagens e desempenho.
- Este relatório e artefatos em `artifacts/vegetation-life-l1-validated`.

Integrações alteradas: `vegetation/catalog.py`, `vegetation/service.py`, `vegetation/resources.py`, `vegetation/actions.py`, `db/models/__init__.py` e `world/reset.py`. Todas as novas regras dependem da presença de uma autoridade L1 validada. Nenhum arquivo de dataset foi editado nesta fase.

Para reproduzir, em `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest app/tests/test_vegetation_lifecycle_l1.py -q
.\.venv\Scripts\python.exe -m scripts.validate_vegetation_life --out ../artifacts/l1-reproduction
.\.venv\Scripts\python.exe -m scripts.benchmark_vegetation_life --out ../artifacts/l1-reproduction
```

O script de provas reutiliza os mesmos preparadores de cenários reais da suíte L1; não utiliza LLM ou geografia fabricada. Um diretório novo fornece uma execução integral; resultados completos existentes podem ser retomados para gerar a figura e o resumo.

## Limites e integração futura

O caminho HTTP existente já coleta, remove, observa altura/estágio e encontra o ocupante atual de uma vaga sem expor coordenadas desconhecidas. `inspect` informa teto R1 e mortalidade L1. Não foi criada uma nova tela: frontend ainda precisa apresentar progresso, indisponibilidade sazonal, jovens e novos ocupantes. Dispersão manual e distúrbios são APIs técnicas confiáveis, sem endpoint público que aceite alegações do jogador.

Não há crescimento contínuo de todas as plantas do planeta, envelhecimento/morte natural, competição ecológica, banco global de sementes, dispersão de longa distância, expansão para espécies ausentes do baseline ou reconfiguração dinâmica de capacidade. A renovação ocupa vagas da própria espécie; a recolonização externa exige uma população compatível real. Os slots virtuais originais e seus indivíduos persistidos são a mesma população, nunca somados em duplicidade.

Fungos, algas, juncos, trepadeiras, consórcios e habitats extremos mantêm as exigências locais ainda não comprovadas nas fases anteriores. Seus perfis temporais podem existir sem autorizar ocorrência. Não foi inventado detrito, suporte, água, energia ou anomalia para desbloqueá-los. Fisionomia regional e taxas sazonais continuam aproximações das autoridades existentes.

Espécies sem órgão reprodutivo bruto calibrado também não recebem sementes fictícias. Uma estratégia declarada de reprodução não fornece sozinha a massa de um propágulo; espécies somente com folhas/casca precisam de um contrato posterior para propágulos não coletáveis. A auditoria por tipo em `profile-audit.json` separa essa limitação anatômica dos bloqueios de habitat. Espécies excepcionais não reproduzem em L1; sua autorização exigirá evidência canônica e extensão explícita do contrato.

| Tipo | Espécies no catálogo | Com rota anatômica de propágulo | Limitação principal |
|---|---:|---:|---|
| Flor | 1.113 | 851 | 262 precisam de contrato de propágulo não coletável |
| Erva | 230 | 174 | 56 sem órgão bruto calibrado; raízes integrais fatais |
| Arbusto | 305 | 295 | 10 sem órgão bruto; clonagem exige estratégia canônica |
| Árvore | 401 | 351 | 50 sem órgão bruto; maturação longa separada da poda |
| Gramínea | 275 | 275 | Produção de sementes respeita fase e estação |
| Samambaia | 119 | 119 | Esporos sujeitos à maturidade e adequação |
| Musgo | 158 | 58 | 100 sem órgão bruto calibrado |
| Líquen | 86 | 86 | Fragmentos finitos; crescimentos novos mais lentos |
| Trepadeira | 78 | 78 | Suporte físico local ainda obrigatório |
| Fungo | 140 | 140 | Nutrição/detrito local não comprovados |
| Junco | 82 | 82 | Hidrografia local necessária |
| Alga | 75 | 5 | Água/energia locais e 70 sem órgão bruto calibrado |
| Consórcio simbiótico | 34 | 34 | Componentes e micro-habitat não comprovados |

Essas 2.548 rotas anatômicas não são 2.548 autorizações ecológicas. As 548 ausências de órgão, os requisitos locais e os bloqueios excepcionais são restrições distintas e podem se sobrepor.

L1 está preparado para experimentação e integração de interface, com provas reais de recuperação, crescimento e renovação finita. A ativação em campanhas reais permanece uma decisão separada e explícita; não ocorre por atualização do código ou visita ao território.
