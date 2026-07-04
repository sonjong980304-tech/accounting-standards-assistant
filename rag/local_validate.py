# -*- coding: utf-8 -*-
"""--local(EXAONE) 5케이스: 게이트 완화 후 4개 답변 + 미국세법만 refusal 확인."""
from rag.graph import build_graph
from rag.search import Index
from rag import common as C

CKPT = C.ROOT / "rag" / "checkpoints_local.db"
CASES = [
    ("c1", "1년 임차 후 1년 연장하면 단기리스 면제 되나?", True),
    ("c2", "전환사채 풋옵션이 파생상품 정의를 충족하는지", True),
    ("c3", "중소기업 회계처리 특례를 적용하지 않다가 다시 적용할 수 있나?", True),
    ("c4", "미국 세법상 감가상각 내용연수는?", False),   # 근거없음 → refusal 유지 기대
]


def main():
    print("인덱스 로드(EXAONE, --local)...", flush=True)
    g = build_graph(Index(), checkpoint_path=CKPT, local=True)
    ok = True
    for th, q, expect_answer in CASES:
        st = g.invoke({"question": q}, {"configurable": {"thread_id": th}})
        a = st.get("answer", {})
        answered = a.get("has_grounds", False)
        mark = "OK" if answered == expect_answer else "✗불일치"
        if answered != expect_answer:
            ok = False
        print(f"\n[{th}] {q[:30]}")
        print(f"  검색근거: {[h['ref_key'] or h['doc_no'] for h in st.get('retrieved',[])][:3]}")
        print(f"  답변({'채택' if answered else 'refusal'}): {(a.get('answer') or '')[:100]}")
        print(f"  used_refs: {a.get('used_refs')} | 기대={expect_answer} → {mark}")
    # 5번: 대화기억 2턴
    st = g.invoke({"question": "1년 임차 후 1년 연장하면 단기리스 되나?"},
                  {"configurable": {"thread_id": "c5"}})
    st2 = g.invoke({"question": "그럼 리스부채는 어떻게 되나?"},
                   {"configurable": {"thread_id": "c5"}})
    print(f"\n[c5] 2턴 재작성: {st2.get('rewritten')}")
    print(f"  2턴 답변({'채택' if st2.get('answer',{}).get('has_grounds') else 'refusal'}): "
          f"{(st2.get('answer',{}).get('answer') or '')[:80]}")
    print(f"\n===== {'전체 기대 일치' if ok else '⚠️ 불일치 있음'} =====")


if __name__ == "__main__":
    main()
