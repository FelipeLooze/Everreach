# World Genesis 1.0.2 — Estoques, massas e coleta vegetal R1

Implementação de 26/10/2026. **Coleta funcional no backend**, com autoridade derivada R1, partes reais do v22, inventário com peso positivo, fluxo HTTP de ações, recibos, undo e persistência. Ativação continua explícita e experimental; o banco real não foi migrado.

## Antes e depois

Antes, Vg2 permitia coleta somente com `PartCalibrationV1` revisada por parte; as novas espécies sem estoque e todos os materiais sem massa dependiam de dados individuais. O inventário usava a massa da definição global, e itens canônicos antigos de massa zero bloqueavam a integração. O arredondamento de peso também escondia materiais pequenos.

Agora, `botanical_gameplay_estimates_r1` deriva parâmetros por tipo, porte e parte. O indivíduo recebe estoques finitos uma única vez, sob uma autoridade independente da paisagem Vg2. Cada lote coletado mantém sua massa e proveniência. Uma definição antiga com massa zero continua intacta, enquanto o lote novo tem peso positivo. A ação estruturada usa o endpoint de ações do jogo, sem o narrador conceder itens.

`VegetationConfigV2`, `regional_canopy_v2`, geografia, clima C3 R1-55, W1/W2/P1 e o v22 não foram recalibrados. O catálogo continua sendo exclusivamente Flora v7.2: 3.096 espécies, 6.192 partes e 6.192 itens. IDs `EV-FL-*` e `IT-EVR-FL-*` são preservados.

## Cobertura efetiva da calibração

| Métrica | Resultado |
|---|---:|
| Espécies com perfil derivado | 3.096 |
| Partes com estimativa positiva de massa e rendimento | 6.192 |
| Partes utilizáveis como matéria bruta | **6.045** |
| Partes pendentes de processamento/evidência específica | **147** |
| Espécies com pelo menos uma parte bruta calibrada | **3.096** |
| Coletas reais executadas nas demonstrações | **30** |
| Espécies distintas realmente coletadas | **25** |

Os números de calibração não afirmam que todas essas espécies existem na mesma região. Elegibilidade ecológica, população estabelecida, disponibilidade sazonal, fase e proximidade continuam sendo verificadas separadamente. Fungos, algas, organismos subterrâneos e espécies excepcionais não são liberados pela simples existência de uma receita de massa.

As 147 pendências são 70 partes `pigmento_bruto`, cujo material exige extração, e 77 partes `po`, cujo estado seco/solto ou processamento não está demonstrado. Há uma estimativa de massa para planejar esses materiais, mas a coleta direta não produz pigmento extraído ou pó seco por conveniência. Não foi criado crafting. As demais partes de suas espécies continuam disponíveis quando houver condições reais.

Em alturas de referência por espécie, o CSV registra massas de **14 a 53.847 mg** por unidade e estoques de **1 a 89 unidades**, com **2.613 massas diferentes**. Alturas individuais diferentes podem produzir valores fora dessa faixa de referência: nas provas houve um ramo de 67.187 mg. Isso é esperado e está registrado por lote, sem reescrever uma massa global.

Arquivos completos: `coverage.json`, `part-calibrations.json` e `part-calibrations.csv`, em `artifacts/plant-resources-r1/`. São diagnósticos técnicos, não um catálogo paralelo nem uma autorização global de ocorrência.

## Regras de derivação e autoridade

`ResourceConfigR1` e `GenesisPlantResources` definem uma autoridade separada, com versão, perfil de balanceamento, conversão de peso, exceções esparsas, parâmetros anatômicos, política de disponibilidade, proveniência e assinatura. A assinatura inclui o catálogo fixado e a autoridade Vg2. Alterações posteriores exigem uma revisão explícita; a configuração de um R1 já estabelecido não é trocada silenciosamente.

Há 13 perfis de organismo e perfis de partes, incluindo folhas, pétalas, frutos, sementes, raízes, ramos, fibras, casca, frondes, talos, corpos frutíferos, esporos, musgos, líquens e amostras de colônia. Regras para madeira/tubérculo só poderão ser usadas se houver parte e item autoritativos: **nenhuma parte ou item de madeira foi inventado** no v22.

O modelo usa:

1. Porte adulto efetivamente definido no indivíduo Vg2. Quando o registro legado carece de altura, a arquitetura por tipo já versionada de Vg2 fornece a referência; ela é uma estimativa de jogo declarada.
2. Biomassa fresca estimada por tipo e pelo quadrado do porte relativo a uma referência. Exemplos de referência: árvore de 20 m com 400 kg de biomassa modelada; arbusto de 1,5 m com 2,5 kg; erva de 60 cm com 90 g; colônias pequenas com reservas menores.
3. Pools removíveis separados: vegetativo 30%, reprodutivo 12% e subterrâneo 25% da biomassa estimada. A parte não utiliza toda a massa da planta por padrão.
4. Porções-alvo por parte, variação morfológica estável por espécie/parte e limites de quantidade dependentes do porte. Raridade e nível do personagem **não entram** na massa ou no rendimento.
5. Orçamento compartilhado: partes de um mesmo pool repartem sua alocação. A massa reservada nas partes nunca supera o pool. Exceções que ultrapassam o orçamento são recusadas.

Uma unidade representa a parte bruta ou pequena porção nomeada no item, conforme a receita; não implica que todos os itens plurais sejam uma folha ou uma semente isolada. Raiz é tratada como raiz inteira, com remoção destrutiva. O material entregue e a massa da porção estão ligados ao mesmo ID canônico.

`quantidade_max` do contrato de coleta é respeitado como rendimento máximo da ação. Ele não é confundido com toda a reserva existente no indivíduo. Isso permite, por exemplo, colher uma porção por procedimento de uma planta que mantém várias porções finitas. A sugestão histórica `estoque_por_no_sugerido` é preservada como referência de proveniência, sem obrigar todas as plantas novas a permanecerem com estoque zero ou três unidades.

Esses valores são **estimativas determinísticas de game design**, não medições científicas. Exceções usam `ResourceConfigR1.overrides[part_id]` com massa/quantidade e justificativa, sem duplicar 6.192 registros ou editar o dataset. O limite físico do pool continua sendo aplicado.

## Maturidade, calendário e tipos de remoção

O estoque fundador é derivado do estado inicial persistente do indivíduo, não da data da primeira visita. Sua disponibilidade no momento da coleta considera o calendário corrente. Assim, a ordem de exploração não cria versões diferentes dos estoques.

- Frutos, sementes, esporos, propágulos e corpos frutíferos exigem fase reprodutiva apropriada; pétalas exigem floração.
- O marcador real do v22 `todo_ano_condicionado_a_atividade_biologica` é reconhecido. A regra de jogo R1 verifica suporte sazonal de temperatura C3 e ET W1 no período correspondente; não interpreta o marcador como disponibilidade irrestrita.
- Manhã, tarde, noite, madrugada e crepúsculo têm faixas explícitas de relógio. A convenção utiliza o calendário existente, sem criar meteorologia diária.
- Flags explícitas de preservação do catálogo são respeitadas. Quando o campo está ausente/null, R1 usa regra anatômica versionada, em vez de tratar null automaticamente como morte ou como preservação.
- Uma raiz, coleta declarada destrutiva ou remoção integral mata o indivíduo, zera suas partes e registra a massa removível descartada. A redução de recursos de uma coleta não destrutiva não mata a planta.

O v22 marca vários ramos de árvores novas e fragmentos de líquens como destrutivos. Por isso algumas provas removem o indivíduo após a coleta; não alteramos esse flag explicitamente definido para tornar o exemplo mais favorável. Uma revisão futura pode tratar exceções como balanceamento explícito.

O registro conserva estoques originais/restantes, pools originais/restantes, massa exportada, massa descartada, estágio, parte removida, momento da coleta, revisão e recibos. A conservação verificada é:

`pools iniciais = pools restantes + massa exportada + massa descartada`.

É o ledger da fração removível modelada, não um inventário global de toda a biomassa do planeta. A biomassa não alocada não vira material coletável implícito.

## Integração real com inventário

O inventário usa unidades genéricas de peso; não impunha kg no contrato. R1 declara **1.000.000 mg por unidade existente de peso** como convenção de sua calibração. Essa relação é persistida e revisável por uma nova autoridade, sem redefinir os itens antigos ou a capacidade global.

`ItemInstance` recebe duas colunas opcionais: `unit_weight_override` e `weight_authority`. Elas representam a massa congelada do lote. O cálculo de peso de itens, equipamentos, recipientes e carga consulta esse valor quando presente; itens antigos continuam usando `ItemDefinition.base_weight` e os fatores de material existentes.

Se a definição canônica já tem massa zero, ela **não é atualizada**. O novo lote utiliza o mesmo `IT-EVR-FL-*`, recebe massa positiva própria e mantém sua proveniência. Instâncias antigas permanecem com o peso anterior. Não são criados IDs alternativos para contornar conflitos, e lotes com massa específica não são misturados automaticamente a pilhas legadas pelo `add_item` genérico.

Foram corrigidos três pontos em que a precisão pequena poderia desaparecer:

- Peso unitário/total do lote na resposta de inventário.
- Peso e razão de carga quando há lotes de massa específica, inclusive dentro de recipientes. Limiares, capacidade por força e penalidades continuam sendo as regras existentes.
- Formatação do painel de inventário existente, que antes mostrava uma só casa decimal. Materiais pequenos agora aparecem com precisão significativa em vez de `0,0`. Foi uma correção de formatação, não uma reconstrução da interface.

O inventário permite sobrecarga conforme suas regras atuais; R1 não inventa um novo limite rígido de coleta. O peso acrescentado muda a faixa de carga corretamente. Limites de recipientes continuam sendo impostos.

### Migração compatível

`v30v3q4r5s6t_plant_resources_r1.py` adiciona somente duas colunas nullable e a tabela de autoridade. Não atualiza massas, quantidades ou campanhas. A migração foi testada em SQLite temporário com linhas legadas.

**A migração de schema precisa ser aplicada ao banco de implantação antes de executar este código contra esse banco. Ela não foi aplicada a `backend/everreach.db`.** Adicionar schema e ativar R1 são operações distintas. Depois da migração, uma campanha antiga continua sem recursos R1 até uma ativação explícita experimental; indivíduos já materializados preservam seu baseline anterior. R1 só fundamenta estoques nos novos indivíduos materializados sob sua autoridade. Não há conversão automática de instâncias antigas de massa zero.

## Fluxo de ações do jogo

O endpoint existente `POST /api/campaigns/{campaign_id}/actions?character_id=...` aceita `plant_action`, além do texto do jogador:

```json
{
  "text": "Quero colher esta parte da planta",
  "action_key": "coleta-planta-001",
  "plant_action": {
    "kind": "harvest",
    "individual_id": "ID retornado pela observação",
    "part_id": "EV-FL-1139-P01",
    "quantity": 1,
    "tool_instance_id": "ID da ferramenta física"
  }
}
```

Operações: `look`, `observe`, `harvest` e `remove`. `look` prepara somente alguns indivíduos finitos a até 5 m da âncora atual do personagem. Inverte a distribuição determinística dos slots, em vez de enumerar a população inteira. Consulta patches físicos vizinhos próximos, inclusive emendas, e retorna no máximo oito indivíduos observáveis. Não aceita coordenadas arbitrárias do cliente nem revela locais desconhecidos.

`observe` informa partes, estoque, massa, rendimento por ação, estágio e motivo de indisponibilidade. Identidade segue o contrato de conhecimento já existente. `harvest` valida indivíduo persistido, presença, parte, quantidade, fase, calendário, ferramenta efetiva, acesso ao equipamento e proficiência real. Não funciona com ferramenta quebrada ou guardada no inventário sem acesso apropriado. `remove` exige a ferramenta correspondente; árvore exige capacidade de serra e não produz madeira inexistente.

As ações respeitam personagem vivo e bloqueio do combate ativo do próprio ator. A proficiência não é concedida por importar flora. Os operadores das demonstrações receberam treinamento e kits explicitamente configurados no ambiente de teste; isso não é feito automaticamente em campanhas.

O resolvedor não chama LLM para decidir quantidade ou adicionar itens. Usa o mesmo sistema de checkpoint/undo da ação existente. Uma ação inválida não exporta massa, remove recursos ou cria lotes. Coleta/remoção válidas custam três minutos de jogo no perfil inicial; repetição idempotente devolve o recibo sem cobrar tempo novamente.

Uma revisão do caminho de replay também eliminou uma alteração desnecessária do contador de escrita que invalidava o fingerprint de undo em ações repetidas. A serialização cosmética dos novos itens entra no checkpoint antes de seu fechamento. O teste HTTP verifica coleta, inventário, replay e undo reais, sem chamadas ao narrador.

Não foi criado um painel de seleção de plantas nem um parser que adivinhe o alvo pelo texto livre. O contrato estruturado já é executável no backend do jogo e pode ser usado pelo cliente; a seleção visual mais ampla permanece fora desta fase.

## Demonstrações com espécies reais

Cinco bancos SQLite isolados foram criados a partir das autoridades reais das seeds 42, 0, 7, 2026 e 12345. Em cada um: seis tipos de organismo, seis transferências, replay de cada ação, tentativa de coleta excessiva, remoção adicional de árvore, fechamento e reabertura do banco.

Resultado conjunto: **30 coletas, 25 espécies distintas, 344.845 mg transferidos**, 20 coletas não destrutivas, 10 destrutivas e cinco remoções integrais adicionais de árvore. Cada replay manteve um só lote; cada tentativa excessiva foi recusada; todas as revisitas preservaram o estado. Nenhum item de madeira ou substância mágica foi criado.

Exemplos reais da seed 42, uma unidade entregue por ação:

| Tipo | Espécie / parte | Massa unitária | Estoque antes → depois | Estado |
|---|---|---:|---:|---|
| Flor | `EV-FL-1139-P01`, pétalas | 169 mg | 5 → 4 | Preservada |
| Erva | `EV-FL-2474-P01`, folhas | 1.343 mg | 33 → 32 | Preservada |
| Arbusto | `EV-FL-1927-P01`, ramos | 28.080 mg | 14 → 13 | Preservado |
| Árvore | `EV-FL-1827-P01`, ramos | 16.964 mg | 14 → 0 | Removida conforme flag do catálogo |
| Gramínea | `EV-FL-2109-P01`, fibras | 926 mg | 3 → 2 | Preservada |
| Líquen | `EV-FL-2789-P01`, fragmentos | 547 mg | 3 → 0 | Removido conforme contrato |

O líquen é o organismo equivalente demonstrado, com componente fúngico simbiótico; não o rotulamos como uma espécie de fungo coletada. Fungos propriamente ditos e os 96 extremos continuam sujeitos às provas ecológicas anteriores. Seus perfis de recursos estão calibrados, mas R1 não inventa energia, água, cavernas ou anomalias para estabelecê-los.

Cada `seed-*-proof.json` registra nome canônico, indivíduo real, coordenada técnica, parte, estoque inicial, observação, massa, recibo, lote, peso, estado após coleta e após reabertura. Os `.sqlite` correspondentes permitem inspeção direta. Os relógios dos cenários foram configurados para uma janela legal antes das ações; o resolvedor de produção não muda a estação para tornar uma coleta possível.

Foi corrigido também um limite do antigo harness: a importação descartável assumia seed 42. Agora usa a seed da autoridade geográfica e a evidência HR1 da mesma seed, sem alterar o solver climático ou hídrico.

## Preparação para a Fase 1.1

Os estados já distinguem recurso original, estoque restante, último momento/parte, indivíduo vivo/removido e pools de tecido. Há proposta inativa de intervalos de recuperação: comuns 5–7 dias, incomuns 10–14, raras 20–30, muito raras 45–60 e excepcionais a partir de 90 dias. São referências para futura parametrização; não tarefas agendadas.

**Não existe respawn, rebrote ou reprodução automática.** A passagem de 120 dias nos testes não repõe recursos. Recuperar folhas/frutos de um indivíduo vivo é um processo futuro diferente de criar e fazer crescer outro indivíduo. Indivíduo morto não recupera estoque por retornar à área.

## Desempenho e testes

Benchmark local de 1.000 derivações: aproximadamente **0,078 ms por perfil**; pico instrumentado de **16.649 bytes**, excluindo catálogo e autoridades já carregados. A compilação completa da auditoria de 6.192 partes levou aproximadamente 0,6–1,2 s nos ensaios.

No cenário medido: materializar o primeiro indivíduo/autoridades locais 2,21 s; observar sete indivíduos próximos 2,68 s; resolver uma coleta 0,97 s; replay 0,32 s. A observação inicialmente levava cerca de 13 s por repetir verificações de fonte. O lote local agora reutiliza o contexto e o pai validados sob o mesmo fence SQLite, preservando verificações de ponto, integridade e proximidade. Há teste de regressão da observação repetida e dos caminhos públicos originais.

São números de um ambiente de desenvolvimento, sem garantia de latência em outro hardware. Não incluem o custo do checkpoint HTTP, que usa o mecanismo existente de snapshot do banco inteiro. Esse mecanismo pode virar gargalo com saves muito grandes; não foi substituído por infraestrutura nova nesta fase. Não há enumeração de plantas planetárias, workers ou simulação contínua.

**906 testes backend distintos aprovados no escopo selecionado**: 724 World Genesis/auditoria climática; 168 de integração e compatibilidade; 25 de R1, descontando 11 testes de persistência repetidos entre os dois primeiros lotes. Verificações dirigidas adicionais validaram a otimização local, ferramenta guardada e a cobertura reprodutiva; não foram contadas duas vezes. Os resultados frontend do painel existente e hashes dos arquivos estão no manifesto de validação.

Também passaram **9 testes frontend** de `InventoryPanel`, incluindo a apresentação positiva de 0,000169 unidade de peso. Os testes backend cobrem as cinco seeds, tipos reais, IDs, calibração, raridade independente da massa, pools compartilhados, fenologia, calendário, estado persistente, limites, estoque negativo/corrupção, HTTP, ausência de chamadas ao LLM, replay, carga/recipientes, massas legadas, undo, rollback, reset e migração aditiva. Aviso conhecido do ambiente: depreciação Starlette/httpx.

## Arquivos e reprodução

Novos:

- `backend/app/game/world/genesis/vegetation/resources.py` — autoridade e derivação R1.
- `backend/app/game/world/genesis/vegetation/actions.py` — observação local e resolvedor compartilhado com HTTP.
- `backend/app/db/models/world_plant_resources.py` e migração `v30v3q4r5s6t`.
- `backend/app/tests/test_plant_resources_r1.py`.
- Scripts `validate_plant_resources.py`, `benchmark_plant_resources.py`, `refresh_plant_resource_views.py`.
- Este documento e `artifacts/plant-resources-r1/`.

Integrações alteradas:

- `vegetation/service.py`, registro de modelos e reset de campanha.
- `ItemInstance`, inventário, peso de itens/recipientes, encumbrance e serialização HTTP.
- Schema e rota de ações, reutilizando checkpoints existentes.
- Harnesses `prove_vegetation.py` e `validate_water_c3.py`, para kits de teste e importação correta de seeds.
- Formatação de peso e teste do painel de inventário existente.

O workspace já continha alterações de fases anteriores; elas não foram revertidas.

Dentro de `backend`, para gerar os artefatos em um ambiente isolado:

```powershell
.venv/Scripts/python.exe -m scripts.validate_plant_resources --coverage-only
.venv/Scripts/python.exe -m scripts.validate_plant_resources --seeds 42 0 7 2026 12345
.venv/Scripts/python.exe -m scripts.benchmark_plant_resources
.venv/Scripts/python.exe -m pytest app/tests/test_plant_resources_r1.py -q
```

O validador recusa sobrescrever bancos de demonstração existentes. Os arquivos entregues já contêm as cinco provas completas. `refresh_plant_resource_views` apenas recalcula a apresentação de peso nos JSON técnicos lendo esses bancos, sem novas transferências ou alterações de estados.

Para uma campanha experimental já preparada com Vg2/C3/W1 corretos, antes de materializar seus novos indivíduos:

```python
from app.game.world.genesis.vegetation.resources import initialize_resources, ResourceConfigR1
initialize_resources(db, campaign_id, ResourceConfigR1(), experimental=True)
db.commit()
```

### Pendências de ativação

Aplicar a migração aditiva ao banco de implantação após revisão, habilitar R1 explicitamente somente nas campanhas desejadas e realizar playtest de rendimentos/porções. Indivíduos antigos não são reabastecidos por essa ativação. As 147 partes de processamento e as dependências ecológicas anteriores permanecem identificadas, sem bloquear milhares de partes brutas por falta de medição científica individual. A etapa funcional está entregue; regeneração, crafting, fauna e novos sistemas de comércio não foram implementados.
