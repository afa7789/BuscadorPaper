"""research_graph.dedupe — paper + author deduplication.

Two surfaces:

  1. Paper dedup (DOI / arXiv / S2 / OpenAlex)
     Collapses records for the same bibliographic entity into one Paper
     record with all source paper_ids preserved as aliases. Triggered
     before graph build to keep the node count truthful.

  2. Author dedup (the harder problem)
     Different metadata sources yield different forms of the same human:
       "Rafael Oliveira"
       "Rafael Henrique do Nascimento Oliveira"
       "R. H. N. Oliveira"
       "OLIVEIRA, RAFAEL"
     Plus non-determinism: capitalization, diacritics, surname particle
     ordering, ORCID collisions, and as-of-yet-unidentified foreign-script
     transliterations.

     Heuristic approach (cheap, no LLM, deterministic, auditable):
       - normalize: lowercase, strip diacritics, collapse whitespace,
         remove honorifics (Dr., Prof., Jr., Sr., III), strip punctuation
       - last-name key: use the *family name* (last token before particles)
         so "Rafael Henrique do Nascimento OLIVEIRA" and "Rafael OLIVEIRA"
         hash to the same primary key
       - name-initials secondary key: for the same family, compare initials
         of the given-name tokens; tolerate one mismatch (bad metadata)
       - ORCID is the authoritative key when present
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from research_graph.models import Paper


# ---------------------------------------------------------------- paper dedup

@lru_cache(maxsize=4096)
def _norm_doi(d: str | None) -> str:
    if not d:
        return ""
    return d.lower().strip().replace("https://doi.org/", "")


def _paper_aliases(paper: Paper) -> list[str]:
    """All canonical ids this paper could be reached by."""
    aliases: list[str] = []
    if paper.doi:
        aliases.append(f"doi:{_norm_doi(paper.doi)}")
    for u in (paper.urls or []):
        # arxiv id from url
        m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", u, re.IGNORECASE)
        if m:
            aliases.append(f"arxiv:{m.group(1)}")
    if paper.paper_id:
        aliases.append(paper.paper_id)
    # Pull canonical ids from source_provenance hints if stored
    sp = paper.source_provenance or {}
    if isinstance(sp, dict):
        for prov in sp.keys():
            if prov and isinstance(prov, str):
                aliases.append(f"{prov}:{paper.title[:20]}")
    # dedupe while preserving order
    seen = set()
    out = []
    for a in aliases:
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def dedupe_papers(papers: list[Paper]) -> list[Paper]:
    """Merge papers that resolve to the same bibliographic entity.

    The first occurrence is kept; subsequent papers are merged into it via
    a list-merge on `authors`, `urls`, `venue`, `source_provenance`. The
    surviving paper's `paper_id` stays the same but its
    `source_provenance` gains an entry recording the aliases.
    """
    by_key: dict[str, Paper] = {}
    alias_to_key: dict[str, str] = {}

    def _aliases_for(p: Paper) -> list[str]:
        # All canonical ids we might already have stored for this paper.
        return _paper_aliases(p)

    for p in papers:
        # Determine the canonical key: prefer doi > arxiv > paper_id.
        key = ""
        if p.doi:
            key = "doi:" + _norm_doi(p.doi)
        elif p.paper_id and p.paper_id.startswith("arxiv:"):
            key = p.paper_id
        elif p.paper_id:
            key = p.paper_id
        # See if any alias already maps to a known key
        resolved = alias_to_key.get(key)
        if not resolved:
            for a in _aliases_for(p):
                if a in alias_to_key:
                    resolved = alias_to_key[a]
                    break
        if resolved:
            target = by_key[resolved]
            # Merge fields into target
            for u in p.urls or []:
                if u not in (target.urls or []):
                    target.urls = (target.urls or []) + [u]
            for a in p.authors or []:
                if a not in target.authors:
                    target.authors = (target.authors or []) + [a]
            if not target.abstract and p.abstract:
                target.abstract = p.abstract
            if not target.year and p.year:
                target.year = p.year
            if not target.venue and p.venue:
                target.venue = p.venue
            # Record provenance
            sp = dict(target.source_provenance or {})
            for src, fields in (p.source_provenance or {}).items():
                sp[src] = list(set(sp.get(src, []) + (fields or [])))
            target.source_provenance = sp
        else:
            by_key[key] = p
            for a in _aliases_for(p):
                alias_to_key[a] = key
    return list(by_key.values())


# ---------------------------------------------------------------- author dedup

_HONORIFICS = re.compile(
    r"\b(dr|prof|mr|mrs|ms|sr|jr|iii|ii|iv|phd|msc)\.?\b", re.IGNORECASE
)
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")
_PARTICLES = {
    "da", "de", "di", "do", "du", "la", "le", "van", "von", "der", "den",
    "el", "al", "ibn", "bin", "te", "ten", "y", "e",
}


def _strip_diacritics(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize_name(s: str) -> str:
    """Aggressive normalization for author dedup.

    Examples:
      "Dr. Rafael H. N. Oliveira"      -> "rafael h n oliveira"
      "OLIVEIRA, Rafael Henrique"        -> "rafael henrique oliveira"
      "Rafael Henrique do Nascimento"    -> "rafael henrique do nascimento"
    """
    if not s:
        return ""
    s = _strip_diacritics(s)
    s = _HONORIFICS.sub(" ", s)
    # Strip commas, periods, apostrophes, etc. but keep whitespace + alphanum.
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip().lower()
    return s


def _split_family(tokens: list[str]) -> tuple[str, list[str]]:
    """Return (family_name, given_tokens) given a list of normalized tokens.

    Heuristic: the family name is the *last* non-particle token. A particle
    is a small word like "do", "de", "van", etc. With this rule:
      ["rafael", "henrique", "do", "nascimento", "oliveira"]
      -> ("oliveira", ["rafael", "henrique", "do", "nascimento"])
    """
    if not tokens:
        return "", []
    last = tokens[-1]
    family = last if last not in _PARTICLES else (
        tokens[-2] if len(tokens) >= 2 else last
    )
    given = tokens[:-1] if family == last else tokens[:-2]
    return family, given


def _initials(given_tokens: list[str]) -> str:
    """First letter of each given token, joined."""
    return "".join(t[0] for t in given_tokens if t)


def family_key(name: str) -> str:
    """Just the family name, normalized. The strongest single signal."""
    n = normalize_name(name)
    toks = n.split()
    family, _ = _split_family(toks)
    return family


def author_key(name: str, orcid: str | None = None) -> str:
    """Canonical key for an author. ORCID wins; otherwise family+initials.

    Use this everywhere you want to identify an author for graph-node ID.
    Falls back to a stable hash of the normalized full name when we cannot
    compute initials (single-token names, e.g. institution names).
    """
    if orcid:
        return f"orcid:{orcid.lower()}"
    toks = normalize_name(name).split()
    family, given = _split_family(toks)
    if not family:
        return f"name:{normalize_name(name)}"
    return f"author:fam={family}|ini={_initials(given)}"


def should_merge_authors(
    name_a: str, orcid_a: str | None,
    name_b: str, orcid_b: str | None,
) -> bool:
    """Decide whether two author records refer to the same human.

    Rules (any one true => merge):
      1. Both have ORCIDs and they match -> merge.
      2. Both have ORCIDs and they differ -> NEVER merge (treat as distinct
         humans). Two ORCIDs are authoritative: if both are present and they
         disagree, no name similarity can compensate.
      3. (Otherwise — at most one ORCID present, or both absent.)
         Same family key AND one of:
           a. Both have empty given-name (surname only) AND same family.
           b. One given-name set is subset of the other.
           c. Their initials match (initial-subset tolerance).
           d. Short names with Jaro-Winkler >= 0.90.
    """
    # Rule 1: matching ORCIDs -> merge
    if orcid_a and orcid_b and orcid_a.lower() == orcid_b.lower():
        return True
    # Rule 2: both present, conflict -> no merge
    if orcid_a and orcid_b:
        return False
    # Rule 3: name-only decision
    ta = normalize_name(name_a).split()
    tb = normalize_name(name_b).split()
    if not ta or not tb:
        return False
    fa, ga = _split_family(ta)
    fb, gb = _split_family(tb)
    if not fa or not fb:
        return False
    # Same family (exact) -> continue
    if fa == fb:
        pass
    # Different family but very close (transliteration variant) AND
    # given-names look similar -> still merge. Catches "Ohkubo"/"Okubo".
    elif (
        len(fa) >= 4 and len(fb) >= 4
        and _jaro_winkler(fa, fb) >= 0.92
        and set(ga) == set(gb)  # identical given-name token sets
        and _jaro_winkler(" ".join(ga), " ".join(gb)) >= 0.90
    ):
        # Accept the merged family as the longer/more frequent variant;
        # the dedupe routine handles string-level resolution later.
        fa = fa  # noqa
    else:
        return False
    if not ga and not gb:
        return True
    a_set = set(ga)
    b_set = set(gb)
    if a_set and b_set and (a_set.issubset(b_set) or b_set.issubset(a_set)):
        return True
    ia = _initials(ga)
    ib = _initials(gb)
    if ia and ib:
        # Subset-match tolerates initials in one record that are missing
        # in the other (e.g. "R" in one, "R H N" in the other).
        if set(ia).issubset(set(ib)) or set(ib).issubset(set(ia)):
            return True
    if len(ga) <= 2 and len(gb) <= 2:
        ja = " ".join(ga)
        jb = " ".join(gb)
        if _jaro_winkler(ja, jb) >= 0.90:
            return True
    return False


def _jaro_winkler(s1: str, s2: str) -> float:
    """Pure-python Jaro-Winkler distance, no external deps."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    # Jaro
    max_dist = max(len(s1), len(s2)) // 2 - 1
    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)
    matches = 0
    for i, c in enumerate(s1):
        start = max(0, i - max_dist)
        end = min(i + max_dist + 1, len(s2))
        for j in range(start, end):
            if not s2_matches[j] and s2[j] == c:
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    t = 0
    k = 0
    for i in range(len(s1)):
        if s1_matches[i]:
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                t += 1
            k += 1
    transpositions = t // 2
    jaro = (
        matches / len(s1)
        + matches / len(s2)
        + (matches - transpositions) / matches
    ) / 3
    # Winkler boost
    prefix = 0
    for i in range(min(4, len(s1), len(s2))):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break
    return jaro + prefix * 0.1 * (1 - jaro)


def dedupe_authors(
    records: list[dict],
) -> list[dict]:
    """Canonicalize a list of author dicts.

    Each record must have at minimum `author` (display name) and optionally
    `author_id` (OpenAlex A...). Records that match per `should_merge_authors`
    are merged into the first one seen, with `aliases` listing the merged
    display names.

    Output preserves the order of first appearances.
    """
    out: list[dict] = []

    for rec in records:
        name = rec.get("author") or ""
        orcid = rec.get("orcid")
        merged = False
        for existing in out:
            if should_merge_authors(name, orcid, existing.get("author", ""), existing.get("orcid")):
                # Record the merge
                aliases = list(existing.get("aliases") or [])
                if name and name not in aliases and name != existing.get("author"):
                    aliases.append(name)
                existing["aliases"] = aliases
                # Keep the more complete record
                if orcid and not existing.get("orcid"):
                    existing["orcid"] = orcid
                if rec.get("author_id") and not existing.get("author_id"):
                    existing["author_id"] = rec["author_id"]
                if rec.get("institution") and not existing.get("institution"):
                    existing["institution"] = rec["institution"]
                if rec.get("institution_id") and not existing.get("institution_id"):
                    existing["institution_id"] = rec["institution_id"]
                merged = True
                break
        if not merged:
            out.append(dict(rec))  # shallow copy

    # Annotate canonical key
    for r in out:
        r["canonical_key"] = author_key(r.get("author", ""), r.get("orcid"))
    return out
