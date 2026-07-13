# -*- coding: utf-8 -*-
"""KASB 기준서 게시판 크롤러 (K-IFRS 3001 / 일반기업회계기준 3003).

질의회신 크롤러(crawler.py)와 달리 목록이 단일 페이지이고
첨부(HWP+PDF)가 목록에서 바로 노출된다.

사용법:
    python3 -m crawl.standards_crawler --board 3001 --match "제1109호|제1116호" --limit 3
    python3 -m crawl.standards_crawler --board 3001 --all
"""
import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from crawl.crawler import BASE_URL, DATA, KasbClient, log_failure, now_iso, sanitize_filename
from parsers import (
    ExtractError,
    extract_document_text,
    extract_term_records,
    fill_page_numbers,
    split_kgaap_chapter,
    split_standard,
)

STD_BOARDS = {
    "3001": {
        "source": "K-IFRS기준서",
        "list_path": "/front/board/ingAccountingList.do",
        "kind": "kifrs",   # 제N호 체계 → 문단/용어 파싱 지원
    },
    "3003": {
        "source": "일반기업회계기준",
        "list_path": "/front/board/List3003.do",
        "kind": "kgaap",   # 제N장 체계 → split_kgaap_chapter로 문단 분리
    },
}

RE_STD_DETAIL = re.compile(r"fn_Detail\('(\d+)','(\d+)'\)")
RE_FILE_DL = re.compile(r"fileDownload\('(-?\d+)','(\d+)'\)")
RE_KIFRS_TITLE = re.compile(r"제(\d{3,4})호\s*(.+)$")
RE_KGAAP_TITLE = re.compile(r"제(\d{1,2})장\s*(.+)$")


def parse_std_list(html, board_id):
    """기준서 목록 → [{seq, title, attachments:[{file_no,file_seq,name}]}]."""
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for a in soup.find_all("a", onclick=RE_STD_DETAIL):
        m = RE_STD_DETAIL.search(a["onclick"])
        if m.group(1) != board_id:
            continue
        tr = a.find_parent("tr")
        atts = []
        if tr:
            for fa in tr.find_all("a", onclick=RE_FILE_DL):
                fm = RE_FILE_DL.search(fa["onclick"])
                name = fa.get_text(strip=True)
                if name:
                    atts.append({"file_no": fm.group(1), "file_seq": fm.group(2),
                                 "name": name})
        rows.append({"seq": m.group(2), "title": a.get_text(strip=True),
                     "attachments": atts})
    return rows


class StdStore:
    def __init__(self, board_id):
        self.board_id = board_id
        self.file_dir = DATA / "raw" / board_id / "files"
        self.text_dir = DATA / "raw" / board_id / "text"
        self.jsonl_path = DATA / "parsed" / (board_id + ".jsonl")
        self.state_path = DATA / "state" / (board_id + ".json")
        for d in (self.file_dir, self.text_dir,
                  self.jsonl_path.parent, self.state_path.parent):
            d.mkdir(parents=True, exist_ok=True)
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        else:
            self.state = {"collected": [], "updated_at": None}
        self._collected = set(self.state["collected"])

    def is_collected(self, seq):
        return seq in self._collected

    def find_file(self, seq, ext):
        hits = sorted(self.file_dir.glob("{}_*.{}".format(seq, ext)))
        return hits[0] if hits else None

    def mark_collected(self, seq):
        self._collected.add(seq)
        self.state["collected"] = sorted(self._collected)
        self.state["updated_at"] = now_iso()
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_records(self, records):
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _download_attachment(client, store, seq, att):
    """첨부 1개 다운로드(이미 있으면 스킵). 저장 경로 반환."""
    ext = att["name"].rsplit(".", 1)[-1].lower()
    existing = store.find_file(seq, ext)
    if existing:
        return existing
    content, server_name = client.download_file(att["file_no"], att["file_seq"])
    fname = sanitize_filename(server_name or att["name"])
    path = store.file_dir / "{}_{}".format(seq, fname)
    path.write_bytes(content)
    return path


def crawl_one_standard(client, store, cfg, board_id, row):
    seq, title = row["seq"], row["title"]
    hwp_att = next((a for a in row["attachments"]
                    if a["name"].lower().endswith(".hwp")), None)
    pdf_att = next((a for a in row["attachments"]
                    if a["name"].lower().endswith(".pdf")), None)
    if not hwp_att and not pdf_att:
        log_failure(board_id, seq, "attachment", "HWP/PDF 첨부 없음: " + title)
        return 0

    hwp_path = _download_attachment(client, store, seq, hwp_att) if hwp_att else None
    pdf_path = _download_attachment(client, store, seq, pdf_att) if pdf_att else None

    # 텍스트 추출 (캐시: hwp5html이 파일당 ~30초라 재실행 대비 필수)
    text_path = store.text_dir / (seq + ".txt")
    if text_path.exists():
        text, text_src = text_path.read_text(encoding="utf-8"), "cache"
    else:
        try:
            text, text_src = extract_document_text(hwp_path, pdf_path)
        except ExtractError as e:
            log_failure(board_id, seq, "extract", repr(e))
            return 0
        text_path.write_text(text, encoding="utf-8")

    common = {
        "source": cfg["source"],
        "board_id": board_id,
        "doc_no": "{}-{}".format(board_id, seq),
        "standard_title": title,
        "src_file": hwp_path.name if hwp_path else (pdf_path.name if pdf_path else None),
        "crawled_at": now_iso(),
    }

    if cfg["kind"] == "kgaap":
        # 일반기업(제N장 체계): "31.9 …" 문단 분리. 장 형식이 아닌 문서
        # (예: 재무회계개념체계)는 원본+텍스트만 수집
        km = RE_KGAAP_TITLE.match(title)
        if not km:
            log_failure(board_id, seq, "title_parse",
                        "제N장 형식 아님(원본만 보관): " + title)
            store.mark_collected(seq)
            return 1
        chapter, ch_title = km.group(1), km.group(2).strip()
        paras = split_kgaap_chapter(text, chapter)
        records = []
        for p in paras:
            rec = dict(common, record_type="paragraph",
                       standard_no="제{}장".format(int(chapter)),
                       standard_name=ch_title)
            rec.update(p)
            records.append(rec)
        store.append_records(records)
        store.mark_collected(seq)
        print("  [OK] seq={} 제{}장 {!r}: 문단 {}건 [text={}]".format(
            seq, int(chapter), ch_title[:24], len(paras), text_src))
        return 1

    m = RE_KIFRS_TITLE.match(title)
    if not m:
        log_failure(board_id, seq, "title_parse", "제N호 형식 아님: " + title)
        store.mark_collected(seq)  # 원본은 확보됨
        return 1
    std_no, std_title = m.group(1), m.group(2).strip()

    paras = split_standard(text, std_no)
    terms = extract_term_records(text, std_no, src_file=common["src_file"])
    if terms and pdf_path:
        for miss in fill_page_numbers(terms, pdf_path):
            log_failure(board_id, seq, "page_no", "용어 {!r} PDF 재탐색 실패".format(miss["term"]))

    records = []
    for p in paras:
        rec = dict(common, record_type="paragraph", standard_no=std_no,
                   standard_name=std_title)
        rec.update(p)
        records.append(rec)
    for t in terms:
        rec = dict(common, record_type="term", standard_no=std_no,
                   standard_name=std_title)
        rec.update(t)
        records.append(rec)
    store.append_records(records)
    store.mark_collected(seq)
    n_pg = sum(1 for t in terms if t.get("page_no"))
    print("  [OK] seq={} 제{}호 {!r}: 문단 {}건 + 용어 {}건(page_no {}/{}) [text={}]".format(
        seq, std_no, std_title[:24], len(paras), len(terms), n_pg, len(terms), text_src))
    return 1


def crawl_standards(board_id, match=None, limit=None):
    cfg = STD_BOARDS[board_id]
    client = KasbClient(cfg["list_path"])
    store = StdStore(board_id)
    html = client.get_html(cfg["list_path"])
    rows = parse_std_list(html, board_id)
    print("[{}] 목록 {}건".format(board_id, len(rows)))

    n_saved = n_skipped = 0
    for row in rows:
        if limit is not None and n_saved >= limit:
            break
        if match and not re.search(match, row["title"]):
            continue
        if store.is_collected(row["seq"]):
            n_skipped += 1
            continue
        try:
            n_saved += crawl_one_standard(client, store, cfg, board_id, row)
        except Exception as e:  # noqa: BLE001 — 실패는 기록하고 계속
            log_failure(board_id, row["seq"], "standard", repr(e))
    return n_saved, n_skipped


def main():
    ap = argparse.ArgumentParser(description="KASB 기준서 크롤러")
    ap.add_argument("--board", default="3001", choices=sorted(STD_BOARDS))
    ap.add_argument("--match", default=None, help="제목 정규식 필터 (예: '제1109호|제1116호')")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if not args.all and args.limit is None and args.match is None:
        ap.error("--match / --limit / --all 중 하나는 지정 (전체 일괄 수집 방지)")
    saved, skipped = crawl_standards(args.board, match=args.match, limit=args.limit)
    print("\n완료: 신규 {}건, 기수집 {}건 스킵".format(saved, skipped))


if __name__ == "__main__":
    main()
