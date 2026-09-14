"""Aggregate the recorded panel scores without treating them as probabilities."""

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IDEA_WEIGHTS = {"relevance": 0.35, "originality": 0.35, "feasibility": 0.30}
REWRITE_WEIGHTS = {
    "clarity": 0.15,
    "quality": 0.35,
    "consistency": 0.25,
    "structure": 0.10,
    "originality": 0.15,
}


def read_json(path):
    return json.loads(path.read_text())


def checked_weighted(row, weights):
    for key in weights:
        assert isinstance(row[key], (int, float)) and 0 <= row[key] <= 10, row
    return sum(row[key] * weight for key, weight in weights.items())


def describe(values):
    return {
        "mean": statistics.mean(values),
        "variance": statistics.pvariance(values),
        "sd": statistics.pstdev(values),
        "min": min(values),
        "max": max(values),
        "n": len(values),
    }


def main():
    reviewers = [f"P{i}" for i in range(1, 7)]
    analyses = {}
    for reviewer in reviewers:
        document = read_json(ROOT / "analyses" / f"{reviewer}.json")
        assert document["reviewer"] == reviewer
        rows = document["ideas"]
        assert len(rows) == 6 and {row["id"] for row in rows} == set(range(1, 7))
        analyses[reviewer] = {row["id"]: row for row in rows}

    ideas = []
    for idea_id in range(1, 7):
        per_reviewer = {
            reviewer: checked_weighted(analyses[reviewer][idea_id], IDEA_WEIGHTS)
            for reviewer in reviewers
        }
        ideas.append({
            "id": idea_id,
            "score": describe(list(per_reviewer.values())),
            "criteria": {
                criterion: describe([analyses[r][idea_id][criterion] for r in reviewers])
                for criterion in IDEA_WEIGHTS
            },
            "reviewers": per_reviewer,
        })
    ideas.sort(key=lambda row: (-row["score"]["mean"], row["id"]))
    for rank, row in enumerate(ideas, 1):
        row["rank"] = rank

    output = {
        "interpretation": "Merit score of original ideas, not an admission probability or official NPP.",
        "idea_weights": IDEA_WEIGHTS,
        "rewrite_weights": REWRITE_WEIGHTS,
        "ideas": ideas,
        "rewrite_reviews_complete": False,
    }
    # Sensitivity to one panel member, not a statistical confidence interval.
    output["leave_one_reviewer_out"] = {}
    for excluded in reviewers:
        retained = [reviewer for reviewer in reviewers if reviewer != excluded]
        means = {
            idea_id: statistics.mean([
                checked_weighted(analyses[reviewer][idea_id], IDEA_WEIGHTS)
                for reviewer in retained
            ])
            for idea_id in range(1, 7)
        }
        output["leave_one_reviewer_out"][excluded] = {
            "ranking": sorted(means, key=lambda idea_id: (-means[idea_id], idea_id)),
            "means": means,
        }
    review_paths = [ROOT / "cross-reviews" / f"{r}.json" for r in reviewers]
    if all(path.exists() for path in review_paths):
        mapping = read_json(ROOT / "anonymization.json")
        matrix = []
        for reviewer, path in zip(reviewers, review_paths):
            document = read_json(path)
            rows = document["versions"]
            assert len(rows) == 5
            assert {row["version"] for row in rows} == {f"V{i}" for i in range(1, 6)}
            for row in rows:
                author = mapping[reviewer][row["version"]]
                assert author != reviewer, "Self-review is forbidden"
                matrix.append({
                    "reviewer": reviewer,
                    "author": author,
                    "version": row["version"],
                    "weighted": checked_weighted(row, REWRITE_WEIGHTS),
                    "axes": {key: row[key] for key in REWRITE_WEIGHTS},
                })
        assert len(matrix) == 30
        rewrites = []
        for author in reviewers:
            author_rows = [row for row in matrix if row["author"] == author]
            assert len(author_rows) == 5
            rewrites.append({
                "author": author,
                "score": describe([row["weighted"] for row in author_rows]),
                "axes": {
                    key: describe([row["axes"][key] for row in author_rows])
                    for key in REWRITE_WEIGHTS
                },
            })
        output["rewrite_reviews_complete"] = True
        output["cross_review_matrix"] = matrix
        output["rewrites"] = sorted(rewrites, key=lambda row: -row["score"]["mean"])

    (ROOT / "scores.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    for row in ideas:
        stats = row["score"]
        print(f"{row['rank']}. Ideia {row['id']}: {stats['mean']:.2f}; range {stats['min']:.2f}–{stats['max']:.2f}")
    print("Cross-reviews complete:", output["rewrite_reviews_complete"])


if __name__ == "__main__":
    main()
