# -*- coding: utf-8 -*-
"""rag.graph.rewrite_query — Pipeline 밖에서 재사용 가능한 재작성 헬퍼 검증(가짜 LLM, 네트워크 없음)."""
from rag.graph import rewrite_query


class _FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def complete(self, system, user, **kw):
        self.calls.append((system, user))
        return self.reply


def test_rewrite_query_returns_llm_output_stripped():
    llm = _FakeLLM("  개발비 자산 인식 요건  ")
    out = rewrite_query(llm, "개발비의 자산인식요건 알려줘")
    assert out == "개발비 자산 인식 요건"


def test_rewrite_query_falls_back_to_original_on_empty_reply():
    llm = _FakeLLM("   ")
    out = rewrite_query(llm, "원본 질문")
    assert out == "원본 질문"


def test_rewrite_query_without_history_uses_plain_question_prompt():
    llm = _FakeLLM("검색 질의")
    rewrite_query(llm, "질문입니다")
    _, usr = llm.calls[0]
    assert "이전 대화" not in usr
    assert "질문입니다" in usr


def test_rewrite_query_with_history_includes_conversation():
    llm = _FakeLLM("검색 질의")
    history = [{"role": "user", "content": "개발비는 어떤가?"},
               {"role": "assistant", "content": "제11장 11.20"}]
    rewrite_query(llm, "그럼 그건 언제 환입하나?", history=history)
    _, usr = llm.calls[0]
    assert "이전 대화" in usr
    assert "개발비는 어떤가?" in usr
