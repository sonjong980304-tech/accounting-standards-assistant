# -*- coding: utf-8 -*-
"""rag.eval.run_batch.expand_with_neighbors() — 실존 인접 문단만 확장하는지 검증."""
from rag.eval.run_batch import expand_with_neighbors


def test_adds_existing_neighbors_on_both_sides():
    hits = {"제1102호 문단 B45"}
    corpus = {"제1102호 문단 B44", "제1102호 문단 B45", "제1102호 문단 B46"}
    out = expand_with_neighbors(hits, corpus)
    assert "제1102호 문단 B44" in out
    assert "제1102호 문단 B46" in out
    assert "제1102호 문단 B45" in out  # 원본 유지


def test_only_adds_neighbor_that_actually_exists_in_corpus():
    hits = {"제1102호 문단 B45"}
    corpus = {"제1102호 문단 B45", "제1102호 문단 B46"}   # B44는 코퍼스에 없음
    out = expand_with_neighbors(hits, corpus)
    assert "제1102호 문단 B46" in out
    assert "제1102호 문단 B44" not in out


def test_does_not_fabricate_neighbor_absent_from_corpus():
    hits = {"제1102호 문단 B45"}
    corpus = {"제1102호 문단 B45"}   # 인접 문단이 코퍼스에 전혀 없음
    out = expand_with_neighbors(hits, corpus)
    assert out == {"제1102호 문단 B45"}


def test_term_section_key_without_parseable_paragraph_is_kept_unchanged():
    hits = {"제1109호 용어의 정의:파생상품"}
    corpus = {"제1109호 용어의 정의:파생상품", "제1109호 용어의 정의:기타"}
    out = expand_with_neighbors(hits, corpus)
    assert out == {"제1109호 용어의 정의:파생상품"}


def test_gap_of_two_is_not_adjacent():
    hits = {"제1102호 문단 45"}
    corpus = {"제1102호 문단 45", "제1102호 문단 47"}   # 46이 없어 진짜 간격 2
    out = expand_with_neighbors(hits, corpus)
    assert out == {"제1102호 문단 45"}
