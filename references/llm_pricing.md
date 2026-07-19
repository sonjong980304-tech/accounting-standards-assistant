# LLM 토큰 단가 — 1차 출처 검증 (2026-07-20)

이 프로젝트가 실제로 쓰는 answer/rewrite/route 모델의 공식 가격. README "생성 성능" 표의
비용($) 계산에 그대로 인용한다. 추측·기억 값 아님 — 아래 URL에서 직접 확인.

## 확정값

| 모델 | 용도(이 프로젝트) | 입력 (1M 토큰당) | 캐시된 입력 (1M 토큰당) | 출력 (1M 토큰당) | 확인일 | 출처 |
|---|---|---|---|---|---|---|
| gpt-4o-mini | rewrite, route | $0.15 | $0.075 | $0.60 | 2026-07-20 | [OpenAI 모델 페이지](https://developers.openai.com/api/docs/models/gpt-4o-mini) |
| gpt-5.5 | answer | $5.00 | $0.50 | $30.00 | 2026-07-20 | [OpenAI 가격표](https://developers.openai.com/api/docs/pricing) + [OpenAI 모델 페이지](https://developers.openai.com/api/docs/models/gpt-5.5) (교차 확인, 두 출처 값 일치) |

- gpt-4o-mini는 모델 페이지에 "Default" 표시 + deprecated/legacy 태그 없음 → 현재 활성 모델.
- gpt-5.5는 가격표 "Flagship models" 섹션과 모델 전용 페이지 양쪽에서 동일 값 확인(교차 대조 통과).
- EXAONE(로컬, Ollama 구동)은 API 과금 대상이 아니므로 비용 $0 — 별도 가격 조회 불필요.

## 확인 안 됨 / 참고

- gpt-5.5는 입력 토큰이 272,000개를 넘는 세션에서 입력 2배·출력 1.5배로 가격이 오르는 장문
  컨텍스트 구간이 있음(모델 페이지 명시). 이 프로젝트의 answer 노드 컨텍스트(근거 8건, 각 700자
  clip)는 이 임계값에 크게 못 미쳐 해당 사항 없음 — 참고로만 기록.
- 원래 `platform.openai.com/docs/pricing`으로 접속을 시도했으나 `developers.openai.com/api/docs/pricing`으로
  301 리다이렉트됨(OpenAI가 개발자 문서 도메인을 이전한 것으로 보임). 위 URL은 리다이렉트 후
  실제 확인한 최종 주소.
