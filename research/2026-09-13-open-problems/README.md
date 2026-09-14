# Candidatos de pesquisa em criptografia, ZK e Web3

Busca realizada em 13/09/2026. Objetivo: partir de trabalhos existentes e propor uma alteração delimitada, implementável e avaliável em um mestrado.

## Página para leitura

A [página HTML](index.html), atualizada em 14/09/2026, reúne seis propostas: três novas candidatas sobre swaps e empréstimos, atualização privada de witnesses KZG, revogação privada de credenciais (ideia 5) e recuperação de pagamentos após períodos offline (ideia 6). Usa HTML estático, seis regras de CSS e nenhum JavaScript. As cinco ideias da primeira busca ficaram no [histórico](history.html).

Após a seleção das ideias 2 e 3, foi acrescentado um [recorte sobre acumuladores e compromissos KZG](accumulators/index.html), com quatro PDFs adicionais. O ponto de partida é a extensão para VC/PCS indicada nos trabalhos futuros do ePrint 2026/832; a aplicação sugerida a Caulk+/Semacaulk continua uma hipótese de pesquisa. A página também distingue trocas já existentes de questões ainda não resolvidas nos protocolos consultados.

As [novas propostas de DeFi](defi/README.md) estão diretamente na página principal: a ideia 1 combina Zswap com pertencimento privado KZG/Caulk+; a ideia 2 combina Zswap com SnarkPack; a ideia 3 investiga certificados de garantia por faixa de preços, tendo Zyga como trabalho relacionado. Foram acrescentados três PDFs: SnarkPack, Zyga e ALOE, este último como leitura complementar. As fontes e os limites da leitura estão em [defi/sources.json](defi/sources.json). Nenhuma das três combinações está confirmada como inédita; a ideia 3 não deve ser apresentada como a primeira reutilização de provas para empréstimos com preços dinâmicos.

Para iniciar o servidor, execute nesta pasta:

```sh
bunx http-server . -a 0.0.0.0 -p 8765 -c-1
```

Acesse `http://localhost:8765` na própria máquina, ou `http://IP-LOCAL:8765` em outro dispositivo na mesma rede. O IP encontrado em 13/09/2026 foi `192.168.0.7`; ele pode mudar ao reconectar à rede. A máquina e o servidor precisam continuar ligados. O script `sh serve.sh` executa o mesmo comando; para usar outra porta: `sh serve.sh 8766`. Para parar: `Ctrl+C` no terminal do servidor.

**Resultado da busca inicial: cinco candidatos para investigar.** As limitações atribuídas aos autores foram conferidas em fontes primárias. As combinações e perguntas abaixo são propostas desta busca, não resultados demonstrados. Nenhuma delas está certificada como inédita. Encontrar uma limitação em um paper não demonstra que trabalhos posteriores não a resolveram.

Foram consultados papers, documentação oficial e repositórios dos autores. A leitura concentrou-se em construção, modelo de adversário, avaliação e limitações relevantes; não foi uma revisão integral de todas as provas de segurança. Os protótipos não foram compilados nem seus benchmarks reproduzidos. Há onze PDFs locais, com textos extraídos e inventário em [sources.json](sources.json).

## Seleção inicial — histórico da busca

A página principal usa numeração contínua de 1 a 6. As antigas R2 e R3 correspondem hoje às ideias 5 e 6; a atualização privada de witnesses KZG é a ideia 4. As ideias 1, 2 e 3 foram acrescentadas como candidatas para avaliação. A tabela e as seções R1–R5 abaixo documentam o levantamento inicial; R1, R4 e R5 saíram da página principal.

| ID | Pergunta curta | Alteração proposta | Principal dificuldade | Prioridade de leitura |
|---|---|---|---|---|
| R1 | Como provar uma falha que exige várias transações sem revelar a sequência? | zkpoex + composição de provas + compromissos de estado | Definir execução admissível e evitar estados intermediários inventados | Alta para Solidity/Rust/ZK |
| R2 | Como consultar revogação privadamente sem aceitar um certificado falso de um servidor comprometido? | PRC + recuperação autenticada + prova vinculada a uma versão pública da base | Compatibilizar autenticidade, privacidade e custo | Alta para criptografia de protocolos |
| R3 | Como uma carteira offline recupera pagamentos antigos sem expor quais são seus? | Caixa recente de Oblivious Signaling + histórico recuperado por OMR | Privacidade do mecanismo de recuperação e custo de manter as duas camadas | Média; exige FHE/PIR |
| R4 | Quanto custa relaxar a privacidade de volumes para fazer matching privado verificável? | Zswap + indifferential privacy + verificação da liquidação | Modelos de privacidade diferentes e composição de protocolos | Exploratória; maior risco |
| R5 | Como detectar falhas entre um circuito ZK correto e o contrato que o utiliza? | Testes metamórficos de ZK + testes de sequências de transações | Criar um oráculo de teste geral e um conjunto de avaliação independente | Alta para pesquisa em ferramentas |

As prioridades são julgamento de adequação, não notas bibliométricas ou probabilidades de publicação. R1 e R5 aproveitam experiência em contratos e testes; R2 exige mais trabalho em definições de segurança. R3 e R4 envolvem integrações mais incertas.

## R1 — Provas privadas de falhas em sequências de transações

**Paper de partida.** *A Framework for Zero-Knowledge Proofs of Exploits in Solidity Smart Contracts*, Cavaliere et al., [DOI](https://doi.org/10.1145/3748522.3779811), associado ao [zkpoex dos autores](https://github.com/ziemen4/zkpoex). A implementação demonstra uma violação de uma especificação sem expor o calldata. O PDF da ACM respondeu HTTP 403 nesta busca; a leitura disponível localmente é a [dissertação do autor](papers/zkpoex-author-thesis.pdf), especialmente os capítulos 2–3 e a conclusão na página 96 do PDF. Ela descreve a execução de um trace EVM e propõe formalizar o mecanismo de condições. Isso não substitui a conferência do texto final do artigo.

**Trabalho próximo.** Um [outro projeto, zkoranges/zkPoEX](https://github.com/zkoranges/zkPoEX), explicita que não cobre nativamente falhas com várias transações ou blocos. Não é o mesmo repositório do paper. Já existe [composição de provas no RISC Zero](https://dev.risczero.com/api/zkvm/composition); desenvolver recursão genérica não seria contribuição nova.

**Combinação proposta.** Adaptar a prova de violação para uma sequência limitada de transições, ligando o compromisso do estado final de cada etapa ao estado inicial da seguinte. Comparar uma execução única contendo a sequência inteira com provas compostas por transação.

**Pergunta de pesquisa.** Para sequências de 2–16 transações, é possível provar uma violação a partir de um estado inicial autenticado, mantendo secretas as chamadas e reduzindo memória ou custo de reprovar sequências com prefixos comuns?

**O que precisa ser definido.** O provador só pode usar endereços que controla, recursos e permissões admitidos pelo modelo. Não pode inventar saldo, trocar bytecode ou alterar o estado entre etapas. A especificação precisa distinguir uma execução contrafactual possível de uma sequência que realmente ocorreu na blockchain. Uma prova de existência da primeira não comprova a segunda.

**Experimento mínimo proposto.** Usar contratos pequenos com falhas conhecidas e respectivas versões corrigidas, em ambiente local. Comparar sequências de comprimentos 1, 2, 4, 8 e 16; medir tempo total, memória de pico, tamanho da prova e custo de reaproveitar prefixos. Verificar o mesmo resultado em uma execução de referência. Incluir casos que tentem trocar o estado intermediário, reutilizar uma prova de outro contrato ou atribuir ao provador permissões inexistentes.

**Contribuição pretendida.** Uma definição precisa da prova de violação sequencial, uma construção que preserve os vínculos entre etapas e a caracterização de quando a composição compensa. Apenas chamar a API de recursão não basta. A zkVM já segmenta execuções longas, portanto não há ganho de memória ou tempo garantido por fragmentar em transações.

**Critério para abandonar ou reformular.** Se a execução única já tiver o mesmo comportamento e custo, sem vantagem de reutilização nem diferença de segurança, o recorte perde força. Antes de escolhê-lo, conferir o artigo final e outras ferramentas de provas de exploit. Viabilidade inicial: média, dependente do custo real do prover; começar com poucos contratos, sem uma zkEVM própria.

## R2 — Revogação privada com autenticidade contra servidor malicioso

**Paper de partida.** *Do You Need a Receipt? Anonymous Credential Revocation at Continental Scale via Private Record Certification*, EdalatNejad et al., USENIX Security 2026. [Página oficial](https://www.usenix.org/conference/usenixsecurity26/presentation/edalatnejad) · [PDF local](papers/prc-revocation-2026.pdf).

O trabalho combina PIR e MPC para certificar privadamente um registro. A limitação relevante está em §4.1, página 8 do PDF: o modelo não garante não falsificabilidade dos tokens contra autoridades de revogação ativamente maliciosas. A discussão de §5.3 deixa claro que assinatura threshold não elimina, sozinha, esse problema. É uma escolha declarada de eficiência e confiança, não um ataque novo descoberto nesta busca.

**Técnica a combinar.** [TAPIR](https://eprint.iacr.org/2025/2177), Falzon, Hetz e O'Toole: recuperação privada autenticada com dois servidores, pré-processamento e atualizações. [PDF local](papers/tapir-2025.pdf) · [código em Go/C++](https://github.com/laurahetz/TAPIR). O ePrint registra ACNS 2026; a menção a ACNS'25 no README está divergente.

**Pergunta de pesquisa.** Quanto custa vincular uma prova privada de não revogação a uma versão autenticada da base, de modo que um servidor comprometido não consiga fazer aceitar um registro falso ou antigo?

**Construção candidata.** Consultar o registro por APIR e demonstrar, em ZK, que o índice privado corresponde à credencial e que o registro válido pertence ao compromisso público aceito para aquela época. A blockchain pode ancorar esse compromisso. A composição concreta entre o resultado autenticado e o token precisa ser desenhada; não é suficiente substituir uma chamada de biblioteca.

**Ponto técnico decisivo.** APIR pode permitir a um cliente honesto detectar uma resposta errada. Isso não impede um cliente malicioso de ignorar a verificação e apresentar um certificado obtido em conluio. O vínculo com a base precisa ser verificável pelo destinatário da prova. A origem autorizada da raiz e a política de atualização permanecem pressupostos explícitos; uma raiz legítima contendo informação falsa não se torna verdadeira por usar ZK.

**Experimento mínimo proposto.** Dois servidores, uma única credencial sintética com estado ativo/revogado, uma raiz por época e tamanhos iniciais de 2^12–2^20 registros, conforme memória disponível. Comparar PRC original, consulta autenticada seguida de prova e uma solução direta de Merkle + ZK. Medir tempo do cliente e servidores, comunicação online, pré-processamento, custo por atualização e atraso máximo de revogação. Testar alteração de registro, resposta de época anterior e falha seletiva.

**Contribuição pretendida.** Uma composição com garantias explícitas contra corrupção ativa e uma fronteira de custo sob atualizações. PRC e APIR isoladamente já existem. A simplicidade de Merkle + ZK é um baseline obrigatório: se ela resolver o mesmo problema com custo comparável, a combinação precisa de outra justificativa.

**Risco de novidade e viabilidade.** Médio a alto. Há uma literatura extensa de revogação com acumuladores; o próprio PRC compara alternativas, incluindo ALLOSAUR. Será necessário revisar essas construções sob o mesmo modelo de adversário antes de reivindicar novidade. A prova completa de composição pode exceder um mestrado se o escopo crescer; limitar a dois servidores e uma política binária.

## R3 — Carteira privada com caixa recente e recuperação do histórico

**Papers de partida.** [*Oblivious Signaling*](https://www.usenix.org/conference/usenixsecurity26/presentation/shuhan), Shuhan, Baldimtsi e Ateniese, e [*InstantOMR*](https://www.usenix.org/conference/usenixsecurity26/presentation/liang), Liang et al.; ambos na USENIX Security 2026. PDFs: [Oblivious Signaling](papers/oblivious-signaling-2026.pdf) e [InstantOMR](papers/instant-omr-2026.pdf).

Oblivious Signaling move trabalho para a entrega e permite ler uma caixa de tamanho fixo. A limitação em §7, página 15 do PDF, é concreta: mensagens antigas saem da caixa quando sua capacidade é ultrapassada. OMR permite recuperar mensagens de uma base sem revelar a correspondência entre mensagem e destinatário. Essa recuperação é relevante para pagamentos recebidos por carteiras privadas.

**Atualização bibliográfica necessária.** [*UnifOMR*](https://eprint.iacr.org/2026/910), Fisch et al., também deve entrar na comparação. A versão consultada registra ACM CCS 2026 e apresenta outro compromisso entre interação, comunicação e computação. [PDF local](papers/unif-omr-2026.pdf). Não usar apenas SophOMR como referência de eficiência.

**Combinação proposta.** Uma camada de caixa recente para consultas frequentes e outra de histórico persistente para recuperação privada após longos períodos offline. Essa arquitetura é uma hipótese nossa. A existência dos dois componentes não demonstra que sua combinação seja eficiente ou inédita.

**Pergunta de pesquisa.** Essa composição consegue manter baixo custo de consultas frequentes e recuperar todas as notificações de pagamento após períodos offline, com menor custo total que usar somente OMR, sem introduzir vazamento adicional pelo acionamento da recuperação?

**Experimento mínimo proposto.** Uma única rede de pagamentos sintéticos, mensagens de tamanho fixo e períodos offline de diferentes durações. Comparar OMR isolado, caixa isolada e a composição. Medir tempo até recuperar a última notificação pendente, bytes, CPU por usuário e custo adicional na criação das mensagens. Contabilizar as duas camadas, inclusive chaves, pistas criptográficas e armazenamento: não tratar a camada de histórico como gratuita.

**Questões de segurança.** A decisão de consultar o histórico pode revelar acúmulo de pagamentos. Investigar consultas em épocas públicas e padding; medir seu custo. A prova de privacidade precisa abranger as observações combinadas dos dois serviços. A recuperação de notificações tampouco demonstra, por si, inclusão canônica, saldo gastável ou disponibilidade contra um servidor que apaga tudo.

**Contribuição pretendida.** Uma política de recuperação com modelo de vazamento e uma avaliação de ponta a ponta. A comparação estática entre OMR e signaling já aparece no paper; não basta repetir sua tabela. O diferencial seria recuperação completa do histórico e análise da composição ao longo do tempo.

**Critério para abandonar ou reformular.** Se a manutenção dupla custar mais que OMR em todos os regimes úteis, ou se privacidade exigir padding que elimine o ganho, registrar esse resultado e reavaliar. Viabilidade: média a difícil, por envolver FHE; usar os [artefatos de OSig](https://doi.org/10.5281/zenodo.20437084) e o [código de InstantOMR](https://github.com/xiangxiecrypto/tfhe-omr), sem desenvolver FHE próprio.

## R4 — Matching com privacidade de volumes relaxada e liquidação verificável

**Paper de partida.** *Zswap: zk-SNARK Based Non-Interactive Multi-Asset Swaps*, Engelmann et al., PoPETs 2022. [Paper](https://petsymposium.org/popets/2022/popets-2022-0120.pdf) · [PDF local](papers/zswap-2022.pdf) · [código](https://github.com/felix-engelmann/zswap-code). Em §1.3, página 4 do PDF, os autores deixam o algoritmo concreto de matching de ofertas fora da construção.

**Ideia a combinar.** *Indifferential Privacy: A New Paradigm and Its Applications to Optimal Matching in Dark Pool Auctions*, Polychroniadou, Chan e Agrawal, AAMAS 2025. [Paper](https://www.ifaamas.org/Proceedings/aamas2025/pdfs/p1670.pdf) · [PDF local](papers/idp-darkpools-2025.pdf) · [código](https://github.com/adya-agrawal/idp-darkpool). O modelo em §2 protege volumes de forma que admite revelação após determinadas condições de execução; assume operador semi-honesto. Não oferece a mesma garantia que ocultar integralmente todas as informações de uma ordem.

**Pergunta de pesquisa.** Em um único par de ativos, qual é o custo de combinar esse modelo de privacidade com liquidação criptograficamente verificável, comparado com matching via MPC?

**Mudança candidata.** Começar com preços públicos e quantidades discretas. Ligar as ofertas aceitas, o resultado do matching e a liquidação a compromissos comuns, para impedir que o operador liquide quantidades diferentes das autorizadas. Especificar o que cada participante aprende antes e depois da execução.

**Experimento mínimo proposto.** Um par de tokens sintéticos, uma política de matching, lotes de 16–256 ordens. Medir volume executado, tempo, comunicação, custo da prova e orçamento de privacidade. Comparar o matching público, a implementação de indifferential privacy e uma implementação restrita com MPC. Os três modelos devem ter suas diferenças de segurança explicitadas antes da comparação de desempenho.

**Trabalho que impede uma alegação ampla de novidade.** [Renegade](https://whitepaper.renegade.fi/) já combina matching via MPC e liquidação com ZK; o [repositório oficial](https://github.com/renegade-fi/renegade) detalha a visibilidade dos relayers. Portanto, “matching privado + ZK” já existe. O recorte seria a escolha explícita de uma garantia de privacidade de volumes mais fraca e seu custo numa liquidação verificável.

**Risco principal.** Adicionar uma prova de liquidação não transforma automaticamente um protocolo semi-honesto em seguro contra um operador ativo. O operador pode explorar o processo de matching, o agendamento ou as mensagens intermediárias. A preservação da garantia de indifferential privacy nessa composição precisa ser demonstrada. Esta é a opção mais exploratória; não construir uma DEX inteira antes de resolver essa questão.

## R5 — Testes de segurança na ligação entre circuito, prova e contrato

**Papers de partida.** [*Fuzzing Processing Pipelines for Zero-Knowledge Circuits*](https://arxiv.org/abs/2411.02077), Hochrainer et al., publicado no CCS 2025, e [*SoK: What Don't We Know? Understanding Security Vulnerabilities in SNARKs*](https://www.usenix.org/system/files/usenixsecurity24-chaliasos.pdf), Chaliasos et al., USENIX Security 2024. PDFs: [Circuzz](papers/circuzz-2025.pdf) e [SoK](papers/snark-security-sok-2024.pdf).

Circuzz usa testes metamórficos nas etapas do processamento de circuitos. Na versão arXiv consultada, §3.6, página 8 do PDF, ampliar os testes da verificação com transformações destrutivas é trabalho futuro. O SoK oferece uma taxonomia de falhas que ajuda a selecionar classes de erro. Isso sustenta a investigação, mas não comprova ausência de ferramentas posteriores.

**Combinação proposta.** Usar as transformações e a geração de casos de uma ferramenta como [Circuzz](https://github.com/Rigorous-Software-Engineering/circuzz) junto a um executor de sequências de transações. O alvo delimitado seria a interface entre um circuito Circom/Groth16 e contratos EVM que administram nullifiers, roots e autorização.

**Pergunta de pesquisa.** Testes que acompanham circuito, entradas públicas e estado do contrato encontram falhas de integração que ferramentas isoladas de circuitos e contratos deixam passar, sob o mesmo orçamento de execução?

**Casos propostos.** Tentar reutilizar uma prova após o gasto de seu nullifier, trocar o contexto do contrato, apresentar uma raiz fora da política de validade ou explorar representações diferentes de um inteiro entre o campo do circuito e a ABI. Nem toda transformação deve invalidar uma prova: a expectativa precisa derivar da especificação da aplicação e do sistema de prova, evitando falsos positivos por maleabilidade legítima.

**Experimento mínimo proposto.** Três famílias pequenas — membership, votação e saque — com versões vulneráveis e corrigidas. Reproduzir bugs públicos e manter casos independentes dos usados para desenvolver o detector. Comparar contra testes de contrato isolados e análise de circuito isolada; medir detecção por classe, falsos positivos, tempo até encontrar a falha e custo de geração de provas. Mocks podem acelerar a exploração, mas cada achado relatado deve reproduzir com prova real.

**Contribuição pretendida.** Um oráculo de teste para invariantes que atravessam circuito e contrato, mais uma avaliação reproduzível. Uma lista manual de auditoria ou testes escritos exclusivamente para os bugs escolhidos não satisfaz esse objetivo.

**Risco e viabilidade.** É a opção de implementação mais controlável, mas a novidade precisa ser contrastada com SNARKProbe, zkFuzz, ferramentas de verificação e trabalhos recentes sobre vinculação de contexto. A busca encontrou o [preprint sobre context-binding de 2026](https://arxiv.org/abs/2604.03900); a ideia geral de ligar uma prova ao contexto também não é nova. Delimitar o ganho da análise conjunta automatizada.

## Ideias que não devem ser tratadas como novas sem um recorte adicional

- **PIR para buscar caminhos de Merkle em carteiras:** já há [TreePIR](https://github.com/PIR-PIXR/TreePIR), [Scaling Semaphore com PIR](https://pse.dev/projects/scaling-semaphore-pir) e [implementação para spendability de Zcash](https://github.com/valargroup/enhance-pir). Um novo trabalho precisaria de outra propriedade, workload ou melhoria demonstrável.
- **Atualizar privadamente witnesses de acumuladores após ficar offline:** é justamente o objeto do [ePrint 2026/832](https://eprint.iacr.org/2026/832). A versão consultada tem revisão de 17/08/2026; não reutilizar números de versões anteriores sem conferir.
- **Reputação anônima com atualizações e bloqueio:** [zk-promises](https://www.usenix.org/conference/usenixsecurity25/presentation/shih) já oferece callbacks e estado privado mutável. O [PDF local](papers/zk-promises-2025.pdf) fica como leitura complementar; propor apenas reputação anônima ou batching repetiria funcionalidades existentes.
- **Matching via MPC com prova ZK:** já aparece no Renegade, citado em R4.

## Como escolher sem comprometer meses de trabalho

Após a preferência expressa por **R2 e R3**, a leitura prioritária passou a ser o [recorte de atualização privada de witnesses KZG](accumulators/index.html), começando pela apresentação de Semacaulk, pelo ePrint 2026/832 e por Caulk+. R2 e R3 correspondem às ideias 5 e 6 na numeração atual. As dificuldades de composição e a novidade ainda precisam ser avaliadas antes de fechar um tema.

Para cada candidato, produzir uma página com: problema do paper; adversário; parte que será modificada; propriedade que deve permanecer; hipótese mensurável; baseline mais próximo; e condição que faria abandonar a ideia. Em seguida, tentar executar o menor exemplo do artefato. Só depois dessa reprodução faz sentido fechar proposta, cronograma ou promessa de ganho.

Uma formulação útil é: **“Partindo de X, substituir ou combinar Y com Z para melhorar a propriedade P, sob o modelo A, comparando com B e medindo M.”** Se não for possível preencher esses campos, o tema ainda está amplo demais.

## Rastreabilidade e limites desta rodada

- [sources.json](sources.json): títulos, fontes, arquivos, hashes e profundidade de leitura.
- [search_log.md](search_log.md): consultas principais, resultados que alteraram o recorte e verificações pendentes.
- Os PDFs são cópias locais de acesso aberto; o arquivo de zkpoex é uma dissertação, não o PDF do artigo SAC.
- Não foi executado o pipeline antigo de expansão por citações. Esta rodada fez busca web dirigida e conferência manual de fontes, sem alterar a configuração ou o ranking de agosto.
- A seleção não é exaustiva. A novidade das cinco propostas, os resultados experimentais e a viabilidade dos artefatos na máquina local continuam pendentes de validação.
