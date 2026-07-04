# -*- coding: utf-8 -*-
"""노드별 모델의 토큰 usage 캡처 검증 (LangSmith가 시각화할 데이터).

- OpenAI 노드(rewrite/route=gpt-4o-mini, answer=gpt-5.5): usage 확인
- 로컬(Ollama): usage가 안 잡히면 tiktoken 근사치 대안 확인
LangSmith 키가 없어도 '토큰 캡처' 자체는 이 스크립트로 검증됨(키 넣으면 그 값이 LangSmith로 전송).
"""
from rag import llm as L

SYS, USR = "한 문장으로 간결히 답하라.", "회계에서 리스란 무엇인가?"


def usage_of(u):
    if u is None:
        return None
    g = lambda k: getattr(u, k, None) if not isinstance(u, dict) else u.get(k)
    return (g("prompt_tokens") or g("input_tokens"),
            g("completion_tokens") or g("output_tokens"))


def main():
    print("=== OpenAI 노드 토큰 캡처 ===")
    for node in ("rewrite", "route"):
        llm = L.get_llm(node)
        llm.complete(SYS, USR)
        pc = usage_of(llm.last_usage)
        print(f"  {node:8} ({L.MODELS[node]}): prompt/completion = {pc}")

    # answer (LangChain ChatOpenAI) — usage_metadata
    m = L.answer_chat_model()
    resp = m.invoke([("system", SYS), ("human", USR)])
    um = getattr(resp, "usage_metadata", None)
    print(f"  {'answer':8} ({L.MODELS['answer']}): usage_metadata = {um}")

    print("\n=== 로컬(Ollama) 토큰 캡처 여부 ===")
    try:
        L.check_ollama_model(L.LOCAL_MODEL)
        llm = L.get_llm("route", local=True)
        llm.complete(SYS, USR)
        pc = usage_of(llm.last_usage)
        if pc and any(pc):
            print(f"  {L.LOCAL_MODEL}: usage 잡힘 prompt/completion = {pc}")
        else:
            print(f"  {L.LOCAL_MODEL}: usage 안 잡힘 → tiktoken 근사 사용")
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            print(f"    tiktoken 근사: prompt≈{len(enc.encode(SYS+USR))} 토큰 "
                  f"(EXAONE/한국어는 실제와 오차 있음, 상대비교용)")
    except L.LLMError as e:
        print("  로컬 스킵:", str(e).splitlines()[0])


if __name__ == "__main__":
    main()
