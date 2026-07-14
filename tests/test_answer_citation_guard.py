# -*- coding: utf-8 -*-
"""answer() 노드의 로컬(EXAONE) 전용 인용 검증 순수함수 검증(LLM/Index 없이 텍스트 로직만).

배경: EXAONE가 검색 근거에 없는 문단번호를 [식별자] 형태로 지어내 인용하는 문제
(Faithfulness 저하의 핵심 원인, compare_models.py·베이스라인 30건 실측으로 확인됨).
"""
import rag.graph as graph_mod
from rag.graph import (
    Pipeline, _extract_citations, _find_invalid_citations, _needs_citation_retry,
    _strip_invalid_citations,
)

REFUSAL = "근거를 찾지 못했습니다."

HITS = [
    {"ref_key": "제1116호 문단 7", "doc_no": "", "collection": "kifrs_standards",
     "score": 0.9, "text": "리스이용자는...", "meta": {}},
]


class _FakeAnswerModel:
    """model.invoke(messages, config=...)를 흉내내는 가짜 LangChain 모델."""

    def __init__(self, replies):
        self.replies = list(replies)
        self._last = self.replies[-1] if self.replies else ""
        self.calls = []

    def invoke(self, messages, config=None):
        self.calls.append(messages)
        content = self.replies.pop(0) if self.replies else self._last
        return type("Resp", (), {"content": content})()


def _patch_model(monkeypatch, replies):
    fake = _FakeAnswerModel(replies)
    monkeypatch.setattr(graph_mod.L, "answer_chat_model", lambda **kw: fake)
    return fake


def test_extract_citations_finds_all_bracketed_identifiers():
    text = "이 답변은 [제1116호 문단 7]에 근거하며, [016005-40670]도 참조합니다."
    assert _extract_citations(text) == ["제1116호 문단 7", "016005-40670"]


def test_extract_citations_empty_when_no_brackets():
    assert _extract_citations("근거를 찾지 못했습니다.") == []


def test_find_invalid_citations_returns_only_citations_not_in_valid_set():
    text = "근거는 [제1116호 문단 7]과 [B4.3.5(5)]입니다."
    valid = {"제1116호 문단 7", "016005-40670"}
    assert _find_invalid_citations(text, valid) == ["B4.3.5(5)"]


def test_find_invalid_citations_empty_when_all_citations_valid():
    text = "근거는 [제1116호 문단 7]입니다."
    valid = {"제1116호 문단 7"}
    assert _find_invalid_citations(text, valid) == []


def test_find_invalid_citations_dedupes_preserving_first_occurrence_order():
    text = "[IE159]에 따르면 ... 또한 [B4.3.5(5)]도 있고 다시 [IE159]가 나옵니다."
    valid = {"제1116호 문단 7"}
    assert _find_invalid_citations(text, valid) == ["IE159", "B4.3.5(5)"]


def test_strip_invalid_citations_removes_only_invalid_brackets():
    text = "근거는 [제1116호 문단 7]이고 지어낸 [B4.3.5(5)]도 있습니다."
    valid = {"제1116호 문단 7"}
    assert _strip_invalid_citations(text, valid) == "근거는 [제1116호 문단 7]이고 지어낸 도 있습니다."


def test_strip_invalid_citations_preserves_text_when_all_valid():
    text = "근거는 [제1116호 문단 7]입니다."
    valid = {"제1116호 문단 7"}
    assert _strip_invalid_citations(text, valid) == text


def test_strip_invalid_citations_cleans_up_double_spaces_left_by_removal():
    text = "문장  [IE159]  중간에서 지웁니다."
    valid = set()
    assert _strip_invalid_citations(text, valid) == "문장 중간에서 지웁니다."


def test_needs_citation_retry_true_when_invalid_citation_present():
    text = "근거는 [B4.3.5(5)]입니다."
    valid = {"제1116호 문단 7"}
    assert _needs_citation_retry(text, valid, REFUSAL) is True


def test_needs_citation_retry_false_when_all_citations_valid():
    text = "근거는 [제1116호 문단 7]입니다."
    valid = {"제1116호 문단 7"}
    assert _needs_citation_retry(text, valid, REFUSAL) is False


def test_needs_citation_retry_false_when_refused():
    text = REFUSAL
    valid = {"제1116호 문단 7"}
    assert _needs_citation_retry(text, valid, REFUSAL) is False


def test_needs_citation_retry_false_when_text_too_short():
    text = "모릅니다"
    valid = {"제1116호 문단 7"}
    assert _needs_citation_retry(text, valid, REFUSAL) is False


def test_pipeline_answer_local_retries_once_on_invalid_citation(monkeypatch):
    fake = _patch_model(monkeypatch, [
        "단기리스는 [B4.3.5(5)]에 따라 면제됩니다.",   # 1차: 지어낸 인용
        "단기리스는 [제1116호 문단 7]에 따라 면제됩니다.",  # 재시도: 유효 인용
    ])
    p = Pipeline(index=None, local=True)
    out = p.answer({"question": "단기리스 면제 요건은?", "retrieved": HITS})
    assert len(fake.calls) == 2
    assert out["answer"]["used_refs"] == ["제1116호 문단 7"]


def test_pipeline_answer_local_retries_at_most_once(monkeypatch):
    fake = _patch_model(monkeypatch, [
        "[B4.3.5(5)]에 따라 면제됩니다.",
        "여전히 [IE159]를 인용합니다.",
    ])
    p = Pipeline(index=None, local=True)
    out = p.answer({"question": "단기리스 면제 요건은?", "retrieved": HITS})
    assert len(fake.calls) == 2   # 2회 넘게 재시도하지 않음
    assert "[IE159]" not in out["answer"]["answer"]   # 최종 텍스트에서 무효 인용 제거


def test_pipeline_answer_local_used_refs_not_fabricated_when_no_citation(monkeypatch):
    _patch_model(monkeypatch, ["단기리스는 조건을 충족하면 면제됩니다."])  # 인용 전혀 없음
    p = Pipeline(index=None, local=True)
    out = p.answer({"question": "단기리스 면제 요건은?", "retrieved": HITS})
    assert out["answer"]["used_refs"] == []   # top-1 근거로 임의 채우지 않음
    assert out["answer"]["has_grounds"] is True   # refusal은 아님(로컬 완화 유지)


def test_pipeline_answer_gpt_path_never_retries(monkeypatch):
    fake = _patch_model(monkeypatch, ["[제1116호 문단 7]에 따라 면제됩니다."])
    p = Pipeline(index=None, local=False)
    p.answer({"question": "단기리스 면제 요건은?", "retrieved": HITS})
    assert len(fake.calls) == 1


def test_local_and_gpt_system_prompt_are_identical():
    """v1/v2 프롬프트 지시 추가 둘 다 30문항 재검증에서 refusal·Faithfulness 악화로
    폐기됨(idx=0/11: 지시가 있으면 모델이 확신 없는 인용을 아예 생략하는 과잉방어).
    지어낸 인용 방지는 코드 레벨 retry+strip만으로 처리 — 프롬프트는 로컬/GPT 동일."""
    local_sys = Pipeline(index=None, local=True)._answer_system_prompt()
    gpt_sys = Pipeline(index=None, local=False)._answer_system_prompt()
    assert local_sys == gpt_sys
