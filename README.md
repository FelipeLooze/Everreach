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
| POST | `/api/campaigns/{campaign_id}/actions?character_id=...` | Resolver uma ação textual |
| GET | `/api/campaigns/{campaign_id}/character?character_id=...` | Ficha do personagem |
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
- Ações de movimento, conversa, descanso, espera, exame e checagem simples de perícia.
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
- **Fase 8 — Progressão: PARTIAL (8A–8G concluídas).** XP de personagem é autoritativo,
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
  caminhos maduros simples e integrados, envia à LLM somente os domínios e sinergias factuais,
  valida estritamente a identidade semântica proposta e persiste ofertas dinâmicas como `PENDING`.
  A proposta não pode criar poderes ou alterar mecânicas, chamadas repetidas são idempotentes e a
  oferta somente fica visível quando um sistema autoritativo confirma um momento seguro.

## Fora do MVP

- Combate completo com turnos, dano e inimigos.
- Geração procedural complexa e novas regiões automáticas.
- Comportamentos sociais, econômicos e políticos profundos para NPCs e jogadores simulados.
- Guildas, PvP, mercado e autenticação multiusuário.
- Mapa gráfico.
- RAG, embeddings e sumarização automática de memórias.
