# -*- coding: utf-8 -*-
"""조인 평가 + 회귀 검증 공용 모듈.

각 정규화 단계 전후로 호출해 조인율을 재측정하고, (board, lineno, refpos)
단위로 '이전에 조인되던 인용이 깨졌는지'(회귀)를 정확히 비교한다.
"""
import json
import re

BOARDS = ["016001", "016002", "016003", "016005", "016006"]
DATA = __import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "parsed"


def load_std_index():
    s3001 = [json.loads(l) for l in (DATA / "3001.jsonl").open(encoding="utf-8")]
    s3003 = [json.loads(l) for l in (DATA / "3003.jsonl").open(encoding="utf-8")]
    return {
        "k_para": {r["ref_key"] for r in s3001 if r["record_type"] == "paragraph"},
        "k_tsec": {r["section_key"] for r in s3001 if r["record_type"] == "term"},
        "k_nos": {r["standard_no"] for r in s3001},
        "g_para": {r["ref_key"] for r in s3003},
        "g_ch": {re.search(r"제(\d+)장", r["standard_no"]).group(1) for r in s3003},
    }


def classify(ref):
    """참조 유형 판정: (kind, precision). precision=True면 문단/용어/장문단(정밀)."""
    if re.match(r"^제\d{1,2}장", ref):
        if "문단" in ref:
            return "장문단", True
        return ("장제목", False) if "'" in ref else ("단독장", False)
    if re.match(r"^제\d{3,4}호", ref):
        if ref.endswith("용어의 정의"):
            return "용어섹션", True
        if "문단" in ref:
            return "문단", True
        return ("제목", False) if "'" in ref else ("단독호", False)
    return "기타", False


def matches(ref, idx):
    """현재 ref가 기준서 레코드와 조인되는지 (정밀은 exact, 상위는 식별)."""
    kind, _ = classify(ref)
    if kind == "장문단":
        return ref in idx["g_para"]
    if kind in ("장제목", "단독장"):
        ch = re.match(r"제(\d+)장", ref).group(1)
        return ch in idx["g_ch"]
    if kind == "용어섹션":
        return ref in idx["k_tsec"]
    if kind == "문단":
        return ref in idx["k_para"]
    if kind in ("제목", "단독호"):
        no = re.match(r"제(\d+)호", ref).group(1)
        return no in idx["k_nos"]
    return False


def evaluate():
    """현재 JSONL 상태로 조인 측정. 반환: dict(rates, joined_precise set, joined_any set)."""
    idx = load_std_index()
    prec_tot = prec_hit = any_tot = any_hit = 0
    joined_precise = set()   # (board, lineno, refpos)
    joined_any = set()
    per_kind = {}
    for b in BOARDS:
        for ln, line in enumerate((DATA / (b + ".jsonl")).open(encoding="utf-8")):
            refs = json.loads(line).get("standard_refs", [])
            for pos, ref in enumerate(refs):
                kind, precise = classify(ref)
                ok = matches(ref, idx)
                d = per_kind.setdefault(kind, [0, 0])
                d[1] += 1
                if ok:
                    d[0] += 1
                    joined_any.add((b, ln, pos))
                any_tot += 1
                any_hit += ok
                if precise:
                    prec_tot += 1
                    prec_hit += ok
                    if ok:
                        joined_precise.add((b, ln, pos))
    return {
        "prec": (prec_hit, prec_tot), "any": (any_hit, any_tot),
        "per_kind": per_kind,
        "joined_precise": joined_precise, "joined_any": joined_any,
    }


def report(r, label=""):
    ph, pt = r["prec"]; ah, at = r["any"]
    print(f"[{label}] 정밀 {ph}/{pt}={100*ph/pt:.1f}% | 전체 {ah}/{at}={100*ah/at:.1f}%")
    for k in ["문단", "용어섹션", "제목", "단독호", "장문단", "장제목", "단독장"]:
        if k in r["per_kind"]:
            h, t = r["per_kind"][k]
            print(f"    {k}: {h}/{t} ({100*h/t:.0f}%)")


def regression(before, after):
    """이전에 조인되던 (board,lineno,refpos)가 깨진 건수."""
    lost_prec = before["joined_precise"] - after["joined_precise"]
    lost_any = before["joined_any"] - after["joined_any"]
    return lost_prec, lost_any


if __name__ == "__main__":
    report(evaluate(), "현재")
