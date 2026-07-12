# -*- coding: utf-8 -*-
"""crawler.extract_standard_refs가 국제표기(IFRS/IAS 등) 참조도 함께 추출하는지 검증.

과거 이 매핑은 별도 1회성 마이그레이션 스크립트로만 적용돼 있었고(코드에 연결 안 됨),
reparse_qa.py --all-records 재실행 시 소실됨(016002 골든셋 142→123건으로 감소해 발견).
extract_standard_refs 파이프라인에 영구 통합해 재발을 막는다.
"""
from crawler import extract_standard_refs


def _detail(question=None, answer=None, related=None, body=None):
    return {"meta": {}, "question": question, "answer": answer,
            "related": related, "body": body}


def test_extracts_korean_refs_as_before():
    d = _detail(question="검토", answer="제1109호 문단 9를 참조한다")
    refs = extract_standard_refs(d)
    assert "제1109호 문단 9" in refs


def test_extracts_intl_standard_reference_merged_with_korean():
    d = _detail(question="검토", answer="IFRS 9 문단 5.1을 참조하며 제1109호와 동일 취지다")
    refs = extract_standard_refs(d)
    assert "제1109호 문단 5.1" in refs   # IFRS 9 → 제1109호 매핑
    assert "제1109호" in refs            # 기존 한국식 추출도 유지


def test_intl_refs_not_duplicated_when_already_present_via_korean_form():
    d = _detail(question="검토", answer="IAS 12 문단 5, 제1012호 문단 5 모두 동일 근거")
    refs = extract_standard_refs(d)
    assert refs.count("제1012호 문단 5") == 1
