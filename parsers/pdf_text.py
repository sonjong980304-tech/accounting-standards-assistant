# -*- coding: utf-8 -*-
"""PDF → 텍스트 추출 (pypdf).

기준서는 HWP가 1차 소스(레이아웃 노이즈가 적음)이고,
PDF는 HWP가 없거나 추출 실패 시의 폴백이다.
+ 용어정의 레코드의 page_no 채우기(A안): HWP 흐름에는 페이지 정보가
없으므로, 레코드 text를 원본 PDF에서 재탐색해 페이지 번호를 얻는다.
"""
import re

from refs import normalize_ref


class PdfExtractError(Exception):
    pass


def _norm_for_match(s):
    """HWP 추출문 vs PDF 추출문 비교용: 따옴표·전각공백 정규화(refs 공용) 후
    공백을 전부 제거 (두 추출 경로의 공백 차이가 커서 포함 검색이 깨짐)."""
    return re.sub(r"\s+", "", normalize_ref(s))


def fill_page_numbers(records, pdf_path, needle_lens=(40, 24, 12)):
    """records[i]["text"] 앞부분을 PDF에서 찾아 page_no(1-기준)를 채운다.

    - 여러 페이지에 걸치면 시작 페이지 사용 (첫 매칭 페이지)
    - 정의 시작부가 페이지 경계에 걸릴 수 있어 바늘 길이를 단계적으로 축소
    - 못 찾은 레코드는 page_no=None 유지, 미스 목록 반환 (호출부가 failures 기록)
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise PdfExtractError("pypdf 미설치 (pip install pypdf 필요)")
    pages = [_norm_for_match(p.extract_text() or "")
             for p in PdfReader(str(pdf_path)).pages]
    misses = []
    for rec in records:
        norm_text = _norm_for_match(rec.get("text", ""))
        norm_term = _norm_for_match(rec.get("term", "") or "")
        # 부록A 표에서는 용어명이 정의 바로 앞에 붙으므로 "용어명+정의"를
        # 우선 시도 → 같은 정의 문장이 본문에도 나오는 경우의 오탐 방지
        candidates = []
        if norm_term:
            candidates += [(norm_term + norm_text)[:len(norm_term) + n]
                           for n in needle_lens[:2]]
        candidates += [norm_text[:n] for n in needle_lens]
        page_no = None
        for needle in candidates:
            if len(needle) < 8:  # 지나치게 짧은 바늘은 오탐만 낳음
                continue
            hit = next((i for i, pt in enumerate(pages, 1) if needle in pt), None)
            if hit is not None:
                page_no = hit
                break
        rec["page_no"] = page_no
        if page_no is None:
            misses.append(rec)
    return misses


def _extract_pdfplumber(path):
    """pdfplumber: 2단 레이아웃·구형 요약카드에서 pypdf보다 정렬 정확도가 높음."""
    import pdfplumber
    with pdfplumber.open(str(path)) as doc:
        return "\n".join(pg.extract_text() or "" for pg in doc.pages)


def _extract_pypdf(path):
    from pypdf import PdfReader
    return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(path)).pages)


def pdf_to_text(path):
    """PDF → 텍스트. pdfplumber 우선(레이아웃 충실), 실패 시 pypdf 폴백.

    구형 K-IFRS 질의회신 요약카드(2단)는 pypdf가 텍스트 조각 순서를 뒤섞어
    숫자·마커를 파괴함 → pdfplumber를 1차로 쓴다.
    """
    errors = []
    for name, fn in (("pdfplumber", _extract_pdfplumber), ("pypdf", _extract_pypdf)):
        try:
            text = fn(path)
        except ImportError:
            errors.append(name + " 미설치")
            continue
        except Exception as e:  # noqa: BLE001 — 각 라이브러리가 다양한 예외를 던짐
            errors.append("{} 실패: {!r}".format(name, e))
            continue
        if text.strip():
            return text
        errors.append(name + " 빈 텍스트")
    raise PdfExtractError("PDF 추출 실패({}): {}".format("; ".join(errors), path))
