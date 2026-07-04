# -*- coding: utf-8 -*-
"""KASB 크롤러 파서 패키지.

- hwp_text: HWP → 텍스트 (hwp5html, 표 내용 포함)
- pdf_text: PDF → 텍스트 (pypdf)
- standard_split: 기준서 텍스트 → 문단 단위 레코드 (ref_key 부여, refs.py 공용)
"""
from .hwp_text import HwpExtractError, hwp_to_text
from .pdf_text import PdfExtractError, fill_page_numbers, pdf_to_text
from .standard_split import extract_term_records, split_kgaap_chapter, split_standard


class ExtractError(Exception):
    """HWP·PDF 모두에서 텍스트 추출에 실패."""


def extract_document_text(hwp_path=None, pdf_path=None):
    """HWP 우선(hwp5html) → 실패 시 PDF(pypdf) 폴백.

    반환: (text, "hwp" | "pdf").
    둘 다 실패하면 ExtractError → 호출부(크롤러)가 failures.log에 기록할 것.
    """
    errors = []
    if hwp_path:
        try:
            return hwp_to_text(hwp_path), "hwp"
        except HwpExtractError as e:
            errors.append("HWP: {}".format(e))
    if pdf_path:
        try:
            return pdf_to_text(pdf_path), "pdf"
        except PdfExtractError as e:
            errors.append("PDF: {}".format(e))
    raise ExtractError("; ".join(errors) or "입력 파일이 지정되지 않음")


__all__ = [
    "hwp_to_text", "HwpExtractError",
    "pdf_to_text", "PdfExtractError", "fill_page_numbers",
    "split_standard", "extract_term_records", "split_kgaap_chapter",
    "extract_document_text", "ExtractError",
]
