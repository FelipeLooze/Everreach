# Everreach — Proficiências Universais (v1)

## Filosofia
O mundo é governado por regras, não por uma lista fechada de ações. Personagens e NPCs aprendem competências com prática relevante, independentemente de ocupação e nível geral. O dataset fornece referências, nunca executa ações nem concede itens.

## Conteúdo
- **17 domínios**, **136 proficiências**, **408 especializações opcionais**, **272 exemplos de atividades**.
- Proficiências e dificuldade em **0–100**, com faixas **descritivas e não bloqueantes**.
- Especializações são focos de aplicação e não habilidades automaticamente desbloqueadas.
- Nenhuma atividade cadastrada é receita obrigatória. Ações inéditas são permitidas se respeitarem os materiais, processos, fontes, riscos e capacidades reais.

## Regra de interoperabilidade
- Dataset **14 v4**: `mineracao` → `EV-PROF-MIN-001`; `prospeccao` → `EV-PROF-MIN-002`.
- Bestiário: `esfolar` → `EV-PROF-FAU-005`; `butchering` → `EV-PROF-FAU-006` (desossa); órgãos/glândulas especiais → `EV-PROF-FAU-007`.
- Flora: `colher_flores`/`colher_folhas` → `EV-PROF-BOT-002`; `colher_raiz` → `EV-PROF-BOT-003`.
- Dataset **6B**: papéis sociais são **contexto**, não substitutos de habilidade. Os IDs existentes usados em links foram verificados.
- Dataset **15 futuro**: processos referenciam IDs de proficiência e dificuldades específicas; Dataset **16 futuro**: ferramentas descrevem capacidades reais.

## Extração, coleta e fabricação
A dificuldade pertence sobretudo **à ação sobre um alvo específico**. A existência do objeto, o acesso, a ferramenta, o estado do alvo, o ambiente e o risco vêm antes da proficiência. Um fragmento de adamantita já solto pode ser fácil de recolher, mas raro de encontrar e impossível de gerar sem fonte/evento persistente.

Para carcaças, pele, ossos, dentes e glândulas exigem técnicas distintas. Nem todas as espécies possuem todas as partes. O bestiário atual ainda tem chances de saque legadas: reconciliar com anatomia, disponibilidade e qualidade antes de ativar um sistema autoritativo de aproveitamento de carcaças.

## Progressão e antifarm
1. Registrar prática verdadeira com ação, ator, alvo, instante do mundo e proveniência.
2. Um evento mecânico idempotente, sem recompensa por repetir uma ação trivial ou botão.
3. Dar relevância à variedade, complexidade e aprendizado com falhas informativas.
4. XP/hora e ganhos numéricos definitivos são definidos pelo backend, não automaticamente por este JSON.
5. NPCs devem ter história, rotina e evidência de treino para ganhar níveis; nenhum nível é concedido por ocupar o papel “ferreiro”.

## Escopo e ressalvas
- Estudo arcano **não concede** feitiços, energia ou cura divina.
- Combate continua sujeito ao módulo de combate do Everreach; atributos de proficiência são candidatos à integração, não estatísticas de dano automaticamente aplicadas.
- Atenção ao mundo vivo, à agência do jogador e à persistência das fontes materiais.
- Arquivo de conteúdo proposto; **não testado no backend**. Testes de estrutura e referências passaram.

## Referência rápida
```json
{
  "proficiência_id": "EV-PROF-FAU-005",
  "atividade": "esfolar_carcaca",
  "fonte": "cadaver_persistido_id",
  "ferramenta": "instancia_real_com_capacidade",
  "dificuldade_base": 50,
  "modificadores": "estado_carcaca, anatomia, ambiente, ferramenta, riscos",
  "resultado": "somente_backend"
}
```
O exemplo não é chamada de API nem fórmula completa.
