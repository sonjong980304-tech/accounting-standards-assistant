# -*- coding: utf-8 -*-
"""기준서 텍스트 → 문단 단위 분리 + ref_key 부여.

통짜 저장 금지: 문단 번호(7, 76A, B8, BC40, …) 기준으로 분리하고,
문단 안의 하위항목 ⑴~⑿ 은 개별 레코드(예: "제1116호 문단 7⑴")로도 저장한다.
ref_key 는 반드시 refs.make_ref_key() 로 생성 → 질의회신 standard_refs 와
완전일치 조인 보장. 텍스트는 refs.normalize_ref() 로 정규화 후 처리한다.

문단 시작 판정(노이즈 필터 2중 게이트):
  1) 한글 게이트: 번호 뒤 60자 안에 한글이 있거나 '['로 시작
     (저작권부 영문 주소 "7 Westferry Circus…" 등 배제)
  2) 순서 게이트: 계열(prefix)별로 번호가 오름차순이어야 하고
     새 계열은 반드시 1부터 시작 (본문 1…, B1…, C1…, IE1…, BC1…, DO1…, IN1…)
"""
import logging
import re

from refs import (
    make_kgaap_ref_key,
    make_ref_key,
    make_section_key,
    make_term_key,
    normalize_ref,
)

logger = logging.getLogger("kasb.parsers")

# 문단 시작 (공백형): 번호 + 공백 + 내용
# (예: "7 리스이용자가…", "BC40 …", 소수점 체계 "4.1.2A …", "B4.1.7 …")
RE_PARA_START = re.compile(
    r"^([A-Z]{1,2})?(\d{1,3}(?:\.\d{1,3})*)([A-Z]{0,2})\s+(\S.*)$")
# 문단 시작 (밀착형): 개정 삽입 문단은 번호와 본문이 붙어 나옴
# (예: "46A실무적 간편법으로…", "104리스이용자는…", "C20BA리스이용자는…")
RE_PARA_START_GLUED = re.compile(
    r"^([A-Z]{1,2})?(\d{1,3}(?:\.\d{1,3})*)([A-Z]{0,2})([가-힣].*)$")
# 밀착형 오탐 가드: "12개월…", "3년간…" 같은 수량 표현의 첫 글자
COUNTER_CHARS = set("개년월일원명번회차억만천퍼")
# 하위항목: ⑴~⒇ 로 시작하는 라인 (refs.PARA_PATTERN과 동일 범위 —
# 제1001호 문단 54가 ⒅까지 실사용해 ⑿→⒇로 확장됨, 2026-07-02)
RE_SUBITEM = re.compile(r"^([⑴-⒇])\s*(.*)$")
# 섹션 헤딩: 현재 문단을 닫는다 (부록A 용어정의 등 무번호 구간이 직전 문단에 붙는 것 방지)
RE_SECTION = re.compile(
    r"^(부록\s*[A-Z]|결론도출근거|적용사례|용어의 정의|한국채택국제회계기준|개정\s)"
)
RE_HANGUL = re.compile(r"[가-힣]")

MAX_NUM_JUMP = 50  # 계열 내 번호 점프 허용치 (삭제 문단 감안, 연도 등 오탐 차단)
# 주: 150으로 올리면 제1039호(IAS39) 등 삭제-갭 문단을 잡지만 IG/예시 번호를
# 문단으로 오인해 오탐 폭증(제1039호 +507). 삭제-갭 복구는 섹션인식 기반의
# 별도 targeted fix 필요 — 전역 cap 상향은 금지.

# 부록A 시작 헤딩 (예: "부록 A. 용어의 정의")
RE_APPENDIX_A = re.compile(r"^부록\s*A[.\s]*용어의 정의$")


def split_kgaap_chapter(text, chapter):
    """일반기업회계기준 장(章) 텍스트 → 문단 레코드 (예: "31.9 내용…").

    ref_key는 refs.make_kgaap_ref_key → 질의회신의 "제31장 문단 31.9"
    참조와 완전일치 조인. 하위항목 ⑴~⒇은 개별 레코드로도 저장.
    """
    text = normalize_ref(text)
    ch = str(int(chapter))
    re_para = re.compile(r"^(" + ch + r"\.\d+[A-Z]*)\s+(\S.*)$")
    records, cur = [], None
    section = ""

    def close():
        if cur is None:
            return
        parts = [cur["pre"].strip()]
        parts += ["{} {}".format(m, t.strip()) for m, t in cur["subs"]]
        records.append({
            "ref_key": make_kgaap_ref_key(ch, para=cur["para_no"]),
            "para_no": cur["para_no"],
            "series": "본문",
            "section": cur["section"],
            "text": "\n".join(p for p in parts if p),
        })
        for mark, sub_text in cur["subs"]:
            records.append({
                "ref_key": make_kgaap_ref_key(ch, para=cur["para_no"] + mark),
                "para_no": cur["para_no"] + mark,
                "series": "본문",
                "section": cur["section"],
                "text": sub_text.strip(),
            })

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if RE_SECTION.match(line) and len(line) < 40:
            close()
            cur = None
            section = line
            continue
        m = re_para.match(line)
        if m and not m.group(2).lstrip().startswith("|"):
            close()
            cur = {"para_no": m.group(1), "section": section,
                   "pre": m.group(2), "subs": []}
            continue
        sm = RE_SUBITEM.match(line)
        if sm and cur is not None:
            mark = sm.group(1)
            if cur["subs"] and ord(mark) <= ord(cur["subs"][-1][0]):
                cur["subs"][-1][1] += "\n" + line  # 목록 재시작 → 연속 텍스트
            else:
                cur["subs"].append([mark, sm.group(2)])
            continue
        if cur is not None:
            if cur["subs"]:
                cur["subs"][-1][1] += "\n" + line
            else:
                cur["pre"] += "\n" + line
    close()
    return records


RE_DEFLIST_START = re.compile(r"용어의 (?:정의|뜻)[^\n]{0,15}다음")


def _valid_term(term, definition):
    """용어/정의 유효성 필터 (부록A 표·콜론 리스트 공용, 3001 오추출 방지)."""
    if not term or not definition:
        return False
    if term in ("용어", "정의", "계", "합계", "소계", "구분", "금액") or len(term) < 2:
        return False
    if len(term) > 30 or not re.search(r"[가-힣]", term):
        return False
    if not re.search(r"[가-힣A-Za-z]", definition):   # 정의가 숫자·기호뿐 = 예시표 셀
        return False
    if re.match(r"^\d{4}\.\s*\d{1,2}\.", term):         # 개정이력 행
        return False
    return True


def extract_colon_terms(text, std_no, src_file=None):
    """부록A 표가 없고 정의가 본문 콜론 리스트로 있는 기준서용 용어 추출.

    예: 제1012호 "5 …용어의 정의는 다음과 같다." → "회계이익: 법인세비용 차감 전 …"
    ⑴⑵/㈎㈏ 하위목록이 딸린 복합 정의는 직전 용어 정의에 이어붙인다.
    다음 번호 문단("12 …")이 나오면 리스트 종료.
    """
    text = normalize_ref(text)
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines)
                  if RE_DEFLIST_START.search(l.strip())), None)
    if start is None:
        return []
    records, seen, cur = [], set(), None

    def flush():
        if not cur:
            return
        term, deflines = cur[0], " ".join(cur[1]).strip()
        if _valid_term(term, deflines):
            key = make_term_key(std_no, term)
            if key not in seen:
                seen.add(key)
                records.append({
                    "ref_key": key, "section_key": make_section_key(std_no),
                    "term": term, "text": deflines,
                    "standard": "제{}호".format(std_no),
                    "page_no": None, "src_file": src_file,
                })

    for l in lines[start + 1:]:
        s = l.strip()
        if not s:
            continue
        if re.match(r"^\d+\s+[가-힣]", s):    # 다음 번호 문단 → 리스트 끝
            break
        m = re.match(r"^([^:：]{1,30})[:：]\s*(.+)$", s)
        if m and re.search(r"[가-힣]", m.group(1)):
            flush()
            cur = [m.group(1).strip(), [m.group(2).strip()]]
        elif cur:
            cur[1].append(s)               # 연속(⑴⑵ 등)
    flush()
    return records


def extract_term_records(text, std_no, src_file=None):
    """부록A '용어의 정의' 표에서 용어 하나당 레코드 하나 추출 (2단 키).

    질의회신이 "(제1109호 용어의 정의)"처럼 용어명 없이 섹션 수준으로
    인용하므로 section_key로 거칠게 조인하고 term 매칭으로 좁힌다.
    page_no: HWP→XHTML 흐름에는 페이지 정보가 없어 None
    (PDF 폴백 파싱을 쓰는 경우에만 채울 수 있음).
    """
    text = normalize_ref(text)
    lines = text.split("\n")

    def region_after(i0):
        """i0 다음부터 다음 섹션 헤딩 전까지의 (start, end)."""
        for j in range(i0 + 1, len(lines)):
            if RE_SECTION.match(lines[j].strip()) and len(lines[j].strip()) < 40:
                return i0 + 1, j
        return i0 + 1, len(lines)

    # 부록A 후보 중 '목차 항목'(다음 섹션이 코앞) 건너뛰고 실제 내용 있는 것 선택
    start = end = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if RE_APPENDIX_A.match(s) or s == "용어의 정의":
            st, en = region_after(i)
            content = [l for l in lines[st:en] if l.strip()]
            if len(content) >= 3:          # 목차(코앞에 부록B)면 content<3 → 스킵
                start, end = st, en
                break
    if start is None:
        # 부록A 표가 없으면 본문 콜론 정의 리스트로 폴백 (제1012·1007·1032호 등)
        return extract_colon_terms(text, std_no, src_file=src_file)

    records, seen = [], set()
    for ln in lines[start:end]:
        if " | " not in ln:
            continue  # 용어 표가 아닌 안내문 등
        cells = [c.strip() for c in ln.split(" | ")]
        term, definition = cells[0], " ".join(c for c in cells[1:] if c).strip()
        if not _valid_term(term, definition):
            continue
        key = make_term_key(std_no, term)
        if key in seen:
            continue
        seen.add(key)
        records.append({
            "ref_key": key,
            "section_key": make_section_key(std_no),
            "term": term,
            "text": definition,
            "standard": "제{}호".format(std_no),
            "page_no": None,
            "src_file": src_file,
        })
    # 부록A 표를 찾았으나 유효 용어가 0이면(예시표만 있던 경우) 콜론 폴백
    if not records:
        return extract_colon_terms(text, std_no, src_file=src_file)
    return records


def _suffix_key(suffix):
    return suffix or ""


def split_standard(text, std_no):
    """기준서 전문 텍스트를 문단 레코드 목록으로 분리.

    반환: [{"ref_key", "para_no", "series", "section", "text"}, ...]
      - 문단 레코드: text = 서문 + 하위항목 전부 (자체 완결 문맥)
      - 하위항목 레코드: ⑴~⑿ 각각 개별 (ref_key 예: "제1116호 문단 7⑴")
    """
    text = normalize_ref(text)
    records = []
    last_in_series = {}   # prefix → num 튜플 (숫자부 최대값)
    seen_in_series = {}   # prefix → {(num, suffix)} — 동일 번호 재등장 차단
    section = ""
    cur = None            # 진행 중 문단: {"para_no","series","section","pre","subs"}

    def close_current():
        if cur is None:
            return
        # 부모 문단 레코드 (서문 + 하위항목 포함 전문)
        parts = [cur["pre"].strip()]
        for mark, sub_text in cur["subs"]:
            parts.append("{} {}".format(mark, sub_text.strip()))
        full = "\n".join(p for p in parts if p)
        records.append({
            "ref_key": make_ref_key(std_no, para=cur["para_no"]),
            "para_no": cur["para_no"],
            "series": cur["series"],
            "section": cur["section"],
            "text": full,
        })
        # 하위항목 개별 레코드
        for mark, sub_text in cur["subs"]:
            records.append({
                "ref_key": make_ref_key(std_no, para=cur["para_no"] + mark),
                "para_no": cur["para_no"] + mark,
                "series": cur["series"],
                "section": cur["section"],
                "text": sub_text.strip(),
            })

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        if RE_SECTION.match(line) and len(line) < 40:
            close_current()
            cur = None
            section = line
            continue

        m = RE_PARA_START.match(line)
        if not m:
            gm = RE_PARA_START_GLUED.match(line)
            if gm and gm.group(4)[0] not in COUNTER_CHARS:
                m = gm
        if m:
            prefix, num_s, suffix, rest = m.group(1) or "", m.group(2), m.group(3), m.group(4)
            num = tuple(int(x) for x in num_s.split("."))  # "4.1.2" → (4,1,2)
            hangul_ok = bool(RE_HANGUL.search(rest[:60])) or rest.startswith("[")
            if rest.lstrip().startswith("|"):
                hangul_ok = False  # 표 행("5 | …")은 문단 시작이 아님
            last = last_in_series.get(prefix)
            seen = seen_in_series.setdefault(prefix, set())
            if last is None:
                # 새 계열 시작: 본문은 1(또는 1.1)부터. 접두 계열(B, BC 등)은
                # 본문 장 번호를 따라가므로(예: 1109의 B3.1.1) 선두 5까지 허용
                lead_max = 1 if not prefix else 5
                order_ok = (num[0] <= lead_max and not suffix)
            else:
                # 숫자부만 단조 증가 요구. 접미사는 사전순을 강제하지 않음
                # (제1001호가 76 → 76ZA → 76A → 76B 순서로 배치됨) —
                # 동일 (번호, 접미사) 재등장만 차단
                order_ok = (
                    (num > last and num[0] - last[0] <= MAX_NUM_JUMP)
                    or (num == last
                        and (num, _suffix_key(suffix)) not in seen)
                )
            if hangul_ok and order_ok:
                close_current()
                last_in_series[prefix] = max(last, num) if last else num
                seen.add((num, _suffix_key(suffix)))
                cur = {
                    "para_no": prefix + num_s + suffix,
                    "series": prefix or "본문",
                    "section": section,
                    "pre": rest,
                    "subs": [],
                }
                continue
            # 게이트 탈락 → 문단 시작이 아니라 본문 연속으로 취급 (아래로 폴스루)

        sm = RE_SUBITEM.match(line)
        if sm and cur is not None:
            mark = sm.group(1)
            if cur["subs"] and ord(mark) <= ord(cur["subs"][-1][0]):
                # 같은 문단 안에서 ⑴⑵… 목록이 재시작 (예: 제1001호 문단 7
                # '용어의 정의'의 용어별 하위목록) → ref_key 중복 방지를 위해
                # 첫 목록만 개별 레코드로 하고 이후 목록은 연속 텍스트로 취급
                cur["subs"][-1][1] += "\n" + line
            else:
                cur["subs"].append([mark, sm.group(2)])
            continue

        # 연속 라인: 열린 하위항목 > 열린 문단 순으로 덧붙임. 문단 밖(표지 등)은 버림
        if cur is not None:
            if cur["subs"]:
                cur["subs"][-1][1] += "\n" + line
            else:
                cur["pre"] += "\n" + line

    close_current()
    return records
