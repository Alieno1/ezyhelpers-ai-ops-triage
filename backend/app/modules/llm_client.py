"""OpenRouter (OpenAI-compatible) chat-completions client.

* Credentials only from the backend environment.
* Timeouts, limited retries with exponential backoff (429 / 5xx / network), Retry-After honoured (capped).
* No retry on 400/401/402/403/404 (bad request, key, credits, permission, unknown model).
* Records actual model, usage and cost ONLY as returned by the provider. Nothing is estimated here.
* ``transport`` can be injected for tests (httpx.MockTransport); such calls are marked simulated.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.schemas import LLMCallRecord

log = logging.getLogger("triage.llm")
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}


def _sum_opt(a: int | None, b: int | None) -> int | None:
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)


class LLMError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class OpenRouterClient:
    provider = "openrouter"

    def __init__(self, api_key: str, model: str, base_url: str = "https://openrouter.ai/api/v1", timeout: float = 45.0,
                 max_retries: int = 2, temperature: float = 0.0, transport: httpx.BaseTransport | None = None,
                 backoff_base: float = 1.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.temperature = temperature
        self.transport = transport
        self.backoff_base = backoff_base

    @property
    def simulated(self) -> bool:
        return self.transport is not None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ezyhelpers-ops-triage",
            "X-Title": "EzyHelpers Ops Triage",
        }

    def chat(self, messages: list[dict[str, Any]], json_schema: dict[str, Any] | None = None, issue_id: str | None = None,
             max_tokens: int = 3500, reasoning_enabled: bool | None = False) -> LLMCallRecord:
        rec = LLMCallRecord(call_id=uuid.uuid4().hex[:12], issue_id=issue_id, ok=False, provider=self.provider,
                            model_requested=self.model, started_at=datetime.now(timezone.utc).isoformat(), duration_ms=0,
                            attempts=0, request_messages=messages, simulated=self.simulated)
        if not self.api_key:
            rec.error_type, rec.error_message = "missing_api_key", "OPENROUTER_API_KEY is not set"
            return rec
        body: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": self.temperature,
                                "max_tokens": max_tokens, "usage": {"include": True}}
        if reasoning_enabled is not None:
            body["reasoning"] = {"enabled": reasoning_enabled}
        if json_schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "triage", "strict": True, "schema": json_schema}}
        t0 = time.monotonic()
        downgraded = False
        reasoning_stripped = False
        router_reasoning_retried = False
        truncated_retried = False
        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            while True:
                rec.attempts += 1
                try:
                    r = client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body)
                except httpx.TimeoutException as e:
                    rec.error_type, rec.error_message = "timeout", f"Request timed out after {self.timeout}s: {e}"
                    if self._sleep_before_retry(rec, None):
                        continue
                    break
                except httpx.HTTPError as e:
                    rec.error_type, rec.error_message = "network_error", str(e)
                    if self._sleep_before_retry(rec, None):
                        continue
                    break
                if r.status_code == 200:
                    try:
                        data = r.json()
                    except ValueError:
                        rec.error_type, rec.error_message = "invalid_provider_json", r.text[:500]
                        break
                    if "error" in data and not data.get("choices"):
                        err = data["error"] or {}
                        rec.error_type = f"provider_error_{err.get('code', 'unknown')}"
                        rec.error_message = str(err.get("message", err))[:500]
                        if self._sleep_before_retry(rec, None):
                            continue
                        break
                    prev = (rec.prompt_tokens, rec.completion_tokens, rec.total_tokens, rec.cost_usd)
                    self._fill_success(rec, data)
                    rec.prompt_tokens = _sum_opt(prev[0], rec.prompt_tokens)
                    rec.completion_tokens = _sum_opt(prev[1], rec.completion_tokens)
                    rec.total_tokens = _sum_opt(prev[2], rec.total_tokens)
                    if prev[3] is not None or rec.cost_usd is not None:
                        rec.cost_usd = (prev[3] or 0.0) + (rec.cost_usd or 0.0)
                    if rec.error_type == "incomplete_response" and not truncated_retried and self.max_retries > 0:
                        truncated_retried = True
                        rec.validation_errors.append(f"truncated output ({rec.model_used or self.model}); retried once")
                        rec.error_type = None
                        rec.error_message = None
                        continue
                    break
                text = r.text[:800]
                if r.status_code == 400 and json_schema and not downgraded and "response_format" in text.lower():
                    # Model does not support json_schema: fall back to json_object mode once.
                    body["response_format"] = {"type": "json_object"}
                    downgraded = True
                    rec.validation_errors.append("json_schema unsupported by model; retried with json_object")
                    continue
                if r.status_code == 400 and "reasoning" in body and "reasoning" in text.lower():
                    if self.model == "openrouter/free" and not router_reasoning_retried and self.max_retries > 0:
                        router_reasoning_retried = True
                        rec.validation_errors.append("routed free model rejected reasoning flag; retried router keeping reasoning config")
                        continue
                    if not reasoning_stripped:
                        body.pop("reasoning", None)
                        reasoning_stripped = True
                        rec.validation_errors.append("reasoning parameter unsupported by model; retried without reasoning")
                        continue
                kind = {401: "invalid_api_key", 402: "insufficient_credits", 403: "forbidden", 404: "model_unavailable",
                        429: "rate_limited"}.get(r.status_code, f"http_{r.status_code}")
                rec.error_type, rec.error_message = kind, text
                if r.status_code in RETRYABLE and self._sleep_before_retry(rec, r.headers.get("retry-after")):
                    continue
                break
        rec.duration_ms = int((time.monotonic() - t0) * 1000)
        log.info("llm_call id=%s issue=%s ok=%s model=%s attempts=%s ms=%s tokens=%s cost=%s err=%s", rec.call_id, issue_id, rec.ok,
                 rec.model_used or rec.model_requested, rec.attempts, rec.duration_ms, rec.total_tokens, rec.cost_usd, rec.error_type)
        return rec

    def _sleep_before_retry(self, rec: LLMCallRecord, retry_after: str | None) -> bool:
        if rec.attempts > self.max_retries:
            return False
        delay = self.backoff_base * (2 ** (rec.attempts - 1))
        if retry_after:
            try:
                delay = max(delay, min(float(retry_after), 10.0))
            except ValueError:
                pass
        time.sleep(delay)
        return True

    @staticmethod
    def _fill_success(rec: LLMCallRecord, data: dict[str, Any]) -> None:
        choices = data.get("choices") or []
        if not choices:
            rec.error_type, rec.error_message = "empty_response", "No choices returned"
            rec.raw_response = data
            return
        ch = choices[0]
        msg = ch.get("message") or {}
        rec.raw_content = msg.get("content")
        rec.finish_reason = ch.get("finish_reason") or ch.get("native_finish_reason")
        rec.model_used = data.get("model")
        rec.provider_upstream = data.get("provider")
        rec.generation_id = data.get("id")
        usage = data.get("usage") or {}
        rec.prompt_tokens = usage.get("prompt_tokens")
        rec.completion_tokens = usage.get("completion_tokens")
        rec.total_tokens = usage.get("total_tokens")
        cost = usage.get("cost")
        rec.cost_usd = float(cost) if isinstance(cost, (int, float)) else None
        rec.raw_response = data
        if rec.finish_reason == "length":
            rec.error_type, rec.error_message = "incomplete_response", "Model stopped at max_tokens; output truncated"
            return
        if not rec.raw_content:
            rec.error_type, rec.error_message = "empty_content", "Model returned no content"
            return
        rec.ok = True


def parse_json_content(content: str) -> dict[str, Any]:
    """Parse model text into JSON, tolerating ```json fences. Raises ValueError on failure."""
    t = (content or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    t = t.strip()
    if not t.startswith("{"):
        start, end = t.find("{"), t.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("No JSON object found in model output")
        t = t[start:end + 1]
    obj = json.loads(t)
    if not isinstance(obj, dict):
        raise ValueError("Model output JSON is not an object")
    return obj

