# Método da avaliação

Referência institucional: PPGCC/DCC/UFMG. Consulta em 14/09/2026. O usuário pediu um ranking das seis ideias de pesquisa, com peer-review, em escala de 0 a 10.

## O que a nota representa

Nota de mérito da formulação atual como ponto de partida para um pré-projeto de mestrado. Não é probabilidade de ingresso, previsão da nota de uma banca nem compromisso de orientação. As descrições não são submissões completas. Não recebem nota zero por estarem em HTML ou por ainda não seguirem a formatação de inscrição.

Usamos como referência o [edital regular PPGCC 2026](https://ppgcc.dcc.ufmg.br/wp-content/uploads/2025/10/Edital-Regular_Ciencia-da-Computacao_MD_2026.pdf), Anexo V: problema/objetivos/aderência (35%), originalidade/coerência (35%) e viabilidade/metodologia (30%). Cada eixo recebe 0 a 10. A fórmula por avaliador é `0,35 × R + 0,35 × O + 0,30 × E`.

No mesmo edital, o pré-projeto tem mínimo de 70/100 na primeira etapa e peso de 20% na nota final de ingresso; formação e currículo completam a avaliação. As notas do painel não equivalem à avaliação oficial. A [página de editais](https://ppgcc.dcc.ufmg.br/editais/) consultada apresentava a seleção de 2026; as regras de uma futura seleção precisam ser conferidas quando publicadas.

## Painel e revisão cruzada

Seis agentes de IA recebem o mesmo artefato original completo, a mesma rubrica e personas com focos distintos. O sorteio das personas usa itens pertinentes dos pools da skill peer-review, sem repetição, com semente registrada em `panel.json`. São perspectivas de análise, não professores reais ou pareceristas vinculados à UFMG.

Cada agente pontua as seis ideias originais antes de propor melhorias. Em seguida, seis revisores em novos contextos recebem as cinco reescritas dos demais, com identificadores embaralhados. Cada reescrita recebe cinco críticas; nenhuma persona revisa a própria versão. A execução ocorre em grupos de até três agentes simultâneos devido ao limite de concorrência da sessão.

O ranking das ideias usa a média aritmética das seis notas ponderadas originais. A amplitude entre a menor e a maior nota mostra desacordo interno; não é intervalo de confiança estatístico. As revisões não são amostras independentes de bancas reais e compartilham modelo, fontes e rubrica.

A qualidade das reescritas é avaliada separadamente em clareza, solidez, consistência, estrutura e originalidade. Essa segunda matriz serve à síntese textual, não estima aprovação das ideias. Seus pesos são 15%, 35%, 25%, 10% e 15%, respectivamente, escolhidos para este painel e não atribuídos à UFMG. Médias e variâncias são calculadas por script.

## Limites e controles

- A [lista de docentes](https://ppgcc.dcc.ufmg.br/docentes/) e as [linhas do programa](https://ppgcc.dcc.ufmg.br/linhas-de-pesquisa/) permitem discutir aderência em criptografia, cibersegurança, sistemas e métodos formais. Não demonstram disponibilidade de vagas ou interesse de um professor por uma proposta específica.
- O currículo, a preparação matemática, a disponibilidade semanal e o orientador do usuário não foram fornecidos. Viabilidade é julgada pelo escopo descrito, sem presumir incapacidade pessoal. O horizonte de 24 meses é uma hipótese de planejamento do painel.
- Limitações dos papers são separadas das combinações sugeridas nesta pesquisa. Uma sugestão de trabalho futuro é evidência de direção aberta naquele texto, não prova de novidade de qualquer solução posterior.
- Resultados negativos podem sustentar uma contribuição quando respondem uma pergunta relevante com método e comparações adequados. Não exigimos melhoria de desempenho garantida nem uma nova primitiva para todo mestrado.
- Melhorias nas reescritas não aumentam retroativamente as notas das versões originais. Recomendações finais explicam eventuais diferenças entre a maior média e a escolha prática para o usuário.

Artefatos: `original.html` preserva a página avaliada; `analyses/` contém os seis pareceres e notas; `cross-reviews/` contém a crítica cruzada. O relatório consolidado registra os resultados e as divergências resolvidas.
