# Swaps e empréstimos privados: três recortes

Busca dirigida em 14/09/2026. [Ler as propostas no site](../index.html#swap-kzg). As seções abaixo registram a pergunta técnica e os critérios para decidir se vale avançar. Não houve implementação, benchmark ou revisão integral das provas de segurança.

Zswap aqui é o protocolo do paper *Zswap: zk-SNARK Based Non-Interactive Multi-Asset Swaps*, PoPETs 2022. “Empréstimo privado” designa a aplicação; não atribuímos as propostas a um paper chamado ZKLoan.

| Candidata | Mudança | Primeiro resultado verificável | Principal incerteza |
|---|---|---|---|
| Ideia 1 | Pertencimento Merkle → KZG/Caulk+ no gasto do Zswap | Prova de gasto completa, com a mesma nota em todas as relações | Composição segura e custo dos vínculos entre provas |
| Ideia 2 | Lista de provas → agregação SnarkPack no lote final | Comparação individual / batch / agregada para provas reais do protocolo | Compatibilidade dos artefatos e novidade além da integração |
| Ideia 3 | Prova para preço exato → certificado por faixa e prazo | Circuito conservador e verificador que invalidam estados antigos | Informação revelada e frequência de renovação |

## Ideia 1 — Pertencimento privado KZG no Zswap

**Base.** [Zswap](https://petsymposium.org/popets/2022/popets-2022-0120.pdf), especialmente a relação de gasto na página 13 e a implementação na página 15 do [PDF local](../papers/zswap-2022.pdf). A construção usa pertencimento Merkle, nullifiers e compromissos de valor/tipo. [Caulk+](https://eprint.iacr.org/2022/957), [PDF local](../accumulators/papers/caulk-plus-2022.pdf), fornece pertencimento com posições ocultas em uma tabela comprometida.

**Hipótese nossa.** Uma composição com lookup privado pode ser vantajosa para certos tamanhos de conjunto e taxas de atualização. É preciso provar que o compromisso aberto no lookup corresponde à nota autorizada pelo circuito de gasto. Manter as definições de privacidade e segurança do Zswap, incluindo os requisitos de extração sob simulação, faz parte do trabalho.

**Experimento.** Dois ativos; começar com 2^10 notas, depois 2^14 e 2^18 se a memória permitir. Controlar o número de entradas e saídas. Medir a prova completa, incluindo vínculos entre componentes, preparação de witnesses, atualização, verificação, memória e comunicação. Comparar contra o Merkle original com o mesmo nível de segurança. Não inferir ganhos de gas a partir do tamanho do witness.

**Decisão de continuidade.** Antes de otimizar, escrever as relações de prova e mostrar por que não permitem trocar a nota entre pertencimento e gasto. Se essa ligação exigir uma composição maior do que o escopo disponível, escolher a ideia 2. [Semacaulk](https://github.com/geometryxyz/semacaulk) já cobre a troca genérica Merkle/KZG para pertencimento privado; a novidade precisa estar na composição ou na análise específica do protocolo.

## Ideia 2 — Agregação das provas do Zswap

**Base.** O [artefato de Zswap](https://github.com/felix-engelmann/zswap-code) tem geração e verificação de provas de gasto e saída, além de junção de transações. [SnarkPack](https://research.protocol.ai/publications/snarkpack-practical-snark-aggregation/), FC 2022, [PDF ePrint local](papers/snarkpack-2021.pdf), agrega Groth16. A seção 3.1 especifica provas com a mesma chave de verificação.

**Hipótese nossa.** Agregar após formar o lote pode reduzir comunicação e verificação acima de um limiar de tamanho, sem alterar a geração independente de provas pelos participantes. Lotes menores podem perder. Uma política de tamanho máximo e prazo de espera poderia ser a variável de pesquisa, com chegadas de transações esparsas e em rajadas.

**Experimento.** Usar provas reais das relações do protocolo. Grupos de 4, 16, 64 e 256 provas por chave de verificação. Comparar verificação individual, batch verification e SnarkPack. Medir geração original, agregação, processamento de entradas públicas, tamanho total, tempo de verificação e latência para fechar o lote. Não chamar de logarítmico o custo total de ler dados públicos que permanecem lineares.

**Integração a verificar.** Arkworks no Zswap e [Bellperson](https://github.com/filecoin-project/bellperson) não implicam formatos intercambiáveis. Conferir curva, codificação, ordem de entradas e parâmetros. SnarkPack usa dois transcripts Powers of Tau para seus parâmetros. Guardar as provas originais até finalizar o lote; re-agregação direta de agregados não é pressuposta.

**Segurança e contribuição.** Fixar o vínculo entre prova e statement, a separação por chave, a ordenação canônica e a rejeição de gasto duplo. Agregação não substitui checagens de saldo por ativo. Definir como as propriedades da prova original são preservadas pelo uso do agregado. A integração funcional é o primeiro marco; um resultado de pesquisa ainda depende de uma questão que não tenha sido respondida por agregação e batching já publicados.

## Ideia 3 — Certificado conservador de garantia

**Trabalho relacionado.** [Zyga](https://eprint.iacr.org/2025/1802), preprint, revisão de 22/12/2025, [PDF local](papers/zyga-2025.pdf), propõe provas com entradas públicas dinâmicas. A seção 8.2, páginas 24–25, já descreve empréstimos com preços públicos variáveis. Não apresentamos essa aplicação geral como nova. Não foi localizado e executado um artefato para comparação direta nesta busca.

**Hipótese nossa.** Um circuito convencional pode certificar antecipadamente uma condição suficiente de saúde para uma faixa de preços e prazo. A pesquisa seria caracterizar o compromisso entre custo de provar, condições conservadoras e informação revelada. Essa hipótese não foi identificada como open problem explícito no paper e exige busca adicional de anterioridade.

**Modelo mínimo.** Uma posição com garantia não negativa C, dívida D, razão de garantia r e crescimento máximo da dívida conhecido até t_max. Provar em ZK, sobre inteiros escalados e limitados:

```text
C × p_min ≥ r × D_max(t_max)
```

Também provar o vínculo de C e D com o estado autorizado e a garantia bloqueada. A faixa [p_min, p_max], o prazo, a política e a versão da posição são públicos e vinculados ao certificado. O contrato aceita a checagem apenas com preço recente dentro da faixa, prazo válido e versão ainda vigente. Para uma garantia única com C ≥ 0, p_min é o extremo necessário à desigualdade; p_max limita a política de reutilização, não fortalece essa condição de solvência.

O certificado é de saúde de uma posição, não uma autorização repetível de desembolso. Novos empréstimos e alterações de saldo mudam a versão. A política de aceitação precisa distinguir a atualização global de uma árvore da alteração efetiva dessa posição, para não invalidar todas as provas por operações de terceiros.

**Experimento.** Reproduzir séries sintéticas de preços com semente fixa, incluindo quedas bruscas e períodos estáveis. Comparar nova prova por preço com faixas comuns e personalizadas, para vários prazos. Contar provas geradas, custo total, reutilização, rejeições conservadoras e divulgação de limites sobre C/D. Incluir observação de múltiplas renovações. Definir arredondamento conservador e casos de fronteira para os inteiros.

**Limite.** O primeiro modelo admite uma posição pública pseudônima e valores privados; verificações do mesmo certificado são correlacionáveis. Liquidar posições privadas sem cooperação do tomador é outra questão. A redução de provas não demonstra que o protocolo completo de empréstimo esteja resolvido.

## Leituras complementares de empréstimo

- [ZeroLender](https://scholarworks.boisestate.edu/cs_facpubs/265/), CODASPY 2020, estuda empréstimos Bitcoin com ZK e desvinculação de credores e tomadores. Leitura apenas do resumo institucional; sem PDF local ou análise integral.
- [ALOE](https://scholarworks.sjsu.edu/faculty_rsca/5019/), SVCC 2023, [PDF dos autores](papers/aloe-2023.pdf), [código](https://github.com/taustin/cryptoCreditBureau/), aborda identidade e score de crédito em Ethereum. Foram lidos resumo, introdução, modelo e trabalhos futuros. A origem de dados e o acompanhamento das dívidas continuam essenciais em qualquer adaptação com ZK.

Busca e versões: [sources.json](sources.json). Os arquivos de texto ao lado dos PDFs são extrações para busca; as páginas citadas se referem aos PDFs. Nenhuma ausência em resultados de busca foi tratada como prova de novidade.
