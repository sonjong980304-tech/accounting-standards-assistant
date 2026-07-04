# -*- coding: utf-8 -*-
"""3단계 검증: 5케이스(라우팅·환각방지·대화기억) + 측정(JSON 깨짐률·노드 지연)."""
import json

from rag.graph import build_graph
from rag.search import Index
from rag import common as C

CKPT = C.ROOT / "rag" / "checkpoints_validate.db"


def brief(state):
    a = state.get("answer", {})
    r = state.get("route", {})
    return {
        "rewritten": state.get("rewritten"),
        "qtype": r.get("qtype"), "collections": r.get("collections"),
        "retrieved": [h["ref_key"] or h["doc_no"] for h in state.get("retrieved", [])],
        "answer": (a.get("answer") or "")[:160],
        "used_refs": a.get("used_refs"), "has_grounds": a.get("has_grounds"),
        "verified": [v["ref"] for v in state.get("verified", [])],
        "trace": state.get("trace", []),
    }


def collect_json_flags(trace):
    return [(t["node"], t.get("json_ok")) for t in trace if "json_ok" in t]


def main():
    print("인덱스 로드 중...", flush=True)
    idx = Index()
    graph = build_graph(idx, checkpoint_path=CKPT)
    json_flags, latencies = [], []

    def run(q, thread):
        st = graph.invoke({"question": q},
                          {"configurable": {"thread_id": thread}})
        b = brief(st)
        json_flags.extend(collect_json_flags(b["trace"]))
        latencies.append({t["node"]: t.get("latency_ms") for t in b["trace"]})
        return b

    print("\n########## 케이스 1: 단기리스 연장 (라우팅+검증) ##########")
    b = run("1년 임차 후 1년 연장하면 단기리스 면제 되나?", "c1")
    print(f"  라우팅: {b['qtype']} → {b['collections']}")
    print(f"  검색: {b['retrieved']}")
    print(f"  답변: {b['answer']}")
    print(f"  used_refs: {b['used_refs']} | verify원문: {b['verified']}")
    hit_qa = any("40677" in x for x in b["retrieved"])
    hit_std = any("제1116호" in x for x in b["retrieved"])
    print(f"  ▶ 40677 검색={hit_qa}, 제1116호 근거={hit_std}, verify반환={len(b['verified'])>0}")

    print("\n########## 케이스 2: 파생상품 정의 (정의조회 라우팅) ##########")
    b = run("전환사채 풋옵션이 파생상품 정의를 충족하는지", "c2")
    print(f"  라우팅: {b['qtype']} → {b['collections']}")
    print(f"  검색: {b['retrieved']}")
    print(f"  답변: {b['answer']}")
    hit = any("40670" in x for x in b["retrieved"])
    hit_term = any("용어의 정의" in x or "제1109호" in x for x in b["retrieved"])
    print(f"  ▶ 40670 검색={hit}, 제1109호/용어정의 근거={hit_term}")

    print("\n########## 케이스 3: 중소기업 특례 (KGAAP 라우팅) ##########")
    b = run("중소기업 회계처리 특례를 적용하지 않다가 다시 적용할 수 있나?", "c3")
    print(f"  라우팅: {b['qtype']} → {b['collections']}")
    print(f"  검색: {b['retrieved']}")
    print(f"  답변: {b['answer']}")
    kgaap = any(c.startswith("qa_kgaap") or c == "kgaap_standards" for c in b["collections"])
    print(f"  ▶ KGAAP 라우팅={kgaap}, 검색근거 {len(b['retrieved'])}건")

    print("\n########## 케이스 4: 근거없는 질문 (환각 방지) ##########")
    b = run("미국 세법상 감가상각 내용연수는?", "c4")
    print(f"  라우팅: {b['qtype']} → {b['collections']}")
    print(f"  검색: {b['retrieved']}")
    print(f"  답변: {b['answer']}")
    refused = (not b["has_grounds"]) or ("근거를 찾지 못" in (b["answer"] or ""))
    print(f"  ▶ 환각 방지(근거없음 명시)={refused}")

    print("\n########## 케이스 5: 대화기억 (같은 thread 2턴) ##########")
    b1 = run("1년 임차 후 1년 연장하면 단기리스 되나?", "c5")
    print(f"  1턴 재작성: {b1['rewritten']}")
    b2 = run("그럼 리스부채는 어떻게 되나?", "c5")
    print(f"  2턴 원질문: 그럼 리스부채는 어떻게 되나?")
    print(f"  2턴 재작성: {b2['rewritten']}")
    print(f"  2턴 답변: {b2['answer']}")
    expanded = ("리스" in b2["rewritten"] and len(b2["rewritten"]) > len("그럼 리스부채는 어떻게 되나?"))
    print(f"  ▶ 후속질문 독립화(맥락 반영)={expanded}")

    print("\n########## 측정 ##########")
    n = len(json_flags)
    broken = [f for f in json_flags if f[1] is False]
    print(f"  JSON 출력: {n}회 중 깨짐 {len(broken)}건 ({100*len(broken)/max(n,1):.0f}%)  {broken}")
    from collections import defaultdict
    agg = defaultdict(list)
    for lat in latencies:
        for node, ms in lat.items():
            if ms is not None:
                agg[node].append(ms)
    print("  노드별 평균 지연(ms):",
          {k: int(sum(v) / len(v)) for k, v in agg.items()})


if __name__ == "__main__":
    main()
