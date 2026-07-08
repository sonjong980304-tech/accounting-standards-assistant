# -*- coding: utf-8 -*-
"""AC13 준비 하니스: 다양한 회계 질문 표본에 대한 감리지적사례 사이드카 결과 출력.

**자동 판정 없음** — 각 질문의 '적절한 참고인가?'(적합/부적합)는 사람이 직접 표기한다.
실제 파이프라인(rewrite → audit_lookup)을 그대로 태워 프로덕션과 동일 경로로 매칭한다.

실행(무거움 + LLM 호출):
    python3 -m rag.eval.audit_sample_review [--local]
키: .env 의 OPENAI_API_KEY 사용(scratch_regress.py 패턴). --local 이면 EXAONE(Ollama).
사전조건: `python3 -m rag.sync_audit_cases` 로 audit_cases 컬렉션 임베딩 완료.
"""
import argparse
from pathlib import Path

from rag.graph import build_graph
from rag.search import Index

# 65건(금감원 감리지적)에 자주 등장하는 주제를 아우르는 다양한 표본(12~15개).
# 매칭 품질을 넓게 관찰하려는 의도이므로 일부는 매칭이 없을 수(임계값 미달) 있음 — 정상.
SAMPLE_QUESTIONS = [
    "위탁판매에서 수익은 언제 인식하나?",
    "재고자산 평가손실은 어떻게 회계처리하나?",
    "전환사채의 전환권은 자본과 부채로 어떻게 구분하나?",
    "영업권 손상차손은 어떤 기준으로 인식하나?",
    "특수관계자 거래는 재무제표에 어떻게 공시하나?",
    "장기공사계약의 진행률은 어떻게 산정하나?",
    "종속기업 지분 취득 시 영업권은 어떻게 계산하나?",
    "매출채권 대손충당금은 어떻게 설정하나?",
    "유형자산 재평가모형에서 재평가잉여금은 어떻게 처리하나?",
    "금융자산의 손상은 어떤 모형으로 인식하나?",
    "충당부채와 우발부채는 어떻게 구분하나?",
    "확정급여제도의 종업원급여는 어떻게 회계처리하나?",
    "정부보조금은 언제 수익으로 인식하나?",
    "무형자산 개발비의 자산인식 요건은?",
    "리스이용자의 사용권자산은 어떻게 측정하나?",
]


def load_env_key():
    env = {}
    p = Path(".env")
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env.get("OPENAI_API_KEY")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="EXAONE(Ollama)로 실행")
    args = ap.parse_args()

    print("인덱스 로드 중 (Chroma + BGE-M3 + 리랭커)...", flush=True)
    idx = Index()
    if "audit_cases" not in idx.colls:
        print("⚠️ audit_cases 컬렉션 미로드 — 먼저 `python3 -m rag.sync_audit_cases` 실행",
              flush=True)
    graph = build_graph(idx, api_key=load_env_key(), local=args.local)

    print("=" * 80)
    print("감리지적사례 사이드카 — 표본 질문 결과 (사람 판단용, 자동 판정 없음)")
    print("=" * 80)
    for i, q in enumerate(SAMPLE_QUESTIONS, 1):
        state = graph.invoke({"question": q},
                             {"configurable": {"thread_id": f"sample-{i}"}})
        cases = state.get("audit_cases", []) or []
        print(f"\n[{i:>2}] 질문: {q}")
        print(f"     재작성: {state.get('rewritten', '')}")
        if not cases:
            print("     감리사례 매칭: (없음 — 임계값 미달 또는 무관)")
        else:
            print(f"     감리사례 매칭 {len(cases)}건:")
            for c in cases:
                print(f"       · [{c['score']:.3f}] {c['title']}  "
                      f"(case_id={c['case_id']}, 기준={c.get('standard', '')})")
        print("     ── 사람 판단(적절한 참고인가?):  [ 적합 / 부적합 ]   ← 여기에 직접 표기")

    print("\n" + "=" * 80)
    print(f"총 {len(SAMPLE_QUESTIONS)}개 질문. '적합' 비율 80% 이상이면 AC13 통과(사람 판단).")
    print("※ 이 스크립트는 출력만 하며 적합/부적합을 자동으로 판정하지 않습니다.")


if __name__ == "__main__":
    main()
