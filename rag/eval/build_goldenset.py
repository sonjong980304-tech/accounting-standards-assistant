# -*- coding: utf-8 -*-
"""골든셋 구축: 질의회신 question + '조인 성공한' standard_refs만 정답으로.

- 정답 = standard_refs 중 실제 기준서 레코드(ref_key/section_key)와 매칭되는 것만.
  (노이즈 번호·미수집 기준서 ref는 검색이 못 찾는 게 당연 → 정답에서 제외해 recall 왜곡 방지)
- refs가 0개가 되는 질의회신은 제외(건수 보고).
- leakage 대비로 doc_no·board 함께 저장(평가 시 자기 자신 제외용).

스키마: {id, question, expected_collections, expected_ref_keys, expected_gist,
         qtype(원본 유지 안함→board), doc_no, board}
"""
import json
from pathlib import Path

from rag import common as C

QA_BOARDS = {"016001": "qa_kifrs", "016002": "qa_kifrs", "016005": "qa_kifrs",
             "016003": "qa_kgaap", "016006": "qa_kgaap"}
OUT = C.ROOT / "eval" / "goldenset.jsonl"
STATS = C.ROOT / "eval" / "goldenset_build_stats.json"


def load_standard_targets():
    """기준서 레코드의 조인 가능 키: 문단/장문단 ref_key, 용어 section_key.

    반환: ref_key→collection, section_key→collection.
    """
    ref2coll, sec2coll = {}, {}
    for coll in ("kifrs_standards", "kgaap_standards"):
        fn = "3001.jsonl" if coll == "kifrs_standards" else "3003.jsonl"
        for line in (C.PARSED / fn).open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("ref_key"):
                ref2coll.setdefault(r["ref_key"], coll)
            if r.get("section_key"):
                sec2coll.setdefault(r["section_key"], coll)
    return ref2coll, sec2coll


def main():
    ref2coll, sec2coll = load_standard_targets()
    print(f"기준서 조인 키: 문단/장문단 {len(ref2coll)} + 용어섹션 {len(sec2coll)}", flush=True)

    rows, skipped = [], []
    per_board = {}
    for board, _ in QA_BOARDS.items():
        for line in (C.PARSED / (board + ".jsonl")).open(encoding="utf-8"):
            r = json.loads(line)
            q = r.get("question")
            if not q:                      # body_fallback 등 질문 없는 글은 평가 부적합
                skipped.append((board, r["doc_no"], "no_question"))
                continue
            valid, colls = [], set()
            for ref in r.get("standard_refs", []):
                if ref in ref2coll:        # 문단/장문단 = 특정 레코드
                    valid.append(ref); colls.add(ref2coll[ref])
                elif ref in sec2coll:      # 용어섹션
                    valid.append(ref); colls.add(sec2coll[ref])
            valid = list(dict.fromkeys(valid))
            if not valid:                  # 조인되는 정답이 하나도 없음 → 제외
                skipped.append((board, r["doc_no"], "no_joinable_ref"))
                continue
            rows.append({
                "id": r["doc_no"],
                "question": q,
                "expected_collections": sorted(colls | {QA_BOARDS[board]}),
                "expected_ref_keys": valid,
                "expected_gist": (r.get("answer") or "")[:200],
                "doc_no": r["doc_no"],
                "board": board,
            })
            per_board[board] = per_board.get(board, 0) + 1

    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    reason = {}
    for _, _, why in skipped:
        reason[why] = reason.get(why, 0) + 1
    stats = {"golden": len(rows), "per_board": per_board,
             "skipped": len(skipped), "skip_reason": reason}
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n골든셋 {len(rows)}건 → {OUT}")
    print(f"게시판별: {per_board}")
    print(f"제외 {len(skipped)}건: {reason}")
    import numpy as np
    nrefs = [len(r["expected_ref_keys"]) for r in rows]
    print(f"정답 ref 개수: 평균 {np.mean(nrefs):.1f}, 중앙 {int(np.median(nrefs))}, 최대 {max(nrefs)}")


if __name__ == "__main__":
    main()
