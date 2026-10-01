# Como usar — procurando perguntas em aberto (open questions)

Guia para quem está usando esta ferramenta pela primeira vez. Sem Knowledge
Graph, sem "RAG", sem jargão. Se você sabe abrir um terminal e copiar um
comando colado, você consegue.

---

## 1. O que essa ferramenta faz

Você dá a ela **um tema** (algumas palavras de busca e/ou os links de 2 ou 3
papers). Ela faz três coisas:

1. **Acha** papers relacionados —following as citações, quem citing quem, e
   os outros trabalhos dos mesmos autores. Desenha um grafo do assunto.
2. **Baixa os PDFs** em texto completo (quando consegue, via fontes abertas).
3. **Lê cada paper com um LLM** e escreve num relatório:
   - as **limitações** que o próprio paper admite ("nosso setup precisa de confiança…"),
   - os **trabalhos futuros** que o paper deixa de fora ("como extensão futura…"),
   - e **ideias de projeto** tiradas dessas lacunas.

A última etapa é a que te interessa. Uma pergunta em aberto, na prática, é
quase sempre uma limitação que 3 ou 4 papers independentes admitem — e o grafo
serve justamente para achar esses 3 ou 4 papers que ainda ninguém conectou.

**O que ela NÃO faz:** não lê os papers pra você, não julga novidade, e não
substitui você abrir o PDF. Ela só te dá um mapa e uma lista curta de candidatos.

---

## 2. O que você precisa ter

| Precisa | Por quê |
|---|---|
| **Python 3.11 ou 3.12** | o programa é em Python |
| [`uv`](https://docs.astral.sh/uv/) | instala as dependências sozinho |
| **Um agente (opencode, Claude Code, Codex) _ou_ uma chave de API de LLM** | é o LLM que lê os papers e extrai as lacunas |
| Terminal | para rodar os comandos |

Instalar o `uv` (Mac ou Linux):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Instalar o Python 3.12, se não tiver:

```bash
uv python install 3.12
```

### O que é realmente obrigatório

- **Um LLM é obrigatório** se você quer perguntas em aberto — o agente
  (opção recomendada, seção 4) ou uma chave de API. Sem nenhum dos dois, o
  pipeline roda e baixa PDFs, mas as seções de limitações / trabalhos futuros
  / ideias saem vazias.
- **O e-mail do OpenAlex é recomendado** (grátis). Sem ele o buscador entra
  numa fila mais lenta e às vezes é limitado.
- **Tavily é opcional.** Melhora a busca web se você tiver chave.

---

## 3. Instalar

```bash
cd buscador-open-questions
uv sync
cp .env.example .env
cp config.exemplo-open-questions.yaml config.yaml
```

Pronto, instalado.

---

## 4. Escolher o LLM

### Opção recomendada — o próprio agente (sem chave)

O template já vem com `llm.provider: "agent"`. Abra a pasta no opencode
(ou Claude Code / Codex) e digite `/buscar` (ou peça: "siga o AGENTS.md").
O agente roda as etapas, lê cada pedido em `output/agent_llm/requests/`,
escreve a resposta e roda a etapa de novo até a fila esvaziar.
Nesse modo, pule as opções A e B abaixo; só preencha os e-mails no `.env`.

Custo: o agente responde um pedido por paper. Comece com
`max_total_papers` baixo (seção 8).

### Ou: chave de API

Troque `provider: "agent"` por `provider: "openai_compatible"` no `config.yaml`.
Abra o arquivo `.env` com qualquer editor de texto e preencha **uma** das
opções. As duas linhas de baixo (`OPENALEX_EMAIL` e `CROSSREF_MAILTO`) devem
receber o seu e-mail real — é de graça e deixa a busca mais rápida.

### Opção A — MiniMax (já vem configurado)

Pegue a chave em <https://platform.minimaxi.com> e cole:

```dotenv
MINIMAX_API_KEY=cole_sua_chave_aqui
MINIMAX_BASE_URL=https://api.minimax.io/v1
MINIMAX_MODEL=MiniMax-Text-01
OPENALEX_EMAIL=seu-email-real@exemplo.com
CROSSREF_MAILTO=seu-email-real@exemplo.com
```

### Opção B — OpenAI

```dotenv
OPENAI_API_KEY=sk-cole_sua_chave_aqui
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
OPENALEX_EMAIL=seu-email-real@exemplo.com
CROSSREF_MAILTO=seu-email-real@exemplo.com
```

> **Opção B:** abra o `config.yaml` e troque estas 3 linhas do bloco `llm:`:
> ```yaml
> base_url_env: "OPENAI_API_BASE"
> api_key_env:  "OPENAI_API_KEY"
> model:        "gpt-4o-mini"
> ```

> ⚠️ **Nunca compartilhe o seu `.env`.** Ele tem a sua chave. O `.env.example`
> (com as chaves vazias) é o único arquivo de chaves que pode circular.

---

## 5. Dizer o que você quer procurar

Abra o `config.yaml` e edite duas coisas. Só duas:

**a) As buscas por assunto.** Cada `- type: "crossref_query"` é uma pergunta
diferente que você quer responder. Escreva como você buscaria no Google
Scholar, em inglês:

```yaml
  - type: "crossref_query"
    value: "seu tema, com palavras que o pessoal da área usa"
```

Use **4 a 8** delas, cada uma apontando para uma **lacuna diferente** — não
só sinônimos. Boas perguntas para gerar buracos:

- `... limitations`
- `... scalability performance`
- `... security assumptions`
- `... open challenges survey`
- `... evaluation methodology`

**b) As palavras-chave** do bloco `research_scope.seed_keywords`.

Tudo mais no arquivo já está pronto. Os trechos que precisam de atenção
estão marcados com `<<< EDITAR`.

---

## 6. Rodar

> **Modo agente:** não use `run` direto — ele só enfileira os pedidos.
> Use `/buscar` no opencode (ou peça ao agente para seguir o `AGENTS.md`).
> O comando abaixo vale para o modo com chave de API.

```bash
uv run research-graph run --config config.yaml
```

Isso roda o pipeline inteiro (buscar → baixar PDFs → ler com LLM → gerar
relatório). Leva de **5 a 40 minutos** dependendo de quantos papers você
pediu e da velocidade da sua chave de LLM.

Pode deixar rodando. Se precisar parar, é só rodar o mesmo comando de novo —
o que já foi feito fica em cache e não é refeito.

### Rodando por etapas (para depurar)

```bash
uv run research-graph ingest          # acha os papers
uv run research-graph expand          # expande o grafo (citações, autores)
uv run research-graph extract         # LLM lê e extrai as lacunas
uv run research-graph download-pdfs   # baixa os PDFs
uv run research-graph generate-report # escreve o relatório
```

---

## 7. O que ler depois

Tudo cai na pasta `output/`:

| Arquivo | O que é |
|---|---|
| **`report.md`** | **Comece por aqui.** O relatório em texto. |
| `graph.html` | o grafo interativo — abra no navegador |
| `papers.json` | a lista bruta de papers, com DOI |
| `extractions.json` | o que o LLM extraiu de cada paper, em JSON |
| `pdf_downloads.json` | quais PDFs conseguiu baixar, e quais falharam |

As seções do `report.md`, em ordem de utilidade para achar perguntas em
aberto:

1. **`8. Declared vs Inferred Limitations`** — as lacunas que os próprios
   papers admitem. É a sua mina de ouro.
2. **`9. Open Questions`** — as perguntas em aberto consolidadas.
3. **`10. Project Ideas`** — ideias de projeto já montadas a partir dessas
   lacunas, agrupadas por dificuldade.
4. `5. Communities` — os subgrupos do assunto. Serve para ver o que ainda
   ninguém ligou entre si.
5. `4. Graph Overview` — os papers mais centrais. Bons pontos de partida.

E **depois**: abra os PDFs em `cache/openalex/` e `cache/unpaywall/`. As
perguntas em aberto de verdade estão nas últimas seções dos papers
("Limitations", "Future Work", "Conclusion").

---

## 8. Ajustando o tamanho da busca

Comece **pequeno** para testar se está funcionando (5 minutos), depois
aumente.

| Quer | Mude |
|---|---|
| Teste rápido | `max_hops: 1`, `max_total_papers: 80`, `max_papers_to_download: 10` |
| Busca normal | `max_hops: 2`, `max_total_papers: 300` |
| Varredura grande | `max_hops: 3`, `max_total_papers: 1000` (dias, e muito LLM) |

Outros dois ajustes úteis:

- **Muito ruído?** suba `min_relevance_score` para `0.4` ou `0.5`.
- **Faltou papers importantes?** baixe para `0.2`.

`max_hops` é o botão mais importante:

- `1` = papers citados e citantes dos seus seeds. Rápido.
- `2` = + os outros trabalhos dos mesmos autores. **Comece aqui.**
- `3` ou mais = a rede toda. Caro e raramente necessário.

---

## 9. Problemas comuns

**`error: required environment variable not set`**
Falta a chave no `.env`. Confira o nome exato da variável — tem que bater com o
`api_key_env` do `config.yaml`.

**`error: config file not found`**
Você não rodou o `cp config.exemplo-open-questions.yaml config.yaml`.

**A seção 9 (Open Questions) saiu vazia**
Modo agente: a fila `output/agent_llm/requests/` não foi esvaziada — peça ao
agente para responder os pedidos e rodar `extract` de novo.
Modo API: causa quase sempre: **falta a chave do LLM**. Confirme que `extract` não
imprimiu aviso de "could not build LLM provider". Também confira se você não
rodou com `--no-llm`. Se a chave está boa e mesmo assim a seção vem vazia, o
LLM não achou lacuna explícita nesses papers — nesse caso use a seção 8 e os
PDFs, que é onde a informação está de qualquer forma.

**`papers.json not found`**
Você pulou o `ingest`. Rode `uv run research-graph ingest` primeiro.

**Muitos papers, poucos PDFs baixados**
Normal. Versão de preprint nem sempre está em acesso aberto. Preencha
`OPENALEX_EMAIL` para melhorar. Para o resto, procure o paper pelo título no
Google Scholar ou no site do autor.

**A busca retornou papers off-topic**
Aumente `min_relevance_score`, ou tire palavras ruins de `exclude_keywords`.

**Rodar de novo não muda nada**
É proposital. O `cache/` guarda o que já foi buscado. Para começar do zero,
apague a pasta `cache/` e a pasta `output/`.

---

## 10. Avisos

- **Não há Google Scholar.** Raspá-lo viola os termos de uso e toma bloqueio
  de IP. As fontes aqui (OpenAlex, Crossref, Semantic Scholar, arXiv) são todas
  com API oficial e gratuita.
- **Afiliação de autor vem do OpenAlex** e às vezes está desatualizada.
- Baixar PDF de fonte pirateada pode ser ilegal na sua jurisdição. O
  `config.exemplo-open-questions.yaml` vem só com as fontes legais ligadas
  (`openalex`, `unpaywall`); as outras estão comentadas de propósito.
- **Nada disso substitui ler os papers.**

---

## 11. Referência rápida de comandos

```bash
uv sync                                                  # instala
uv run research-graph run --config config.yaml           # roda tudo
uv run research-graph run --config config.yaml --no-llm  # roda sem gastar LLM
uv run pytest -q                                         # roda os testes
uv run research-graph --help                             # todos os comandos
```
