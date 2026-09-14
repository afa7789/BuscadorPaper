# Registro da busca — 13/09/2026

Busca web dirigida, seguida de abertura de fontes primárias e leitura de trechos dos PDFs. Não é uma revisão sistemática nem um censo bibliográfico. Resultados de buscadores foram usados para descoberta; a fundamentação da seleção usa papers, documentação oficial e repositórios de autores. Notícias, agregadores e resumos automáticos não fundamentam as propostas.

## Consultas principais e decisões

| Família | Exemplos de consultas executadas | Consequência |
|---|---|---|
| Revogação | `"zk-creds" "revocation"`; `"anonymous credentials" "revocation" "2025"`; `"SNARK" "revocation" "2026" credentials` | Encontrados zk-creds, PRC e trabalhos recentes; revogação genérica descartada como novidade |
| Recuperação privada de witnesses | `cryptographic accumulators private delegation 2026 witness updates`; `"private" "Merkle" "PIR" witness update` | Encontrados ePrint 2026/832, TreePIR, Scaling Semaphore e implementação Zcash; combinação genérica Merkle+PIR não selecionada |
| Revogação autenticada | `"TAPIR" "Authenticated" "PIR"`; leitura de §4.1 e §5.3 do PRC | R2 formulada a partir da limitação contra corrupção ativa; composição com APIR permanece hipótese |
| Carteiras e mensagens | `"oblivious message" "2025" "2026"`; `"InstantOMR"`; `"Oblivious Signaling" paper`; `"UnifOMR"` | R3 passou a focar recuperação do histórico após overflow; UnifOMR acrescentado como baseline recente |
| Matching privado | `"Zswap" "zk-SNARK" matching future`; `"Indifferential Privacy" dark pool code`; `"Renegade" dark pool whitepaper MPC` | R4 delimitada à privacidade relaxada de volumes; descartada a alegação de que matching MPC+ZK seria novo |
| Delegação de provas | `"zkSaaS" private delegation proving 2025 2026` | Encontrados DFS, Siniel, coZK e trabalhos próximos; sem recorte suficientemente sustentado para a seleção principal |
| Provas de exploit | `"zkpoex" paper multi transaction limitations`; título exato do artigo; `"zero-knowledge proofs of exploits" recursive`; `"proof" "exploit" "multi-transaction" "zero"` | R1 formulada; distinguidos o código dos autores, outro projeto homônimo e a dissertação; pesquisa não estabelece ausência de solução equivalente |
| Segurança de circuitos | `"SNARK" vulnerabilities "smart contract" 2025 2026`; `"Circuzz" "SnarkProbe" "zkFuzz"`; título exato de Circuzz; `"zk" "circuit" "stateful" testing` | R5 delimitada à interface com contrato e estado, com alerta sobre trabalhos de context-binding |
| Reputação | `"zk-promises" anonymous credentials`; `"zk-promises" "private record certification"` | Paper lido para evitar reapresentar callbacks, bloqueio ou batching como inéditos; não selecionado como proposta principal |

Consultas compostas ou muito específicas retornaram, por vezes, resultados irrelevantes. Ausência de resultado útil não foi interpretada como prova de novidade. Também houve triagem inicial de light clients, shuffle, prova de passivos e zkTLS; sem um recorte melhor sustentado que os cinco escolhidos nesta rodada.

## Conferências relevantes

- PRC: limitação contra autoridades ativamente maliciosas conferida na página 8 do PDF; não confundida com sua propriedade de privacidade.
- Oblivious Signaling: FIFO com capacidade limitada, exclusões do modelo e comparação OMR conferidas na página 15 do PDF.
- Circuzz: passagem sobre ampliar oráculos de verificação encontrada na página 8 da cópia arXiv.
- Zswap: matching concreto deixado em aberto em §1.3, página 4 do PDF de PoPETs.
- Indifferential Privacy: adversário semi-honesto e informação pública/privada conferidos em §2, página 3 do PDF AAMAS.
- zkpoex: a limitação explícita de várias transações no README pertence a `zkoranges/zkPoEX`, distinto de `ziemen4/zkpoex`. A dissertação do autor descreve um trace EVM e propõe formalizar condições na página 96.
- TAPIR: ePrint registra ACNS 2026; README menciona ACNS'25. Registrada a divergência em vez de copiar o ano do código.
- UnifOMR: incluído após encontrar trabalho mais recente; a consulta a resumo/metadados não foi descrita como leitura integral.

## Limites e próximos testes de novidade

1. R1: obter a versão final SAC do artigo; comparar provas sequenciais com ferramentas atuais e com execução única segmentada pela zkVM. O download ACM respondeu HTTP 403; foi usada cópia pública da dissertação do autor, em URL fixada por commit.
2. R2: revisar ALLOSAUR e outras construções de revogação citadas pelo PRC; definir a autenticidade da raiz e a ameaça de conluio cliente-servidor. APIR verificado apenas pelo cliente não fecha esse problema.
3. R3: revisar implementações atuais de UnifOMR e alternativas de histórico/inbox; calcular custo completo de manter duas formas de recuperação e avaliar vazamento por retries.
4. R4: verificar composição das garantias de IDP com liquidação e definir se o operador segue sendo semi-honesto. Não equiparar essa garantia à do matching via MPC.
5. R5: verificar versões atuais de Circuzz, SNARKProbe e zkFuzz, e ler integralmente o preprint de context-binding. Delimitar o que uma análise conjunta detecta além das ferramentas existentes.

O pacote registra hipóteses para escolha e leitura. Não afirma ganhos de desempenho, descoberta de vulnerabilidades novas, prova formal concluída ou lacuna global confirmada.
