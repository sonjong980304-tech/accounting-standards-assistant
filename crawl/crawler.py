# -*- coding: utf-8 -*-
"""KASB(한국회계기준원) 질의회신 게시판 크롤러.

작업 순서 2단계: 단일 게시판(List016005) 크롤러.
사용법:
    python3 -m crawl.crawler --board 016005 --limit 3    # 3건 테스트
    python3 -m crawl.crawler --board 016005 --pages 1    # 1페이지
    python3 -m crawl.crawler --board 016005 --all        # 전체
"""
import argparse
import json
import random
import re
import sys
import time
import urllib.parse
import warnings
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from refs import extract_intl_refs, extract_refs
from parsers import ExtractError, extract_document_text

warnings.filterwarnings("ignore")

BASE_URL = "https://www.kasb.or.kr"
SITE_CD = "002000000000000"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FAILURES_LOG = ROOT / "failures.log"

# 본문 Q/A 마커: 게시판별로 헤딩 형식이 다름. 각 항목은 "대안 패턴 목록"
# (연식별 변형 대비 — 첫 매칭 사용). 신속처리(016005/016006)는 [질의]/[회신] 괄호형.
DEFAULT_MARKERS = {
    "q": [r"\[\s*질\s*의\s*\]"],
    "a": [r"\[\s*회\s*신\s*\]"],
    "rel": [r"\[\s*관련\s*회계기준\s*\]"],
}

BOARDS = {
    "016001": {
        "source": "K-IFRS질의회신",
        "list_path": "/front/board/List016001.do",
        # 신형: 본문에 "배경 및 질의/회신/판단근거" 헤딩.
        # 구형: 본문은 색인 카드뿐, Q/A는 첨부 PDF에만 → 비앵커 패턴이 첨부용
        # (pypdf 추출문은 줄바꿈이 거의 없어 ^…$ 앵커가 안 걸림)
        "markers": {
            "q": [r"^배경 및 질의$", r"^질의\s*내용$", r"\[\s*질\s*의\s*\]",
                  r"배경 및 질의"],
            "a": [r"^회신$", r"\[\s*회\s*신\s*\]", r"회신(?=\s*\d)"],
            "rel": [r"^판단근거$", r"^관련\s*회계기준$", r"판단근거"],
        },
        "footer": [r"^이 자료는 한국회계기준원이"],
    },
    "016002": {
        "source": "IFRS해석위원회",
        "list_path": "/front/board/List016002.do",
        "markers": {   # "1. 질의 내용" / "2. 검토 내용과 결정|조사 결과와 결론"
            "q": [r"^1\.\s*질의\s*내용$"],
            "a": [r"^2\.\s*검토\s*내용과?\s*결정$", r"^2\.\s*조사\s*결과와?\s*결론$"],
            "rel": [],
        },
        "footer": [r"^●\s*색인어", r"^●\s*Notice", r"^●\s*알림"],
    },
    "016003": {
        "source": "일반기업질의회신",
        "list_path": "/front/board/List016003.do",
        "markers": {   # 아라비아("1.질의현황"…)/로마숫자("Ⅰ.현황 Ⅱ.질의 Ⅲ.회신") 혼재
            # 번호(아라비아/로마) + . + '(질의)현황' 또는 '질의…' / '회신…' 헤딩.
            # 현황을 우선 잡아 배경까지 질문에 포함. 회신은 '회신 내용/요약'도 매칭($ 없음).
            "q": [r"(?m)^\s*(?:\d+|[ⅠⅡⅢⅣⅤⅥIVX]+)\s*\.\s*(?:질의\s*)?현황",
                  r"(?m)^\s*(?:\d+|[ⅠⅡⅢⅣⅤⅥIVX]+)\s*\.\s*질\s*의",
                  r"\[\s*질\s*의\s*\]"],
            "a": [r"(?m)^\s*(?:\d+|[ⅠⅡⅢⅣⅤⅥIVX]+)\s*\.\s*회\s*신",
                  r"\[\s*회\s*신\s*\]"],
            "rel": [r"^판단근거(?:\(질의\d+\))?$"],
        },
    },
    "016005": {
        "source": "K-IFRS신속처리",
        "list_path": "/front/board/List016005.do",
        "markers": DEFAULT_MARKERS,
    },
    "016006": {
        "source": "일반기업신속처리",
        "list_path": "/front/board/List016006.do",
        "markers": {   # 괄호형([질의]) + 아라비아/로마 헤딩형 혼재 (016003과 동일 계열)
            "q": [r"\[\s*질\s*의\s*\]",
                  r"(?m)^\s*(?:\d+|[ⅠⅡⅢⅣⅤⅥIVX]+)\s*\.\s*(?:질의\s*)?현황",
                  r"(?m)^\s*(?:\d+|[ⅠⅡⅢⅣⅤⅥIVX]+)\s*\.\s*질\s*의"],
            "a": [r"\[\s*회\s*신\s*\]",
                  r"(?m)^\s*(?:\d+|[ⅠⅡⅢⅣⅤⅥIVX]+)\s*\.\s*회\s*신"],
            "rel": [r"\[\s*관련\s*회계기준\s*\]", r"^판단근거(?:\(질의\d+\))?$"],
        },
    },
}

RE_DETAIL_CALL = re.compile(r"fn_Detail\('(\d+)','(\d+)'\)")
RE_FILE_DOWNLOAD = re.compile(r"fileDownload\('(-?\d+)','(\d+)'\)")
# 기준서 참조 추출/정규화는 공용 모듈 refs.py 사용 (질의회신·기준서 파서 공유 필수)
RE_DISCLAIMER = re.compile(r"[‘']신속처리질의[’']\s*는")
# 공식 문서번호 (첨부 파일명에서 추출, 예: 2025-I-KQA006 / 2025-G-KQA001)
RE_OFFICIAL_NO = re.compile(r"\d{4}-[A-Z]{1,3}-[A-Z]{2,5}\d+")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log_failure(board_id, seq, stage, err):
    line = f"{now_iso()}\tboard={board_id}\tseq={seq}\tstage={stage}\t{err}\n"
    with open(FAILURES_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"  [FAIL] {stage} seq={seq}: {err}", file=sys.stderr)


class KasbClient:
    """세션/딜레이/인코딩을 책임지는 HTTP 클라이언트."""

    def __init__(self, list_path):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": BASE_URL + list_path,
        })
        self._first = True

    def _nap(self):
        if self._first:          # 첫 요청은 딜레이 불필요
            self._first = False
            return
        time.sleep(1.0 + random.uniform(0.0, 1.0))  # 1~2초 jitter

    def get_html(self, path, params=None):
        self._nap()
        r = self.s.get(BASE_URL + path, params=params, timeout=30)
        r.raise_for_status()
        r.encoding = "utf-8"     # 역분석 확인: 사이트는 UTF-8
        return r.text

    def post_html(self, path, data):
        self._nap()
        r = self.s.post(BASE_URL + path, data=data, timeout=30)
        r.raise_for_status()
        r.encoding = "utf-8"
        return r.text

    def download_file(self, file_no, file_seq):
        """첨부 다운로드. (bytes, 서버가 준 파일명 or None) 반환."""
        self._nap()
        r = self.s.post(
            BASE_URL + "/commonFile/fileDownload.do",
            data={"fileNo": file_no, "fileSeq": file_seq},
            timeout=60,
        )
        r.raise_for_status()
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(
            r'filename="?([^";]+)"?', cd
        )
        fname = urllib.parse.unquote(m.group(1)) if m else None
        return r.content, fname


# ---------------------------------------------------------------- 목록 파싱

def parse_list_rows(html, board_ctg):
    """목록 HTML → [{seq, title, reply_date, open_date}] (공지 제외)."""
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for a in soup.find_all("a", onclick=RE_DETAIL_CALL):
        m = RE_DETAIL_CALL.search(a["onclick"])
        seq, ctg = m.group(1), m.group(2)
        if ctg != board_ctg:     # 상단 고정 공지(016009 등) 제외
            continue
        tr = a.find_parent("tr")
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")] if tr else []
        # 컬럼: 번호/제목/첨부/회신일/공개일
        rows.append({
            "seq": seq,
            "title": a.get_text(strip=True),
            "reply_date": tds[3] if len(tds) > 3 else "",
            "open_date": tds[4] if len(tds) > 4 else "",
        })
    return rows


def last_page_no(html):
    """페이지네이션의 Last 링크에서 전체 페이지 수 추출."""
    nums = re.findall(r"G_MovePage\((\d+)\)", html)
    return max(int(n) for n in nums) if nums else 1


# ---------------------------------------------------------------- 상세 파싱

def parse_detail(html, markers=None, footer=None):
    """상세 HTML → 메타/본문/첨부 dict."""
    soup = BeautifulSoup(html, "lxml")

    # 1) 메타 테이블 (th → 바로 옆 td)
    meta = {}
    view_wrap = soup.find("div", class_=re.compile(r"board_view_wrap"))
    if view_wrap:
        for th in view_wrap.find_all("th"):
            td = th.find_next_sibling("td")
            if td is not None:
                meta[th.get_text(strip=True)] = td.get_text(" ", strip=True)

    # 2) 첨부 (fileNo, fileSeq, 표시 파일명)
    attachments = []
    fbox = soup.find("div", class_="board_view_file")
    if fbox:
        for a in fbox.find_all("a", onclick=RE_FILE_DOWNLOAD):
            m = RE_FILE_DOWNLOAD.search(a["onclick"])
            name = a.get_text(strip=True)
            attachments.append({
                "file_no": m.group(1), "file_seq": m.group(2), "name": name,
            })

    # 3) 본문 텍스트 (면책/푸터 문구 제거)
    cont = soup.find("div", class_=re.compile(r"board_view_cont"))
    body_text = cont.get_text("\n", strip=True) if cont else ""
    dm = RE_DISCLAIMER.search(body_text)
    if dm:
        body_text = body_text[: dm.start()].rstrip()
    for pat in (footer or []):
        fm = re.compile(pat, re.M).search(body_text)
        # 앞부분 오탐 방지: 본문 후반부(40% 이후)에 있을 때만 푸터로 간주
        if fm and fm.start() > len(body_text) * 0.4:
            body_text = body_text[: fm.start()].rstrip()
            break

    # 4) 질의/회신 분리 (게시판별 마커)
    question, answer, related = split_qa(body_text, markers)

    return {
        "meta": meta,
        "attachments": attachments,
        "body": body_text,
        "question": question,
        "answer": answer,
        "related": related,
    }


def _find_first(patterns, text, offset=0):
    """대안 패턴 목록 중 첫 매칭 반환 (offset 이후에서 탐색, 멀티라인)."""
    for pat in patterns:
        m = re.compile(pat, re.M).search(text, offset)
        if m:
            return m
    return None


def split_qa(body_text, markers=None):
    """본문을 게시판별 질의/회신/관련근거 마커로 분리.

    - 회신 마커는 질의 마커 '이후'에서만 탐색 ("질의회신" 같은 앞부분 오탐 방지)
    - 분리 실패 또는 빈 질의/회신 → (None, None, None)
      (빈 Q/A를 조용히 통과시키지 않음 — 호출부가 실패 기록 + body 폴백)
    """
    mk = markers or DEFAULT_MARKERS
    mq = _find_first(mk["q"], body_text)
    if not mq:
        return None, None, None
    ma = _find_first(mk["a"], body_text, mq.end())
    if not ma:
        return None, None, None
    mr = _find_first(mk.get("rel") or [], body_text, ma.end())
    question = body_text[mq.end(): ma.start()].strip()
    if mr:
        answer = body_text[ma.end(): mr.start()].strip()
        related = body_text[mr.end():].strip()
    else:
        answer = body_text[ma.end():].strip()
        related = None
    if not question or not answer:
        return None, None, None
    return question, answer, related


def extract_standard_refs(detail):
    """메타(기준서 명) + 본문에서 기준서 참조 추출.

    정규화/추출/중복제거 규칙은 공용 모듈 refs.py가 단일 소스로 관리한다
    (질의회신 standard_refs ↔ 기준서 문단 ref_key 조인 보장).
    """
    sources = [
        detail["meta"].get("기준서 명", ""),
        detail.get("question"),
        detail.get("answer"),
        detail.get("related"),
    ]
    if detail.get("question") is None:
        # Q/A 분리 실패(body 폴백) 문서도 참조는 본문에서 최대한 추출
        sources.append(detail.get("body"))
    refs = extract_refs(*sources)
    seen = set(refs)
    for r in extract_intl_refs(*sources):    # IFRS/IAS/IFRIC/SIC 국제표기 → 한국 기준서번호
        if r not in seen:
            seen.add(r)
            refs.append(r)
    return refs


# ---------------------------------------------------------------- 상태/저장

def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip() or "unnamed"


class BoardStore:
    def __init__(self, board_id):
        self.board_id = board_id
        self.raw_html_dir = DATA / "raw" / board_id / "html"
        self.raw_file_dir = DATA / "raw" / board_id / "files"
        self.jsonl_path = DATA / "parsed" / (board_id + ".jsonl")
        self.state_path = DATA / "state" / (board_id + ".json")
        for d in (self.raw_html_dir, self.raw_file_dir,
                  self.jsonl_path.parent, self.state_path.parent):
            d.mkdir(parents=True, exist_ok=True)
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        else:
            self.state = {"collected": [], "updated_at": None}
        self._collected = set(self.state["collected"])

    def is_collected(self, seq):
        return seq in self._collected

    def save_record(self, seq, record, raw_html):
        (self.raw_html_dir / (seq + ".html")).write_text(raw_html, encoding="utf-8")
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._collected.add(seq)
        self.state["collected"] = sorted(self._collected)
        self.state["updated_at"] = now_iso()
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def save_attachment(self, seq, filename, content):
        path = self.raw_file_dir / (seq + "_" + sanitize_filename(filename))
        path.write_bytes(content)
        return path


# ---------------------------------------------------------------- 크롤 본체

def list_page_payload(page_no):
    return {
        "siteCd": SITE_CD, "seq": "", "ctgCd": "", "replySummary": "N",
        "searchfield": "ALL", "searchword": "",
        "s_date_start": "", "s_date_end": "", "page": str(page_no),
    }


def detail_url(board_id, seq):
    params = urllib.parse.urlencode({
        "siteCd": SITE_CD, "seq": seq, "ctgCd": board_id, "replySummary": "N",
        "searchfield": "ALL", "searchword": "", "s_date_start": "", "s_date_end": "",
    })
    return "/front/board/View{}.do?{}".format(board_id, params)


class FallbackGuardTripped(Exception):
    """body_fallback 비율이 임계치를 넘어 게시판 수집을 중단."""

    def __init__(self, board_id, n_saved, n_fallback, ratio):
        self.board_id = board_id
        self.n_saved = n_saved
        self.n_fallback = n_fallback
        self.ratio = ratio
        super().__init__(
            "[{}] body_fallback 비율 {:.1%} ({}/{}) — 임계치 초과로 중단".format(
                board_id, ratio, n_fallback, n_saved))


def crawl_board(board_id, limit=None, max_pages=None,
                max_fallback_ratio=None, guard_min_sample=20):
    """게시판 수집. max_fallback_ratio 지정 시, guard_min_sample건 이상
    수집된 뒤 body_fallback 비율이 임계치를 넘으면 FallbackGuardTripped."""
    cfg = BOARDS[board_id]
    client = KasbClient(cfg["list_path"])
    store = BoardStore(board_id)

    # 1페이지 GET → 세션 확보 + 전체 페이지 수 파악
    first_html = client.get_html(cfg["list_path"])
    total_pages = last_page_no(first_html)
    pages = total_pages if max_pages is None else min(max_pages, total_pages)
    print(f"[{board_id}] 전체 {total_pages}페이지 중 {pages}페이지 수집 예정"
          + (f" (limit {limit}건)" if limit else ""), flush=True)

    n_saved = n_skipped = n_fallback = 0
    for page in range(1, pages + 1):
        html = first_html if page == 1 else client.post_html(
            cfg["list_path"], list_page_payload(page))
        rows = parse_list_rows(html, board_id)
        print(f"[{board_id}] {page}p: 글 {len(rows)}건", flush=True)

        for row in rows:
            if limit is not None and n_saved >= limit:
                print(f"[{board_id}] limit {limit}건 도달 → 종료", flush=True)
                return n_saved, n_skipped
            seq = row["seq"]
            if store.is_collected(seq):
                n_skipped += 1
                continue
            try:
                qa_source = crawl_one(client, store, cfg, board_id, row)
                n_saved += 1
                if qa_source == "body_fallback":
                    n_fallback += 1
            except Exception as e:  # noqa: BLE001 — 실패는 로그에 남기고 계속
                log_failure(board_id, seq, "detail", repr(e))
                continue
            # 가드레일: 표본이 쌓인 뒤 fallback 비율 초과 시 중단
            if (max_fallback_ratio is not None and n_saved >= guard_min_sample
                    and n_fallback / n_saved > max_fallback_ratio):
                raise FallbackGuardTripped(
                    board_id, n_saved, n_fallback, n_fallback / n_saved)
    return n_saved, n_skipped


def crawl_one(client, store, cfg, board_id, row):
    """상세 1건 수집. 성공 시 1 반환."""
    seq = row["seq"]
    durl = detail_url(board_id, seq)
    raw_html = client.get_html(durl)
    detail = parse_detail(raw_html, cfg.get("markers"), cfg.get("footer"))

    # 첨부 다운로드 (원본 보관)
    saved_names, saved_paths = [], []
    for att in detail["attachments"]:
        try:
            content, server_name = client.download_file(att["file_no"], att["file_seq"])
            fname = server_name or att["name"]
            saved_paths.append(store.save_attachment(seq, fname, content))
            saved_names.append(fname)
        except Exception as e:  # noqa: BLE001
            log_failure(board_id, seq, "attachment:" + att["name"], repr(e))

    # 본문에서 Q/A 분리 실패 + 첨부 존재 → 첨부 텍스트에서 재시도
    # (extract_document_text: HWP→hwp5html, 실패 시 PDF→pypdf)
    qa_source = "html"
    att_text = None
    if detail["question"] is None and saved_paths:
        hwp = next((p for p in saved_paths if p.suffix.lower() == ".hwp"), None)
        pdf = next((p for p in saved_paths if p.suffix.lower() == ".pdf"), None)
        if hwp or pdf:
            try:
                att_text, kind = extract_document_text(hwp, pdf)
                # 1) 일반 마커 → 2) 구형 요약카드 전용 스플리터
                q2, a2, r2 = split_qa(att_text, cfg.get("markers"))
                tag = kind
                if q2 is None:
                    q2, a2, r2 = split_oldcard_qa(att_text)
                    tag = kind + ",oldcard"
                if q2 is not None:
                    detail["question"], detail["answer"], detail["related"] = q2, a2, r2
                    qa_source = "attachment(" + tag + ")"
            except ExtractError as e:
                log_failure(board_id, seq, "attachment_extract", repr(e))

    # doc_no: 첨부 파일명의 공식 문서번호(예: 2025-I-KQA006) 우선, 없으면 게시판-seq
    official = _find_first_official_no([row["title"]] + saved_names
                                       + [a["name"] for a in detail["attachments"]])
    record = {
        "source": cfg["source"],
        "doc_no": official or "{}-{}".format(board_id, seq),
        "post_id": "{}-{}".format(board_id, seq),  # 사이트 내 안정적 식별자 (중복 방지 키)
        "title": row["title"],
        "reply_date": detail["meta"].get("회신일자") or row["reply_date"],
        "question": detail["question"],
        "answer": detail["answer"],
        "standard_refs": extract_standard_refs(detail),
        "attachments": saved_names,
        "qa_source": qa_source,
        "url": BASE_URL + durl,
        "crawled_at": now_iso(),
    }
    if detail["question"] is None:  # 분리 최종 실패 (빈 Q/A 포함) → 전문 저장
        record["body"] = (att_text if att_text
                          and len(att_text.strip()) > len(detail["body"].strip())
                          else detail["body"])
        record["qa_source"] = "body_fallback"
        log_failure(board_id, seq, "qa_split",
                    "질의/회신 분리 실패(빈 Q/A 포함) → body 저장 (본문 {}자, 첨부 {}개)".format(
                        len(detail["body"]), len(saved_names)))

    store.save_record(seq, record, raw_html)
    print(f"  [OK] seq={seq} doc_no={record['doc_no']} {row['title'][:36]!r}"
          f" (Q/A={record['qa_source']}, 첨부 {len(saved_names)}개,"
          f" refs {len(record['standard_refs'])}개)")
    return record["qa_source"]


def split_oldcard_qa(text):
    """구형 K-IFRS 질의회신 요약카드 전용 Q/A 분리.

    구조: [헤더카드] → 배경(번호문단) → (질의) 질문 → 회신(번호문단)
          → 면책문구 → 참고자료(부N). '회신' 헤더가 없어 일반 마커로는 못 나눔.
    - question = 배경 + '(질의) …?' (첫 번호문단부터 질의 문장 끝까지)
    - answer   = 질의 이후 ~ 면책문구 경계
    - related  = 참고자료(부N) — refs 추출용
    분리 실패 시 (None, None, None).
    """
    mq = re.search(r"\(\s*질\s*의\s*\)", text)
    if not mq:
        return None, None, None
    # 면책/참고자료 경계: 질의 '이후'의 면책문구에서 잘라야 함
    # (헤더카드 preamble "이 자료는 한국회계기준원…"이 질의 앞에도 있어 전역 검색은 오탐)
    fm = re.search(r"이\s*참고자료는|이\s*자료는\s*한국회계기준원", text[mq.end():])
    main_end = mq.end() + fm.start() if fm else len(text)
    # 질문 끝: (질의) 이후 첫 물음표, 없으면 다음 번호문단 직전
    qtail = text[mq.end():main_end]
    qend_m = re.search(r"[?？]", qtail)
    if qend_m:
        q_end = mq.end() + qend_m.end()
    else:
        nxt = re.search(r"\n\s*\d+\s", qtail)
        q_end = mq.end() + (nxt.start() if nxt else len(qtail))
    # 배경 시작: 첫 번호문단 "1 " (없으면 질의 문장만)
    bg = re.search(r"(?m)^\s*1\s+\S", text[:mq.start()])
    q_start = bg.start() if bg else mq.start()
    question = _strip_pagemarks(text[q_start:q_end])
    answer = _strip_pagemarks(text[q_end:main_end])
    related = _strip_pagemarks(text[main_end:]) or None
    if len(question) < 10 or len(answer) < 20:
        return None, None, None
    return question, answer, related


def _strip_pagemarks(s):
    """PDF 페이지 번호 라인("2/8" 등)만 제거 (구형 카드 추출 노이즈)."""
    lines = [ln for ln in s.split("\n") if not re.match(r"^\s*\d+/\d+\s*$", ln)]
    return "\n".join(lines).strip()


def _find_first_official_no(names):
    for n in names:
        m = RE_OFFICIAL_NO.search(n or "")
        if m:
            return m.group(0)
    return None


def main():
    ap = argparse.ArgumentParser(description="KASB 질의회신 크롤러")
    ap.add_argument("--board", default="016005", choices=sorted(BOARDS))
    ap.add_argument("--limit", type=int, default=None, help="수집 글 수 제한 (테스트용)")
    ap.add_argument("--pages", type=int, default=None, help="수집 페이지 수 제한")
    ap.add_argument("--all", action="store_true", help="전체 페이지 수집")
    args = ap.parse_args()

    if not args.all and args.limit is None and args.pages is None:
        ap.error("--limit / --pages / --all 중 하나는 지정해야 합니다 (한 번에 전체 긁기 방지)")

    saved, skipped = crawl_board(args.board, limit=args.limit, max_pages=args.pages)
    print(f"\n완료: 신규 {saved}건 저장, 기수집 {skipped}건 스킵")
    print(f"JSONL: {DATA / 'parsed' / (args.board + '.jsonl')}")


if __name__ == "__main__":
    main()
