# -*- coding: utf-8 -*-
"""검증 3케이스: 정답을 아는 질의로 end-to-end 확인 + 리랭커 전/후 순위 비교."""
from rag.search import Index, run

CASES = [
    "1년 임차 후 1년 연장하면 단기리스 면제 되나?",                 # 40677 + 제1116호 문단7
    "전환사채 풋옵션이 파생상품 정의를 충족하는지",                # 40670 + 제1109호 용어정의(파생상품)
    "중소기업 회계처리 특례를 적용하지 않다가 다시 적용할 수 있나?",   # qa_kgaap + 제31장
]
# 각 케이스에서 상위 5에 들기를 기대하는 타깃(정답 근거)
EXPECT = [
    ["016005-40677", "제1116호 문단 7"],
    ["016005-40670", "제1109호 용어의 정의:파생상품", "제1109호"],
    ["제31장", "중소기업"],
]


def main():
    print("인덱스 로드 중 (Chroma + BGE-M3 + 리랭커 + BM25)...", flush=True)
    idx = Index()
    print(f"준비 완료: 문서 {len(idx.docs)}건, 컬렉션 {idx.colls}\n", flush=True)
    for q, exp in zip(CASES, EXPECT):
        res = run(idx, q)   # 결과 재사용 (리랭커 중복 실행 방지)
        post_keys = []
        for i, _ in res["post"]:
            m = idx.metas[idx.pos[i]]
            post_keys.append((m.get("ref_key") or "") + " " + m.get("doc_no", ""))
        hit = [e for e in exp if any(e in k for k in post_keys)]
        print(f"\n  ▶ 기대 근거 {exp} 중 상위5 적중: {hit if hit else '없음 ✗'}")


if __name__ == "__main__":
    main()
