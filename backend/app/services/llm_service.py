"""
LLM Service interfacing with LiteLLM and Groq provider with multi-key failover.
"""
import time
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import litellm

from app.config import settings
from app.utils.key_manager import KeyManager, KeyEntry
from app.utils.exceptions import AllProvidersUnavailableException

logger = logging.getLogger(__name__)

# Ensure LiteLLM telemetry and unnecessary noise are suppressed
litellm.telemetry = False
litellm.suppress_debug_info = True

RETRYABLE_STATUS_CODES = {429, 500, 502, 503}
RETRYABLE_EXCEPTION_TYPES = (
    litellm.RateLimitError,
    litellm.InternalServerError,
    litellm.BadGatewayError,
    litellm.ServiceUnavailableError,
    litellm.APIConnectionError,
    litellm.BudgetExceededError,
    litellm.Timeout if hasattr(litellm, "Timeout") else TimeoutError,
)


# def is_retryable_error(exc: Exception) -> bool:
#     """
#     Determine if an exception represents a retryable provider error:
#     - HTTP 429 / RateLimitError / Quota exhaustion
#     - HTTP 500 / InternalServerError
#     - HTTP 502 / BadGatewayError
#     - HTTP 503 / ServiceUnavailableError
#     - Transient network / connection / timeout errors
#     """
#     if isinstance(exc, RETRYABLE_EXCEPTION_TYPES):
#         return True

#     status_code = getattr(exc, "status_code", None)
#     if status_code in RETRYABLE_STATUS_CODES:
#         return True

#     response = getattr(exc, "response", None)
#     if response and getattr(response, "status_code", None) in RETRYABLE_STATUS_CODES:
#         return True

#     err_str = str(exc).lower()
#     for code_str in ["429", "rate limit", "quota", "500", "502", "503", "service unavailable", "bad gateway"]:
#         if code_str in err_str:
#             return True

#     return False

def is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, RETRYABLE_EXCEPTION_TYPES):
        return True

    status_code = getattr(exc, "status_code", None)

    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)

    if status_code in RETRYABLE_STATUS_CODES:
        return True

    if status_code in {401, 403}:
        return True

    return isinstance(exc, (ConnectionError, TimeoutError))
@dataclass
class LLMExecutionResult:
    """Encapsulates the result of an LLM completion execution."""
    reply: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    resolution_source: str  # "LIVE_INFERENCE" or "LLM_CACHE"
    key_id: Optional[str]
    fallback_attempts: int


class LLMService:
    """Service responsible for LiteLLM gateway calls to Groq with sequential key failover."""

    @staticmethod
    def get_model_name() -> str:
        """
        Return the standardized model string for LiteLLM Groq provider.
        e.g., 'groq/llama-3.3-70b-versatile'
        """
        model = settings.GROQ_MODEL.strip()
        if not model.startswith("groq/"):
            return f"groq/{model}"
        return model

    @classmethod
    def call_completion(
        cls,
        messages: List[Dict[str, str]],
        api_key: str,
        key_id: Optional[str] = "key_1",
        fallback_attempts: int = 0
    ) -> LLMExecutionResult:
        """
        Execute a completion call through LiteLLM with a specific API key.
        Measures server latency and extracts token usage.
        """
        model_name = cls.get_model_name()
        start_time = time.perf_counter()

        response = litellm.completion(
            model=model_name,
            messages=messages,
            api_key=api_key,
            max_tokens=settings.MAX_TOKENS if settings.MAX_TOKENS and settings.MAX_TOKENS > 0 else 1024
        )

        elapsed_ms = int(round((time.perf_counter() - start_time) * 1000))

        # Check for LiteLLM cache hit
        hidden_params = getattr(response, "_hidden_params", {})
        if not isinstance(hidden_params, dict):
            hidden_params = {}

        is_cache = False
        if hidden_params.get("custom_llm_provider") == "cache" or hidden_params.get("cache_hit") is True:
            is_cache = True
        elif hasattr(response, "is_cached") and response.is_cached is True:
            is_cache = True

        resolution_source = "LLM_CACHE" if is_cache else "LIVE_INFERENCE"

        # Extract content
        choice = response.choices[0]
        content = choice.message.content if hasattr(choice.message, "content") else choice.message.get("content", "")

        # Extract token usage
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

        try:
            prompt_tokens = int(prompt_tokens)
        except (ValueError, TypeError):
            prompt_tokens = 0
        try:
            completion_tokens = int(completion_tokens)
        except (ValueError, TypeError):
            completion_tokens = 0

        actual_model = getattr(response, "model", None) or model_name

        return LLMExecutionResult(
            reply=content or "",
            model=actual_model,
            latency_ms=elapsed_ms,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            resolution_source=resolution_source,
            key_id=None if is_cache else key_id,
            fallback_attempts=0 if is_cache else fallback_attempts
        )

    @classmethod
    def execute_with_failover(
        cls,
        messages: List[Dict[str, str]],
        key_manager: KeyManager,
        simulated_failures: Optional[Dict[str, int]] = None
    ) -> LLMExecutionResult:
        """
        Execute completion with automatic sequential failover across configured keys.
        - Preserves identical model and prompt messages across retries.
        - Switches to next key on 429, rate limits, quota exhaustion, 500, 502, 503, etc.
        - Returns a clean 503 (AllProvidersUnavailableException) when all keys fail.
        """
        entries: List[KeyEntry] = key_manager.get_entries()
        if not entries:
            raise AllProvidersUnavailableException("all providers unavailable")

        fallback_attempts = 0
        last_exception: Optional[Exception] = None

        for entry in entries:
            key_id = entry.key_id
            api_key = entry.secret

            # Check if simulation hook applies to this key
            try:
                if simulated_failures:
                    simulated_status = simulated_failures.get(key_id) or simulated_failures.get("*")
                    if simulated_status:
                        logger.info("Simulating failure HTTP %s for %s", simulated_status, key_id)
                        err = RuntimeError(f"Simulated provider error HTTP {simulated_status} for {key_id}")
                        err.status_code = simulated_status  # type: ignore[attr-defined]
                        raise err

                result = cls.call_completion(
                    messages=messages,
                    api_key=api_key,
                    key_id=key_id,
                    fallback_attempts=fallback_attempts
                )
                return result

            except Exception as exc:
                last_exception = exc
                err_detail = str(exc).replace(api_key, "***")[:250]
                if is_retryable_error(exc):
                    logger.warning(
                        "Key %s failed with transient error: %s (%s). Attempting failover.",
                        key_id,
                        exc.__class__.__name__,
                        err_detail,
                    )
                    fallback_attempts += 1
                    continue
                else:
                    # Non-retryable error, still try next key if available
                    logger.error(
                        "Key %s encountered unexpected error: %s. Attempting failover.",
                        key_id,
                        exc.__class__.__name__
                    )
                    raise
                    # fallback_attempts += 1
                    # continue

        # All keys in pool exhausted
        logger.error("All %d configured API keys failed. Raising 503.", len(entries))
        raise AllProvidersUnavailableException("all providers unavailable")
