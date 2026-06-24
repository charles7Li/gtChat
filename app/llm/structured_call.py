from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


class LLMError(RuntimeError):
    pass


class LLMDisabledError(LLMError):
    pass


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
        raise LLMDisabledError("LLM_ENABLE is not enabled")

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMDisabledError("LLM_API_KEY or OPENAI_API_KEY is required")

    selected_model = model or os.getenv("LLM_MODEL", "gpt-4.1-mini")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    timeout = timeout_seconds or int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    prompt = _load_prompt(prompt_name)
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
    return result


def _load_prompt(prompt_name: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / f"{prompt_name}.md"
    if not prompt_path.exists():
        raise LLMError(f"Prompt not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


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


def _parse_json_response(response: dict) -> dict:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM response did not contain choices[0].message.content") from exc

    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise LLMError("LLM response content is not text")

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
