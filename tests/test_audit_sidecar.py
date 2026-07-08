# -*- coding: utf-8 -*-
"""감리지적사례 사이드카 단위 테스트 (무거운 모델 불필요 — 순수 로직/격리 검증).

실행: python3 -m pytest tests/test_audit_sidecar.py -q
커버: AC1(격리) · AC2(embed_text) · AC3(metadata) · AC4(answer 격리) · AC6(임계값 필터).
"""
import pytest

from rag import common as C

# audit-sentinel cases.jsonl 1건을 KASB record_type='audit_case' 형식으로 축약한 표본.
SAMPLE = {
    "record_type": "audit_case",
    "case_id": "FSS/2311-01",
    "title": "위탁가맹점 관련 매출액 과소계상",
    "facts": "회사는 위탁가맹점을 운영하며 위험과 보상을 부담한다.",
    "violation": "제품 인도시점에 수익을 인식하였다.",
    "basis": "일반기업회계기준 제16장(수익)에 따르면 통제 이전 시점에 인식한다.",
    "audit_gap": "감사인은 계약서를 면밀히 검토하지 않았다.",
    "implication": "강화된 감사절차가 필요하다.",
    "standard": "일반기업회계기준 제16장(수익)",
    "source_url": "https://www.fss.or.kr/fss/bbs/B0000188/view.do?nttId=131698",
    "standard_superseded": False,
    "fiscal_year": "2018",
}


# --------------------------------------------------------------- AC1: 라우터 격리
def test_audit_collections_separate_dict():
    assert C.AUDIT_COLLECTIONS is not C.COLLECTIONS
    assert "audit_cases" in C.AUDIT_COLLECTIONS
    assert "audit_cases" not in C.COLLECTIONS


def test_audit_collection_name_avoids_standards_suffix():
    # search.retrieve_routed 의 min_standards 로직은 '*_standards' 접미사에 의존 → 회피 필수
    assert not any(name.endswith("standards") for name in C.AUDIT_COLLECTIONS)


def test_audit_not_in_router_candidates():
    graph = pytest.importorskip("rag.graph")
    assert "audit_cases" not in graph.ALL_COLLS


# --------------------------------------------------------------- AC2: embed_text
def test_embed_text_includes_facts_violation_basis():
    txt = C.embed_text(SAMPLE)
    assert "위탁가맹점을 운영하며" in txt      # facts
    assert "제품 인도시점" in txt              # violation
    assert "제16장(수익)에 따르면" in txt      # basis


def test_embed_text_excludes_audit_gap_and_implication():
    txt = C.embed_text(SAMPLE)
    assert "감사인은 계약서" not in txt        # audit_gap 미포함
    assert "강화된 감사절차" not in txt        # implication 미포함


# --------------------------------------------------------------- AC3: metadata
def test_to_metadata_preserves_display_fields():
    md = C.to_metadata(SAMPLE, "audit_cases")
    for f in ("case_id", "title", "standard", "source_url",
              "fiscal_year", "audit_gap", "implication"):
        assert md.get(f) == SAMPLE[f], f"{f} not preserved"
    assert md.get("standard_superseded") is False
    assert md["record_type"] == "audit_case"


def test_to_metadata_superseded_true_preserved():
    md = C.to_metadata(dict(SAMPLE, standard_superseded=True), "audit_cases")
    assert md.get("standard_superseded") is True


def test_to_metadata_values_are_chroma_scalars():
    # Chroma 는 str/int/float/bool 만 허용 → 리스트/None/dict 금지
    md = C.to_metadata(SAMPLE, "audit_cases")
    for k, v in md.items():
        assert isinstance(v, (str, int, float, bool)), f"{k}={v!r} not scalar"


# --------------------------------------------------------------- AC6: 임계값 필터
def test_audit_filter_drops_below_threshold():
    graph = pytest.importorskip("rag.graph")
    thr = graph.AUDIT_CASE_SCORE_THRESHOLD
    hits = [
        {"score": thr + 0.1, "meta": {"case_id": "A"}},
        {"score": thr, "meta": {"case_id": "B"}},          # 경계값 포함
        {"score": thr - 0.001, "meta": {"case_id": "C"}},  # 미달 제외
    ]
    kept = [h["meta"]["case_id"] for h in graph._audit_filter(hits)]
    assert kept == ["A", "B"]


def test_audit_filter_empty_input():
    graph = pytest.importorskip("rag.graph")
    assert graph._audit_filter([]) == []


# --------------------------------------------------------------- AC4: answer 격리
def test_answer_source_does_not_reference_audit_cases():
    import inspect
    graph = pytest.importorskip("rag.graph")
    src = inspect.getsource(graph.Pipeline.answer)
    assert "audit_cases" not in src   # 프롬프트·has_grounds 게이트에 사이드카 미유입


def test_audit_card_shape():
    graph = pytest.importorskip("rag.graph")
    card = graph._audit_card({"score": 0.87, "text": "사실관계: ...",
                              "meta": SAMPLE})
    assert card["case_id"] == SAMPLE["case_id"]
    assert card["title"] == SAMPLE["title"]
    assert card["text"] == "사실관계: ..."
    assert card["standard_superseded"] is False
    assert isinstance(card["score"], float)


# --------------------------------------------------------------- 그래프 위상 (AC4/AC5 배선)
def test_graph_topology_parallel_sidecar():
    build = pytest.importorskip("rag.graph").build_graph

    class _DummyIdx:
        colls = []

    gr = build(_DummyIdx()).get_graph()
    edges = {(e.source, e.target) for e in gr.edges}
    assert ("route", "retrieve") in edges
    assert ("route", "audit_lookup") in edges     # 병렬 fan-out
    assert ("retrieve", "answer") in edges
    assert ("audit_lookup", "answer") in edges    # answer 로 fan-in
