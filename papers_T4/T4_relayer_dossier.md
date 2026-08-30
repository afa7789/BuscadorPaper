# T4 — Relayer como adversário em shielded pools (dossiê pro orientador)

PDFs neste diretório: `railgun_2606.25926.pdf`, `wang_mixers_2201.09035.pdf` (+ `.txt` extraídos).

## Pergunta

Quanto anonimato um usuário perde quando o **relayer** (quem submete a tx de withdraw em troca de fee) é o adversário — loga proof, IP, timing, escolha de relayer? Nenhum paper mediu. Dois papers de referência dizem explicitamente que **não** estudaram isso.

## Fonte 1 — Huseynov, Shahzaib, Seres, Tapolcai. *A Tattered Cloak of Invisibility: Measuring Anonymity Loss in Railgun on Ethereum*. arXiv:2606.25926, jun/2026 (ELTE Budapest). 8 págs.

**Números (Seção 4–5):**
- "We identified **124 relayers**" (§2, linha ~245) vs "**Self-broadcaster (N=981)** / Broadcasters (N=124)" (Fig. 8)
- "We identify **6856 withdraw transactions as self-broadcast**" — depositante paga o próprio gas, expõe o endereço de depósito
- 124 relayers servem **89,12%** de todo o volume relayed
- 17,65% dos unshields linkados unicamente (abstract)

**Threat model exclui relayer (§2.4, verbatim):**
> "We assume a passive adversary, i.e., we only assume access to the public Ethereum blockchain data. [...] However, we note that, for example, **relayers or other Ethereum full nodes could link the depositor/withdrawer IP addresses to their public 0x Ethereum addresses. We leave it to future work** to evaluate the efficacy of active attacks on privacy"

**Recomendação de design deixada em aberto (§5, verbatim):**
> "Third, the **relayer infrastructure could be improved to make relayer selection more uniform** across the broadcaster population, reducing the fingerprinting potential of relayer choice patterns. **We leave the formal analysis** of the privacy improvements achievable by such protocol modifications **to future work**."

**Future work (§7, verbatim):**
> "Multi-layered privacy analysis — [...] One may even consider **'active' privacy attacks, e.g., when the adversary is one of the Railgun relayers or users**."

## Fonte 2 — Wang, Chaliasos, Qin, Zhou, Gao, Berrang, Livshits, Gervais. *On How Zero-Knowledge Proof Blockchain Mixers Improve, and Worsen User Privacy*. WWW 2023. arXiv:2201.09035 (Imperial College).

**Relayers filtrados das heurísticas, não estudados (§5, Heuristic 2 + nota 3, verbatim):**
> "Heuristic 2: We assume that given a depositor-withdrawer pair (a_d, a_w) in a pool, **where a_d is not a relayer**³, if a_d generates a withdrawal and assigns a_w to receive the withdrawn coins, then a_d and a_w belong to the same user"
>
> "³ Relayers are addresses who help users withdraw coins from a mixer towards a new address by paying for the transaction fees, in exchange receive a share of the withdrawn coins."

→ Relayer aparece só como **filtro de falso-positivo**; comportamento/poder do relayer nunca é analisado.

**Future work (§8, verbatim):**
> "TC could exploit our methodology and results to provide a service that would **compute the probability that a provided address for a withdrawal could be linked with a depositor**. [...] there might be other potential factors (e.g., AM profits and ETH or BNB prices) which could also affect the usage of ZKP mixers. **We leave the detailed analysis for future work**."

**Números:** anonymity set anunciado reduzível em 27,34% (Tornado) / 46,02% (Typhoon); OFAC cortou depósitos diários >83%.

## Por que é tema de mestrado

1. **Lacuna explícita** em 2 papers de grupos fortes (Imperial 2023, ELTE 2026) — "we leave to future work" citado verbatim.
2. **Dados públicos**: contratos Railgun/Tornado on-chain, 124 relayers identificáveis, registry de relayers do Tornado (ENS/ subgraph).
3. **Mensurável**: perda de anonimato em bits (entropia de Shannon, mesma métrica dos papers), concentração de relayers (Herfindahl), linkage rate.
4. **Dois lados**: (a) medir ataque (relayer honesto-mas-curioso + relayer concentrado); (b) propor e medir mitigação (seleção uniforme de relayer, relayer-mixing multi-hop, custo em gas/latência) — exatamente o que Railgun §5 deixou "para future work".

## Perguntas derivadas (do `output/open_problems.md`, eixo C)

- C1 Relayer-as-adversary: perda de anonimato quando relayer loga (proof, IP, timing); relayer-mixing multi-hop e custo.
- C2 Economia de relayer: concentração (Herfindahl) prevê linkability? Dados pós-delisting Tornado 2025–26 (arXiv:2510.09443).
- C6 Wallet-fingerprint: 13.203/66.248 txs Tornado linkáveis por fingerprint de carteira (ACM SAC 2025, doi:10.1145/3672608.3707896) — combina com escolha de relayer.
