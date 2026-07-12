# -*- coding: utf-8 -*-
"""기존 수집분을 raw 원본에서 재파싱 (네트워크 재요청 없음).

용도: pdfplumber 전환 + 구형 카드 스플리터 반영 후, 이미 저장된
body_fallback 레코드가 Q/A로 복구되는지 확인하고 JSONL을 갱신한다.

사용법:
    python3 reparse_qa.py 016001 016003        # 지정 게시판
    python3 reparse_qa.py --only-fallback ...   # body_fallback 레코드만
"""
import argparse
import glob
import json
from pathlib import Path

from crawler import (
    BOARDS, DATA, extract_standard_refs, log_failure, parse_detail,
    split_oldcard_qa, split_qa,
)
from parsers import ExtractError, extract_document_text


def reparse_record(board_id, rec):
    """레코드 1건 재파싱. (갱신된 rec, 변경여부) 반환."""
    cfg = BOARDS[board_id]
    # 016005 등 일부 게시판은 post_id 필드가 없음 → doc_no("게시판-seq")로 폴백
    seq = rec.get("post_id", rec["doc_no"]).split("-")[1]
    html_path = DATA / "raw" / board_id / "html" / (seq + ".html")
    if not html_path.exists():
        return rec, False
    d = parse_detail(html_path.read_text(encoding="utf-8"),
                     cfg.get("markers"), cfg.get("footer"))
    qa_source = "html"

    if d["question"] is None:
        hwp = next(iter(glob.glob(str(DATA / "raw" / board_id / "files"
                                       / (seq + "_*.hwp")))), None)
        pdf = next(iter(glob.glob(str(DATA / "raw" / board_id / "files"
                                       / (seq + "_*.pdf")))), None)
        if hwp or pdf:
            try:
                att_text, kind = extract_document_text(hwp, pdf)
                q2, a2, r2 = split_qa(att_text, cfg.get("markers"))
                tag = kind
                if q2 is None:
                    q2, a2, r2 = split_oldcard_qa(att_text)
                    tag = kind + ",oldcard"
                if q2 is not None:
                    d["question"], d["answer"], d["related"] = q2, a2, r2
                    qa_source = "attachment(" + tag + ")"
            except ExtractError as e:
                log_failure(board_id, seq, "reparse_extract", repr(e))

    rec["standard_refs"] = extract_standard_refs(d)
    if d["question"] is not None:
        rec["question"], rec["answer"] = d["question"], d["answer"]
        rec["qa_source"] = qa_source
        rec.pop("body", None)
        return rec, True
    # 여전히 실패 → body_fallback 유지
    rec["qa_source"] = "body_fallback"
    rec["body"] = d["body"]
    return rec, False


def reparse_board(board_id, only_fallback=True):
    path = DATA / "parsed" / (board_id + ".jsonl")
    if not path.exists():
        print(f"[{board_id}] JSONL 없음 — 스킵")
        return
    recs = [json.loads(l) for l in path.open(encoding="utf-8")]
    targets = [r for r in recs
               if not only_fallback or r.get("qa_source") == "body_fallback"]
    print(f"[{board_id}] 총 {len(recs)}건 중 대상 {len(targets)}건 재파싱")

    recovered = 0
    still_fb = []
    for rec in targets:
        _, changed = reparse_record(board_id, rec)
        if changed:
            recovered += 1
        elif rec.get("qa_source") == "body_fallback":
            still_fb.append(rec)

    with path.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    final_fb = [r for r in recs if r.get("qa_source") == "body_fallback"]
    print(f"  복구: {recovered}건 / 잔여 body_fallback: {len(final_fb)}건")
    for r in final_fb:
        print(f"    [잔여] {r['doc_no']} {r['title'][:36]!r} (첨부 {len(r.get('attachments', []))}개)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--all-records", action="store_true",
                    help="body_fallback뿐 아니라 전 레코드 재파싱")
    args = ap.parse_args()
    for b in args.boards:
        reparse_board(b, only_fallback=not args.all_records)


if __name__ == "__main__":
    main()
