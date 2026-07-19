# -*- coding: utf-8 -*-
"""README '생성 성능' 표의 4개 실제 사례(compare_models.py의 CASES와 동일 질문)를
GPT/EXAONE 두 경로로 재실행하며 각 노드(rewrite/route/answer) 실제 usage_metadata를 캡처.

- rewrite/route: rag.llm.LLM.complete()가 이미 raw OpenAI SDK 응답의 .usage를
  self.last_usage에 담아두므로, 이 메서드를 monkey-patch해 호출마다 기록.
- answer: rag.llm.answer_chat_model()이 항상 LangChain ChatOpenAI를 반환(GPT/로컬 공통,
  로컬은 base_url만 Ollama로 바뀜) → ChatOpenAI.invoke를 monkey-patch해
  응답의 .usage_metadata를 기록. 둘 다 프로덕션 코드(rag/graph.py, rag/llm.py)는
  전혀 수정하지 않음(읽기 전용 계측).

일회성 측정 스크립트. 결과는 매 케이스 즉시 JSONL에 append.
사용: python3 -m rag.eval.capture_token_usage
비용 환산은 references/llm_pricing.md의 확정 단가를 별도로 곱해서 계산할 것
(이 스크립트는 토큰 수만 실측 — 단가를 하드코딩하지 않음).
"""
import json
import time
from pathlib import Path

from langchain_openai import ChatOpenAI

import rag.llm as L
from rag import common as C
from rag.eval.compare_models import CASES, _env_key
from rag.graph import build_graph
from rag.search import Index

ROOT = C.ROOT
RESULTS = ROOT / "eval" / "results"
OUT = RESULTS / "token_usage.jsonl"

captured = []  # 현재 케이스 실행 중 캡처된 노드별 usage


def patched_complete(self, system, user, temperature=0.0, json_mode=False):
    text = _orig_complete(self, system, user, temperature=temperature, json_mode=json_mode)
    u = self.last_usage
    if u is not None:
        captured.append({"node": self.node, "model": self.model,
                          "prompt_tokens": u.prompt_tokens,
                          "completion_tokens": u.completion_tokens,
                          "total_tokens": u.total_tokens})
    return text


def patched_chat_invoke(self, *args, **kwargs):
    # streaming=True인 ChatOpenAI는 OpenAI 공식 엔드포인트가 아닌 base_url(Ollama 등)에서
    # stream_usage 기본값이 꺼져 있어 usage_metadata가 항상 None으로 온다(실측 확인).
    # 측정 목적으로만 인스턴스 속성을 켜서 우회 — 프로덕션 코드(rag/llm.py)는 건드리지 않음.
    self.stream_usage = True
    resp = _orig_chat_invoke(self, *args, **kwargs)
    um = getattr(resp, "usage_metadata", None)
    if um:
        captured.append({"node": "answer", "model": self.model_name,
                          "prompt_tokens": um.get("input_tokens"),
                          "completion_tokens": um.get("output_tokens"),
                          "total_tokens": um.get("total_tokens")})
    return resp


_orig_complete = L.LLM.complete
_orig_chat_invoke = ChatOpenAI.invoke
L.LLM.complete = patched_complete
ChatOpenAI.invoke = patched_chat_invoke


def run_case(index, label, question, model_name, local, openai_key, tag):
    global captured
    captured = []
    ckpt = ROOT / "rag" / "checkpoints_tokcap_{}.db".format(tag)
    # 신선한 첫 턴 상태 보장: 이전 실행의 체크포인트가 남아있으면 history가 이어져
    # entry edge가 route를 건너뛰고 rewrite로 잘못 진입한다(실측으로 발견된 문제).
    if ckpt.exists():
        ckpt.unlink()
    g = build_graph(index, checkpoint_path=ckpt, api_key=openai_key, local=local)
    t0 = time.time()
    st = g.invoke({"question": question}, {"configurable": {"thread_id": tag}})
    elapsed = time.time() - t0
    ans = st.get("answer", {})
    nodes = list(captured)
    total_prompt = sum(n["prompt_tokens"] for n in nodes)
    total_completion = sum(n["completion_tokens"] for n in nodes)
    ckpt.unlink(missing_ok=True)   # 측정용 임시 체크포인트 — 결과는 JSONL에 이미 저장됨
    return {
        "label": label, "question": question, "model": model_name,
        "elapsed_s": round(elapsed, 1),
        "has_grounds": ans.get("has_grounds", False),
        "nodes": nodes,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
    }


def main():
    openai_key = _env_key("OPENAI_API_KEY")
    assert openai_key, "OpenAI 키 필요(.env) — GPT 경로 생성용"

    print("인덱스 로드...", flush=True)
    index = Index()

    RESULTS.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fout:
        for i, (label, q) in enumerate(CASES):
            for model_name, local in (("GPT-5.5", False), ("EXAONE", True)):
                tag = "{}_{}".format(model_name.replace(".", ""), i)
                row = run_case(index, label, q, model_name, local, openai_key, tag)
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                fout.flush()
                print("[{}] {} — prompt={} completion={} total={} ({:.1f}s)".format(
                    label, model_name, row["total_prompt_tokens"],
                    row["total_completion_tokens"], row["total_tokens"], row["elapsed_s"]),
                    flush=True)

    print("저장:", OUT)


if __name__ == "__main__":
    main()
