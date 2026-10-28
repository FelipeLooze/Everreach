# World Genesis — política de design AP1

Revisão 1, 27 de outubro de 2026. Direção de design solicitada para o Everreach; não é uma migração de autoridades planetárias nem um preset ativado nas campanhas.

> O mundo deve ser consistente nas consequências, mas fantástico nas possibilidades.

Everreach é um RPG de fantasia. A prioridade de implementação passa a ser, nesta ordem:

1. Diversão, descoberta e exploração.
2. Variedade de paisagens e conteúdo.
3. Consequências persistentes das ações do jogador.
4. Consistência interna e geração determinística.
5. Plausibilidade ambiental.
6. Realismo científico quando acrescentar valor ao jogo.

## Regras de decisão

Uma restrição deve proteger uma consequência observável, um limite de recurso, uma identidade ou uma compatibilidade. Fidelidade científica, isoladamente, não justifica bloquear conteúdo.

As autoridades V4/T1, J1/JR1, C3, W1/W2/P1, E1 e Vg2 existentes continuam reproduzíveis. Elas descrevem o mundo de fundo. Uma regra fantástica futura pode estabelecer uma exceção regional canônica, com identidade e estado próprios, sem fingir que o solver de fundo a previu.

“Desconhecido” não vira automaticamente “comprovado”. O caminho para sair de uma pendência é **gerar e persistir o elemento do mundo por uma regra autorizada**, não exigir uma demonstração científica completa nem alterar a resposta de uma consulta antiga.

## Possibilidades regionais

Vales férteis, bolsões verdes, lagos de montanha, oásis, fissuras de gelo habitáveis e pequenos ecossistemas fantásticos podem ter regras próprias. Devem respeitar o caráter regional, sem quotas planetárias de biomas, distribuição por nível do protagonista ou sorteio a cada visita.

Uma futura exceção deve carregar: versão da regra; linhagem da seed; endereço espacial estável; dimensões; identidade; vínculo com a região e suas interfaces; fonte canônica que autoriza sua existência; estado persistente e alterações. Seus limites precisam continuar através de setores e faces quando a extensão exigir.

Clima de fundo e condição local podem diferir. Essa diferença deve ser explícita. Uma regra de vale protegido não muda silenciosamente a chuva C3 de todo o continente nem reclassifica retroativamente um E1 persistido. A composição regional de Vg2 permanece a referência para evitar mosaicos aleatórios.

Para água, distinguir apresentação, uso e recurso mecânico. Um lago cenográfico não autoriza consumo infinito. Um reservatório utilizável tem estoque finito, unidade, estado e operações autoritativas. Uma eventual fonte fantástica possui origem e taxa explicitamente canônicas; não é um crédito W1 duplicado nem prova hidrológica fabricada.

As condições locais de flora extrema poderão ser criadas juntamente com o microambiente apropriado. Não é preciso esperar uma simulação de cavernas ou geofísica completa. Autorizações excepcionais do catálogo continuam obrigatórias; a política AP1 não concede anomalias específicas por conta própria.

## Ritmo e consequências

Prazos de crescimento são balanceamento em dias do calendário do jogo. Estações e ambiente podem modular o ritmo; não devem transformar uma expectativa comum de semanas em anos. Espécies, indivíduos e portes podem diferir. Raridade não determina automaticamente maturação.

Recuperar folhas ou frutos, amadurecer um novo indivíduo e reconstruir uma comunidade são processos distintos. Coleta, remoção, extinção e devastação continuam persistentes. Um indivíduo novo não apaga a identidade ou a morte do anterior.

O primeiro componente operacional desta direção é a política **GA1**, `adventure_calendar_ga1`, implementada sobre o motor L1. O nome é distinto de G1, a hidrografia local existente. GA1 não acelera automaticamente a reprodução L2, não muda elegibilidade de habitat e não ativa nenhuma campanha real.

A extensão experimental **GA2**, `adventure_renewal_ga2`, acrescenta oportunidades mais frequentes, orçamento reprodutivo por tempo e estabelecimento curto sobre L2/S1. Continua usando GA1 para maturação. Descendentes não encontrados mantêm registros compactos persistentes e recebem corpo coletável apenas ao serem encontrados. Os [resultados GA2](world-genesis-ga2.md) distinguem nascimento, crescimento e recuperação estrutural, sem substituir autoridades anteriores.

## Custo proporcional ao que o jogador percebe

Preferir coortes, integração analítica, eventos esparsos e processamento sob demanda. Individuais ficam persistidos quando envolvidos em interação ou quando necessários às consequências. Não expandir livros de massa ou validações físicas sem ganho mecânico identificável.

Um futuro executor agregado pode substituir detalhes internos se preservar os resultados relevantes e possuir versão explícita quando esses resultados mudarem. Não é obrigatório conservar um cálculo apenas por já existir. Estoques e inventário autoritativos, remoções, identidade de indivíduos interagidos, descobertas e ocupação finita continuam sendo obrigações.

Não criar workers planetários, serviços distribuídos ou simulação diária global. Medir preparação fria, atualização, consulta e revisita separadamente; não esconder latência mudando o trabalho de etapa.

## Compatibilidade e aceitação

Nenhuma política nova reinterpreta automaticamente snapshots ou campanhas. As versões anteriores permanecem disponíveis; um corte explícito futuro requer analisar estados, eventos pendentes e autoridades dependentes.

A aprovação deve incluir percursos, paisagens reconhecíveis, locais que possam ser encontrados, crescimento perceptível e revisitas com consequências. Métricas climáticas e contagens de catálogo são diagnósticos, não substitutos dessa experiência.

O [relatório desta revisão](world-genesis-gameplay-review.md) identifica os bloqueios reais, a primeira entrega e o que ainda depende de pequenos ajustes posteriores. Não autoriza iniciar fauna nem Atlas.
