# World Genesis WGS3.1: água física explorável

## Decisão

O perfil experimental opt-in `world_genesis_ap1_tp1_wgs3_v1` preserva o seletor, a geografia, as formações WGS2 v5, a cobertura multissetorial e o microambiente vegetal canônico. `WGS3_LOCAL_WATER_R1` é uma projeção da fonte local já persistida em `GenesisLocalWaterBody`. Não há novo estoque, migração, recarga automática nem alteração de W1/W2/P1. Saves anteriores seguem nos perfis e resultados originais. O catálogo v24 não foi alterado.

## Matriz das autoridades

| Autoridade | Dados estabelecidos | Limite para exploração hídrica |
|---|---|---|
| V4/T1 | topologia esférica, elevação e declive local | não fornece água, profundidade ou leito |
| H1 | oceano de referência em amostras, bacias e corredores potenciais de drenagem | corredor não é rio ativo; depressão não é lago ocupado |
| C3 | precipitação, temperatura, PET e transporte climático | chuva não estabelece corpo d'água local |
| W1 | contas sazonais de entrada, estoque, evaporação e escoamento | volume macro não possui geometria local de rio/lago |
| W2 | reconciliação e histórico de transferências autorizadas | revisão não cria curso d'água permanente |
| P1 | provas locais episódicas de lâmina superficial e passagem | não estabelece margem, lago permanente ou rede conectada |
| E1 | classificação e habitats potenciais | ambiente úmido não confirma água visível |
| J1/JR1 | unidades e substratos geológicos | não mapeia aquífero ou nascente subterrânea |
| TP1 | âncoras, grafo e rota amostrada; oceano de referência pode bloquear caminhada | sem profundidade de água doce para novos bloqueios |
| WGS2 v5 | formação `EV-LOC-0068`, posição, cobertura, acesso e estoque finito próprio | fonte local não debita W1 e não implica fluxo ou recarga |
| Inventário/R1 | itens e recipientes com capacidade por **peso** | não há capacidade líquida em litros, conteúdo fluido ou transferência de fonte |

Existem amostras oceânicas, corredores potenciais e contas de água. Não existem leitos fluviais locais finais, lagos ocupados, margens navegáveis, aquíferos mapeados ou conectividade hídrica autoritativa. `EV-LOC-0068` é a fonte física local atualmente suportada; não é prova de rede de nascentes global nem de rio permanente. Outros arquétipos hídricos do catálogo ainda não têm adaptador e evidência suficientes nesta etapa.

## Contrato local e estados

A fonte usa a chave canônica derivada da seed/endereço/arquétipo da formação, repetível entre campanhas da mesma geografia. O ID da instância e o estoque mutável pertencem à campanha. O contrato interno inclui âncora esférica e cobertura da formação, origem `generated_local_spring`, tipo, unidade `litre`, capacidade, volume disponível, revisão e assinatura do estado. A assinatura muda quando o estoque ou a revisão muda; a chave da fonte permanece. O objeto enviado ao jogador omite âncora e origem interna. A consulta lê o registro `GenesisLocalWaterBody`, inclusive após revisita, sem reutilizar o snapshot de criação em `formation.data.water` como volume atual.

| Estado | Nesta entrega |
|---|---|
| Observável | sim, quando o estoque é positivo e o personagem está na fonte; fissura seca é descrita como seca |
| Fisicamente presente | sim, se `available_litres > 0` no registro autoritativo |
| Acessível | sim, ao chegar à formação/acesso pelo grafo existente |
| Coletável | não; falta capacidade líquida e transferência autoritativa no inventário |
| Armazenada em recipiente | não |
| Consumida ou transferida | não |

A nascente mantém os **12.000 L iniciais já existentes** e o limite de capacidade do mesmo registro. Não se afirma potabilidade, correnteza, temperatura, vazão, recarga ou qualidade da água. Inspecionar e interagir mostram o estado sem debitá-lo. O mesmo registro atende a acessos em células distintas da cobertura; não nasce uma nova fonte ao visitar outra célula. Um estoque zero não é regenerado por observação ou tempo.

## Descoberta, deslocamento e inventário

A observação na fonte apresenta apenas água visível na fissura, ou fissura sem água se o estoque estiver vazio. Indícios próximos seguem sem nome e sem coordenadas de local desconhecido. Inspeção e investigação são liberadas somente no local da formação ou de seu acesso. O narrador recebe fatos confirmados; o mapa público não recebe âncora nem cobertura oculta.

TP1 já bloqueia superfície oceânica de referência e declives pedestres acima do limite amostrado. A nascente local não possui largura/profundidade para bloquear uma trilha, então não se criou obstáculo adicional. P1 não foi promovido a rio ou lago. O inventário limita recipientes por massa de itens, sem capacidade volumétrica, fluido contido ou operação de transferência em litros. Coleta e consumo ficam bloqueados; representar água como item sólido produziria quantidade e peso sem autoridade.

## Validação e desempenho

Os testes controlados escolhem o arquétipo `0068` numa célula terrestre real da seed 42, preservando a classificação física E1/T1/H1. Isso demonstra suporte e não frequência orgânica. A fonte foi inspecionada no local principal e em um acesso de outra célula, com uma só linha de estoque. O teste verificou assinatura estável após commit/reload, alteração de assinatura após revisão/volume, estoque seco sem reposição, isolamento entre duas campanhas de mesma geografia e rejeição de uma formação `0068` sem estoque físico. Nenhuma migração foi executada no banco principal.

Em 25 consultas aquecidas no SQLite de teste, a mediana da projeção de contrato foi 0,398 ms e da inspeção completa 0,920 ms na execução final (uma execução anterior mediu 0,679 e 1,433 ms). São tempos locais de uma sessão, sem comparação V5 controlada ou carga HTTP; as consultas usam a PK da formação e a âncora, sem recalcular planos globais.

## Playtest HTTP e regressões

O script `backend/scripts/playtest_wgs2_canonical_http.py` usa Uvicorn real, LLM desativada e SQLite temporário. No cenário controlado da seed 42, somente o **seletor do fixture** escolheu `EV-LOC-0068`; o ponto terrestre, evidências E1/T1/H1, cobertura, grafo e estoque vieram das autoridades existentes. A campanha iniciou em 18,792 s; o primeiro deslocamento levou 1,317 s. Houve observação, acesso pelo grafo, inspeção, interação de consulta sem coleta, retorno, reinício do servidor e revisita. A chave `971bf7633e7e2245842ca312b618c5702b3ebe7b592def9ca013d8204f6c8c10` e os 12.000 L permaneceram. O mapa público não revelou coordenadas ocultas.

Nos percursos **orgânicos** das seeds 7 e 2026, não apareceu fonte próxima ao início; isso não invalida o cenário controlado nem demonstra frequência global. Os tempos de inicialização foram 33,480 e 33,297 s; os primeiros deslocamentos, 2,357 e 2,174 s. Esses tempos são observações de uma execução, sem comparação controlada de perfis. Os resultados resumidos estão em `artifacts/wgs3-water/http-results.json`.

O teste dirigido WGS3 terminou com 3 aprovados. A bateria dirigida WGS3/WGS2 e formações legadas terminou com 30 aprovados antes dos ajustes finais de narração; depois deles passaram novamente os 3 testes WGS3, 12 testes de contexto narrativo e o playtest HTTP. A tela de criação passou em 9 testes e `tsc`/Vite compilaram. O teste verifica a mesma fonte em dois pontos de cobertura, estoque único, alteração de assinatura ao mudar volume/revisão, secagem sem reposição, isolamento de campanhas, observação seca, contexto narrativo atual e ausência de água fabricada quando falta o registro. Sem contrato volumétrico de inventário, não existe operação de transferência para testar rollback de coleta.

## Arquivos da integração

O contrato está em `backend/app/game/world/genesis/local_water.py`; o perfil e o dispatch em `playable.py`, `local_formations.py` e `vegetation/microhabitat_canonical.py`. A observação e o narrador foram ligados em `perception/service.py`, `ai/context_builder.py` e `api/routes/actions.py`. O opt-in de campanha e a interface foram ligados em `api/routes/campaigns.py`, `schemas/campaign.py`, `frontend/src/pages/CampaignSetupPage.tsx` e `frontend/src/features/game/GameScreen.tsx`. A validação está em `backend/app/tests/test_genesis_wgs3_water.py`, no teste da tela de criação e no script HTTP citado acima.

## Próximos contratos necessários

Para coleta, o inventário precisa de recipiente com capacidade volumétrica, conteúdo líquido e operação transacional que debite a fonte e credite o recipiente uma vez. Para rios e lagos, H1/W1/W2/P1 precisam estabelecer geometria, conectividade, presença e, para obstáculos de viagem, largura ou profundidade/classe de travessia. A fonte local, por si só, não autoriza esses dados nem um bônus Vg2 de umidade.
