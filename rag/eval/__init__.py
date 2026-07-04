# -*- coding: utf-8 -*-
"""평가 스텁 (시그니처+TODO만, 구현은 나중).

평가는 RAGAS 지표로 나중에 구현하며, 입력은 graph.py가 남기는 trace 로그
(data/traces.jsonl)와 골든셋(eval/goldenset.jsonl)이다.

- retrieval:  context_recall, context_precision   (골든셋으로 자동 채점)
- generation: faithfulness, answer_relevancy       (LLM-as-Judge)
"""
