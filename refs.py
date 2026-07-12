# -*- coding: utf-8 -*-
"""기준서 참조(ref_key) 정규화 모듈 — 질의회신·기준서 파서 공용 (필수 공유).

ref_key 매칭이 깨지면 답변↔원문 대조(조인)가 불가능해지므로,
참조를 만들거나 추출하는 모든 코드는 반드시 이 모듈을 거쳐야 한다.

ref_key 형식 (양쪽 파서 동일 — 완전일치로 조인됨):
  - 문단 참조: "제1116호 문단 7⑴"  ← 기준서 파서가 문단 단위 저장 시 부여하는 키
  - 제목 참조: "제1116호 '리스'"
  - 단독 참조: "제1109호"
"""
import re

# ── 1) 문자 정규화: 따옴표 변종 → ' / 전각공백·NBSP → 일반 공백 ──
_REF_TRANS = str.maketrans({
    "‘": "'", "’": "'", "＇": "'", "`": "'", "´": "'",
    "“": "'", "”": "'", "＂": "'", '"': "'",
    "　": " ",  # 전각 공백
    " ": " ",  # NBSP
})


def normalize_ref(text):
    """모든 따옴표 변종을 일반 ' 로, 전각 공백을 일반 공백으로 통일.

    참조 추출·ref_key 생성 전에 반드시 적용한다 (양쪽 파서 공용).
    """
    return text.translate(_REF_TRANS)


# ── 2) 문단 번호 패턴 ──
# 커버: 9, 69, 76A, AG33, BC40, 7⑴ (일반형)
#     + 4.1.2A, B4.1.7 (제1109호 등 소수점 체계)
#     + 10.14, 2.82⑶ (일반기업회계기준 장.문단 체계)
# 하위항목 원문자는 ⑴~⒇ (제1001호 문단 54가 ⒅까지 실사용 → ⑿에서 확장)
# 한글(조사 을/의/를…)이 나오는 순간 즉시 끊김. "문단 9." 같은 문장끝
# 마침표는 \.\d 요구 때문에 붙지 않음.
PARA_PATTERN = r"(?:[A-Z]{1,2})?\d+(?:\.\d+)*[A-Z]*(?:[⑴-⒇])?"

# 기준서 참조 전체: 제NNNN호 + (기준서 명)? + (문단 번호)?
RE_STANDARD_REF = re.compile(
    r"제(\d{3,4})호"
    r"(?:\s*'([^'\n]{1,40})')?"
    r"(?:[^\n]{0,15}?문단\s*(" + PARA_PATTERN + r"))?"
)
# "문단 9, 문단 BC40, 문단 BC41"처럼 쉼표로 이어지는 추가 문단
RE_PARA_CONT = re.compile(r"\s*[,，]\s*문단\s*(" + PARA_PATTERN + r")")
# "문단 10~12"/"문단 B9~B31"처럼 물결표로 이어지는 범위(끝 번호는 "문단" 키워드 없이 등장)
RE_PARA_RANGE = re.compile(r"\s*[~∼]\s*(" + PARA_PATTERN + r")")
_LAST_INT = re.compile(r"\d+")
MAX_RANGE_WIDTH = 50  # 이 폭을 넘으면 중간값 확장 없이 시작/끝만 추가(폭주 방지)
# 용어정의 섹션 인용: "(제1109호 용어의 정의)" — 용어명 없는 섹션 수준 참조
RE_TERMS_SECTION_REF = re.compile(r"제(\d{3,4})호[^\n]{0,10}?용어의 정의")
# 일반기업회계기준 장(章) 참조: "제10장 '유형자산' 문단 10.14"
RE_KGAAP_REF = re.compile(
    r"제(\d{1,2})장"
    r"(?:\s*'([^'\n]{1,40})')?"
    r"(?:[^\n]{0,15}?문단\s*(" + PARA_PATTERN + r"))?"
)


def _split_last_int(label):
    """문단 라벨을 (접두, 마지막 정수, 꼬리)로 분해. 정수 없으면 None.

    "B31" → ("B", 31, ""), "10.14" → ("10.", 14, ""), "7⑴" → ("", 7, "⑴").
    """
    ints = list(_LAST_INT.finditer(label))
    if not ints:
        return None
    last = ints[-1]
    return (label[:last.start()], int(last.group()), label[last.end():])


def _expand_para_range(start_label, end_label, max_width=MAX_RANGE_WIDTH):
    """물결표 범위("10~12", "B9~B31")의 시작·끝 문단 라벨을 확장.

    같은 접두·꼬리 체계일 때만 중간 번호를 채운다(다르면 안전하게 두 끝만).
    폭이 max_width를 넘으면 폭주 방지로 두 끝만 반환.
    """
    a, b = _split_last_int(start_label), _split_last_int(end_label)
    if not a or not b or a[0] != b[0] or a[2] != b[2] or a[1] > b[1]:
        return [start_label, end_label]
    prefix, tail = a[0], a[2]
    if b[1] - a[1] + 1 > max_width:
        return [start_label, end_label]
    return ["{}{}{}".format(prefix, n, tail) for n in range(a[1], b[1] + 1)]


def _consume_para_extras(text, pos, para, key_fn, add):
    """문단 뒤에 이어지는 물결표 범위·쉼표 나열을 소비하며 key_fn(para=...)를 add한다.

    key_fn은 para 키워드만 받는 콜러블(예: lambda **kw: make_ref_key(std_no, **kw)).
    다음 파싱 위치(int)를 반환.
    """
    rm = RE_PARA_RANGE.match(text, pos)
    if rm:
        for p in _expand_para_range(para, rm.group(1)):
            add(key_fn(para=p))
        pos = rm.end()
    while True:
        c = RE_PARA_CONT.match(text, pos)
        if not c:
            break
        add(key_fn(para=c.group(1)))
        pos = c.end()
    return pos


def make_ref_key(std_no, para=None, name=None):
    """정준(canonical) ref_key 생성.

    기준서 파서는 문단 단위 저장 시 반드시 이 함수로 ref_key를 만들어야
    질의회신 standard_refs와 완전일치 조인이 보장된다.

    make_ref_key("1116", para="7⑴")  → "제1116호 문단 7⑴"
    make_ref_key("1116", name="리스") → "제1116호 '리스'"
    """
    if para:
        return "제{}호 문단 {}".format(std_no, para)
    if name:
        return "제{}호 '{}'".format(std_no, re.sub(r"\s+", " ", name).strip())
    return "제{}호".format(std_no)


def make_kgaap_ref_key(chapter, para=None, name=None):
    """일반기업회계기준 장(章) 참조의 정준 ref_key.

    make_kgaap_ref_key("10", para="10.14") → "제10장 문단 10.14"
    make_kgaap_ref_key("15", para="5")     → "제15장 문단 15.5"  (축약형 접두 보정)
    make_kgaap_ref_key("2", name="재무제표의 작성과 표시Ⅰ") → "제2장 '재무제표의 작성과 표시Ⅰ'"
    장 번호의 선행 0은 제거 ("제02장" 표기와 "제2장" 표기를 같은 키로).
    """
    chapter = str(int(chapter))
    if para:
        return "제{}장 문단 {}".format(chapter, normalize_kgaap_para(chapter, para))
    if name:
        return "제{}장 '{}'".format(chapter, re.sub(r"\s+", " ", name).strip())
    return "제{}장".format(chapter)


def normalize_kgaap_para(chapter, para):
    """일반기업회계기준 문단번호를 완전형(장.문단)으로 보정.

    QA가 장 접두를 생략해 인용하는 경우(제15장 "문단 5")를 3003 저장형
    "문단 15.5"과 일치시킨다. 이미 완전형이면 그대로(N.N.M 중복 방지).
      normalize_kgaap_para("15", "5")     → "15.5"
      normalize_kgaap_para("15", "15.5")  → "15.5"  (이미 완전형)
      normalize_kgaap_para("31", "9⑴")    → "31.9⑴"
      normalize_kgaap_para("6", "5.5")    → "5.5"   (점 있으나 장≠접두 → 모호, 건드리지 않음)
    """
    chapter = str(int(chapter))
    if para.startswith(chapter + "."):        # 이미 완전형
        return para
    if re.match(r"^\d+(?:[A-Z]|[⑴-⒇])*$", para):  # 축약형: 5, 5A, 9⑴
        return "{}.{}".format(chapter, para)
    return para                                # 그 외(모호)는 보존


# 국제표기 → 한국 기준서번호 접두 (IFRS N→제11NN, IAS N→제10NN,
# IFRIC N→제21NN, SIC N→제20NN). 3001 실측 목록으로 대조 검증됨(2026-07-03).
_INTL_PREFIX = {"IFRS": "11", "IAS": "10", "IFRIC": "21", "SIC": "20"}
RE_INTL_REF = re.compile(
    r"(?<![-\w])(IFRS|IAS|IFRIC|SIC)\s*(\d{1,2})\b"   # (?<![-\w]): 'K-IFRS' 오매칭 방지
    r"(?:\s*'([^'\n]{1,40})')?"
    r"(?:[^\n]{0,15}?문단\s*(" + PARA_PATTERN + r"))?"
)


def map_intl_standard_no(kind, num):
    """국제표기 표준번호 → 한국 기준서번호. IAS 12 → '1012', IFRS 9 → '1109'."""
    return "{}{:02d}".format(_INTL_PREFIX[kind], int(num))


def extract_intl_refs(*texts):
    """자유 텍스트의 국제표기(IFRS/IAS/IFRIC/SIC N)를 한국식 ref_key로 추출.

    'IAS 29 문단 3' → '제1029호 문단 3', "IFRS 9 '금융상품'" → "제1109호 '금융상품'".
    한국식 extract_refs가 놓치는 국제표기 인용 보강용 (조인 키 정규화).
    """
    refs, seen = [], set()

    def add(r):
        if r not in seen:
            seen.add(r)
            refs.append(r)

    for text in texts:
        if not text:
            continue
        text = normalize_ref(text)
        for m in RE_INTL_REF.finditer(text):
            kind, num, name, para = m.group(1), m.group(2), m.group(3), m.group(4)
            no = map_intl_standard_no(kind, num)
            if name:
                add(make_ref_key(no, name=name))
            if para:
                add(make_ref_key(no, para=para))
            if not name and not para:
                add(make_ref_key(no))
    return refs


def make_section_key(std_no):
    """용어정의 섹션 키. 질의회신이 "(제1109호 용어의 정의)"처럼 용어명 없이
    섹션 수준으로 인용하므로, 거친 조인은 이 키로 한다.

    make_section_key("1109") → "제1109호 용어의 정의"
    """
    return "제{}호 용어의 정의".format(std_no)


def make_term_key(std_no, term):
    """용어정의 레코드의 ref_key (2단 키의 정밀 단계).

    make_term_key("1109", "파생상품") → "제1109호 용어의 정의:파생상품"
    """
    term = re.sub(r"\s+", " ", normalize_ref(term)).strip()
    return "{}:{}".format(make_section_key(std_no), term)


def extract_refs(*texts):
    """자유 텍스트에서 기준서 참조를 추출해 정준 ref_key 목록으로 반환.

    - 정규화(normalize_ref) 후 추출
    - 중복 제거는 정규화 후 완전일치만 (등장 순서 유지)
    - 기준서 제목참조와 문단참조는 별개로 둘 다 보존
    """
    refs, seen = [], set()

    def add(ref):
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)

    for text in texts:
        if not text:
            continue
        text = normalize_ref(text)
        for m in RE_STANDARD_REF.finditer(text):
            std_no, name, para = m.group(1), m.group(2), m.group(3)
            if name:
                add(make_ref_key(std_no, name=name))
            if para:
                add(make_ref_key(std_no, para=para))
                # 물결표 범위("문단 10~12") + 쉼표 나열("문단 9, 문단 BC40") 확장
                _consume_para_extras(
                    text, m.end(), para,
                    lambda **kw: make_ref_key(std_no, **kw), add)
            if not name and not para:
                add(make_ref_key(std_no))
        # 용어정의 섹션 참조 (예: "(제1109호 용어의 정의)")
        for m in RE_TERMS_SECTION_REF.finditer(text):
            add(make_section_key(m.group(1)))
        # 일반기업회계기준 장 참조 (예: "제10장 '유형자산' 문단 10.14")
        for m in RE_KGAAP_REF.finditer(text):
            chapter, name, para = m.group(1), m.group(2), m.group(3)
            if name:
                add(make_kgaap_ref_key(chapter, name=name))
            if para:
                add(make_kgaap_ref_key(chapter, para=para))
                _consume_para_extras(
                    text, m.end(), para,
                    lambda **kw: make_kgaap_ref_key(chapter, **kw), add)
            if not name and not para:
                add(make_kgaap_ref_key(chapter))
    return refs
