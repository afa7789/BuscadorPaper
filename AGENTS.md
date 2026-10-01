# Agent guide — research-graph

With `llm.provider: agent` in the config, **you (the coding agent) are the LLM**.
No API key needed. The pipeline queues each LLM call as a file; you answer it.

## Loop

1. `uv run research-graph ingest --config config.yaml`
2. `uv run research-graph expand --config config.yaml`
3. `uv run research-graph extract --config config.yaml`
4. Answer the queue (below). Re-run `extract`. Repeat until
   `<output_dir>/agent_llm/requests/` is empty (claims classification
   appears only after the first extraction pass is answered).
5. `uv run research-graph build-graph --config config.yaml`
6. `uv run research-graph analyze --config config.yaml`
7. `uv run research-graph synthesize --config config.yaml` → answer queue → re-run until empty.
8. `uv run research-graph generate-report --config config.yaml`
9. Read `<output_dir>/report.md` (section 8 = limitations, section 9 = open questions).

## Answering the queue

Each `<output_dir>/agent_llm/requests/<id>.json` has:

- `messages` — system + user prompt. Follow the system prompt as instructions.
- `schema` — JSON schema the reply must match (null → plain text).
- `reply_format`, `max_words`.
- `answer_path` — write your reply here (`answers/<id>.txt`).

Rules:
- Write only the reply: a single JSON object when `schema` is set, no fences, no prose.
- Ground answers in the prompt text (title/abstract). Never invent DOIs or paper_ids.
- Do not delete request files; the pipeline removes them once answered.
- Many requests? Do them in batches; one file per answer.
