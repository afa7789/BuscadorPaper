from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from research_graph.models import Paper
from research_graph.papers_kv import get_paper_by_doi, page_papers, write_papers_kv


def _papers() -> list[Paper]:
    return [
        Paper(
            paper_id=f"doi:10.1234/{number}",
            doi=f"10.1234/{number}",
            title=title,
            abstract=abstract,
            year=2020 + number,
        )
        for number, title, abstract in [
            (1, "Safeguarding in schools", "A field survey of teachers"),
            (2, "Disclosure after institutional abuse", "Interviews with survivors"),
            (3, "Child protection policy", "Implementation in public schools"),
            (4, "Clergy abuse response", "A survivor-centred qualitative study"),
            (5, "Prevention education", "Parents and coaches were surveyed"),
        ]
    ]


def test_cursor_pagination_and_doi_lookup(tmp_path):
    path = tmp_path / "papers.lmdb"
    write_papers_kv(path, _papers())

    first = page_papers(path, limit=2)
    assert [item["doi"] for item in first["items"]] == ["10.1234/1", "10.1234/2"]
    assert first["next_after"] == 2
    assert first["has_more"] is True

    second = page_papers(path, limit=2, after=first["next_after"])
    assert [item["doi"] for item in second["items"]] == ["10.1234/3", "10.1234/4"]
    assert second["next_after"] == 4

    last = page_papers(path, limit=2, after=second["next_after"])
    assert [item["doi"] for item in last["items"]] == ["10.1234/5"]
    assert last["next_after"] is None
    assert last["has_more"] is False

    assert get_paper_by_doi(path, "10.1234/4")["title"] == "Clergy abuse response"
    assert get_paper_by_doi(path, "10.1234/missing") is None


def test_inverted_index_query_and_parallel_readers(tmp_path):
    path = tmp_path / "papers.lmdb"
    write_papers_kv(path, _papers())

    result = page_papers(path, limit=10, query="institutional survivors")
    assert [item["doi"] for item in result["items"]] == ["10.1234/2"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        pages = list(executor.map(lambda _: page_papers(path, limit=3), range(32)))
    assert all(len(page["items"]) == 3 for page in pages)


def test_rebuild_replaces_the_snapshot(tmp_path):
    path = tmp_path / "papers.lmdb"
    write_papers_kv(path, _papers())
    write_papers_kv(path, _papers()[:1])

    page = page_papers(path, limit=10)
    assert len(page["items"]) == 1
    assert page["items"][0]["doi"] == "10.1234/1"


def test_rejects_invalid_page_arguments(tmp_path):
    path = tmp_path / "papers.lmdb"
    write_papers_kv(path, _papers())

    for kwargs in ({"limit": 0}, {"limit": 201}, {"after": -1}):
        try:
            page_papers(path, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {kwargs}")
