#!/usr/bin/env bash
# KASB 감리지적사례 동기화 스케줄러 설치기 (분기: 2·5·8·11월 1일).
#
# rag.sync_audit_cases (audit-sentinel cases.jsonl → KASB audit_cases 재임베딩) 를 cron 에 등록.
#   - 정시 잡: 매 2·5·8·11월 1일 **04:00** 동기화+재임베딩
#     ※ audit-sentinel 크론(각 월 1일 03:00)보다 1시간 뒤로 오프셋 — 원본이 먼저 갱신된 뒤
#       KASB가 그 결과를 읽도록 하고, 두 크론의 타이밍 경합을 낮춘다.
#
# 사용:
#   install_audit_scheduler.sh            # (기본) 설치될 crontab 내용만 출력 — 시스템 변경 없음
#   install_audit_scheduler.sh --print    # 위와 동일
#   install_audit_scheduler.sh --install  # 실제 crontab 등록(멱등: 기존 kasb-audit 항목 교체)
#   install_audit_scheduler.sh --uninstall# kasb-audit 항목만 제거
#
# ⚠️ 실제 crontab 변경(--install/--uninstall)은 시스템 전역 상태를 바꾼다. 미리보기는 --print.
# 파이썬 경로는 PYTHON 환경변수로 덮어쓸 수 있다(기본: 현재 python3).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)"          # rag/ 의 부모 = kasb-crawler 루트
PYTHON="${PYTHON:-$(command -v python3 || true)}"
LOG="$PROJECT/data/audit_sync.log"
TAG="# kasb-audit-sync scheduler"

if [ -z "$PYTHON" ]; then
  echo "오류: python3 를 찾을 수 없습니다. PYTHON=<경로> 로 지정하세요." >&2
  exit 1
fi

# cron 라인 (TAG 주석으로 멱등 교체·제거 대상 식별). 04:00 = audit-sentinel 03:00 이후 오프셋.
SCHEDULED="0 4 1 2,5,8,11 * cd $PROJECT && $PYTHON -m rag.sync_audit_cases >> $LOG 2>&1 $TAG"

print_block() {
  echo "# ── kasb-audit 분기 동기화 스케줄 (2·5·8·11월 1일 04:00, audit-sentinel 03:00 이후) ──"
  echo "$SCHEDULED"
}

case "${1:---print}" in
  --print)
    echo "다음 1줄이 crontab 에 등록됩니다 (실제 등록: --install):"
    echo
    print_block
    echo
    echo "파이썬: $PYTHON"
    echo "프로젝트: $PROJECT"
    echo "로그:   $LOG"
    ;;
  --install)
    # 기존 kasb-audit 항목은 지우고(멱등) 새로 추가. 그 외 사용자 항목은 보존.
    { crontab -l 2>/dev/null | grep -vF "$TAG" || true; echo "$SCHEDULED"; } | crontab -
    echo "설치 완료. 현재 kasb-audit 항목:"
    crontab -l 2>/dev/null | grep -F "$TAG" || true
    ;;
  --uninstall)
    { crontab -l 2>/dev/null | grep -vF "$TAG" || true; } | crontab -
    echo "kasb-audit 스케줄 항목을 제거했습니다."
    ;;
  *)
    echo "알 수 없는 옵션: $1" >&2
    echo "사용: install_audit_scheduler.sh [--print|--install|--uninstall]" >&2
    exit 2
    ;;
esac
