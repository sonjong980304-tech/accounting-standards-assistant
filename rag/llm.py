# -*- coding: utf-8 -*-
"""모델 추상화: 노드별 모델을 쉽게 교체. OpenAI(기본) / Ollama(--local) / Gemini(vendor="google").

키 우선순위: 명시 인자(UI 입력) > 환경변수 OPENAI_API_KEY/GOOGLE_API_KEY > .env(개발용).
입력 키는 인스턴스 메모리에만 보관 — 파일·로그·코드에 절대 저장하지 않는다.

노드별 기본 모델(환경변수로 개별 교체 가능):
  rewrite/route → gpt-4o-mini,  answer → gpt-5.5
  --local 시 전 노드 → EXAONE 3.5 7.8B (Ollama)
  vendor="google" 시 전 노드 → Gemini (OpenAI 호환 엔드포인트, google-genai SDK 불필요)
"""
import os

MODELS = {
    "rewrite": os.getenv("KASB_MODEL_REWRITE", "gpt-4o-mini"),
    "route": os.getenv("KASB_MODEL_ROUTE", "gpt-4o-mini"),
    "answer": os.getenv("KASB_MODEL_ANSWER", "gpt-5.5"),
}
LOCAL_MODEL = os.getenv("KASB_LOCAL_MODEL", "exaone3.5:7.8b")
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

# QLoRA 파인튜닝(v1/v2) 둘 다 held-out 30문항에서 베이스보다 Faithfulness가 낮게 나와
# 폐기(2026-07-17). 로컬 모델은 베이스(LOCAL_MODEL) 고정.

# Gemini는 OpenAI 호환 엔드포인트를 제공해, 기존 openai/langchain_openai 클라이언트를
# base_url만 바꿔 그대로 재사용한다(별도 SDK 의존성 불필요). 실측(2026-07-14): 일반 호출·
# json_mode·LangChain ChatOpenAI 스트리밍 모두 정상 동작 확인.
GEMINI_BASE = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
GEMINI_MODELS = {
    # 전 노드 gemini-2.5-flash-lite로 통일: gemini-2.5-flash/gemini-2.0-flash류는
    # "신규 사용자에게 더 이상 제공 안 함"(404)으로 이 프로젝트가 발급받은 키에서 접근
    # 불가능함을 실측 확인(2026-07-14, rag/eval/judge.py 판사 실험과 동일 증상).
    # flash-lite만 안정적으로 응답 확인됨.
    "rewrite": os.getenv("KASB_GEMINI_MODEL_REWRITE", "gemini-2.5-flash-lite"),
    "route": os.getenv("KASB_GEMINI_MODEL_ROUTE", "gemini-2.5-flash-lite"),
    "answer": os.getenv("KASB_GEMINI_MODEL_ANSWER", "gemini-2.5-flash-lite"),
}


class LLMError(RuntimeError):
    pass


def _load_dotenv_once():
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv(usecwd=True))   # .env → os.environ (개발용)
    except Exception:  # noqa: BLE001
        pass


_ls_valid = None   # None=미검증, True/False=1회 검증 결과 (프로세스당 1회)


def _validate_ls_key(key):
    """LangSmith 키가 실제로 인증되는지 1회 확인 (401/403 무효키 조용히 차단용)."""
    try:
        import requests
        ep = os.environ.get("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
        r = requests.get(ep + "/sessions?limit=1", headers={"x-api-key": key}, timeout=8)
        return r.status_code < 300
    except Exception:  # noqa: BLE001
        return False


def configure_langsmith():
    """LangSmith 트레이싱 활성화. 키 없거나 '무효(401/403)'면 조용히 비활성.

    반환: 활성 여부(bool). 답변 결과에는 영향 없음.
    """
    global _ls_valid
    _load_dotenv_once()
    want = os.environ.get("LANGCHAIN_TRACING_V2", "").lower() in ("true", "1")
    key = os.environ.get("LANGCHAIN_API_KEY")
    if not (want and key):
        if want and not key:
            os.environ["LANGCHAIN_TRACING_V2"] = "false"   # 키 없음 → 조용히 off
        return False
    if _ls_valid is None:                 # 무효 키가 매 호출 403 뿜지 않게 1회 검증
        _ls_valid = _validate_ls_key(key)
    if not _ls_valid:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"       # 무효 키 → 조용히 off
        return False
    os.environ.setdefault("LANGCHAIN_PROJECT", "kasb-rag")
    return True


def _tracing_on():
    # configure_langsmith가 무효 키면 TRACING_V2를 이미 꺼두므로 이 값만 보면 됨
    return os.environ.get("LANGCHAIN_TRACING_V2", "").lower() in ("true", "1") \
        and bool(os.environ.get("LANGCHAIN_API_KEY")) and _ls_valid is not False


def resolve_openai_key(explicit=None):
    """키 우선순위: 명시(UI 입력) > env. .env는 env로 로드. 없으면 안내 예외."""
    if explicit:
        return explicit                       # 메모리에서만 사용, 저장 금지
    _load_dotenv_once()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise LLMError(
            "OpenAI API 키가 없습니다. 다음 중 하나로 제공하세요:\n"
            "  1) 환경변수:  export OPENAI_API_KEY=sk-...\n"
            "  2) 개발용 .env 파일에 OPENAI_API_KEY=sk-... (이미 .gitignore 처리됨)\n"
            "  3) (추후 UI) 입력 키 — 세션 메모리에만 보관\n"
            "  또는 로컬 모델로 실행:  --local (Ollama EXAONE 3.5)")
    return key


def resolve_google_key(explicit=None):
    """키 우선순위: 명시(UI 입력) > env GOOGLE_API_KEY. .env는 env로 로드. 없으면 안내 예외."""
    if explicit:
        return explicit                       # 메모리에서만 사용, 저장 금지
    _load_dotenv_once()
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise LLMError(
            "Google(Gemini) API 키가 없습니다. 다음 중 하나로 제공하세요:\n"
            "  1) 환경변수:  export GOOGLE_API_KEY=AIzaSy...\n"
            "  2) 개발용 .env 파일에 GOOGLE_API_KEY=AIzaSy... (이미 .gitignore 처리됨)\n"
            "  3) (UI) 입력 키 — 세션 메모리에만 보관\n"
            "  키 발급: https://aistudio.google.com/apikey")
    return key


class LLM:
    """단일 인터페이스. provider='openai'|'ollama'|'google'. api_key는 메모리에만."""

    def __init__(self, provider, model, api_key=None, node=None):
        self.provider = provider
        self.model = model
        self.node = node
        self.last_usage = None      # 직전 호출 토큰 usage (검증·근사치용)
        from openai import OpenAI
        if provider == "openai":
            client = OpenAI(api_key=resolve_openai_key(api_key))
        elif provider == "ollama":
            client = OpenAI(base_url=OLLAMA_BASE, api_key="ollama")
        elif provider == "google":
            client = OpenAI(base_url=GEMINI_BASE, api_key=resolve_google_key(api_key))
        else:
            raise LLMError("알 수 없는 provider: " + provider)
        # LangSmith: raw openai 호출도 토큰·모델과 함께 추적 (활성 시에만)
        if _tracing_on():
            try:
                from langsmith.wrappers import wrap_openai
                client = wrap_openai(client)
            except Exception:  # noqa: BLE001
                pass
        self._client = client

    def complete(self, system, user, temperature=0.0, json_mode=False):
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        # GPT-5 계열은 temperature 커스텀 미지원(기본 1만) → 생략. 그 외엔 결정성 위해 지정.
        if not self.model.startswith("gpt-5"):
            kwargs["temperature"] = temperature
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        # LangSmith 노드·모델 태그 (활성 시). answer 외 rewrite/route도 모델비교에 포함.
        if _tracing_on():
            kwargs["langsmith_extra"] = {
                "name": self.node or "llm",
                "metadata": {"node": self.node, "model": self.model},
                "tags": ["node:" + (self.node or "?"), "model:" + self.model]}
        try:
            r = self._client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            raise LLMError("{} 호출 실패({}): {}".format(self.provider, self.model, e))
        self.last_usage = getattr(r, "usage", None)
        return r.choices[0].message.content or ""


def check_ollama_model(model):
    """Ollama에 모델이 설치돼 있는지 확인 (없으면 pull 안내 예외)."""
    import subprocess
    try:
        out = subprocess.run(["ollama", "list"], capture_output=True, timeout=10,
                             text=True).stdout
    except Exception:  # noqa: BLE001
        raise LLMError("Ollama가 설치/실행돼 있지 않습니다. https://ollama.com 설치 후 "
                       "`ollama pull {}`".format(model))
    base = model.split(":")[0]
    if base not in out:
        raise LLMError(
            "로컬 모델 '{}'이(가) 설치돼 있지 않습니다.\n"
            "  설치:  ollama pull {}\n"
            "  (설치된 모델: {})".format(
                model, model, ", ".join(
                    l.split()[0] for l in out.splitlines()[1:] if l.strip()) or "없음"))


def get_llm(node, local=False, api_key=None, vendor=None, local_model=None):
    """노드용 LLM 반환. local=True면 EXAONE(설치 확인), vendor="google"이면 Gemini.
    local_model을 지정하면 LOCAL_MODEL 대신 그 Ollama 태그를 사용(예: 파인튜닝 버전).
    local과 vendor가 둘 다 지정되면 local이 우선(기존 --local 동작 보존)."""
    configure_langsmith()   # 키 없으면 TRACING_V2 강제 off (401 방지, 조용히 비활성)
    if local:
        model = local_model or LOCAL_MODEL
        check_ollama_model(model)
        return LLM("ollama", model, node=node)
    if vendor == "google":
        return LLM("google", GEMINI_MODELS[node], api_key=api_key, node=node)
    return LLM("openai", MODELS[node], api_key=api_key, node=node)


def answer_chat_model(local=False, api_key=None, vendor=None, local_model=None):
    """answer 노드용 LangChain 스트리밍 모델 (graph의 messages 스트리밍용).

    답변 토큰을 UI로 흘리기 위해 answer만 LangChain ChatOpenAI 사용.
    키는 메모리에서만 쓰고 저장하지 않는다. Gemini도 OpenAI 호환 엔드포인트라
    ChatOpenAI를 base_url만 바꿔 그대로 재사용(실측 검증됨, 별도 SDK 불필요).
    local_model을 지정하면 LOCAL_MODEL 대신 그 Ollama 태그를 사용(예: 파인튜닝 버전).
    local과 vendor가 둘 다 지정되면 local이 우선(기존 --local 동작 보존).
    """
    configure_langsmith()   # ChatOpenAI 생성 전 트레이싱 상태 확정 (빈 키면 off)
    from langchain_openai import ChatOpenAI
    if local:
        model = local_model or LOCAL_MODEL
        check_ollama_model(model)
        return ChatOpenAI(model=model, base_url=OLLAMA_BASE,
                          api_key="ollama", streaming=True, temperature=0)
    if vendor == "google":
        return ChatOpenAI(model=GEMINI_MODELS["answer"], base_url=GEMINI_BASE,
                          api_key=resolve_google_key(api_key), streaming=True, temperature=0)
    model = MODELS["answer"]
    kw = {"model": model, "api_key": resolve_openai_key(api_key), "streaming": True}
    kw["temperature"] = 1 if model.startswith("gpt-5") else 0  # GPT-5 계열은 1만 허용
    return ChatOpenAI(**kw)
