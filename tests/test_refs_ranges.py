# -*- coding: utf-8 -*-
"""refs.extract_refs() 물결표(~) 범위 인용 확장 테스트."""
from refs import extract_refs


def test_simple_numeric_range_expands_all_paragraphs():
    refs = extract_refs("제1102호 문단 10~12를 참조")
    assert "제1102호 문단 10" in refs
    assert "제1102호 문단 11" in refs
    assert "제1102호 문단 12" in refs


def test_letter_prefixed_range_expands_all_paragraphs():
    refs = extract_refs("제1109호 문단 B9~B31 참조")
    expected = ["제1109호 문단 B{}".format(n) for n in range(9, 32)]
    for e in expected:
        assert e in refs
    assert len(expected) == 23


def test_two_letter_prefixed_range_expands_all_paragraphs():
    refs = extract_refs("제1039호 문단 BC322~BC325")
    assert refs.count("제1039호 문단 BC322") + refs.count("제1039호 문단 BC323") \
        + refs.count("제1039호 문단 BC324") + refs.count("제1039호 문단 BC325") == 4
    for n in (322, 323, 324, 325):
        assert "제1039호 문단 BC{}".format(n) in refs


def test_oversized_range_only_adds_endpoints_not_full_expansion():
    refs = extract_refs("제1001호 문단 1~200")
    assert "제1001호 문단 1" in refs
    assert "제1001호 문단 200" in refs
    # 폭주 방지: 중간값(예: 100)은 확장되지 않아야 함
    assert "제1001호 문단 100" not in refs


def test_existing_comma_separated_paragraphs_still_work():
    refs = extract_refs("제1109호 문단 9, 문단 BC40, 문단 BC41")
    assert "제1109호 문단 9" in refs
    assert "제1109호 문단 BC40" in refs
    assert "제1109호 문단 BC41" in refs


def test_existing_single_paragraph_extraction_unaffected():
    refs = extract_refs("제1116호 문단 7⑴을 적용한다")
    assert refs == ["제1116호 문단 7⑴"]


def test_kgaap_chapter_range_expands():
    refs = extract_refs("제10장 문단 10.14~10.16")
    assert "제10장 문단 10.14" in refs
    assert "제10장 문단 10.15" in refs
    assert "제10장 문단 10.16" in refs
