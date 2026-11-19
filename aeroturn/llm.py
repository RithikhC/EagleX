"""LLM providers: local Ollama (qwen3), Groq, Gemini Flash, or offline.

All three hosted/local options expose an OpenAI-compatible chat-completions
endpoint with native tool calling, so one small stdlib HTTP client covers
them. No SDK dependencies are needed.

Selection (env AEROTURN_LLM = auto | ollama | groq | gemini | offline):
  auto -> Ollama if reachable on localhost, else GROQ_API_KEY, else GEMINI_API_KEY,
          else offline (deterministic policy, clearly labelled as "no LLM").
Keys can live in a .env file in the project root (see .env.example).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field

from .config import ROOT


def load_dotenv(path=None) -> None:
    path = path or ROOT / ".env"
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str = ""
    raw: dict = field(default_factory=dict)


_THINK = re.compile(r"<think>(.*?)</think>", re.S | re.I)


class OpenAICompatClient:
    def __init__(self, provider: str, base_url: str, api_key: str, model: str, timeout: int = 180):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def label(self) -> str:
        return f"{self.model} via {self.provider}"

    @property
    def is_qwen3(self) -> bool:
        return "qwen3" in self.model.lower()

    def chat(self, messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2,
             max_tokens: int = 1200) -> LLMResponse:
        body: dict = {"model": self.model, "messages": messages, "temperature": temperature,
                      "max_tokens": max_tokens, "stream": False}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}",
                     "User-Agent": "aeroturn/1.0"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            raise RuntimeError(f"{self.provider} HTTP {e.code}: {detail}") from None
        msg = (data.get("choices") or [{}])[0].get("message", {}) or {}
        content = msg.get("content") or ""
        thinking = "\n".join(m.strip() for m in _THINK.findall(content))
        if msg.get("reasoning_content"):
            thinking = (thinking + "\n" + msg["reasoning_content"]).strip()
        if msg.get("reasoning"):
            thinking = (thinking + "\n" + str(msg["reasoning"])).strip()
        content = _THINK.sub("", content).strip()
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments") or "{}"
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {"__unparseable__": args[:200]}
            calls.append(ToolCall(id=tc.get("id") or f"call_{uuid.uuid4().hex[:8]}", name=fn.get("name", ""),
                                  arguments=args if isinstance(args, dict) else {}))
        if not calls and content:
            calls = _parse_inline_tool_call(content)
            if calls:
                content = ""
        return LLMResponse(content=content, tool_calls=calls, thinking=thinking, raw=data)


def _parse_inline_tool_call(text: str) -> list[ToolCall]:
    """Fallback for models that print a JSON tool call instead of using native tool calling."""
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    name = obj.get("tool") or obj.get("name") or obj.get("function")
    args = obj.get("arguments") or obj.get("args") or obj.get("parameters") or {}
    if isinstance(name, str) and isinstance(args, dict):
        return [ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=name, arguments=args)]
    return []


def _ollama_models(host: str) -> list[str]:
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=1.5) as r:
            return [m["name"] for m in json.loads(r.read().decode()).get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def detect() -> dict:
    """Describe which brain would be used, without making a chat call."""
    load_dotenv()
    choice = os.environ.get("AEROTURN_LLM", "auto").lower()
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if choice in ("auto", "ollama"):
        models = _ollama_models(host)
        want = os.environ.get("OLLAMA_MODEL")
        if models:
            model = want if want in models else next((m for m in models if m.startswith("qwen3")), models[0])
            return {"provider": "ollama", "model": model, "base_url": f"{host.rstrip('/')}/v1", "api_key": "ollama"}
        if choice == "ollama":
            return {"provider": "offline", "reason": f"Ollama not reachable at {host}"}
    if choice in ("auto", "groq") and os.environ.get("GROQ_API_KEY"):
        return {"provider": "groq", "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                "base_url": "https://api.groq.com/openai/v1", "api_key": os.environ["GROQ_API_KEY"]}
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if choice in ("auto", "gemini") and key:
        return {"provider": "gemini", "model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "api_key": key}
    return {"provider": "offline", "reason": "no LLM configured (set AEROTURN_LLM / keys in .env)"}


def make_client(info: dict | None = None) -> OpenAICompatClient | None:
    info = info or detect()
    if info["provider"] == "offline":
        return None
    return OpenAICompatClient(info["provider"], info["base_url"], info["api_key"], info["model"])


def describe(info: dict) -> str:
    if info["provider"] == "offline":
        return f"Offline policy, no LLM ({info.get('reason', '')})"
    return f"{info['model']} via {info['provider']}"
