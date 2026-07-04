# -*- coding: utf-8 -*-
"""HWP → 텍스트 추출 (hwp5html 기반, 표 내용 포함).

hwp5txt는 표 내용을 통째로 누락시키므로(<표> 마커만 남김) hwp5html로
XHTML 변환 후 표를 행 단위 텍스트(셀 구분자 " | ")로 복원한다.
실패 시 HwpExtractError → 호출부는 pypdf 폴백 후 failures.log에 기록
(parsers.extract_document_text 참조).

주의: hwp5html 변환은 파일당 수십 초 걸림 → 크롤러는 추출 결과를
파일로 캐시할 것.
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


class HwpExtractError(Exception):
    pass


def _find_tool(name):
    exe = shutil.which(name)
    if exe:
        return exe
    # pip install --user 시 PATH에 없는 경우 (macOS)
    candidates = sorted(glob.glob(os.path.expanduser("~/Library/Python/*/bin/" + name)))
    if candidates:
        return candidates[-1]
    raise HwpExtractError("{} 실행 파일을 찾을 수 없음 (pip install pyhwp 필요)".format(name))


def _clean(el):
    # sep 없이 이어붙여 span 경계의 인공 공백을 막고, 원문 공백만 하나로 접음
    return re.sub(r"\s+", " ", el.get_text("")).strip()


def hwp_to_text(path):
    """HWP 파일 → 표 내용 포함 전체 텍스트. 실패 시 HwpExtractError."""
    exe = _find_tool("hwp5html")
    with tempfile.TemporaryDirectory() as tmp:
        outdir = os.path.join(tmp, "out")
        try:
            # 대형 기준서(제1109호 2.8MB)는 변환에 10분 이상 걸릴 수 있음
            proc = subprocess.run(
                [exe, "--output", outdir, str(path)],
                capture_output=True, timeout=1800,
            )
        except subprocess.TimeoutExpired:
            raise HwpExtractError("hwp5html 타임아웃(1800s): {}".format(path))
        if proc.returncode != 0:
            raise HwpExtractError("hwp5html 실패(exit {}): {}".format(
                proc.returncode, proc.stderr.decode("utf-8", "replace")[:300]))
        xhtml = os.path.join(outdir, "index.xhtml")
        if not os.path.exists(xhtml):
            raise HwpExtractError("hwp5html 결과물(index.xhtml) 없음: {}".format(path))
        with open(xhtml, encoding="utf-8") as f:
            html = f.read()
    text = xhtml_to_text(html)
    if not text.strip():
        raise HwpExtractError("hwp5html 추출 텍스트가 비어 있음: {}".format(path))
    return text


def xhtml_to_text(html):
    """hwp5html XHTML → 평문. 표는 행당 한 줄, 셀은 ' | ' 구분."""
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup
    # 중첩(안쪽) 표부터 문자열로 치환 → 바깥 표의 셀이 그 내용을 흡수
    # (find_all은 문서 순서 = 부모 먼저이므로 reversed가 안쪽 우선)
    # 행 경계는 \x00 센티널로 보호: 표가 <p> 안에 중첩된 경우
    # 아래 p 치환의 _clean(\s+ 접기)이 행 구분 개행을 지우는 것을 방지
    SENT = "\x00"
    for tbl in reversed(body.find_all("table")):
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [_clean(td) for td in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(" | ".join(cells))
        tbl.replace_with(SENT + SENT.join(rows) + SENT)
    # 문단(<p>)을 한 줄 문자열로 치환 (span 경계 인공 공백/개행 방지)
    for p in body.find_all("p"):
        p.replace_with(_clean(p) + "\n")
    text = body.get_text("").replace(SENT, "\n")
    return re.sub(r"\n{3,}", "\n\n", text)
