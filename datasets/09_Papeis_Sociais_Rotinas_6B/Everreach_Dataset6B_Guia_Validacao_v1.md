# Everreach — Dataset 6B (v1)

## Resumo

- **350 papéis sociais**: 120 ocupações ligadas aos IDs da Economia v4, 225 especializações de 75 funções sociais e 5 papéis singulares.
- **1.200 atividades**: 200 ações-base nas 50 famílias de edifícios do 6A e 40 ações-base em 10 ambientes externos, cada uma com 5 condições distintas.
- **650 variações de rotina**: 130 perfis-base para papéis referenciados, cada um com 5 contextos dependentes de eventos reais.
- **Total: 2.200 registros**, excluindo índices auxiliares.

## Uso previsto

1. O gerador seleciona ou valida um NPC já existente e sua etapa de vida, casa, contatos e local de trabalho.
2. O backend atribui um papel elegível, sem impor ofício por raça, gênero ou cultura.
3. O agendador escolhe uma rotina **orientativa** (não uma mudança instantânea de posição).
4. A atividade depende da presença no local, de recursos, de acessibilidade e do evento contextual.
5. O narrador só descreve mudanças já processadas e confirmadas.

## Dependências

- `08_Povoados_Estruturas_6A/Everreach_Dataset6A_1500_Matriz_250x100_v7.json`: edifícios, ambientes e instalações.
- `04_Economia_e_Oficios/Everreach_Economia_2220_Registros_120_Oficios_v4.json`: IDs de 120 ocupações.
- `07_Povos_e_Ancestralidades/Everreach_Ancestralidades_5_Povos_10_Combinacoes_v1.json`: cinco povos e descendência mista.
- Backend: persistência dos NPCs, endereços, relógio, deslocamento, escalas, condições e eventos.

## Delimitação entre cura religiosa e natural

- Sacerdote, clérigo, acólito: tarefas ligadas a templo; cura sagrada só com habilidade adquirida.
- Herbalista, boticário, curandeiro: medicina por ingredientes/serviços reais; magia nunca implícita.
- Druida: vínculo com natureza e rituais; cura natural mágica somente quando capacidade cadastrada.

## Limites e proteção da consistência

- Crianças e adolescentes podem estudar, brincar ou colaborar em tarefas leves, nunca assumir risco laboral de adulto automaticamente.
- Idosos podem exercer profissões e ter rotinas ativas; aposentadoria é um papel possível, não obrigação.
- Intervalos de horário são janelas locais de disponibilidade e **não autorizam teleporte nem avanço compulsório do relógio**.
- Folgas, chuva, festas e ocorrências só alteram agendas quando existem evidências persistidas.
- Comércio, produção, recuperação de HP e recompensas dependem dos respectivos sistemas autoritativos.
- 240 ações-base e 130 rotinas-base variam por contexto; os 2.200 registros **não são 2.000 conceitos independentes**.

## Validação

- IDs únicos: aprovado.
- Referências às ocupações, edifícios e povos: aprovadas.
- 50 famílias de edifícios cobertas pelas atividades.
- Nenhuma atividade cria itens ou instancia NPCs automaticamente.
- Nenhuma profissão concede cura ou magia automaticamente.
- **Integração funcional com backend: pendente**.
