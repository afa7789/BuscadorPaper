"""research_graph.ingestion.methodology — screen papers by research design.

Why this exists
---------------
``seed_keywords`` / ``include_domains`` / ``exclude_keywords`` are declared in
``config.yaml`` but never consulted by the pipeline, and
``expansion.ranking`` is a bag-of-words similarity that cannot tell an
empirical study from a doctrinal essay. So a search aimed at *field research*
still comes back full of **pesquisa documental**: systematic reviews,
literature reviews, historiographies, legal/policy analysis, and theological
reflection.

A field-research paper is identifiable from its own abstract: it reports
primary data it collected. This module screens on exactly that signal, with a
deterministic lexicon — no LLM call, no network, no API cost, and an
explainable verdict per paper.

Verdicts
--------
``primary``     — reports data the authors collected (survey, interviews,
                  clinical series, administrative records, experiments).
``documentary`` — the corpus *is* the data (reviews, archives, canon law,
                  policy texts, doctrinal argument).
``unknown``     — no method signal; abstracts are often missing or too terse.

A strong-documentary marker wins over a primary marker, because a systematic
review that also runs a survey is still, for the reader, a review.
"""

from __future__ import annotations

import re
from typing import Literal

from research_graph.models import Paper

Verdict = Literal["primary", "documentary", "unknown"]

# ---------- Lexicon ----------------------------------------------------------
#
# Patterns are matched against lowercased "title + abstract". They are written
# to fire on the phrase a methods section would actually contain, not on bare
# topic words: "participants", not "abuse".

# Markers that make a paper documentary regardless of anything else present.
_STRONG_DOCUMENTARY: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p) for p in (
        r"\bsystematic\s+review\b",
        r"\bscoping\s+review\b",
        r"\bnarrative\s+review\b",
        r"\bmeta[- ]analys[ei]s\b",
        r"\bbibliometric\b",
        r"\bliterature\s+review\b",
        r"\breview\s+of\s+(the\s+)?literature\b",
        r"\bhistoriograph",
        r"\bstate\s+of\s+the\s+art\b",
        r"\brevis[ãa]o\s+(sistem[áa]tica|bibliogr[áa]fica|integrativa|narrativa)\b",
        r"\bmeta[- ]an[áa]lise\b",
    )
)

# Documentary, but a paper can also carry primary data.
_WEAK_DOCUMENTARY: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p) for p in (
        r"\bdoctrinal\b",
        r"\btheological\s+(reflection|analysis|ethics)\b",
        r"\bethic[sa]l\s+reflection\b",
        r"\bpolicy\s+(analysis|document)\b",
        r"\blegal\s+analysis\b",
        r"\bcanon\s+law\b",
        r"\bcanonical\s+law\b",
        r"\binquiry\s+commission\b",
        r"\bcommission\s+of\s+inquiry\b",
        r"\broyal\s+commission\b",
        r"\barchive[sd]?\b",
        r"\bcase\s+law\b",
        r"\bdocuments\s+(were|was)\s+(analy[sz]ed|reviewed)\b",
        r"\btextual\s+analysis\b",
        r"\bdiscourse\s+analysis\s+of\s+(the\s+)?(documents?)\b",
        r"\bpolicy\s+pathways\b",
        r"\bgovernance\s+reform\b",
    )
)

# Field research: primary data collected by these authors.
_PRIMARY: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p) for p in (
        # quantitative
        r"\bparticipants\b",
        r"\brespondents\b",
        r"\bquestionnaire\b",
        r"\bcross[- ]sectional\b",
        r"\bmultivariate\b|\bregression\b",
        r"\bstatistical\s+(analysis|significance)\b",
        r"\bvalidated\s+(scale|questionnaire|instrument)\b",
        r"\bpsychometric\b",
        r"\blikert\b",
        r"\bsample\s+of\s+\d",
        r"\b[nN]\s*=\s*\d",
        r"\bparticipants\s+were\b",
        r"\bprevalence\s+(study|survey|rate)\b",
        r"\bsurvey(ed)?\b",
        r"\bwe\s+(surveyed|interviewed|recruited|collected|enrolled)\b",
        r"\bdata\s+were\s+collected\b",
        # qualitative
        r"\bin[- ]depth\s+interviews?\b",
        r"\bsemi[- ]structured\s+interviews?\b",
        r"\bfocus\s+groups?\b",
        r"\bqualitative\s+(study|analysis|design|research|data)\b",
        r"\bthematic\s+analysis\b",
        r"\bgrounded\s+theory\b",
        r"\bethnograph",
        r"\bqualitative\s+content\s+analysis\b",
        r"\blife\s+histories\b",
        r"\bnarratives?\b",
        # clinical / epidemiological / administrative
        r"\bcase[- ]control\b",
        r"\bretrospectiv",
        r"\bcohort\s+(study|of)\b",
        r"\bclinical\s+(sample|cohort|data)\b",
        r"\bmedical\s+records?\b",
        r"\bcase\s+(files?|records?)\b",
        r"\boutpatients?\b|\bpatients?\b",
        r"\bvictims?\b|\bsurvivors?\b",
        # Portuguese
        r"\bentrevistas?\b",
        r"\bquestion[áa]rio\b",
        r"\bdados\s+prim[áa]rios\b",
        r"\bescola\s+\b",
    )
)


def _text(paper: Paper) -> str:
    return " ".join(filter(None, [paper.title, paper.abstract])).lower()


def _hits(patterns: tuple[re.Pattern[str], ...], text: str) -> int:
    return sum(1 for p in patterns if p.search(text))


def classify(paper: Paper) -> Verdict:
    """Return the research design implied by ``paper``'s own title+abstract."""
    text = _text(paper)
    if not text.strip():
        return "unknown"
    if _hits(_STRONG_DOCUMENTARY, text):
        return "documentary"
    primary = _hits(_PRIMARY, text)
    doc = _hits(_WEAK_DOCUMENTARY, text)
    if primary:
        # Primary markers beat weak documentary ones only if they outnumber them.
        return "documentary" if doc > primary else "primary"
    # No method signal at all: a doctrinal/legal/archival marker is still
    # positive evidence of a documentary design.
    return "documentary" if doc else "unknown"


def screen(
    papers: list[Paper],
    *,
    keep: Literal["primary", "primary_and_unknown"] = "primary_and_unknown",
) -> tuple[list[Paper], dict[str, int]]:
    """Split ``papers`` by design.

    ``keep="primary"`` drops unknown verdicts too (maximum precision);
    ``keep="primary_and_unknown"`` keeps them (maximum recall). Returns the
    kept list and a verdict histogram for logging.
    """
    counts: dict[str, int] = {"primary": 0, "documentary": 0, "unknown": 0}
    kept: list[Paper] = []
    for p in papers:
        v = classify(p)
        counts[v] += 1
        if v == "primary" or (v == "unknown" and keep == "primary_and_unknown"):
            kept.append(p)
    return kept, counts


__all__ = ["classify", "screen", "Verdict"]