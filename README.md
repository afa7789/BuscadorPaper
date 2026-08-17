# BuscadorPaper

Descobre papers relevantes por citação e co-autoria, e baixa os PDFs automaticamente.

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
  max_hops: 5                # passos de expansão (máx. 5)
  max_total_papers: 3000     # máximo de papers no grafo
  max_papers_per_query: 150
  min_relevance_score: 0.25  # menor = mais papers aceitos
  years_from: 2015
  years_to: 2026

outputs:
  enable_pdf_download: true
  max_papers_to_download: 100
  pdf_download_providers: [openalex, scihub, annas]
  save_json: false
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
uv run research-graph expand       # citações e co-autores
uv run research-graph download-pdfs # baixa PDFs
```

Re-rodar é seguro — cache em `cache/` evita duplicatas e re-baixos.

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
| `output/graph.html` | Grafo interativo |
| `output/analysis.json` | Centralidade + comunidades |
| `output/people.json` | Autores com instituição |

## Avisos

- **Sem Google Scholar.** Scraping dele viola ToS e IP-bloqueia.
- Afiliações vêm do OpenAlex — podem estar desatualizadas.
- Nada disso substitui ler os papers.

## Licença

MIT.
