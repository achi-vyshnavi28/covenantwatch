"""One model-agnostic call path: any LiteLLM model (Gemini, Gemma, Claude, OpenAI), JSON output validated by pydantic,
retries on rate limits, a disk cache (re-running an eval costs nothing), and latency / token / cost accounting."""

import hashlib
import json
import os
import time

from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from covenantwatch.config import CACHE, MODELS


def _complete(model_id: str, messages: list[dict]):
    # imported lazily: the API and the daily rule checks run without loading the LLM stack at all
    import litellm

    litellm.suppress_debug_info = True
    transient = (litellm.RateLimitError, litellm.InternalServerError, litellm.ServiceUnavailableError,
                 litellm.APIConnectionError, litellm.Timeout)

    @retry(retry=retry_if_exception_type(transient), wait=wait_exponential(min=4, max=90), stop=stop_after_attempt(8), reraise=True)
    def attempt():
        return litellm.completion(model=model_id, messages=messages, temperature=0, timeout=120,
                                  response_format={"type": "json_object"})

    return attempt()


KEY_FOR = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY"}


class MissingKey(RuntimeError):
    pass


def call(model: str, system: str, user: str, schema: type[BaseModel], use_cache: bool = True) -> tuple[BaseModel, dict]:
    spec = MODELS[model]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    key = hashlib.sha256(json.dumps([spec["id"], messages, schema.__name__]).encode()).hexdigest()[:32]
    path = CACHE / "llm" / f"{key}.json"
    if use_cache and path.exists():
        hit = json.loads(path.read_text(encoding="utf-8"))
        return schema.model_validate(hit["out"]), {**hit["meta"], "cached": True}
    env = KEY_FOR.get(spec["id"].split("/")[0])
    if env and not os.getenv(env):  # fail fast: without a key some providers hang instead of erroring
        raise MissingKey(f"{env} is not set")
    t = time.time()
    r = _complete(spec["id"], messages)
    text = r.choices[0].message.content or "{}"
    try:
        out = schema.model_validate_json(_strip_fences(text))
    except ValidationError:  # one repair attempt: show the model its own output and the error
        r2 = _complete(spec["id"], messages + [{"role": "assistant", "content": text},
                                               {"role": "user", "content": "That was not valid JSON for the schema. Return only the corrected JSON."}])
        out = schema.model_validate_json(_strip_fences(r2.choices[0].message.content or "{}"))
    pin, pout = r.usage.prompt_tokens or 0, r.usage.completion_tokens or 0
    meta = {"model": model, "latency_s": round(time.time() - t, 2), "tokens_in": pin, "tokens_out": pout,
            "cost_usd": round((pin * spec["in"] + pout * spec["out"]) / 1e6, 6), "cached": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"out": out.model_dump(), "meta": meta}), encoding="utf-8")
    return out, meta


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text
