# World Genesis — Integração Jogável 1

**Data:** 27 de outubro de 2026

**Perfil experimental:** `world_genesis_ap1_v1`

## Resultado

Foi conectada uma campanha opt-in ao fluxo de campanha, personagem, início do mundo, observação e coleta vegetal, inventário, relógio e persistência. O perfil legado continua sendo o padrão. A cadeia de autoridades é inicializada somente ao iniciar uma campanha explicitamente AP1; não há inicialização ou conversão automática de campanhas antigas.

O servidor real, apontado a um SQLite temporário migrado, completou criação, início, observação, coleta, retry idempotente, espera, revisita e retomada após reiniciar o backend. Os testes HTTP cobrem duas seeds. A interface possui controles e testes de componente, mas **a sessão visual no browser não pôde ser concluída neste ambiente**: não havia browser disponível (`Browser is not available: iab`) e o helper nativo de automação falhou ao conectar. Portanto, a fatia técnica foi entregue e exercitada por rotas reais, mas a validação visual final continua pendente; não declaro todos os critérios de aceite concluídos.

## Perfil e compatibilidade

`CampaignCreateRequest` aceita `legacy` e `world_genesis_ap1_v1`; omitir o campo mantém `legacy`. A tela de criação oferece a seleção explícita do perfil e uma seed opcional. O perfil e a seed são persistidos na campanha. A migração `z34_ap1_profile` só acrescenta colunas nullable `world_profile` e `playable_state`; não ativa campanhas existentes.

No início AP1, `start_playable` inicializa um descriptor persistente e idempotente. O mundo simplificado é global, mas setores, ambientes e indivíduos são preparados sob demanda. A posição inicial é encontrada por uma busca determinística limitada a 128 sondagens e 32 verificações de fundador. Se não encontrar terreno e uma parte vegetal acessível, falha com erro controlado; não cria espécie ou coordenada artificial.

As autoridades efetivamente chamadas pelo bootstrap são:

- Geografia esférica V4 e terreno T1.
- Hidrologia H1/HR1, clima C3 R1-55 (`land_recycling_ppm=550_000`), W1, geometria G1 e reconciliação W2/P1.
- Geologia J1/JR1 e ambientes E1.
- Vegetação Vg2 com `regional_canopy_v2`, recursos R1, ciclo GA1 e renovação/reprodução GA2.

As versões são escolhidas explicitamente no orquestrador, em vez de depender dos defaults históricos. Os contratos hídricos são inicializados com o manifesto local de evidências vazio; isso não materializa rios nem autoriza fontes de água não comprovadas. A navegação continua usando o grafo existente e não passa a ser navegação planetária.

## Fluxo do jogador

1. Em **Nova jornada**, escolher **World Genesis — expedição experimental**. O campo de seed é opcional; sem valor, usa-se a seed gerada pela criação da campanha.
2. Criar campanha e personagem, entrar na tela do jogo e selecionar **Iniciar mundo**.
3. Em **Vegetação próxima**, selecionar **Observar vegetação**. A lista usa somente indivíduos que o backend encontrou perto da âncora física. Espécies desconhecidas aparecem por tipo e índice local, sem nome canônico.
4. Examinar um indivíduo ou escolher uma parte disponível e **Coletar**. A solicitação contém apenas o identificador recebido do backend, a parte observada, a quantidade e a ferramenta real no inventário. O backend valida distância, estoque, fase, ferramenta e proficiência; R1 debita a fonte e o inventário recebe o item e sua massa autoritativa.
5. Para passar tempo, usar uma ação explícita como “Espero 16 horas”. Quando o interpretador classificar esse pedido como `FREEFORM`, o fallback estreito agora o encaminha para o `WAIT` existente, que limita a espera a 16 horas e usa o relógio único da campanha.
6. Observar novamente a vegetação. O catch-up é feito ao consultar a área; GA1/GA2 avançam até o horário canônico, sem tick diário global.
7. Desfazer a última coleta pelo controle existente de undo, quando ainda for a ação corrente. Reiniciar o backend e retomar a campanha preserva posição, inventário, autoridades, estoques e estado vegetal.

O componente envia `plant_action` pelo endpoint normal de ações; não cria inventário, grafo, relógio ou endpoint de coleta paralelo. O prompt do narrador recebe uma lista permitida de fatos observados e o resultado mecânico, sem IDs de espécies ocultos ou coordenadas. Se a IA narrativa não responder, há texto de reserva; os resultados mecânicos continuam sendo do backend.

## Banco e execução isolada

Migrei um banco novo, sem copiar ou abrir para escrita o banco local da campanha:

`C:\Users\Felipe\AppData\Local\Temp\everreach-world-genesis-ap1-migrations.sqlite`

O Alembic percorreu a cadeia completa e terminou em `z34_ap1_profile`. Nesse arquivo executei o servidor real, criei uma campanha de seed `24680` e retomei a mesma campanha depois de reiniciar o processo. O arquivo contém apenas essa campanha de validação.

O banco normal `backend/everreach.db` não recebeu migrações nem campanhas de teste. Seu SHA-256 permaneceu `88f5540cb26aec661b8808247ad18bc8762b2ba55f8fba0d1c5cdbc20d5971f3`, igual ao valor da auditoria anterior.

## Evidência de playtest e desempenho

### HTTP no servidor real

- Seed `24680`: perfil AP1, personagem iniciado na **Clareira de chegada**, âncora espacial e um setor esférico persistidos. O descriptor registra uma sonda e uma verificação de fundador.
- Preparação persistida medida: bootstrap `15,21 s`; preparação inicial `16,17 s`; o endpoint completo de início mediu `18,56 s` nessa execução.
- Observação retornou quatro indivíduos próximos; a gramínea permaneceu não identificada.
- Uma parte de fibras foi coletada: estoque `17 → 16`, quantidade `1`, massa exportada `2.378 mg`, tesoura `QUICK` e item presente no inventário.
- Retry com a mesma `action_key` devolveu o mesmo recibo sem duplicar item nem consumir estoque novamente.
- Após o reinício do backend, a campanha e o inventário foram recuperados. “Espero 16 horas” avançou exatamente `960` minutos. A revisita retornou quatro indivíduos e o cursor persistido de catch-up GA2 alcançou o minuto canônico `1444`.

### Medidas dos testes de duas seeds

No teste de integração HTTP, os tempos observados variam com cache e disponibilidade do narrador. Na execução instrumentada anterior ao ajuste do fallback `WAIT`, o endpoint de início levou `49,93 s` na seed 42 e `17,17 s` na seed 8.675.309; observação levou `5,84 s`/`3,32 s`, coleta `2,16 s`/`1,03 s` e revisita `5,87 s`/`3,25 s`. O caminho real isolado da seed `24680` mediu 15–18 segundos para bootstrap/preparação/início. O primeiro início pode incluir custo frio e tentativa de narração externa; esses tempos não devem ser tratados como benchmark estável. A busca de spawn ficou em uma sonda e um fundador no caso real medido.

## Alteração de espera

O playtest real identificou que a intenção “Espero 16 horas” caía em `FREEFORM` quando o provedor não classificava a frase, avançando somente um minuto. O backend já possuía `WAIT` e cálculo limitado de duração; acrescentei o reconhecimento determinístico apenas para espera explícita com duração ou horário. Frases como “Espero que a chuva pare” continuam sendo ação livre. Não foi criado outro relógio nem nova simulação.

## Arquivos alterados nesta entrega

- `backend/app/game/world/genesis/playable.py`: ferramenta de campo provisionada no slot de cintura, acessível segundo o serviço de equipamento existente.
- `backend/app/game/engine.py`: fallback de intenção de espera explícita para o `WAIT` canônico.
- `backend/app/tests/test_genesis_playable.py`: cobertura de slot acessível, descritores GA1/GA2 e avanço de 16 horas/catch-up.
- `backend/app/tests/test_village_residents.py`: casos positivos e negativo do reconhecimento de espera.
- `frontend/src/pages/CampaignSetupPage.test.tsx`: seleção legada e opt-in com seed.
- `frontend/src/features/game/VegetationNearby.test.tsx`: novo teste de observação de desconhecidos e envio de alvos confirmados pelo backend.
- `docs/world-genesis-playable-integration-1.md`: este relatório.

O checkout já continha, antes desta execução, as alterações de integração AP1 em rotas, schemas, modelo da campanha, tela de criação, tela de jogo, cliente de ações, serializadores e `playable.py`. Elas foram auditadas e reutilizadas; não foram reatribuídas a esta alteração. Permanecem outras mudanças locais preexistentes no checkout e não foram descartadas.

## Testes executados

- `pytest app/tests/test_genesis_playable.py app/tests/test_village_residents.py -q` — **9 passaram**, incluindo perfil legado, duas seeds AP1, espera explícita e regressões de residentes.
- `pytest app/tests/test_plant_resources_r1.py app/tests/test_vegetation_growth_ga1.py app/tests/test_vegetation_renewal_ga2.py app/tests/test_equipment.py app/tests/test_api_campaign_flow.py -q` — **74 passaram**.
- `npm.cmd test -- src/pages/CampaignSetupPage.test.tsx src/features/game/VegetationNearby.test.tsx` — **8 passaram**.
- `npm.cmd run build` — TypeScript e Vite concluíram.
- Migração Alembic de banco SQLite novo — concluiu em `z34_ap1_profile`.

Não executei a suíte completa do projeto. Os testes de integração automatizados usam o mesmo contrato HTTP das rotas, e também houve um percurso pelo processo Uvicorn real no banco migrado. A UI real foi compilada e testada em componentes, mas não visualmente percorrida neste ambiente.

## Limitações restantes

- Falta completar o playtest visual no browser: criar a campanha pela página, clicar nos controles, conferir a atualização visual do inventário e da revisita. O ambiente não expôs browser/janela ao helper de automação.
- A coleta experimental oferece tesoura e proficiência de campo de nível 35; não concede identificação científica. Os outros protocolos continuam bloqueados quando faltam ferramenta, habilidade, maturidade ou disponibilidade.
- A busca inicial é deliberadamente limitada. Seeds sem sítio elegível falham com diagnóstico em vez de receber um spawn fabricado.
- A espera é limitada a 16 horas por ação. O percurso demonstrou catch-up, não exige que a vegetação se regenere durante esse intervalo.
- Viagem pelo planeta, fauna ambiental, locais fantásticos, rios/lagos exploráveis e Atlas não foram ativados nesta etapa.
- O processo narrativo externo não estava disponível durante parte do playtest; os textos de reserva funcionaram e não alteraram os resultados mecânicos.

## Reproduzir em banco isolado

No PowerShell, use um arquivo novo em caminho temporário explícito. **Não substitua o valor pelo banco padrão do projeto.**

```powershell
cd D:\Games\Codigo\vrmmo\backend
$env:DATABASE_URL = 'sqlite:///C:/Users/Felipe/AppData/Local/Temp/everreach-world-genesis-ap1-repro.sqlite'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest app/tests/test_genesis_playable.py app/tests/test_village_residents.py -q
```

Para abrir o servidor e a interface em terminais separados, mantendo a mesma variável `DATABASE_URL` no processo backend:

```powershell
# backend
cd D:\Games\Codigo\vrmmo\backend
$env:DATABASE_URL = 'sqlite:///C:/Users/Felipe/AppData/Local/Temp/everreach-world-genesis-ap1-repro.sqlite'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend
cd D:\Games\Codigo\vrmmo\frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Abra `http://127.0.0.1:5173`, crie uma campanha **World Genesis — expedição experimental**, inicie o mundo, observe a vegetação, colete uma parte disponível, confira o inventário, espere 16 horas, revisite, reinicie o backend mantendo o mesmo `DATABASE_URL` e retome a campanha. A tela visual continua sendo a etapa manual pendente deste relatório.

## Próximo passo

Concluir a verificação visual manual da campanha AP1 no frontend usando o banco temporário acima. Em seguida, registrar eventuais ajustes de experiência observados antes de disponibilizar o perfil experimental para outras campanhas. Não migrar o banco real nem ativar AP1 como padrão nesse passo.
