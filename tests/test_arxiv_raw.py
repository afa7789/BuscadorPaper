"""Regression: arxiv provider must not pass an XML Element as ProviderResult.raw."""
from unittest.mock import MagicMock

from research_graph.providers.arxiv import ArxivProvider

_FEED = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2202.06877v1</id>
    <title>A Review of zk-SNARKs</title>
    <published>2022-02-14T00:00:00Z</published>
    <summary>x</summary>
    <author><name>Thomas Chen</name></author>
  </entry>
</feed>"""


def _provider() -> ArxivProvider:
    p = ArxivProvider.__new__(ArxivProvider)
    p._base = "x"
    p._limiter = MagicMock()
    resp = MagicMock(status_code=200, text=_FEED)
    p._client = MagicMock(get=MagicMock(return_value=resp))
    return p


def test_fetch_by_arxiv_id_returns_ok_with_dict_raw() -> None:
    r = _provider().fetch_by_arxiv_id("2202.06877")
    assert r.status == "ok"
    assert r.data.title == "A Review of zk-SNARKs"
    assert isinstance(r.raw, dict)


def test_search_by_title_returns_ok_with_dict_raw() -> None:
    r = _provider().search_by_title("A Review of zk-SNARKs")
    assert r.status == "ok"
    assert len(r.data) == 1
    assert isinstance(r.raw, dict)
