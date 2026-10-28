# Everreach 6A — Matriz ambiental de povoados (v7)

Esta atualização complementa o Dataset 6A anterior e a taxonomia de 100 ambientes (v6). Preserva **250 arquétipos, 500 edifícios, 400 infraestruturas e 350 características regionais**. Acrescenta **25.000 avaliações**, não 25.000 novos povoados.

## Interpretação

- **16.250 avaliações naturais**: `favoravel_candidato`, `condicional` ou `inadequado_sem_adaptacao_excepcional`.
- **6.250 avaliações construídas**: infraestrutura associada ou não essencial; um porto, estrada ou templo jamais substitui o terreno real.
- **2.500 avaliações anômalas**: bloqueadas até aprovação canônica.

A pontuação `adequacao_heuristica` de 0 a 100 serve apenas para ordenar candidatos. Nenhum resultado autoriza criação automática. Mesmo `favoravel_candidato` exige água potável, suprimentos, rota/acesso, terreno estável e comprovação do recurso produtivo, com evidências reais do mapa.

## Estrutura

- `Everreach_Dataset6A_1500_Matriz_250x100_v7.json`: Dataset 6A completo com matriz incorporada.
- `Everreach_Dataset6A_Matriz_250x100_v7.json`: só matriz e perfis ecológicos propostos.
- `Everreach_Dataset6A_Matriz_Naturais_250x65_v7.csv`: tabela plana das avaliações naturais.
- `Everreach_Dataset6A_Matriz_Validacao_v7.json`: integridade verificada e ressalvas.

## Como aplicar no backend

1. Escolher uma área com ID persistido e classificação natural confirmada.
2. Ler no registro da matriz a avaliação de `arquetipo_id` e `ambiente_id`.
3. Verificar evidências requeridas, fontes de água, alimentos e viabilidade do terreno.
4. Se `condicional` ou `inadequado_sem_adaptacao_excepcional`, exigir justificativa material: irrigação, importação de insumos, edifícios persistidos, rota de transporte ou obras efetivamente realizadas. Inadequado exige revisão manual ou regra excepcional explícita.
5. Confirmar sítios de extração, cultivo, pesca ou mineração reais; `adequacao_heuristica` não cria recursos.
6. Instanciar local, edifícios e habitantes apenas pelos sistemas autoritativos já existentes; o narrador descreve sem gerar entidades.

**Goblins e orcs seguem fora dos povos moradores comuns**, e os cinco povos jogáveis e seus descendentes não possuem restrições ambientais intrínsecas. O uso de templos ou boticas também não atribui cura automaticamente.

## Verificação

- versao: `v7`
- estado: `estrutura_validada_heuristicas_precisam_revisao`
- quantidade_arquetipos: `250`
- quantidade_ambientes: `100`
- avaliacoes: `25000`
- naturais: `16250`
- construidos: `6250`
- anomalos: `2500`
- total_registros_dataset_6a_sem_alteracao: `1500`
- ids_originais_preservados: `True`
- edificios_infraestrutura_caracteristicas_preservados: `True`

### Exemplos (núcleo estável)

- Comunidade cerealista em EV-BIO-PRADARIA: `favoravel_candidato`.
- Comunidade cerealista em EV-BIO-DESERTO_DUNAS: `inadequado_sem_adaptacao_excepcional`.
- Aldeia ribeirinha de pesca em EV-BIO-RIO_LENTO: `favoravel_candidato`.
- Porto de pescadores em EV-BIO-COSTA_ROCHOSA: `favoravel_candidato`.
- Assentamento de mineração em EV-BIO-SERRA_GRANITICA: `favoravel_candidato`.
- Bairro subterrâneo habitado em EV-BIO-CAVERNA_CALCARIA: `favoravel_candidato`.

**Limite:** validação estrutural e critérios propostos, sem leitura da configuração real da engine e sem teste de comportamento em tempo de jogo.
