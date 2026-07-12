# -*- coding: utf-8 -*-
"""rag.search의 RRF 병합·컬렉션 스코핑 BM25 후보 선정 순수 함수 테스트.

Chroma/BGE 모델 로딩 없이 병합 로직·순위 계산만 검증한다.
"""
from rag.search import RRF_K, _bm25_candidates_for_collections, _rrf_merge


def test_rrf_merge_single_list_preserves_rank_order():
    merged = _rrf_merge([["a", "b", "c"]], k=60)
    assert [i for i, _ in merged] == ["a", "b", "c"]


def test_rrf_merge_combines_overlapping_ids_with_higher_score():
    # b는 두 리스트 모두에 있어 단독보다 점수가 높아 1위가 되어야 함
    merged = _rrf_merge([["a", "b", "c"], ["b", "d"]], k=60)
    order = [i for i, _ in merged]
    assert order[0] == "b"
    scores = dict(merged)
    # b: 1번리스트 순위1(1/62) + 2번리스트 순위0(1/61)
    assert scores["b"] == 1.0 / 62 + 1.0 / 61
    assert scores["a"] == 1.0 / 61   # 1번리스트 순위0
    assert scores["d"] == 1.0 / 62   # 2번리스트 순위1


def test_rrf_merge_default_k_matches_module_constant():
    merged_default = _rrf_merge([["x"]])
    merged_explicit = _rrf_merge([["x"]], k=RRF_K)
    assert merged_default == merged_explicit


def test_bm25_candidates_filters_by_target_collections_only():
    ids = ["s1", "s2", "q1", "s3"]
    doc_coll = ["kifrs_standards", "kifrs_standards", "qa_kifrs", "kgaap_standards"]
    scores = [0.5, 0.9, 0.99, 0.7]
    out = _bm25_candidates_for_collections(ids, doc_coll, scores,
                                            colls=["kifrs_standards"], per_coll=10)
    assert "q1" not in out       # 라우팅 안 된 컬렉션 제외
    assert "s3" not in out       # 다른 standards 컬렉션도 제외
    assert out == ["s2", "s1"]   # 점수 내림차순


def test_bm25_candidates_respects_per_coll_cap():
    ids = ["a", "b", "c", "d"]
    doc_coll = ["kifrs_standards"] * 4
    scores = [0.1, 0.4, 0.3, 0.2]
    out = _bm25_candidates_for_collections(ids, doc_coll, scores,
                                            colls=["kifrs_standards"], per_coll=2)
    assert out == ["b", "c"]
