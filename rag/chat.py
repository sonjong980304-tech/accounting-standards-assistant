# -*- coding: utf-8 -*-
"""RAG 챗 CLI: 질문 → (rewrite→route→retrieve→answer→verify) → 답변.

사용법:
    python3 -m rag.chat "1년 임차 후 1년 연장하면 단기리스 면제 되나?"
    python3 -m rag.chat --thread t1 --interactive           # 대화기억
    python3 -m rag.chat --local "..."                        # EXAONE(Ollama)

키: 환경변수 OPENAI_API_KEY 또는 .env. 없으면 안내(또는 --local).
"""
import argparse

from rag import common as C
from rag import llm as L
from rag.graph import build_graph
from rag.search import Index

CKPT = C.ROOT / "rag" / "checkpoints.db"


def show(state):
    a = state.get("answer", {})
    print("\n" + "─" * 72)
    print("재작성:", state.get("rewritten"))
    r = state.get("route", {})
    print("라우팅:", r.get("qtype"), "→", r.get("collections"))
    print("검색 근거:", [h["ref_key"] or h["doc_no"] for h in state.get("retrieved", [])])
    print("─" * 72)
    print("답변:", a.get("answer"))
    print("사용 ref:", a.get("used_refs"), "| 근거있음:", a.get("has_grounds"))
    ver = state.get("verified", [])
    if ver:
        print("\n[verify] DB 원문 조회 (LLM 재생성 아님):")
        for v in ver:
            m = v["metadata"]
            loc = m.get("url") or (m.get("src_file", "") + (
                " p.{}".format(m["page_no"]) if m.get("page_no") else ""))
            print("  · {} [{}]  {}".format(v["ref"], v["collection"], loc))
            print("      {}".format(v["text"][:120].replace("\n", " ")))
    # 노드 지연
    lat = {t["node"]: t.get("latency_ms") for t in state.get("trace", [])}
    print("\n지연(ms):", lat, "| 합계", sum(v for v in lat.values() if v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?")
    ap.add_argument("--thread", default="default", help="대화 thread_id (기억 단위)")
    ap.add_argument("--local", action="store_true", help="EXAONE 3.5 (Ollama)")
    ap.add_argument("--interactive", action="store_true")
    args = ap.parse_args()

    # 키/모델 사전 점검 (무거운 Index 로드 전에 안내)
    try:
        L.get_llm("route", local=args.local)
    except L.LLMError as e:
        print("[모델 준비 안됨]\n" + str(e))
        return

    print("인덱스 로드 중 (Chroma + BGE-M3 + 리랭커 + BM25)...", flush=True)
    index = Index()
    graph = build_graph(index, checkpoint_path=CKPT, local=args.local)
    cfg = {"configurable": {"thread_id": args.thread}}
    print(f"준비 완료 (thread={args.thread}, local={args.local})")

    def run(q):
        state = graph.invoke({"question": q}, cfg)
        show(state)

    if args.interactive:
        while True:
            try:
                q = input("\n질문> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q:
                run(q)
    elif args.query:
        run(args.query)
    else:
        ap.error("query 또는 --interactive 필요")


if __name__ == "__main__":
    main()
