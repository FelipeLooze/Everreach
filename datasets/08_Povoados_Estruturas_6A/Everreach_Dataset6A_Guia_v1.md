# Everreach — Dataset 6A: Povoados e Estruturas

**1.500 registros propostos**: 250 arquétipos de povoados, 500 construções, 400 infraestruturas e 350 características regionais.

## Conceito

Os registros são **modelos reutilizáveis**, não vilas existentes nem conteúdo automaticamente importado para o mundo. Cada arquétipo combina uma identidade econômica com um contexto social; por isso há 25 bases de povoado x 10 contextos.
As construções são 50 famílias x 10 versões funcionais; infraestrutura 40 famílias x 10 modelos de implantação; características regionais 35 fenômenos x 10 estados de observação. As variantes têm custos, capacidades, limitações e requisitos diferentes.
O narrador descreve somente o que o backend realmente instanciou.

## Compatibilidade

- 5 povos civis jogáveis, 10 possibilidades de origem mista; nenhuma profissão é determinada por raça.
- Goblins e orcs não são selecionados como população padrão.
- 120 perfis comerciais existentes são referenciados por ID exato; nenhum vendedor inventado.
- 10 biomas reconhecidos no bestiário; sugestões de nomes de lugares apontam para IDs reais do catálogo de 4.000 nomes, **não criam locais**.
- Tratamento religioso, medicina de ervas e magia natural continuam independentes.
- Salário de referência da economia escassa: 8 a 12 cobres por turno, sem geração espontânea de caixa, mercadorias ou serviços.

## Integração em etapas

1. Escolha a região e valide bioma, rotas e fontes de recursos realmente presentes.
2. Escolha um `arquétipos_de_povoados[*].id` cujo contexto seja compatível.
3. Crie a instância persistida (ID próprio do save, diferente de ID de modelo), e reserve um nome do Dataset 5B.
4. Alocar lotes e somente então instanciar edifícios, infraestrutura e observações regionais.
5. Associar NPCs já instanciados e ofícios reais, seguindo economia e rotina; não gerar pessoas a partir de descrições.
6. Instanciar estoques, demanda, horários, obras e acontecimentos através dos subsistemas autoritativos.
7. Entregar ao narrador um resumo dos fatos persistidos, nunca as permissões de criar vilas, NPCs ou itens.

## Distribuição de arquétipos por bioma principal

- arredores_povoados: 30
- bosques_florestas: 60
- cavernas_subterraneo: 10
- colinas_montanhas: 30
- costa: 30
- pantanos_mangues: 10
- planicies_cultivos: 30
- regioes_frias: 10
- rios_lagos: 30
- ruinas_estruturas: 10

## Checagens
- 23 verificações executadas, 23 aprovadas.
- Ajustes de referência durante a validação: edifícios 0, características regionais 0.
- Conteúdo estrutural validado; **não houve teste de integração com o código de Everreach**.

## Arquivos
- `Everreach_Dataset6A_Povoados_Estruturas_1500_v1.json`: dados completos
- `Everreach_Dataset6A_Indice_1500_v1.json`: índice de consulta
- `Everreach_Dataset6A_Validacao_v1.json`: relatório automático de consistência
- `Everreach_Dataset6A_Guia_v1.md`: este guia
