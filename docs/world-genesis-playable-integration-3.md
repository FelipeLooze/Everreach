# World Genesis — Integração Jogável 3

Status da entrega: **implementação candidata**, isolada no perfil opt-in `world_genesis_ap1_tp1_wgs1_v1`.

## Decisões

- Reutilizar o endereço esférico TP1, `Location`, `LocationConnection`, descoberta e mapa existentes. Não foi criado grafo físico nem atlas paralelo.
- Não alterar AP1, TP1, o pacote v24 ou saves existentes. A campanha só recebe `natural_formations_wgs1` quando inicia com o perfil novo.
- Seleção puramente determinística por versão, seed e célula física. A primeira visita/materialização não define a geografia.
- Persistir instâncias e água local em tabelas próprias. Água local não é crédito, escoamento ou estoque de W1/W2/P1.
- Usar pontos de acesso na superfície a 10 m geodésicos do setor, mantendo o contrato de viagem e materializando o ponto E1 quando há plano ambiental.
- No perfil WGS1, resolver frases explícitas de movimento contra as conexões já conhecidas antes de usar o alvo genérico do parser. A travessia continua executada pelo serviço de viagem atual.

Alternativas descartadas nesta fase: gerar o planeta em alta resolução antecipadamente; introduzir outro grafo de deslocamento; inferir conteúdos por bioma/altitude; selecionar formações anômalas/ley lines sem as autoridades físicas correspondentes.

## Dataset e escopo efetivo

O arquivo `datasets/Everreach_v24_REENVIO.zip` é validado por SHA-256 `db4aced7cf5ed8d0a0d4df45b8def5789ce66d47d52a67411ed318e12483d3f0`. O catálogo tem 240 arquétipos, índice alinhado e 56 manifestações. Cinco arquétipos possuem adaptador jogável nesta versão:

| ID | Uso nesta fase |
| --- | --- |
| EV-LOC-0036 | formação natural rochosa |
| EV-LOC-0042 | vale de pontes rochosas sem origem arcana obrigatória |
| EV-LOC-0050 | caverna simples com interior e retorno pelo grafo |
| EV-LOC-0068 | nascente com estoque local finito e origem explicitada |
| EV-LOC-0236 | micro-habitat de sombra/depressão; sem flora injetada |

Os outros 235 arquétipos são apenas dados catalogados. Os 30 anômalos continuam indisponíveis. Nenhuma fauna, flora, minério, loot ou recompensa foi criada.

O seletor divide cada célula TP1 em 1.000 resultados determinísticos e reserva intervalos pequenos aos cinco arquétipos (total 1,1% por célula elegível). É uma densidade provisória de oportunidades, não reprodução de raridade canônica. Em amostras técnicas de 10.000 células: seed 42 gerou 102 candidatos; 0: 95; 7: 110; 2026: 116; 12345: 121. Essas contagens avaliam o seletor puro, não a quantidade de formações válidas em território alcançável.

## Estados de conteúdo

- **CANDIDATO:** devolvido pelo seletor para uma seed/célula; ainda não cria localização pública.
- **MATERIALIZADO:** instância e arestas persistidas quando o território físico é preparado. IDs derivam de campanha, seed, endereço e arquétipo; revisita reusa o registro.
- **EXPLORÁVEL:** localização/aresta já descoberta pelo personagem no fluxo de exploração. A API de mapa filtra conteúdo desconhecido; resposta de inspeção publica apenas nome, dimensões, características e estado local da água, não IDs internos nem coordenadas.

Para a nascente, o estoque inicial é 12.000 L, com limite persistido e fonte `generated_local_spring`; não há coleta nem transferência para inventário nesta entrega. Para a caverna, foi criado um interior simples ligado por arestas `entrar`/`sair`, sem conteúdo inventado. A evidência materializada é marcada como local e nunca afirma alteração da autoridade climática, geológica ou hidrológica regional.

Na validação: os cinco adaptadores foram materializados em testes isolados; na seed 42, a API levou o personagem até a nascente e uma caverna real, permitiu inspecionar/interagir, entrar/sair e revisitar mantendo estado e estoque. Assim, esses dois exemplos chegaram a **EXPLORÁVEL** no fluxo testado; isso não equivale à aprovação do perfil para campanhas reais.

## Arquivos

Implementação: `backend/app/game/world/genesis/local_formations.py`; modelos em `backend/app/db/models/world_natural_formations.py`; migração aditiva `backend/alembic/versions/z36_genesis_local_formations.py`; ativação explícita no perfil e integração nas rotas de território/ações; seletor na criação de campanha; tipos e botões da interface.

Testes em `backend/app/tests/test_genesis_local_formations.py`. A migração cria apenas as duas tabelas novas e não reescreve registros de campanhas AP1.

## Validação executada

- WGS1 backend: 6 testes passaram (seletor determinístico, cinco adaptadores, persistência após commit/expiração, idempotência, migração e jornada HTTP seed 42).
- Jornada HTTP: iniciou opt-in, confirmou mapa inicial sem locais desconhecidos, percorreu setores, explorou a nascente e seu estoque persistente sem extração, entrou/saiu da caverna e revisitou os locais.
- Regressões de exploração, ação de explorar, viagem e mapa: 31 testes passaram.
- Frontend: 6 testes de criação de campanha passaram; `npm run build` passou. Vitest retornou código 0, mas reportou timeout de fechamento do processo após os testes concluírem.
- `compileall` e `git diff --check` dos arquivos alterados passaram.
- A migração WGS1 isolada z35→z36 passou no teste dedicado. A verificação antiga de schema do banco do zero continua falhando por esperar colunas de peso de itens ausentes nessa cadeia (`unit_weight_override`, `weight_authority`); z36 não altera `item_instances`.

## Limites e próximos passos

- A cobertura está limitada a uma célula TP1 (máximo de 700 m de extensão nesta primeira fatia); formações multissetoriais extensas ainda não têm contrato de cobertura/travessia.
- A elegibilidade contextual ainda é mínima: o seletor usa endereço/seed e não confirma evidências de terreno regional para validar cada substrato. Não use esta candidata para ativar campanhas reais sem uma etapa de calibração e revisão de regras.
- A nascente tem estoque persistente inicial de 12.000 L, apenas como parâmetro técnico provisório da autoridade local; não está calibrado pelo Dataset v24 nem por W1/W2/P1, não é consumível e não recebe recarga. Isso prova persistência, não validação hidrogeológica regional.
- A caverna não é uma rede de cavernas nem um sistema de expedição.
- O percurso de API e persistência após commit são automatizados; reinício de processo e teste manual visual não são simulados. Nenhuma captura de tela é reivindicada.
- Uma execução da suíte de migração integral revelou uma falha preexistente na expectativa do teste de esquema (`item_instances` espera `unit_weight_override`/`weight_authority` ausentes no caminho de migrações atual). A migração WGS1 isolada z35→z36 é verificada separadamente; esse desvio não foi alterado nesta fase.

Antes de habilitar além do perfil experimental: testar reinício real do backend com save WGS1, auditar a elegibilidade de cada formação contra T1/E1/Vg2 e decidir como a interação de água local deve alimentar inventário sem contornar W1/W2/P1.
