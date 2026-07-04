# -*- coding: utf-8 -*-
"""RAG 공용 모듈: 컬렉션 정의, 임베딩 텍스트/메타데이터 매핑, 모델 로딩.

임베딩(일괄)과 검색(상시)이 각각 필요한 모델만 로드하도록 분리:
  - 임베딩: load_embedder()          (BGE-M3만)
  - 검색:   load_embedder() + load_reranker()
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "data" / "parsed"
CHROMA_DIR = ROOT / "data" / "chroma"

EMB_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
MAX_SEQ = 8192          # 8192 초과 레코드는 자동 절단 (13건, 병합 아티팩트)
EMB_DIM = 1024

# 컬렉션 = 라우팅 단위. 파일 → 컬렉션 매핑.
COLLECTIONS = {
    "kifrs_standards": ["3001.jsonl"],
    "kgaap_standards": ["3003.jsonl"],
    "qa_kifrs": ["016001.jsonl", "016002.jsonl", "016005.jsonl"],
    "qa_kgaap": ["016003.jsonl", "016006.jsonl"],
}
BASE_URL = "https://www.kasb.or.kr"


def embed_text(rec):
    """레코드 → 임베딩 대상 텍스트.

    - 기준서(문단/용어): text
    - 질의회신: 'question' + 'answer' 를 합쳐 하나로 (질문 유사도·답변 내용 둘 다 매칭)
      분리 실패(body_fallback) 문서는 body 사용.
    """
    rt = rec.get("record_type")
    if rt == "term":
        # 용어명을 앞에 붙여 임베딩 (정의문에는 용어명이 안 들어가 매칭 실패 방지)
        term = rec.get("term", "")
        return "{}: {}".format(term, rec.get("text", "")) if term else rec.get("text", "")
    if rt == "paragraph":
        return rec.get("text", "")
    q, a = rec.get("question"), rec.get("answer")
    if q or a:
        return "질의: {}\n회신: {}".format(q or "", a or "")
    return rec.get("body", "")


def to_metadata(rec, coll):
    """검색 결과에서 원문카드·PDF페이지·KASB링크를 만들 재료.

    Chroma 메타데이터는 str/int/float/bool만 허용 → None/리스트는 제외·변환.
    """
    md = {
        "collection": coll,
        "doc_no": rec.get("doc_no", ""),
        "source": rec.get("source", ""),
        "record_type": rec.get("record_type", ""),
    }
    for k in ("ref_key", "section_key", "src_file", "standard_no",
              "standard_name", "para_no", "term", "title", "reply_date",
              "qa_source"):
        v = rec.get(k)
        if v not in (None, ""):
            md[k] = v
    if rec.get("page_no") is not None:
        md["page_no"] = int(rec["page_no"])
    # url: 질의회신은 저장된 url, 기준서는 게시판 상세로 구성
    if rec.get("url"):
        md["url"] = rec["url"]
    # 첨부는 리스트라 문자열로 join
    if rec.get("attachments"):
        md["attachments"] = " | ".join(rec["attachments"])
    return md


def iter_records():
    """(collection, file, lineno, record) 스트림. id = f'{file}:{lineno}' (재개용 안정키)."""
    for coll, files in COLLECTIONS.items():
        for fn in files:
            path = PARSED / fn
            if not path.exists():
                continue
            for i, line in enumerate(path.open(encoding="utf-8")):
                yield coll, fn, i, json.loads(line)


def record_id(fn, lineno):
    return "{}:{}".format(fn.replace(".jsonl", ""), lineno)


# ------------------------------------------------------------------ 모델

def pick_device():
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


def load_embedder(device=None):
    from sentence_transformers import SentenceTransformer
    dev = device or pick_device()
    m = SentenceTransformer(EMB_MODEL, device=dev)
    m.max_seq_length = MAX_SEQ
    if dev != "cpu":
        m.half()   # fp16: 긴 문서(8192) 어텐션 메모리 절반 + 속도 향상 (MPS OOM 방지)
    return m


def load_reranker(device=None):
    from sentence_transformers import CrossEncoder
    dev = device or pick_device()
    # max_length 512: 문서 대부분이 짧음(중앙 161자·90%tile 444자≈150토큰)이라 512로
    #   99%+ 온전 커버, 긴 문서만 절단. cross-encoder 비용은 길이에 민감 → 1024대비 2~4배 빠름.
    ce = CrossEncoder(RERANK_MODEL, device=dev, max_length=512)
    if dev != "cpu":
        try:
            ce.model.half()   # fp16: 임베더와 동일 정책. fp32 대비 ~2배 속도·메모리 절반
        except Exception:
            pass              # fp16 미지원/불안정 시 fp32 유지(안전)
    return ce


def get_chroma():
    import chromadb
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))
