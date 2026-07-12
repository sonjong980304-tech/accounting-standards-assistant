# -*- coding: utf-8 -*-
"""정의조회 보너스 골든셋(30건) 평가 — 메인 배치와 별개, 검증된 score()/retrieve_routed() 재사용.

메인 골든셋(eval/goldenset.jsonl)과 절대 안 섞임. 결과도 별도 파일로 저장.
사용: python3 -m eval.run_definition_eval
"""
import json

from rag.eval.run_batch import RESULTS, got_keys, score
from rag.search import Index

GOLD = __import__("rag.common", fromlist=["ROOT"]).ROOT / "eval" / "goldenset_definition.jsonl"


def main():
    golden = [json.loads(l) for l in GOLD.open(encoding="utf-8")]
    print(f"정의조회 평가 {len(golden)}건, Index 로드...", flush=True)
    idx = Index()
    ks = (5, 10)
    per_q = []
    agg = {k: [] for k in ks}
    for g in golden:
        hits = idx.retrieve_routed(g["question"], g["expected_collections"],
                                   k=max(ks) + 3, min_standards=0, per_coll=50)
        exp = g["expected_ref_keys"]
        row = {"id": g["id"], "question": g["question"], "expected": exp}
        for k in ks:
            got = got_keys([h["meta"] for h in hits[:k]])
            ex, rel, ho, hitrate, nhit = score(exp, got)
            agg[k].append(ex)
            row[f"exact@{k}"] = ex
        per_q.append(row)
        print(f"  [{g['id']}] {g['question']} exact@5={row['exact@5']:.0f} exact@10={row['exact@10']:.0f}")

    summary = {f"exact@{k}": round(sum(v) / len(v), 4) for k, v in agg.items()}
    print("\n=== 정의조회 30건 결과 ===")
    print(f"  exact@5={summary['exact@5']:.3f}  exact@10={summary['exact@10']:.3f}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "definition_lookup.json").write_text(
        json.dumps({"summary": summary, "per_question": per_q}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"저장: {RESULTS / 'definition_lookup.json'}")


if __name__ == "__main__":
    main()
