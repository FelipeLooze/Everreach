# Everreach — Dataset 6C: Vida Comunitária

## Resumo
O arquivo principal contém 1.500 modelos combináveis, não 1.500 acontecimentos que já ocorreram no mundo.
Os 200 modelos extras opcionais ficam em arquivo independente para permitir expansão sem misturar a meta original.

| Categoria | Modelos | Famílias de situações | Variantes por família |
|---|---:|---:|---:|
| Eventos comunitários | 400 | 100 | 4 |
| Problemas locais | 400 | 100 | 4 |
| Costumes e tradições | 350 | 70 | 5 |
| Interações sociais | 350 | 70 | 5 |

## Como o jogo deve usar
1. Primeiro selecionar um povoado real persistido e validado na matriz 6A.
2. Conferir se há local/edifício real e NPCs presentes, disponíveis pela rotina 6B.
3. Verificar calendário, clima, recursos, estoque e registros de problema quando aplicável.
4. Instanciar uma ocorrência com ID estável e registrar estado, participantes e consequências verificadas.
5. Narrador só descreve a ocorrência resolvida ou em progresso, sem decidir inventário, missões ou falas do jogador.
6. Para uma missão, enviar sugestão ao Diretor (430 modelos) e exigir um dos sete gatilhos oficiais.

## Segurança de mundo / qualidade de simulação
- Nenhum template habilitado automaticamente. `habilitado_no_backend:false` exige integração explícita.
- Cada `familia_id` suporta exclusão de variantes simultâneas incoerentes.
- Poboados, edifícios e perfis de papel têm IDs reais dos datasets anteriores, mas são somente referências de modelos.
- Tradições não derivam obrigatoriamente da espécie e não estabelecem divindades ou deuses canônicos.
- Crianças não trabalham em atividades perigosas; qualquer participação exige idade/maturidade apropriada e supervisão quando cabível.
- Uma conversa entre NPCs não cria amizade, romance ou parentesco sem evento canônico do sistema social.
- Não cria moedas, bens, clientes, visitantes nem locais por narrativa.
- Não ativa automaticamente ambientes anômalos.

## Compatibilidade e limitações
Referências 6A e 6B foram verificadas por ID; a compatibilidade com funções e eventos reais do backend não foi testada.
Os motivos e preocupações são texto de apoio para geração de cena, e as condições são propostas de contrato runtime.
As categorias de ambiente natural são candidatas; a matriz ambiental 6A continua a autoridade para instanciar povoados.

## Verificações
- 1500 modelos / 1500 IDs únicos, sem títulos duplicados.
- 100 famílias de eventos, 100 famílias de problemas, 70 famílias de costumes e 70 famílias de interações.
- Referências de edifícios, arquétipos e papéis presentes nos JSONs 6A e 6B.
- Gatihos de missão sugeridos restritos aos sete tipos existentes.
- 200 modelos extras opcionais separados (não inclusos na contagem principal).

## Arquivos principais
- `Everreach_Dataset6C_Vida_Comunitaria_1500_v1.json` — dataset completo de 1.500.
- `Everreach_Dataset6C_Expansao_Opcional_200_v1.json` — 200 modelos opcionais.
- `Everreach_Dataset6C_Indice_1500_v1.json` — índice leve.
- `Everreach_Dataset6C_Validacao_v1.json` — relatório de integridade.
- `Everreach_Dataset6C_Pacote_1500_v1.zip` — pacote somente 6C.
- `Everreach_TODOS_Datasets_Com_6C_v9.zip` — conjunto geral atualizado para a versão 9.
