# Everreach — Economia ampliada (v4)

## Conteúdo

| Bloco | Antes | Agora |
|---|---:|---:|
| Ofícios / perfis comerciais | 55 | 120 |
| Mercadorias propostas | 139 | 1.000 |
| Serviços propostos | 14 | 150 |
| Receitas de fabricação propostas | 0 | 500 |
| Perfis de estoque | 0 | 250 |
| Perfis de demanda | 0 | 200 |
| **Total de registros desses seis blocos** | — | **2.220** |

## Autoridade e limitações

Todos os registros são conteúdo **proposto**, não eventos já presentes no mapa. O backend continua responsável por saldo financeiro, estoque, fabricação, preço, jornada de trabalho, qualidade dos materiais, jornada, existência de NPC, habilidades e efeitos de serviços. O narrador **não pode criar estoque, inventar preços nem conceder cura**.

As **500 receitas são rascunhos bloqueados**: elas referenciam IDs existentes, mas ainda exigem compatibilidade física dos insumos, catalogação de componentes em falta, verificação de comestibilidade e ferramentas, além de implementação e teste do sistema de receitas. Uma referência válida **não garante que o material seja adequado** para fabricar o produto final.

Os **250 perfis de estoque** descrevem capacidade potencial. O valor inicial sem seed é zero. Os **200 perfis de demanda** são sugestões condicionais e não originam eventos; preços só mudam com estado verificável. Não é permitido recriar dinheiro na virada do dia.

Os **120 perfis** incluem religiosos, trabalhadores urbanos, produtores, transportadores, curandeiros não mágicos e prestadores de serviços. Nenhuma profissão concede automaticamente poder mágico, cura sagrada ou cura natural; goblins e orcs não são povos comerciais selecionáveis por padrão.

## Economia escassa

Mantida referência de **8–12 cobres por turno** (1 cobre = 1 bronze). Itens caros exigem mais de um turno de trabalho, e NPCs possuem caixa limitado. Aceitação de itens é por ID explícito, não apenas pela categoria geral. Recursos sem comprador ficam sem venda normal.

## Validação realizada

- IDs únicos dentro de todos os blocos.
- Verificação de **500 monstros / 810 itens de bestiário** e **1.500 espécies / 3.000 itens de flora**.
- Referências de itens, mercadorias, serviços, receitas, produtos em estoque e categorias de demanda existentes.
- **Compatibilidade do código real e balanceamento: ainda não testados.**

## Arquivos

- `Everreach_Economia_2220_Registros_120_Oficios_v4.json`: arquivo completo da economia
- `Everreach_Economia_Indice_Compradores_v4.json`: índice reverso de compra por item
- `Everreach_Economia_2220_Validacao_v4.json`: relatório estruturado
- `Everreach_Economia_2220_Guia_v4.md`: este guia
