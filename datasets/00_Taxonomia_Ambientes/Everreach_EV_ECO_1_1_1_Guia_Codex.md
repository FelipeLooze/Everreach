# Everreach — Guia de integração ambiental EV-ECO-1.1.1 (pacote v20)

## Ponto de entrada único
Importar todos os arquivos do diretório `00_Taxonomia_Ambientes/`. Fontes de dados autoritativas:

- **Taxonomia**: `Everreach_Taxonomia_250_Ambientes_EV_ECO_1_1.json` (100 naturais, 100 construídos, 50 anômalos; os 100 originais sem mudanças).
- **Índice**: `Everreach_EV_ECO_1_1_Indice_250.json`.
- **Regras físicas ativas**: `Everreach_EV_ECO_1_1_1_Regras_Fisicas_250.json`. Não carregar as regras EV-ECO-1.1 anteriores.
- **Testes e validação de contrato**: `test_ev_eco_1_1_1.py`, `Everreach_EV_ECO_1_1_1_Validacao.json` e `Everreach_Validacao_Pacote_v20.json`.

Tudo que estiver em `HISTORICO_TAXONOMIA_NAO_IMPORTAR/` é referência histórica, **não conteúdo adicional**.

## Regras de classificação
1. V4 fornece tectônica e geografia; T1 relevo e altitude; C2 clima; JR1 substratos; W1/W2/P1 evidências hídricas. Esses nomes descrevem contratos propostos: adaptar para os campos reais do backend, não assumir que os JSONs já integram.
2. **Potencial natural** não depende de plantas já instanciadas. A classificação climática/geomorfológica pode resultar em `elegivel`; a confirmação de cobertura vem de vegetação persistida posteriormente. Nunca atribuir prova de vegetação ao P1.
3. Evidência desconhecida deve resultar em `candidato_pendente`, nunca zero/falso/favorável por padrão. Rios, lagos, recifes, geleiras e cavernas exigem confirmação física da fonte correspondente.
4. **Construído** requer instância persistida com tipo e função correspondentes ao `ambiente_id`, além de âncora espacial; uma forja não é biblioteca apenas por existir.
5. **Anômalo** requer autorização canônica específica e fonte/evento correspondentes ao mesmo ID; 50 ambientes mágicos ficam desabilitados por padrão.
6. Ambientes principais coexistem com elementos locais, assentamentos e anomalias; não converter toda cachoeira ou falésia em bioma principal.
7. Nenhum JSON faz spawn de espécies ou fixa biomas por nível do jogador. Populações e vegetação são fases posteriores.

## Limitações
Os parâmetros físicos são calibráveis para um planeta gigantesco, com geração regional progressiva. Os 100 ambientes naturais estão disponíveis como candidatos na Fase 0.9, mas a integração backend V4/T1/C2/JR1/W1/W2/P1 não foi testada. A matriz 6A e os vínculos com espécies ainda requerem curadoria.
