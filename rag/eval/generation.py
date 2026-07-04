# -*- coding: utf-8 -*-
"""생성 품질 평가 스텁 — RAGAS의 faithfulness/answer_relevancy. 구현은 나중.

LLM-as-Judge. 입력: trace(question·answer·used_refs·근거텍스트).
"""


def faithfulness(answer, grounding_texts):
    """답변의 주장들이 근거에 실제로 있는지 (환각 검출). 0~1.

    RAGAS: 답변을 주장 단위로 분해 → 각 주장이 근거에서 지지되는 비율.
    TODO: LLM-as-Judge 구현.
    """
    raise NotImplementedError("RAGAS faithfulness (LLM-judge) — 나중에 구현")


def answer_relevancy(question, answer):
    """답변이 질문에 실제로 답했는지. 0~1.

    RAGAS: 답변에서 역질문 생성 → 원 질문과의 임베딩 유사도 평균.
    TODO: 구현.
    """
    raise NotImplementedError("RAGAS answer_relevancy — 나중에 구현")


def score_from_traces(traces_path, judge_llm=None):
    """trace 로그를 소비해 케이스별 faithfulness/answer_relevancy 집계.

    TODO: traces.jsonl 로드 → 근거텍스트 재조회 → LLM-judge 채점 → 요약.
    """
    raise NotImplementedError("trace 기반 생성평가 — 나중에 구현")
