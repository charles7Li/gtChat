from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from contextvars import ContextVar, Token
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError


class LLMError(RuntimeError):
    pass


class LLMDisabledError(LLMError):
    pass


_LLM_EVENTS: ContextVar[list[dict] | None] = ContextVar("llm_events", default=None)


def start_llm_trace() -> Token:
    return _LLM_EVENTS.set([])


def finish_llm_trace(token: Token) -> list[dict]:
    events = list(_LLM_EVENTS.get() or [])
    _LLM_EVENTS.reset(token)
    return events


def structured_llm_call(
    prompt_name: str,
    payload: dict,
    schema: type | None = None,
    *,
    model: str | None = None,
    timeout_seconds: int | None = None,
) -> dict:
    """Call an OpenAI-compatible chat completions API and parse JSON output."""
    if os.getenv("LLM_ENABLE", "").lower() not in {"1", "true", "yes"}:
        message = "LLM_ENABLE is not enabled"
        _record_llm_event(prompt_name, "disabled", error=message)
        raise LLMDisabledError(message)

    preset = os.getenv("LLM_PRESET", "").lower()
    api_key = _api_key_for_preset(preset)
    if not api_key:
        message = "LLM_API_KEY, OPENAI_API_KEY, or preset-specific API key is required"
        _record_llm_event(prompt_name, "disabled", error=message)
        raise LLMDisabledError(message)

    selected_model = model or os.getenv("LLM_MODEL", "gpt-4.1-mini")
    base_url = _base_url_for_preset(preset)
    timeout = timeout_seconds or int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    provider = os.getenv("LLM_PROVIDER", "openai-compatible").lower()

    try:
        prompt = _load_prompt(prompt_name)
        if provider == "langchain":
            result = _call_langchain_chat_openai(
                base_url=base_url,
                api_key=api_key,
                model=selected_model,
                prompt=prompt,
                payload=payload,
                timeout_seconds=timeout,
            )
            _validate_mapping(result)
            validated = _validate_schema(result, schema)
            _record_llm_event(prompt_name, "success", provider=provider, model=selected_model)
            return validated

        response = _post_chat_completion(
            base_url=base_url,
            api_key=api_key,
            model=selected_model,
            prompt=prompt,
            payload=payload,
            timeout_seconds=timeout,
        )
        result = _parse_json_response(response)
        _validate_mapping(result)
        validated = _validate_schema(result, schema)
        _record_llm_event(prompt_name, "success", provider=provider, model=selected_model)
        return validated
    except LLMError as exc:
        _record_llm_event(prompt_name, "failed", provider=provider, model=selected_model, error=str(exc))
        raise


def _load_prompt(prompt_name: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / f"{prompt_name}.md"
    if not prompt_path.exists():
        raise LLMError(f"Prompt not found: {prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8")
    skill = _load_skill(prompt_name)
    if skill:
        return f"{prompt}\n\n# Node Skill\n{skill}"
    return prompt


def _load_skill(prompt_name: str) -> str:
    skill_path = Path(__file__).resolve().parents[1] / "skills" / f"{prompt_name}.md"
    if not skill_path.exists():
        return ""
    return skill_path.read_text(encoding="utf-8").strip()


def _api_key_for_preset(preset: str) -> str | None:
    if preset == "packyapi":
        return os.getenv("PACKY_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    return os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")


def _base_url_for_preset(preset: str) -> str:
    if os.getenv("LLM_BASE_URL"):
        return os.getenv("LLM_BASE_URL", "").rstrip("/")
    if preset == "packyapi":
        return "https://www.packyapi.com/v1"
    return "https://api.openai.com/v1"


def _post_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    payload: dict,
    timeout_seconds: int,
) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, indent=2),
            },
        ],
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.4")),
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMError(f"LLM HTTP {exc.code}: {detail[:1000]}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc


def _call_langchain_chat_openai(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    payload: dict,
    timeout_seconds: int,
) -> dict:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise LLMError("LLM_PROVIDER=langchain requires langchain-openai") from exc

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.4")),
        timeout=timeout_seconds,
    ).bind(response_format={"type": "json_object"})
    try:
        response = llm.invoke(
            [
                ("system", prompt),
                ("human", json.dumps(payload, ensure_ascii=False, indent=2)),
            ]
        )
    except Exception as exc:
        raise LLMError(f"LangChain ChatOpenAI call failed: {exc}") from exc

    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return _parse_json_text(str(content))


def _parse_json_response(response: dict) -> dict:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM response did not contain choices[0].message.content") from exc

    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise LLMError("LLM response content is not text")

    return _parse_json_text(content)


def _parse_json_text(content: str) -> dict:
    text = _strip_code_fence(content.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM response is not valid JSON: {text[:500]}") from exc


def _strip_code_fence(text: str) -> str:
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return match.group(1).strip() if match else text


def _validate_mapping(result: object) -> None:
    if not isinstance(result, dict):
        raise LLMError("LLM JSON output must be an object")


def _validate_schema(result: dict, schema: type | None) -> dict:
    if schema is None:
        return result
    try:
        validated = TypeAdapter(schema).validate_python(result)
    except ValidationError as exc:
        raise LLMError(f"LLM JSON output failed schema validation: {exc}") from exc
    return _to_plain_dict(validated)


def _to_plain_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if is_dataclass(value):
        return asdict(value)
    raise LLMError("Validated LLM output could not be converted to a dict")


def _record_llm_event(
    prompt_name: str,
    status: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    error: str | None = None,
) -> None:
    events = _LLM_EVENTS.get()
    if events is None:
        return
    event = {
        "prompt": prompt_name,
        "status": status,
    }
    if provider:
        event["provider"] = provider
    if model:
        event["model"] = model
    langsmith = _langsmith_context()
    if langsmith:
        event["langsmith"] = langsmith
    if error:
        event["error"] = error[:500]
    events.append(event)


def _langsmith_context() -> dict:
    context = {}
    tracing = os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2")
    project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT")
    run_name = os.getenv("LANGSMITH_RUN_NAME") or os.getenv("LANGCHAIN_RUN_NAME")
    endpoint = os.getenv("LANGSMITH_ENDPOINT")
    if tracing:
        context["tracing"] = tracing
    if project:
        context["project"] = project
    if run_name:
        context["run_name"] = run_name
    if endpoint:
        context["endpoint"] = endpoint
    return context
