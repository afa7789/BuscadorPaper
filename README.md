# BuscadorPaper

Descobre papers relevantes por citação e co-autoria, e baixa os PDFs automaticamente.

> **Layout do repo (15/09/2026):** este repositório guarda apenas o mecanismo
> de pesquisa (código + configs + testes; `cache/` regenerável). As propostas de
> mestrado atuais — com a página HTML, pdfs e notas de revisão — ficam no
> diretório pai: `../2026-09-13-open-problems/`.

## Instalação

Requer Python 3.11+ e [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/afa7789/BuscadorPaper.git
cd BuscadorPaper
uv sync
cp .env.example .env
cp config.example.yaml config.yaml
```

## Configurar `.env`

```dotenv
OPENALEX_API_KEY=                  # Recomendado (grátis; sem chave o OpenAlex usa um orçamento diário por IP)
OPENALEX_EMAIL=seu-email@real.com   # Recomendado (libera o polite-pool)
CROSSREF_MAILTO=seu-email@real.com  # Recomendado
TAVILY_API_KEY=                    # Opcional — melhora a busca web
```

## Configurar `config.yaml`

```yaml
seed_inputs:
  - type: "pdf"
    value: "./meu_paper.pdf"
  - type: "crossref_query"
    value: "zk-SNARK cross-chain light client"

research_scope:
  max_hops: 2                # passos por execução do `expand` (máx. 5)
  max_total_papers: 100      # núcleo: os N melhores vão pro LLM e download
  # max_graph_papers: 5000   # teto opcional do grafo (padrão: sem teto)
  max_papers_per_query: 150
  min_relevance_score: 0.25  # menor = mais papers aceitos
  years_from: 2015
  years_to: 2026

outputs:
  enable_pdf_download: true
  max_papers_to_download: 100
  pdf_download_providers: [openalex, scihub, annas]
  save_json: false
  save_lmdb: false           # true = snapshot KV binário, indexado e memory-mapped
  save_networkit: false      # true = topologia binária para análise C++ paralela
  save_html_graph: false
  save_graphml: false
  save_markdown_report: false
```

Tipos de seed:
- `pdf` — arquivo local (extrai DOI do texto)
- `doi` — identificador direto (`10.1145/2699436`)
- `url` — link para arxiv/eprint
- `title` — busca pelo título
- `crossref_query` — busca por tema (140M+ papers, sem rate limit)

## Rodar

```bash
# Pipeline completo (sem LLM, só descoberta + download)
uv run research-graph run --config config.yaml --no-llm

# Só baixar PDFs (se o grafo já existe)
uv run research-graph download-pdfs --config config.yaml

# Stage por stage
uv run research-graph ingest       # resolve seeds em papers
uv run research-graph expand       # citações e co-autores (rodar de novo = continua)
uv run research-graph download-pdfs # baixa PDFs

# Snapshot binário opcional + paginação por cursor
uv run research-graph index-papers --config config.yaml
uv run research-graph papers-page --config config.yaml --limit 25 --after 0
uv run research-graph papers-page --config config.yaml --query "clergy abuse"
```

Re-rodar é seguro — cache em `cache/` evita re-baixar PDFs.

## Grafo × núcleo

- **Grafo** (`papers.json`): sem teto. Cada `expand` anda até `max_hops` passos
  a partir da borda, caminhando os 25 melhores papers ainda não visitados por passo.
- **Expandir mais:** rode `expand` de novo. Ele continua de onde parou
  (`output/expand_state.json`) sem repetir paper nem autor. `ingest` recomeça do zero.
- **Núcleo**: `papers.json` sai ordenado (seeds → pesquisa de campo → mais
  conectados no grafo → com abstract → mais citados → mais recentes). Só os
  primeiros `max_total_papers` vão pro LLM (`extract`) e pro download.
- `output/links.json`: quem cita quem dentro do grafo (vira aresta `CITES`).

## Onde ficam os PDFs

| Caminho | Conteúdo |
|---|---|
| `cache/openalex/` | PDFs de acesso aberto (OpenAlex) |
| `cache/scihub/` | PDFs via Sci-Hub |
| `cache/annas/` | PDFs via Anna's Archive |

Indexados por SHA-256 do DOI. Papers já baixados não são re-baixados.

## Saída completa (opcional)

Com LLM habilitado, gera também:

| Arquivo | O que tem |
|---|---|
| `output/report.md` | Relatório Markdown (13 seções) |
| `output/papers.json` | Papers coletados |
| `output/papers.lmdb` | KV binário LMDB + MessagePack, com índices e cursor |
| `output/graph.nkbg` | Topologia binária nativa do NetworKit |
| `output/graph.nkbg.msgpack` | IDs, tipos e atributos completos do grafo |
| `output/graph.html` | Grafo interativo |
| `output/analysis.json` | Centralidade + comunidades (NetworKit quando habilitado) |
| `output/people.json` | Autores com instituição |

## Avisos

- **Sem Google Scholar.** Scraping dele viola ToS e IP-bloqueia.
- Afiliações vêm do OpenAlex — podem estar desatualizadas.
- Nada disso substitui ler os papers.

## Licença

MIT.
