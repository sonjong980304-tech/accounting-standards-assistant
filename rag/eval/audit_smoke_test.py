# -*- coding: utf-8 -*-
"""AC12: 감리지적사례 자가회수 스모크테스트 (65건 전수 자동 판정).

각 사례의 facts 앞부분을 질의로 audit_cases 컬렉션을 dense+리랭킹 검색해, 자기 자신이
top-k(기본 3) 안에 회수되는지 자동 판정하고 통과율을 출력한다.

주의: 여기서는 **표시 임계값(AUDIT_CASE_SCORE_THRESHOLD)을 적용하지 않는다** — 이 테스트는
순수 '회수/랭킹' 성능(top-k 안에 드는가)을 재는 것이고, 임계값은 '표시/숨김'을 가르는 별개
장치이기 때문이다. 대신 자기매칭 리랭커 점수의 분포를 함께 출력해 임계값 튜닝의 근거로 쓴다.

실행(무거움 — Chroma + BGE-M3 + 리랭커 로드, 수 분):
    python3 -m rag.eval.audit_smoke_test [--prefix 120] [--k 3]
사전조건: `python3 -m rag.sync_audit_cases` 로 audit_cases 컬렉션 임베딩 완료.
"""
import argparse
import json
import statistics

from rag import common as C
from rag.search import Index


def load_cases():
    path = C.PARSED / C.AUDIT_COLLECTIONS["audit_cases"][0]
    if not path.exists():
        raise SystemExit(f"{path} 없음 — 먼저 `python3 -m rag.sync_audit_cases` 실행")
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", type=int, default=120, help="질의로 쓸 facts 앞 글자수")
    ap.add_argument("--k", type=int, default=3, help="top-k 회수 판정 기준")
    args = ap.parse_args()

    cases = load_cases()
    print(f"감리사례 {len(cases)}건 자가회수 스모크테스트 "
          f"(top-{args.k}, 질의=facts[:{args.prefix}])", flush=True)
    print("인덱스 로드 중 (Chroma + BGE-M3 + 리랭커)...", flush=True)
    idx = Index()
    if "audit_cases" not in idx.colls:
        raise SystemExit("audit_cases 컬렉션이 로드되지 않음 — 임베딩 여부를 확인하세요.")

    passed = 0
    self_scores = []
    fails = []
    for rec in cases:
        cid = rec.get("case_id", "")
        query = (rec.get("facts", "") or "")[:args.prefix]
        hits = idx.retrieve_routed(query, ["audit_cases"], k=args.k,
                                   min_standards=0, per_coll=len(cases))
        top_ids = [h["meta"].get("case_id") for h in hits]
        if cid in top_ids:
            passed += 1
            self_scores.append(float(hits[top_ids.index(cid)]["score"]))
        else:
            fails.append((cid, rec.get("title", ""), top_ids))

    n = len(cases)
    print(f"\n=== 자가회수율: {passed}/{n} = {100 * passed / n:.1f}% (top-{args.k}) ===")
    if self_scores:
        print("자기매칭 리랭커 점수 분포: "
              f"min {min(self_scores):.3f} · median {statistics.median(self_scores):.3f} "
              f"· max {max(self_scores):.3f}")
        print("  → AUDIT_CASE_SCORE_THRESHOLD 는 이 최솟값보다 낮게 잡아야 자기회수분이 표시됨.")
    if fails:
        print(f"\n미회수 {len(fails)}건:")
        for cid, title, tops in fails:
            print(f"  - [{cid}] {title[:34]} → top: {tops}")
    # 통과 기준(예: 100% 또는 사전 합의 최소치)은 사람이 결과를 보고 1회 확정(스펙 AC12 노트).


if __name__ == "__main__":
    main()
