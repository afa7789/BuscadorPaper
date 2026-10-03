"""Tests for ingestion.methodology — the field-research vs documentary screen."""

from research_graph.ingestion.methodology import classify, screen
from research_graph.models import Paper


def _p(title: str, abstract: str | None = None) -> Paper:
    return Paper(paper_id=title, title=title, abstract=abstract)


# ---------- classify: primary (pesquisa de campo) ---------------------------

def test_cross_sectional_survey_is_primary():
    assert classify(_p(
        "Barriers to disclosure in the French Church",
        "A cross-sectional survey of 412 survivors was conducted. "
        "Participants completed a validated questionnaire and logistic "
        "regression was used to identify predictors of reporting behaviour.",
    )) == "primary"


def test_qualitative_interviews_is_primary():
    assert classify(_p(
        "Perceptions of helpful institutional responses",
        "We conducted in-depth interviews with 24 survivors. Thematic analysis "
        "was used to code the transcripts.",
    )) == "primary"


def test_clinical_cohort_is_primary():
    assert classify(_p(
        "Psychological consequences in victims of ecclesiastical abuse",
        "A retrospective study of a clinical sample of 180 patients assessed "
        "posttraumatic stress symptoms.",
    )) == "primary"


def test_case_file_analysis_is_primary():
    assert classify(_p(
        "Child sexual abuse in Spain: a descriptive analysis",
        "We analysed 2,341 case files from the national registry. Sample of "
        "records spanning 2010-2020.",
    )) == "primary"


def test_prevalence_study_is_primary():
    assert classify(_p(
        "Prevalence of sexual grooming behaviours in clergy",
        "A large sample of 6,000 clergy completed an online questionnaire; "
        "weighted prevalence estimates are reported.",
    )) == "primary"


def test_portuguese_markers_are_primary():
    assert classify(_p(
        "Percepções de|escolares sobre denúncia",
        "Foram realizadas entrevistas semiestruturadas com 20 profissionais. "
        "A análise de dados primários seguiu análise temática.",
    )) == "primary"


# ---------- classify: documentary (pesquisa documental) ----------------------

def test_systematic_review_is_documentary():
    assert classify(_p(
        "Child sexual abuse in the Catholic Church: a review of literature",
        "This systematic literature review synthesises findings from 1981-2013 "
        "and identifies gaps in the evidence base.",
    )) == "documentary"


def test_meta_analysis_is_documentary():
    assert classify(_p(
        "Prevalence of childhood sexual abuse: a meta-analysis",
        "We performed a meta-analysis of 55 published studies.",
    )) == "documentary"


def test_doctrinal_essay_is_documentary():
    assert classify(_p(
        "Between ecclesiology and ethics",
        "This article offers a theological reflection on the dignity of the "
        "child within the ecclesiology of the church.",
    )) == "documentary"


def test_canon_law_analysis_is_documentary():
    assert classify(_p(
        "Canon law on clergy sexual abuse of children",
        "We offer a doctrinal analysis of the normative provisions of canon "
        "law and their interpretation.",
    )) == "documentary"


def test_royal_commission_document_analysis_is_documentary():
    assert classify(_p(
        "The impact of the Royal Commission on institutional responses",
        "A documentary analysis of the Royal Commission final report; the "
        "documents were analyzed using thematic coding of policy pathways.",
    )) == "documentary"


def test_strong_marker_beats_primary_marker():
    # A systematic review that also ran a survey is still a review.
    assert classify(_p(
        "Safeguarding practices: a systematic review",
        "We conducted a systematic review of 88 studies and also surveyed "
        "312 participants about reporting behaviour.",
    )) == "documentary"


# ---------- classify: unknown -----------------------------------------------

def test_empty_abstract_is_unknown():
    assert classify(_p("Some title with no method at all")) == "unknown"


def test_no_method_signal_is_unknown():
    assert classify(_p(
        "Reformed social ethics",
        "The essay surveys recent scholarship on church and society.",
    )) == "unknown"


# ---------- screen -----------------------------------------------------------

def test_screen_keeps_primary_and_unknown():
    papers = [
        _p("a", "we surveyed 100 participants"),
        _p("b", "a systematic review of the literature"),
        _p("c"),
    ]
    kept, counts = screen(papers, keep="primary_and_unknown")
    assert [p.paper_id for p in kept] == ["a", "c"]
    assert counts == {"primary": 1, "documentary": 1, "unknown": 1}


def test_strict_screen_drops_unknown():
    papers = [
        _p("a", "we surveyed 100 participants"),
        _p("b", "a systematic review of the literature"),
        _p("c"),
    ]
    kept, counts = screen(papers, keep="primary")
    assert [p.paper_id for p in kept] == ["a"]
    assert counts == {"primary": 1, "documentary": 1, "unknown": 1}


def test_screen_preserves_input_order():
    papers = [_p("z", "participants"), _p("y", "a meta-analysis"), _p("x", "interviews")]
    kept, _ = screen(papers)
    assert [p.paper_id for p in kept] == ["z", "x"]


def test_screen_empty():
    kept, counts = screen([])
    assert kept == []
    assert counts == {"primary": 0, "documentary": 0, "unknown": 0}