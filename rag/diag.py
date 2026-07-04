# -*- coding: utf-8 -*-
"""진단: 기준서 타깃이 검색 풀에서 어디에 랭크되는지 + 컬렉션별 검색 확인."""
import re
from rag.search import Index, RRF_K, POOL_PER

QUERIES = [
    ("1년 임차 후 1년 연장하면 단기리스 해당 여부", "제1116호 문단 7", "kifrs_standards"),
    ("전환사채 풋옵션 파생상품 정의 충족", "제1109호 용어의 정의:파생상품", "kifrs_standards"),
]


def rank_of(index, query, target_ref):
    """dense/BM25/RRF 각 랭킹에서 target_ref의 순위 리포트."""
    dense = index._dense(query)
    bm25 = index._bm25(query)
    rrf = {}
    for lst in (dense, bm25):
        for r, i in enumerate(lst):
            rrf[i] = rrf.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
    fused = [i for i, _ in sorted(rrf.items(), key=lambda x: -x[1])]

    def find(lst):
        for r, i in enumerate(lst, 1):
            if index.metas[index.pos[i]].get("ref_key") == target_ref:
                return r
        return None
    return find(dense), find(bm25), find(fused)


def coll_search(index, query, coll, target_ref):
    """해당 컬렉션만 대상으로 dense top5(+리랭킹) — 라우팅 시 노출 여부."""
    col = index.client.get_collection(coll)
    qv = index.emb.encode([query], normalize_embeddings=True)[0].tolist()
    r = col.query(query_embeddings=[qv], n_results=30,
                  include=["documents", "metadatas"])
    ids = r["ids"][0]
    docs = r["documents"][0]
    metas = r["metadatas"][0]
    rr = index.reranker.predict([(query, d) for d in docs])
    order = sorted(range(len(ids)), key=lambda k: -rr[k])
    top = [(metas[k].get("ref_key"), float(rr[k])) for k in order[:5]]
    trank = next((n for n, k in enumerate(order, 1)
                  if metas[k].get("ref_key") == target_ref), None)
    return top, trank


def main():
    print("인덱스 로드 중...", flush=True)
    idx = Index()
    for q, target, coll in QUERIES:
        print(f"\n{'='*72}\n질의: {q}\n타깃: {target}\n{'='*72}")
        d, b, f = rank_of(idx, q, target)
        print(f"  전체 풀 순위 — dense: {d} / BM25: {b} / RRF: {f}  (None=풀에 없음)")
        top, tr = coll_search(idx, q, coll, target)
        print(f"  [{coll}]만 검색 시 리랭킹 top5에서 타깃 순위: {tr}")
        for n, (rk, s) in enumerate(top, 1):
            mark = " ★" if rk == target else ""
            print(f"     {n}. {s:6.3f}  {rk}{mark}")


if __name__ == "__main__":
    main()
