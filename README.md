# Everreach — RPG Solo de Mundo Vivo

Everreach é um RPG solo web de fantasia medieval ambientado em um mundo vivo e persistente.

Pessoas do nosso mundo começaram misteriosamente a ser transportadas para Everreach,
um mundo real habitado por povos, culturas e sociedades próprias. Ninguém sabe por que
as chegadas começaram, o que as causa ou se existe uma maneira de voltar.

Os transportados possuem acesso a uma misteriosa Interface, mas Everreach não é um jogo.
O mundo existe independentemente dela e continua mudando mesmo sem a presença do protagonista.

O backend é a autoridade sobre o estado e as regras do mundo. O modelo local via Ollama
interpreta intenções e escreve a narração, mas não altera o banco nem decide resultados
mecânicos.

## Estrutura

```text
backend/
  alembic/            migrations do banco
  app/ai/             contexto, intenção, narrador e cliente Ollama
  app/api/            rotas, dependências e serialização HTTP
  app/db/             engine SQLAlchemy e entidades persistidas
  app/game/           regras e serviços de domínio
  app/simulation/     simulação simples do mundo
  app/tests/          testes unitários, integração e arquitetura

frontend/
  src/api/            cliente HTTP tipado
  src/features/       painéis e tela principal
  src/hooks/          carregamento do estado
  src/stores/         sessão local com Zustand
  src/types/          contratos TypeScript da API
```

## Pré-requisitos

- Python 3.11 ou mais recente.
- Node.js 20.19 ou mais recente e npm.
- Ollama é opcional. Sem ele, o jogo usa respostas mecânicas ou introduções de reserva e informa `narrator_unavailable: true`.

## Backend local

No PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

No Linux/macOS, use `source .venv/bin/activate` e `cp .env.example .env` nos passos equivalentes.

A API fica em `http://localhost:8000`, a documentação interativa em `http://localhost:8000/docs` e a verificação de saúde em `GET /api/health`.

Testes e validação de migration:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
```

## Ollama

Com o Ollama instalado:

```powershell
ollama pull hermes3:8b-llama3.1-q4_K_M
ollama serve
```

As opções `OLLAMA_BASE_URL`, `OLLAMA_MODEL` e `OLLAMA_TIMEOUT_SECONDS` ficam em `backend/.env`. Toda comunicação HTTP com Ollama está isolada em `app/ai/llm_service.py`.

O narrador recebe separadamente o contexto atual, até seis mensagens recentes, a entrada
exata do jogador e os fatos mecânicos já resolvidos. Ele continua a cena em tempo real e
não possui acesso ao banco. Para inspecionar System Prompt, contexto, histórico, entrada e
resposta bruta durante o desenvolvimento, use `LOG_LEVEL=DEBUG` no `.env`; esses dados não
são exibidos na interface do jogo.

### Cânone e conhecimento

- `Region`, `Location`, `LocationFeature` e `LocationConnection` são a fonte estruturada
  para região, tipo oficial, características perceptíveis e rotas.
- `KnowledgeFact` registra a verdade complementar e seu `subject`; `KnowledgeKnower`
  registra quem conhece o fato, a fonte, a certeza (`RUMOR`, `BELIEVED` ou `CONFIRMED`) e
  quando ele foi descoberto.
- O Context Builder consulta somente a localização atual, presenças visíveis, interlocutor
  ativo e conhecimentos explicitamente ligados ao NPC e ao personagem. Fatos do assunto
  atual têm prioridade; fatos remotos só entram quando possuem termos relevantes para a
  pergunta. Cada conhecedor envia no máximo seis fatos por interação.
- Descoberta global de uma localização não concede automaticamente sua rota ao personagem.
  Uma conexão só aparece em seu contexto quando existe conhecimento explícito daquela conexão.
- O banco impede chaves canônicas duplicadas dentro da campanha e vínculos duplicados entre
  fato e conhecedor. Índices cobrem as consultas de assunto, conhecedor e conexão de origem.
- A entrada do jogador passa por uma verificação contra o cânone. Uma suposição na fala não
  cria estradas, prédios, geografia, história ou religião.
- A saída narrativa é auditada e pode ser revisada pelo modelo. Se persistirem violações
  detectáveis, uma resposta neutra de desconhecimento impede que o texto estabeleça cânone.
  O texto dessa auditoria é tratado como conteúdo não confiável e nunca como autorização
  para o modelo confirmar a suposição.

Teste manual dos cinco diálogos de cânone com o Ollama configurado:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\manual_canon_dialogue.py
```

Teste manual da continuidade narrativa por três turnos, passando pelo Intent Parser,
Game Engine, Event Log, memória, relacionamento, Context Builder e Narrator reais:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\manual_narrative_continuity.py
```

### Eventos, memórias e relações

- Todo `WorldEvent` possui importância de 1 a 5. Eventos importantes criam memórias
  determinísticas e rastreáveis ao evento de origem; não há sumarização inventada pelo LLM.
- Memórias pertencem separadamente a `PLAYER`, `NPC`, `SIMULATED_PLAYER` ou `WORLD`, possuem
  assunto estruturado e nunca são tratadas automaticamente como verdade canônica.
- Conversas registram a entrada exata e a resposta validada para jogador e NPC. O Context
  Builder recupera no máximo quatro lembranças relevantes por entidade.
- Relações entre personagem e NPC persistem familiaridade, confiança e afinidade. Toda
  alteração gera `RELATIONSHIP_CHANGED` no Event Log.
- Conhecimento só é propagado por uma chamada explícita do domínio. A fonte precisa conhecer
  o fato; fonte e certeza são preservadas, e texto livre do Narrator nunca ensina fatos.
- O Diário retorna somente eventos e memórias do personagem selecionado, evitando vazamento
  de acontecimentos ou lembranças privadas de outras entidades.

### World Tick e simulação em camadas

- O avanço do relógio executa, em ordem determinística, chegadas, jogadores simulados, NPCs,
  desenvolvimentos persistentes e circulação social de conhecimento.
- Entidades na localização de um protagonista ativo usam simulação `DETAILED`. NPCs distantes
  já conhecidos usam `RELEVANT`; NPCs distantes desconhecidos usam atualização agregada
  `ABSTRACT` por função, diretamente no banco.
- Pessoas transportadas com identidade persistente são no mínimo `RELEVANT`. Pessoas ainda
  não encontradas permanecem em `SimulatedPlayerPopulation`, sem criar uma linha por pessoa.
- Jogadores simulados detalhados têm oportunidades horárias; os relevantes distantes usam
  uma oportunidade agregada a cada seis horas. Conclusão de viagem e expiração de atividades
  continuam verificadas em todo avanço de tempo.
- A circulação social considera apenas participantes detalhados ou relevantes e seleciona um
  par sem construir a combinação quadrática de todos os pares possíveis.

### Pessoas transportadas simuladas

- Pessoas materializadas possuem identidade, XP, Level, tolerância a risco, objetivo, skills,
  mastery, localização, atividade, rotina, relações, memórias e conhecimento próprios.
- Tolerância `CAUTIOUS`, `BALANCED` ou `BOLD` limita quais rotas perigosas cada pessoa aceita.
- Treino concede XP e mastery de forma autoritativa. Objetivos de treino, exploração, busca por
  perigo e coleta de conhecimento podem terminar e são substituídos por um novo objetivo coerente.
- Relações entre pessoas transportadas persistem familiaridade, confiança e afinidade. Contato
  social e compartilhamento de fatos podem ocorrer sem participação do protagonista.
- Grupos temporários possuem líder, membros, objetivo e localização. Seus membros podem viajar
  juntos, entrar, sair e dissolver o grupo; guildas continuam reservadas para a Fase 13.
- Morte exige uma causa mecânica explícita, é permanente, encerra atividades e participação em
  grupos, cria um fato canônico e concede conhecimento e memória às testemunhas locais.

## Frontend local

Em outro terminal:

```powershell
cd frontend
npm install
npm run dev
```

O frontend fica em `http://localhost:5173` e encaminha `/api` para o backend em `http://localhost:8000`.

Para validar o build de produção:

```powershell
npm test
npm run build
```

## Fluxo atual

1. A tela inicial lista campanhas persistidas e permite continuar ou excluir um save.
2. Para uma nova jornada, o usuário cria a campanha e um personagem Level 0, ainda sem região ou localização.
3. Mapa e missões permanecem vazios.
4. Ao clicar em **Iniciar mundo**, o backend cria a região inicial, posiciona o personagem em Cardal, inicia a primeira missão e pede ao narrador uma introdução.
5. A introdução é salva no Event Log e reaparece após atualizar a página.
6. No começo, somente Cardal aparece no mapa. Os demais locais permanecem `UNKNOWN`.

## Endpoints

| Método | Caminho | Função |
|---|---|---|
| GET | `/api/health` | Saúde da API |
| GET | `/api/campaigns` | Listar campanhas persistidas e seus personagens |
| POST | `/api/campaigns` | Criar campanha |
| GET | `/api/campaigns/{campaign_id}` | Ler campanha |
| DELETE | `/api/campaigns/{campaign_id}` | Apagar a campanha atual e seus dados |
| POST | `/api/campaigns/{campaign_id}/characters` | Criar personagem Level 0 |
| POST | `/api/campaigns/{campaign_id}/start?character_id=...` | Iniciar mundo e obter introdução |
| GET | `/api/campaigns/{campaign_id}/state?character_id=...` | Obter GameState |
| POST | `/api/campaigns/{campaign_id}/actions?character_id=...` | Resolver ação textual ou uso explícito e idempotente de técnica |
| GET | `/api/campaigns/{campaign_id}/character?character_id=...` | Ficha do personagem |
| GET | `/api/campaigns/{campaign_id}/character/progression?character_id=...` | Contexto de progressão visível no System |
| GET | `/api/campaigns/{campaign_id}/inventory?character_id=...` | Inventário |
| GET | `/api/campaigns/{campaign_id}/quests?character_id=...` | Missões |
| GET | `/api/campaigns/{campaign_id}/map?character_id=...` | Mapa conhecido pelo personagem |
| GET | `/api/campaigns/{campaign_id}/journal?character_id=...` | Eventos e memórias do personagem |
| GET | `/api/campaigns/{campaign_id}/story?character_id=...` | Histórico narrativo do personagem |

## Funcionalidades do MVP

- Campanha, personagem Level 0 e início explícito do mundo.
- Listagem, continuação e exclusão de campanhas persistidas na tela inicial.
- Uma região inicial com locais conectados, habitantes nativos e outras pessoas transportadas.
- Mapa limitado ao conhecimento atual do jogador.
- Missão inicial e conclusão simples de objetivo por conversa.
- Ações de movimento, conversa, descanso, espera, exame, checagem simples de perícia e uso
  explícito de técnicas conhecidas. O cliente envia `technique_id` e uma `action_key`; texto livre
  isolado nunca comprova capacidade ou integração mecânica.
- Relógio persistido e avanço do mundo conforme ações.
- World Tick com simulação detalhada, relevante e abstrata.
- Event Log estruturado e introdução narrativa persistida.
- Última troca restaurada após atualizar a página e painel com o log narrativo completo.
- Painel de configurações com saída para o menu inicial sem apagar a campanha. A exclusão
  permanente continua disponível somente na lista de campanhas do menu inicial.
- Atributos, perícias, técnicas e inventário extensíveis.
- Morte permanente no domínio.
- Separação entre fatos do mundo e quem conhece esses fatos.
- Fallback quando o Ollama está indisponível.

## Estado do roadmap

- **Fase 1 — Fundação: COMPLETE.** Backend, frontend, SQLite, migrations, Ollama via
  `LLMService`, campanhas retomáveis, personagem, GameState, tempo, mundo inicial,
  Narrator e Event Log estão integrados e possuem cobertura automatizada de backend e frontend.
- **Fase 2 — Narrativa correta: COMPLETE.** O Narrator responde em tempo real com a entrada
  exata do jogador e uma janela de seis mensagens recentes. O interlocutor ativo é derivado
  do Event Log estruturado, sobrevive a falas subsequentes que omitem o nome do NPC e é
  encerrado por mudança de cena. O prompt e as validações protegem a agência do protagonista,
  exigem diálogo direto com travessão e limitam respostas a no máximo três parágrafos.
- **Fase 3 — Cânone e Context Builder: COMPLETE.** Estado, localização, características
  visíveis, geografia conhecida, NPC ativo e conhecimentos de jogador/NPC permanecem
  separados e são selecionados por relevância. O contexto é limitado e não carrega o banco
  inteiro. Suposições do jogador não autorizam fatos, prosa do Narrator não modifica o cânone,
  e respostas persistentes não sustentadas são revisadas ou substituídas por fallback seguro.
- **Fase 4 — Eventos e Memória: COMPLETE.** Eventos têm importância, memórias possuem dono,
  assunto e evento de origem, NPCs recordam conversas relevantes, relações são persistidas e
  eventadas, e fatos podem ser propagados explicitamente com isolamento e proveniência. A
  recuperação é estruturada e lexical; RAG e embeddings continuam corretamente adiados.
- **Fase 5 — Exploração e Viagem: COMPLETE.** Descoberta e mapa são individuais por personagem;
  conexões conhecidas possuem distância, perigo e modificador de terreno. Viagem consome tempo
  e stamina, respeita ritmo, pode produzir incidentes e registra descoberta e visita no Event Log.
- **Fase 6 — World Tick: COMPLETE.** Tempo, chegadas, atividades, rotinas, desenvolvimentos e
  conhecimento avançam por cadências explícitas. O escopo compartilhado separa simulação
  `DETAILED`, `RELEVANT` e `ABSTRACT`, usando populações agregadas e atualizações em lote para
  evitar materializar ou carregar todo o mundo em cada ação.
- **Fase 7 — Outros Jogadores: COMPLETE.** Identidade, população abstrata, chegadas, objetivos,
  tolerância a risco, treino e progressão, exploração, viagem, rotinas, relações entre pessoas,
  grupos temporários, morte permanente e informação compartilhada estão integrados ao World Tick
  e cobertos por testes de múltiplos dias.
- **Fase 8 — Progressão: COMPLETE (8A–8J).** XP de personagem é autoritativo,
  permanece fracionário e usa a curva `round(25 * (level + 1) ** 1.7)`, sem limite arbitrário.
  Somente experiências significativas, categorizadas pelo backend e identificadas de forma
  idempotente, podem concedê-lo; skill checks rotineiros não dão XP automaticamente. Profissões
  possuem catálogo extensível, XP/Level independentes e criação preguiçosa no primeiro ganho de
  pelo menos 0,1 XP. Cada transportado pode ter no máximo uma afinidade profissional coerente
  com sua experiência na Terra, concedendo somente +10% de Profession XP na profissão associada.
  Coleta, trabalho, crafting e prática possuem fontes mecânicas separadas, com resultados parciais,
  relevância por complexidade e diminishing returns por repetição. Classes são opcionais,
  não dependem de Level e possuem ofertas pendentes, disponíveis e adiadas, com apenas uma classe
  ativa por personagem. O catálogo possui 129 domínios; evidências, sinergias, maturidade e
  diminishing returns são persistidos sem exposição ao jogador ou à LLM. O backend detecta
  caminhos maduros simples e integrados por meio de um resolvedor mecânico determinístico. Ele
  audita profundidade, consistência, diversidade e evidência explícita de integração, pontua e
  ordena candidatos, limita cada identidade a quatro domínios conectados e mantém os motivos de
  rejeição internos. Somente após essa decisão o gerador envia à LLM os domínios e sinergias
  factuais, valida estritamente a identidade semântica proposta e persiste ofertas como `PENDING`.
  Técnicas possuem associações de domínio autoritativas e ocultas: quando o jogador seleciona uma
  técnica realmente conhecida e o uso mecânico tem sucesso, a ponte registra evidência dos
  domínios e de suas integrações. Falhas, técnicas não aprendidas, texto livre e retries não geram
  evidência indevida.
  A proposta não pode criar poderes ou alterar mecânicas, chamadas repetidas são idempotentes e a
  oferta somente fica visível quando um sistema autoritativo confirma um momento seguro. Força,
  Agilidade, Vitalidade, Inteligência, Sabedoria e Resistência possuem chaves mecânicas estáveis,
  valores independentes de Level, profissão e classe, além de desenvolvimento autoritativo oculto
  com diminishing returns. Checagens podem selecionar explicitamente um atributo relevante com
  influência moderada. Sorte é um atributo adicional exclusivo do protagonista, não existe nos
  transportados simulados, não substitui competência e permanece reservado ao futuro sistema de
  loot, sem efeito atual em checagens ou probabilidades gerais. HP, Mana e Stamina possuem desenvolvimento independente e
  protegido contra farming: Vitalidade relaciona-se diretamente ao HP, Resistência à Stamina e Mana
  exige desenvolvimento mágico real, sem bônus automático de Inteligência ou Character Level.
  Fórmulas definitivas de combate permanecem corretamente adiadas à Fase 9. Resultados mecânicos
  estruturados atravessam uma única ponte idempotente de progressão, que distribui recompensas aos
  serviços autoritativos e avalia classes sem permitir escrita narrativa. O contexto público do
  System mostra XP arredondado, profissões existentes, classes visíveis, atributos e recursos, sem
  domain evidence, requisitos internos, afinidades privadas ou progresso fracionário oculto.
- **Fase 9 — Combate: COMPLETE (9A–9L concluídas).** Encontros possuem fronteira persistente,
  campanha e localização concretas, estado ativo ou terminal, minuto de início/fim e participantes
  polimórficos validados (`CHARACTER`, `NPC` e `SIMULATED_PLAYER`). Cada participante pertence a
  um lado, possui faixa de distância e percepção inicial, precisa estar vivo e presente e não pode
  ocupar dois confrontos ativos. Entrada, saída, reentrada e encerramento são autoritativos,
  idempotentes e registrados no Event Log. A iniciativa usa Agilidade do personagem e penalidades
  de percepção, possui desempate determinístico e é persistida junto da ordem. Rodadas e turnos
  têm histórico próprio, turno atual recuperável, conclusão idempotente e tratamento seguro de
  entrada, saída e encerramento. Ataques corpo a corpo e à distância são resolvidos apenas pelo
  backend no turno correto, com validação de lado e alcance, Força ou Agilidade, defesa derivada,
  extremos naturais e reenvio idempotente. Cada resultado é persistido e registrado no Event Log.
  A 9C determina acerto ou erro. A 9D aplica dano idempotente (`1d6 + atributo`, ou `2d6`
  no crítico), mantém HP persistente para personagens, NPCs e pessoas transportadas simuladas e
  registra os valores anterior e posterior. HP zero remove o participante e encerra o encontro
  quando resta apenas um lado; a resolução entre incapacitação e morte é concluída pela 9L. A 9E adiciona Mana e Stamina persistentes aos
  demais atores e cobra Stamina antes de ataques básicos: 2 no corpo a corpo e 1 à distância.
  Ações sem recurso são recusadas antes do dado e custos ficam registrados com snapshots, sem
  cobrança duplicada em retries. A 9F mantém condições temporárias por turnos do afetado:
  `STUNNED` pula o turno, `WEAKENED` reduz ataque em 2 e `EXPOSED` reduz defesa em 2. Aplicação,
  ativação, expiração e remoção são persistentes, idempotentes e registradas, inclusive em saída ou
  encerramento do encontro. A 9G permite anexar a uma técnica descoberta um perfil mecânico
  imutável com alcance, atributo de ataque e dano, custo de Mana/Stamina, dados de dano e condição.
  Apenas personagens que conhecem a técnica podem usá-la; custo, rolagem, dano, condição e turno
  passam pelos mesmos resolvedores idempotentes. O resultado também gera evidência real de domínio
  e sinergia para a progressão de classes. A 9H introduz ações táticas autoritativas que também
  consomem exatamente um turno: defender, esquivar, aproximar, recuar, desengajar e fugir.
  Defender e esquivar concedem +2 de defesa até o fim do próximo turno do usuário, sem acumular;
  deslocamentos alteram uma faixa de distância por ação; e fugir usa `d20 + Agilidade` contra
  dificuldade 12, encerrando o encontro como fuga do protagonista ou vitória quando o último
  inimigo abandona o combate. Todas cobram Stamina, persistem custos, alcance e rolagens e são
  idempotentes. A 9I centraliza o descanso em um resolvedor autoritativo: um descanso curto leva
  60 minutos e recupera 25% do HP máximo, 25% da Mana máxima e 50% da Stamina máxima, sempre
  limitado pelos máximos atuais. A recuperação é proibida durante combate ou após a morte, mantém
  snapshots persistentes, registra o resultado no Event Log e não recupera recursos nem avança o
  relógio novamente em retries da mesma ação. A 9J resolve turnos de NPCs e pessoas transportadas
  sem consultar a LLM. O backend seleciona primeiro o oponente alcançável mais próximo e, em caso
  de empate, o mais ferido; então escolhe ataque, aproximação, defesa, fuga ou espera conforme HP,
  Stamina e distância. Ataques à distância só são escolhidos quando função ou habilidade persistida
  comprova essa capacidade; caso contrário, o ator se aproxima. A tolerância a risco é efetiva:
  `CAUTIOUS`, `BALANCED` e `BOLD` começam a
  tentar fugir respectivamente com 50%, 30% e 15% de HP. Cada decisão e seu motivo ficam ligados
  ao turno e à ação resolvida, com snapshots de risco e recursos, Event Log e retry idempotente.
  Um orquestrador resolve turnos autônomos consecutivos e para antes do turno do protagonista.
  O Narrator continua sem qualquer autoridade sobre escolhas ou resultados mecânicos. A 9K
  acrescenta dano `PHYSICAL`, `FIRE`, `COLD`, `LIGHTNING`, `POISON` e `ARCANE`. Ataques básicos
  causam dano físico e técnicas mantêm um tipo autoritativo em seu perfil imutável. Armadura reduz
  somente dano físico; resistências reduzem apenas o tipo correspondente; e mitigação total pode
  produzir dano zero. Personagens recebem proteção de itens realmente equipados, com um item
  mecânico por slot, enquanto NPCs e transportados podem possuir defesas intrínsecas persistentes.
  Dano bruto, armadura, resistência e dano final ficam registrados separadamente e preservam a
  idempotência do ataque. A 9L transforma dano comum que reduz HP a zero em estado crítico
  persistente para personagens, NPCs e pessoas transportadas. Testes `d20 + Vitalidade` contra 10
  acumulam três sucessos para estabilizar ou três falhas para morte permanente; 20 natural
  estabiliza imediatamente e 1 natural conta duas falhas. A recuperação estabilizada restaura no
  mínimo 1 HP sem reinserir o ator no combate encerrado. Cada teste e transição é idempotente e
  registrada no Event Log. Apenas dano devastador — dano final igual ou superior ao HP restante
  somado ao HP máximo — causa morte imediata, preservando a regra de uma única vida.
- **Fase 10 — Inventário e Equipamento: IN PROGRESS (10A–10D concluídas).** `ItemDefinition`
  representa o conceito canônico compartilhado de um item e `ItemInstance` representa um objeto
  físico único ou uma pilha intercambiável. Definições possuem chave mecânica estável, categoria
  validada e modo `STACKABLE` ou `UNIQUE`; instâncias únicas sempre possuem quantidade 1, enquanto
  pilhas aceitam quantidade positiva. A migration preserva o catálogo e os perfis defensivos da
  Fase 9, reconhecendo itens com perfil de combate como únicos. O campo livre legado `stats_json`
  não concede autoridade mecânica e não foi expandido. Cada instância agora pertence a uma
  campanha e possui localização física independente de sua propriedade social: pode estar sem
  posição, carregada/equipada por personagem, com NPC ou no chão de uma localização. Mudanças de
  localização e propriedade são validadas contra entidades reais, não atravessam campanhas, são
  idempotentes e geram eventos estruturados. O inventário legado foi migrado para instâncias e
  removido como segunda fonte de verdade; API e proteção de combate consomem a nova localização.
  A morte do portador não apaga nem desloca itens. Na 10C, cada definição recebe peso base
  não negativo e pilhas multiplicam esse valor pela quantidade. A carga contabiliza apenas itens
  fisicamente carregados ou equipados; propriedade social e objetos no chão não pesam sobre o
  personagem. A capacidade padrão é `Força × 2,5`, com limites configuráveis e testados em 50%,
  75% e 100% para `NORMAL`, `LIGHTLY_ENCUMBERED`, `HEAVILY_ENCUMBERED` e `OVERLOADED`.
  Sobrecarga aumenta progressivamente os custos de Stamina de viagem e ações táticas e penaliza
  testes de Agilidade, sem apagar itens, impedir sua posse ou criar um limite binário de inventário.
  A API e o painel exibem peso por entrada, peso total, capacidade e estado de carga.
  A 10D persiste a posição física de cada instância equipada e separa esse estado do perfil
  canônico que define posições permitidas. Os slots são conceitos corporais úteis — cabeça,
  torso, pernas, pés, mãos, mão principal, mão secundária, duas mãos, costas e cintura — sem uma
  grade extensa de MMORPG. Regras por categoria impedem configurações incoerentes; `BOTH_HANDS`
  reserva as duas mãos. Acessibilidade distingue uso imediato, acesso rápido, item vestido e item
  guardado, sem antecipar fórmulas de tempo de combate. Equipar, reposicionar e desequipar passam
  por serviço autoritativo, validam conflitos, são idempotentes e geram eventos. A estrutura da
  9K foi migrada de `BODY` para `TORSO`, e o combate agora consome o mesmo estado físico da 10D.
  API e painel expõem instância, posição, acessibilidade e posições permitidas. Operações por
  intenção continuam reservadas para a 10L.
  Recipientes permanecem bloqueados até a 10K, quando ciclos poderão ser impedidos corretamente.
  Armas, armaduras,
  ferramentas, qualidade, condição, materiais, recipientes, transferências por intenção e contexto
  do System permanecem deliberadamente nas subfases 10E–10M.

## Fora do MVP

- Geração procedural complexa e novas regiões automáticas.
- Comportamentos sociais, econômicos e políticos profundos para NPCs e jogadores simulados.
- Guildas, PvP, mercado e autenticação multiusuário.
- Mapa gráfico.
- RAG, embeddings e sumarização automática de memórias.
