# -*- coding: utf-8 -*-
"""검색 품질 평가 스텁 — RAGAS의 context recall/precision. 구현은 나중.

입력: 골든셋(질문·기대 ref_key) + trace(retrieved_refs). 골든셋으로 자동 채점.
"""


def context_recall(expected_refs, retrieved_refs):
    """기대 ref_key 중 실제 검색된 비율 (재현율).

    RAGAS context_recall 근사: |expected ∩ retrieved| / |expected|.
    TODO: 구현. 지금은 시그니처만.
    """
    raise NotImplementedError("RAGAS context_recall — 나중에 구현 (trace 소비)")


def context_precision(expected_refs, retrieved_refs):
    """검색 결과 중 관련(기대) 비율 (정밀도), 순위 가중 옵션.

    TODO: 구현. RAGAS는 순위별 precision@k 평균 사용.
    """
    raise NotImplementedError("RAGAS context_precision — 나중에 구현")


def score_from_traces(goldenset_path, traces_path):
    """골든셋 × trace 로그를 조인해 케이스별 recall/precision 집계.

    TODO: goldenset.jsonl 로드 → 질문 매칭 → context_recall/precision 계산 → 요약.
    """
    raise NotImplementedError("골든셋-trace 자동 채점 — 나중에 구현")
