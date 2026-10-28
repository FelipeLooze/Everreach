# Everreach — Bestiário: Anatomia, extração e aproveitamento v7

**Natureza:** camada de dados proposta e não integrada; o Codex/backend detém toda autoridade de instanciar anatomia, corpos, fontes, ações e saques. Nenhum novo item é criado por esta atualização.

## Quantidades
- 500 espécies preservadas do bestiário v6 (compatível com 100 ambientes)
- 1.500 saques existentes, sem mudança de IDs, chances, nomes, preços ou quantidades
- 500 perfis anatômicos sugeridos
- 1.500 protocolos por saque (dificuldade de 0 a 100; habilidades e ferramentas por capacidade)
- 136 proficiências externas disponíveis; cada protocolo usa IDs existentes no dataset universal
- 14 alertas semânticos (incluindo 1 bloqueios manuais)

## O que importa ao importar
1. Referência para o bestiário anterior v6: `HISTORICO_BESTIARIO_v6_NAO_IMPORTAR/Everreach_Bestiario_500_Biomas100_v6.json`. Use a v7 como substituição **ativa**, não em conjunto para evitar duplicação.
2. Referência para proficiências: `12_Profiencias_Universais/Everreach_Dataset_Profiencias_Universais_136_v1.json`.
3. O campo `anatomia_aproveitamento_v7` de cada monstro é uma proposta de morfotipo, nunca anatomia instanciada.
4. O campo `protocolo_aproveitamento_v7` de cada saque indica a fonte física, habilidade, dificuldade, ferramenta por capacidade, risco e regra de conservação.
5. A anatomia de cada indivíduo só passa a existir quando a criatura é de fato gerada no mundo, com partes físicas e quantidades reais. O loot não substitui essa instância.
6. Processar partes em transação, com ledger de origem, integridade e partes já consumidas. Evitar obter carne e órgãos integrais de processos mutuamente destrutivos.
7. Uma chance histórica `chance_base_pct` não representa a possibilidade de um animal desenvolver espontaneamente um dente, um chifre ou uma asa. Mantida apenas para compatibilidade e marcada como configuração legada de recuperabilidade a revisar; jamais ignorar física e fonte.
8. O nível de criatura (1–5) não é nível de coleta. O índice de dificuldade não é uma porcentagem de sucesso nem um nível mínimo obrigatório. Um iniciante pode tentar quando há fonte e meios físicos; ferramentas inadequadas continuam inadequadas para um expert.
9. Danos recebidos antes da morte, degradação por tempo contínuo, ambiente, conservação, técnicas e ferramentas alteram qualidade e quantidade. Índices de deterioração por hora são parâmetros abstratos a calibrar e não tempos biológicos absolutos.
10. Humanoides possuem somente saque de equipamentos efetivamente portados; não devem ser submetidos a aproveitamento anatômico automático. Plantas e fungos hostis usam anatomia não animal; entidades espectrais precisam de ancoragem física/mágica confirmada para qualquer resíduo.
11. Ovo, ninho, material solto e equipamentos exigem fonte ambiental/portada distinta e persistente. Nem abate nem Sorte fabricam fontes.
12. Cada espécie só revela suas partes ao jogador por observação e prática. O narrador não promete reagentes/órgãos que o backend não confirmou.
13. Mantivemos o inventário de 810 itens. Se o mundo revelar uma parte nova, o backend pode gerar um item emergente compatível com as propriedades observadas (não previsto neste arquivo) e registrar procedência.

## Distribuição dos morfotipos propostos
| Morfotipo | Registros |
|---|---:|
| mamifero | 224 |
| ave | 54 |
| reptil | 35 |
| serpente | 28 |
| aracnideo | 26 |
| inseto | 23 |
| peixe | 20 |
| crustaceo | 18 |
| humanoide | 15 |
| anfibio | 14 |
| molusco | 11 |
| flora_ou_fungo | 8 |
| constructo | 5 |
| miriapode | 5 |
| fantastico_indefinido | 5 |
| espectral | 4 |
| anelideo | 2 |
| amorfo | 2 |
| restos_animados | 1 |

## Métodos de coleta preexistentes
| Método | Operações |
|---|---:|
| extrair | 452 |
| processar | 348 |
| esfolar | 310 |
| recolher | 194 |
| butchering | 64 |
| coletar | 49 |
| vasculhar | 48 |
| depenar | 17 |
| capturar | 10 |
| filtrar | 3 |
| tosquiar | 3 |
| vasculhar ninho | 2 |

## Auditoria semântica
Existe diferença entre **alerta para confirmação** e **bloqueio manual**. Os alertas não são alterações do cânone. Descrições de loot potencialmente incoerentes precisam ser corrigidas por curadoria antes de virar conteúdo autorizado.

- `EV-M2-04` Cobra-Cobre / `EV-M2-04-D2` Bolsa de veneno: confirmar glandula e composição; atenção a riscos de contaminação
- `EV-M3-11` Centopeia Gume / `EV-M3-11-D2` Veneno diluído: confirmar glandula e composição; atenção a riscos de contaminação
- `EV-M4-13` Víbora de Prata / `EV-M4-13-D2` Bolsa de veneno lunar: confirmar glandula e composição; atenção a riscos de contaminação
- `EV-M5-04` Aranha Viúva-de-Brejo / `EV-M5-04-D2` Glândula de veneno: confirmar glandula e composição; atenção a riscos de contaminação
- `EV-FAU-003` Perdiz de Peito Vermelho / `EV-FAU-003-D3` Ovo de perdiz: exigir ninho, casca, ovo ou deposito realmente instanciado; sem criacao a partir do cadaver
- `EV-FAU-019` Cobra de Barriga Amarela / `EV-FAU-019-D3` Bolsa de veneno intacta: confirmar glandula e composição; atenção a riscos de contaminação
- `EV-FAU-025` Escorpião de Rocha Pequeno / `EV-FAU-025-D3` Vesícula de veneno íntegra: confirmar glandula e composição; atenção a riscos de contaminação
- `EV-FAU-042` Vespa de Mandíbula Longa / `EV-FAU-042-D1` Cera de ninho: exigir ninho, casca, ovo ou deposito realmente instanciado; sem criacao a partir do cadaver
- `EV-FAU-043` Serpente de Pescoço Largo / `EV-FAU-043-D3` Vesícula de veneno íntegra: confirmar glandula e composição; atenção a riscos de contaminação
- `EV-FAU-049` Escorpião de Pinças Dobradas / `EV-FAU-049-D3` Glândula de veneno íntegra: confirmar glandula e composição; atenção a riscos de contaminação
- `EV-TRAD-210` Víbora Marrom / `EV-TRAD-210-D3` Glândula de veneno intacta: confirmar glandula e composição; atenção a riscos de contaminação
- `EV-TRAD-310` Avestruz Selvagem / `EV-TRAD-310-D3` Casca de ovo abandonada: exigir ninho, casca, ovo ou deposito realmente instanciado; sem criacao a partir do cadaver
- `EV-TRAD-315` Cobra Coral / `EV-TRAD-315-D3` Glândula de veneno preservada: confirmar glandula e composição; atenção a riscos de contaminação
- `EV-EXP-M3-50` Raposa de Mandíbula Larga / `EV-EXP-M3-50-D3` Cálamo de falcão da geada: estrutura de pena/asa deve ser observada nesta espécie; item rotulado com outra espécie (falcao): revisão obrigatória

O relatório JSON contém todos os alertas e o status de cada protocolo. Consulte-o antes de importar.

## Testes de integração sugeridos para Codex
- Lobo morto com dano grave na pele: esfolar não produz pele excelente.
- Extração de presas depois de perder a mandíbula: nenhum dente intacto recuperável.
- Tentar usar faca inadequada em carapaça rígida: erro de capacidade, não de nível apenas.
- Ninho sem ovos: nenhuma rolagem concede ovo.
- Chefe goblin sem bolsa real no inventário: nenhuma bolsa aparece após vasculhar.
- Espectro sem ancoragem arcana: captura impossível, independentemente da proficiência.
- Dois personagens extraindo a mesma presa ao mesmo tempo: apenas um resultado vence (transação).
- Proficiência 5 com boas ferramentas pode tentar; proficiência 100 sem fonte real não pode.
- Fragmento encontrado já coletado não reaparece ao reentrar na cena.
- Carne com temperatura elevada e demora deve deteriorar; gelo/conservação ajuda se aplicado no mundo.
- Saque com alerta semântico bloqueado não é autorizado só porque está no JSON.

**Status:** dados propostos e validação estrutural concluída; nenhuma integração/playtest de backend executado.
