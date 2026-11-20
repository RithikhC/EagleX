"""LLM providers: local Ollama (qwen3), Groq, Gemini Flash, or offline.

All three hosted/local options expose an OpenAI-compatible chat-completions
endpoint with native tool calling, so one small stdlib HTTP client covers
them. No SDK dependencies are needed.

Selection (env AEROTURN_LLM = auto | ollama | groq | gemini | offline):
  auto -> Ollama if reachable on localhost, else GROQ_API_KEY, else GEMINI_API_KEY,
          else offline (deterministic policy, clearly labelled as "no LLM").
Keys can live in a .env file in the project root (see .env.example).

Resilience (Round 3): every call goes through ResilientClient:
  * a time limit per call (AEROTURN_LLM_TIMEOUT, default 20 s), so one slow call cannot freeze the agent;
  * at most 2 retries with a short wait (1 s, then 2 s), then stop;
  * a fallback chain: primary model -> backup provider/model -> the local offline policy (no network);
  * plain messages for the user ("timed out, retrying", "using the backup") instead of a crash;
  * every call is metered (provider, latency, input/output tokens) for the cost and latency report.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
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


_RETRY_IN = re.compile(r"try again in\s+(?:(\d+)m)?\s*([\d.]+)\s*(ms|s)?", re.I)


class OpenAICompatClient:
    # Free tiers (Groq, Gemini) limit tokens per minute: a few large calls beat many small ones.
    RATE_LIMITED_PROVIDERS = ("groq", "gemini")

    def __init__(self, provider: str, base_url: str, api_key: str, model: str, timeout: float | None = None,
                 max_retries: int = 2, max_wait_s: float = 20.0):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout or float(os.environ.get("AEROTURN_LLM_TIMEOUT", "20"))
        self.max_retries = max_retries
        self.max_wait_s = max_wait_s
        self.on_wait = None          # callback(seconds, reason) so the UI can show "rate limited, waiting"
        self._dropped: set[str] = set()

    @property
    def label(self) -> str:
        return f"{self.model} via {self.provider}"

    @property
    def is_qwen3(self) -> bool:
        return "qwen3" in self.model.lower()

    @property
    def rate_limited(self) -> bool:
        return self.provider in self.RATE_LIMITED_PROVIDERS

    def _post(self, body: dict, timeout: float | None = None) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}",
                     "User-Agent": "aeroturn/1.0"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            return json.loads(r.read().decode())

    def chat(self, messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2,
             max_tokens: int = 1200, json_mode: bool = False, timeout: float | None = None) -> LLMResponse:
        body: dict = {"model": self.model, "messages": messages, "temperature": temperature,
                      "max_tokens": max_tokens, "stream": False}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if json_mode and "response_format" not in self._dropped:
            body["response_format"] = {"type": "json_object"}
        if self.provider == "groq" and "reasoning_effort" not in self._dropped:
            # keep hidden reasoning short: it counts against the free tier's tokens-per-minute
            if "gpt-oss" in self.model:
                body["reasoning_effort"] = "low"
            elif "qwen" in self.model:
                body["reasoning_effort"] = "none"
        attempt = 0
        while True:
            try:
                data = self._post(body, timeout)
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:600]
                bad = next((p for p in ("reasoning_effort", "response_format") if p in body and p in detail), None)
                if e.code == 400 and bad:          # provider/model does not support an optional parameter
                    self._dropped.add(bad)
                    body.pop(bad, None)
                    continue
                if e.code in (429, 500, 502, 503) and attempt < self.max_retries:
                    attempt += 1
                    wait = _retry_wait(e.headers.get("retry-after"), detail, attempt)
                    if wait > self.max_wait_s:
                        raise RuntimeError(f"{self.provider} rate limit: retry would take {wait:.0f}s") from None
                    if self.on_wait:
                        self.on_wait(wait, "rate limit" if e.code == 429 else f"HTTP {e.code}")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"{self.provider} HTTP {e.code}: {detail[:300]}") from None
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


def _retry_wait(header: str | None, detail: str, attempt: int) -> float:
    try:
        if header:
            return float(header) + 0.5
    except ValueError:
        pass
    m = _RETRY_IN.search(detail or "")
    if m:
        minutes_part = float(m.group(1) or 0) * 60
        val = float(m.group(2))
        return minutes_part + (val / 1000 if (m.group(3) or "s").lower() == "ms" else val) + 0.5
    return min(30.0, 2.0 * attempt)


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
        return {"provider": "groq", "model": _pick_groq_model(os.environ["GROQ_API_KEY"], os.environ.get("GROQ_MODEL")),
                "base_url": "https://api.groq.com/openai/v1", "api_key": os.environ["GROQ_API_KEY"]}
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if choice in ("auto", "gemini") and key:
        return {"provider": "gemini", "model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "api_key": key}
    return {"provider": "offline", "reason": "no LLM configured (set AEROTURN_LLM / keys in .env)"}


GROQ_PREFERENCE = ("openai/gpt-oss-120b", "qwen/qwen3", "llama-3.3-70b-versatile", "openai/gpt-oss-20b",
                   "meta-llama/llama-4")


def _pick_groq_model(api_key: str, wanted: str | None) -> str:
    """Use GROQ_MODEL if Groq still serves it, else the best available tool-calling model."""
    try:
        req = urllib.request.Request("https://api.groq.com/openai/v1/models",
                                     headers={"Authorization": f"Bearer {api_key}", "User-Agent": "aeroturn/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            available = [m["id"] for m in json.loads(r.read().decode()).get("data", [])]
    except Exception:  # noqa: BLE001 - offline / bad key: keep the configured name and let chat() report it
        return wanted or GROQ_PREFERENCE[0]
    if wanted and wanted in available:
        return wanted
    for pref in GROQ_PREFERENCE:
        hit = next((m for m in available if m.startswith(pref)), None)
        if hit:
            return hit
    return wanted or (available[0] if available else GROQ_PREFERENCE[0])


# ---------------------------------------------------------------------------
# Resilience: timeout, limited retries, fallback chain, metering
# ---------------------------------------------------------------------------
RETRIES = 2                  # per model, after the first try
RETRY_WAITS_S = (1.0, 2.0)   # short waits between retries
SIMULATION = {"mode": None}  # "slow_primary": the primary model gets a 0.05 s limit, so it really times out
CALL_LOG: list[dict] = []    # every model call in this process (for the cost and latency report)


def _kind(exc: Exception) -> str:
    text = str(exc).lower()
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in text or "timeout" in text:
        return "timeout"
    if "rate limit" in text or "http 429" in text:
        return "rate limit"
    if "http 401" in text or "http 403" in text:
        return "auth"
    return "error"


class ResilientClient:
    """Same interface as OpenAICompatClient, but every call has a time limit, at most two short retries, and a
    fallback to the next model in the chain. When every model fails it raises, and the agent's local offline
    policy (deterministic, no network) finishes the job."""

    def __init__(self, chain: list[OpenAICompatClient]):
        self.chain = chain
        self.on_wait = None
        self.on_notice = None        # callback(text): plain messages for the user
        self.calls: list[dict] = []  # this client's metered calls
        self.used = chain[0]
        self.simulate_slow = False   # per client: the primary model gets a 0.05 s limit and really times out
        self.waits: list[float] = []  # seconds spent waiting on provider rate limits (measured, for the latency report)

    # identity of the primary model (what the run is labelled with)
    @property
    def label(self) -> str:
        return self.chain[0].label

    @property
    def model(self) -> str:
        return self.chain[0].model

    @property
    def provider(self) -> str:
        return self.chain[0].provider

    @property
    def is_qwen3(self) -> bool:
        return self.chain[0].is_qwen3

    @property
    def rate_limited(self) -> bool:
        return self.chain[0].rate_limited

    @property
    def backups(self) -> list[str]:
        return [c.label for c in self.chain[1:]]

    def _notice(self, text: str) -> None:
        if self.on_notice:
            self.on_notice(text)

    def chat(self, messages: list[dict], **kw) -> LLMResponse:
        last = "no model configured"
        def waited(s, why, _outer=self.on_wait):
            self.waits.append(float(s))
            if _outer:
                _outer(s, why)

        for i, c in enumerate(self.chain):
            c.on_wait = waited
            slow = self.simulate_slow or SIMULATION["mode"] == "slow_primary"
            limit = 0.05 if (slow and i == 0) else c.timeout
            for attempt in range(RETRIES + 1):
                t0 = time.perf_counter()
                try:
                    resp = c.chat(messages, timeout=limit, **kw)
                except Exception as exc:  # noqa: BLE001 - classified, logged, retried or handed over
                    kind = _kind(exc)
                    last = f"{c.label}: {kind}"
                    self._meter(c, i, attempt, kind, t0, None, str(exc)[:160])
                    if kind in ("timeout", "error") and attempt < RETRIES:
                        wait = RETRY_WAITS_S[attempt]
                        self._notice(f"{c.model} {kind} after {limit:g} s. Still working: retry {attempt + 1}/"
                                     f"{RETRIES} in {wait:g} s")
                        time.sleep(wait)
                        continue
                    break
                self._meter(c, i, attempt, "ok", t0, (resp.raw or {}).get("usage") or {}, "")
                self.used = c
                if i > 0:
                    self._notice(f"Answered by the backup model {c.label}")
                return resp
            nxt = self.chain[i + 1].label if i + 1 < len(self.chain) else "the local offline policy (no network)"
            self._notice(f"Couldn't reach {c.label} ({last.split(': ')[-1]}). Using {nxt} instead")
        raise RuntimeError(f"all models unavailable ({last}); the local offline policy takes over")

    def _meter(self, c: OpenAICompatClient, rank: int, attempt: int, status: str, t0: float, usage: dict | None,
               error: str) -> None:
        rec = {"at": time.strftime("%H:%M:%S"), "provider": c.provider, "model": c.model,
               "role": "primary" if rank == 0 else "backup", "attempt": attempt + 1, "status": status,
               "latency_ms": int((time.perf_counter() - t0) * 1000),
               "input_tokens": int((usage or {}).get("prompt_tokens") or 0),
               "output_tokens": int((usage or {}).get("completion_tokens") or 0), "error": error}
        self.calls.append(rec)
        CALL_LOG.append(rec)
        del CALL_LOG[:-500]


BACKUP_PREFERENCE = ("llama-3.3-70b-versatile", "openai/gpt-oss-20b", "llama-3.1-8b-instant")


_MODELS_CACHE: dict[str, list[str]] = {}


def _groq_models(api_key: str) -> list[str]:
    if api_key in _MODELS_CACHE:
        return _MODELS_CACHE[api_key]
    try:
        req = urllib.request.Request("https://api.groq.com/openai/v1/models",
                                     headers={"Authorization": f"Bearer {api_key}", "User-Agent": "aeroturn/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            _MODELS_CACHE[api_key] = [m["id"] for m in json.loads(r.read().decode()).get("data", [])]
            return _MODELS_CACHE[api_key]
    except Exception:  # noqa: BLE001
        return []


def backup_chain(info: dict) -> list[OpenAICompatClient]:
    """Backups after the primary: a second provider when its key exists (Gemini, Groq), then a second Groq model."""
    out: list[OpenAICompatClient] = []
    gem = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    groq = os.environ.get("GROQ_API_KEY")
    if info["provider"] != "gemini" and gem:
        out.append(OpenAICompatClient("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", gem,
                                      os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")))
    if groq:
        if info["provider"] != "groq":
            out.append(OpenAICompatClient("groq", "https://api.groq.com/openai/v1", groq,
                                          _pick_groq_model(groq, os.environ.get("GROQ_MODEL"))))
        available = _groq_models(groq)
        want = os.environ.get("GROQ_BACKUP_MODEL")
        pick = want if want and (not available or want in available) else next(
            (m for m in BACKUP_PREFERENCE if m in available and m != info.get("model")), None)
        if pick:
            out.append(OpenAICompatClient("groq", "https://api.groq.com/openai/v1", groq, pick))
    return out


def make_client(info: dict | None = None) -> ResilientClient | None:
    info = info or detect()
    if info["provider"] == "offline":
        return None
    primary = OpenAICompatClient(info["provider"], info["base_url"], info["api_key"], info["model"])
    return ResilientClient([primary] + backup_chain(info))


def describe(info: dict) -> str:
    if info["provider"] == "offline":
        return f"Offline policy, no LLM ({info.get('reason', '')})"
    return f"{info['model']} via {info['provider']}"
