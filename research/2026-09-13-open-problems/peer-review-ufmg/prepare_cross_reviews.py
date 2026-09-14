"""Prepare five anonymized peer rewrites per reviewer, excluding their own."""

import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REFERENCE = Path("/Users/afa/.codex/skills/peer-review/reference/panel-prompts.md")


def main():
    panel = json.loads((ROOT / "panel.json").read_text())
    original = (ROOT / "original.html").read_text()
    rewrites = {}
    for person in panel:
        text = (ROOT / "analyses" / f"{person['id']}.md").read_text()
        analysis, rewrite = text.split("## REWRITE", 1)
        assert "## ANALYSIS" in analysis and rewrite.strip()
        rewrites[person["id"]] = rewrite.strip()

    template = re.findall(r"```\n(.*?)\n```", REFERENCE.read_text(), re.S)[4]
    rng = random.Random(20260914491)
    mapping = {}
    for person in panel:
        reviewer = person["id"]
        peers = [author for author in rewrites if author != reviewer]
        rng.shuffle(peers)
        mapping[reviewer] = {f"V{i}": author for i, author in enumerate(peers, 1)}
        assert len(peers) == 5 and reviewer not in peers
        peer_text = "\n\n".join(
            f"{version}:\n{rewrites[author]}"
            for version, author in mapping[reviewer].items()
        )
        prompt = template
        values = {
            "NAME": reviewer,
            "SPECIALTY": person["specialty"],
            "PRIORITY": person["motto"],
            "STYLE": person["style"],
            "N-1": "5",
            "FULL_ORIGINAL_CONTENT": original,
        }
        for key, value in values.items():
            prompt = prompt.replace("{" + key + "}", value)
        start = prompt.index("V1:\n{rewrite_from_other_agent_1}")
        end = prompt.index("\n>>>", start)
        prompt = prompt[:start] + peer_text + prompt[end:]
        output_md = ROOT / "cross-reviews" / f"{reviewer}.md"
        output_json = ROOT / "cross-reviews" / f"{reviewer}.json"
        prompt += f"""

Contrato de entrega: escreva em português. Avalie o mérito dos cinco textos
fornecidos como reformulações de propostas de mestrado, não como protocolos
implementados. Escala de mérito não é probabilidade de ingresso. A rubrica das
IDEIAS foi 35% relevância, 35% originalidade/coerência e 30% viabilidade; os CINCO
eixos desta revisão cruzada medem a qualidade das REESCRITAS e são distintos.
Não atribua autoria às versões nem tente descobri-la. Não leia outros arquivos
de pareceres, panel.json ou anonymization.json. Não crie subagentes.
Preserve críticas técnicas concretas: contribuição pode ser incremental,
resultado negativo pode ser útil, teste não substitui argumento de segurança.
Não use sua nota para fingir avaliação por um professor real da UFMG.

Grave o texto integral, com SCORES e CRITIQUES, em {output_md}.
Grave também {output_json}, no formato:
{{"reviewer":"{reviewer}","versions":[{{"version":"V1","clarity":0,
"quality":0,"consistency":0,"structure":0,"originality":0,
"critique":"crítica específica em 2–4 linhas"}}, ...V2 até V5]}}.
Só escreva esses dois arquivos. Na resposta final, informe os caminhos e a
principal tensão encontrada. Não reescreva mais uma vez as seis ideias.
"""
        (ROOT / "prompts" / f"{reviewer}-cross.md").write_text(prompt)
    (ROOT / "anonymization.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n"
    )
    print("Prepared six blind review packets; five peers each; no self-review.")


if __name__ == "__main__":
    main()
