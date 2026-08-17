# BuscadorPaper

Pega 3 artigos (PDFs, DOIs, URLs ou títulos), descobre papers relacionados
por citação e co-autoria, monta um grafo heterogêneo, e gera
`output/report.md` em Markdown com sugestões de projetos de mestrado.

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

Preencha o mínimo necessário:

```dotenv
MINIMAX_API_KEY=sk-...           # OBRIGATÓRIO para sugestões de mestrado
MINIMAX_BASE_URL=https://api.minimax.io/v1
MINIMAX_MODEL=MiniMax-Text-01
OPENALEX_EMAIL=seu-email@real.com   # Recomendado (libera o polite-pool)
CROSSREF_MAILTO=seu-email@real.com  # Recomendado
TAVILY_API_KEY=                    # Opcional — melhora a busca web
```

Sem `MINIMAX_API_KEY` o pipeline ainda roda, mas gera relatório sem ideias
de mestrado. Use `--no-llm` para pular o LLM por completo.
Qualquer LLM OpenAI-compatible serve (GPT-4o, Claude via proxy, Groq).

## Configurar `config.yaml`

Edite as entradas que você vai usar:

```yaml
seed_inputs:
  - type: "pdf"          # ou "doi", "url", "title", "crossref_query"
    value: "./meu_paper.pdf"
  - type: "crossref_query"  # busca por tema — descobre papers
    value: "zk-SNARK cross-chain light client"

research_scope:
  max_total_papers: 1500   # máximo de papers no grafo
  max_hops: 4              # quantos passos de expansão
  years_from: 2015
  years_to: 2026

outputs:
  save_html_graph: true    # grafo interativo no navegador
  save_markdown_report: true
```

Tipos de seed:
- `pdf`: arquivo local (você precisa de um DOI; vai adivinhar do texto)
- `doi`: identificador direto (`10.1145/2699436`)
- `url`: link para arxiv/eprint
- `title`: busca pelo título
- `crossref_query`: busca por tema (140M+ papers, sem rate limit)

## Rodar

```bash
# Pipeline completo
uv run research-graph run --config config.yaml

# Ou stage por stage
uv run research-graph ingest      # baixa metadados dos seeds
uv run research-graph expand      # anda pelas citações e co-autores
uv run research-graph people      # resolve instituições dos autores
uv run research-graph extract     # LLM extrai info de cada paper
uv run research-graph build-graph # monta o grafo
uv run research-graph analyze     # centralidade + comunidades
uv run research-graph synthesize  # resumo executivo
uv run research-graph generate-report
```

Cada stage salva em `output/` e pode ser re-rodado com segurança (cache em
`cache.sqlite`). Para pular o LLM (sem `MINIMAX_API_KEY` ou qualquer):

```bash
uv run research-graph run --config config.yaml --no-llm
```

## Saída

`uv run research-graph generate-report`

# Opt-in: download PDFs (openalex_pdf → scihub → annas chain)
uv run research-graph download-pdfs
```

Para `download-pdfs`, antes ative em `config.yaml`:
```yaml
outputs:
  enable_pdf_download: true
  max_papers_to_download: 5
  pdf_download_providers: [openalex, scihub, annas]
```
Esse comando escreve em `cache/openalex/`, `cache/scihub/`, `cache/annas/` por
papel, indexado pelo SHA-256.



Tudo em `output/`:

| Arquivo | O que tem |
|---|---|
| `report.md` | Relatório final em Markdown (13 seções) |
| `papers.json` | Papers coletados, deduplicados |
| `graph.html` | Grafo interativo (abre no navegador) |
| `graph.graphml` / `.gexf` / `.cyjs` / `.mmd` | Grafos para Gephi, Cytoscape, Mermaid |
| `analysis.json` | Centralidade, comunidades Louvain |
| `people.json` | Autores com instituição canônica |
| `synthesis.json` | Resumo executivo + ideias de mestrado |

## Avisos

- **Sem Google Scholar.** Scraping dele viola ToS e IP-bloqueia. Use DOIs.
- O grafo mostra **proximidade na rede**, não qualidade científica.
- Afiliações vêm do OpenAlex last-known institution — podem estar desatualizadas.
- O LLM pode inventar. Veja `confidence` em cada ideia de mestrado.
- Nada disso substitui ler os papers nem confirmar com um orientador.

## Licença

MIT.
