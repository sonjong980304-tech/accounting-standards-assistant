# -*- coding: utf-8 -*-
"""질의회신 5개 게시판 전체 수집 드라이버 (1차).

- 게시판별 순차 (016001 → 016002 → 016003 → 016005 → 016006)
- 각 게시판 --all (전체 페이지), 요청 간 딜레이는 KasbClient가 담당
- state/ 재개, raw/ 원본 보관 (crawl_board가 처리)
- 게시판 1개 완료마다 집계 블록 출력 + progress.json 갱신
- body_fallback 비율 > 5% 이면 해당 게시판 중단 후 전체 종료 (원인 보고용)
"""
import json
from collections import Counter
from pathlib import Path

from crawler import DATA, FAILURES_LOG, FallbackGuardTripped, crawl_board

BOARD_ORDER = ["016001", "016002", "016003", "016005", "016006"]
MAX_FALLBACK_RATIO = 0.05
PROGRESS_PATH = DATA.parent / "qa_progress.json"


def board_stats(board_id):
    path = DATA / "parsed" / (board_id + ".jsonl")
    if not path.exists():
        return None
    recs = [json.loads(l) for l in path.open(encoding="utf-8")]
    srcs = Counter(r.get("qa_source", "html") for r in recs)
    n_fb = srcs.get("body_fallback", 0)
    stats = {
        "total": len(recs),
        "qa_source": dict(srcs),
        "body_fallback": n_fb,
        "fallback_ratio": (n_fb / len(recs)) if recs else 0.0,
        "official_doc_no": sum(1 for r in recs if not r["doc_no"].startswith(board_id)),
        "refs_zero": sum(1 for r in recs if not r.get("standard_refs")),
    }
    return stats


def count_failures():
    if not FAILURES_LOG.exists():
        return 0
    return sum(1 for _ in FAILURES_LOG.open(encoding="utf-8"))


def print_block(board_id, stats, new_failures):
    print("\n" + "=" * 60, flush=True)
    print(f"[집계] {board_id} 완료", flush=True)
    print(f"  누적 건수      : {stats['total']}", flush=True)
    print(f"  qa_source 분포 : {stats['qa_source']}", flush=True)
    print(f"  body_fallback  : {stats['body_fallback']}건 "
          f"({stats['fallback_ratio']:.1%})", flush=True)
    print(f"  공식 doc_no    : {stats['official_doc_no']}건", flush=True)
    print(f"  refs 0개       : {stats['refs_zero']}건", flush=True)
    print(f"  failures 신규  : {new_failures}건", flush=True)
    print("=" * 60 + "\n", flush=True)


def main():
    progress = {"completed": [], "boards": {}, "stopped": None}
    fail_before_all = count_failures()

    for board_id in BOARD_ORDER:
        fail_before = count_failures()
        print(f"\n########## {board_id} 수집 시작 ##########", flush=True)
        try:
            saved, skipped = crawl_board(
                board_id, max_fallback_ratio=MAX_FALLBACK_RATIO)
            tripped = False
        except FallbackGuardTripped as e:
            print("\n!!!!! 가드레일 발동 !!!!!", flush=True)
            print(" ", e, flush=True)
            saved, skipped, tripped = e.n_saved, 0, True

        stats = board_stats(board_id)
        new_failures = count_failures() - fail_before
        print_block(board_id, stats, new_failures)

        progress["boards"][board_id] = {
            "saved_this_run": saved, "skipped": skipped,
            "tripped": tripped, "new_failures": new_failures, **stats,
        }
        PROGRESS_PATH.write_text(
            json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")

        if tripped:
            progress["stopped"] = board_id
            PROGRESS_PATH.write_text(
                json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[중단] {board_id}에서 body_fallback 5% 초과 → 전체 종료", flush=True)
            return
        progress["completed"].append(board_id)

    # 전체 완료 요약
    print("\n########## 1차 질의회신 전체 완료 ##########", flush=True)
    grand = sum(progress["boards"][b]["total"] for b in progress["boards"])
    grand_fb = sum(progress["boards"][b]["body_fallback"] for b in progress["boards"])
    print(f"  총 {grand}건, body_fallback {grand_fb}건, "
          f"failures 신규 {count_failures() - fail_before_all}건", flush=True)
    print(f"  016002 refs 0개: {progress['boards']['016002']['refs_zero']}건", flush=True)
    PROGRESS_PATH.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
