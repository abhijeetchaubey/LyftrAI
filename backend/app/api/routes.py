"""
API route definitions for health, chat, and sessions.
"""
from typing import Optional, Dict
from fastapi import APIRouter, Header, status, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database.connection import get_db, check_database_health
from app.services.conversation_service import ConversationService
from app.services.llm_service import LLMService
from app.schemas.chat_schema import (
    HealthResponse,
    ChatRequest,
    ChatResponse,
    ChatResponseMetadata,
    MessageItem,
    SessionHistoryResponse,
)
from app.utils.key_manager import KeyManager
from app.utils.exceptions import (
    SessionNotFoundException,
    AllProvidersUnavailableException,
)

router = APIRouter()

# Global key manager instance initialized from settings
key_manager = KeyManager(settings.api_keys)

SUPPORTED_SIMULATED_STATUSES = {429, 500, 502, 503}


def parse_simulate_failure_header(header_value: Optional[str]) -> Optional[Dict[str, int]]:
    """
    Parse X-Simulate-Failure header into a mapping of key_id -> HTTP status code.
    Supports comma-separated pairs like 'key_1=429,key_2=500' or '*=429'.
    Only active when settings.ENABLE_FAILURE_SIMULATION is True.
    """
    if not settings.ENABLE_FAILURE_SIMULATION or not header_value:
        return None

    simulated: Dict[str, int] = {}
    for raw_pair in header_value.split(","):
        pair = raw_pair.strip()
        if "=" not in pair:
            continue
        key_part, status_part = pair.split("=", 1)
        key_id = key_part.strip()
        try:
            status_code = int(status_part.strip())
        except ValueError:
            continue
        if key_id and status_code in SUPPORTED_SIMULATED_STATUSES:
            simulated[key_id] = status_code

    return simulated or None


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns 200 only when database is reachable, key pool has >=2 keys, and cache is enabled."
)
async def health_check():
    """
    Health check endpoint:
    Verifies database reachability, API key pool count (at least 2 keys), and cache configuration.
    """
    # 1. Database reachability check
    if not check_database_health():
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Database is unreachable"}
        )

    # 2. Key pool check (at least 2 keys configured)
    keys_count = key_manager.count
    if keys_count < 2:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Insufficient API keys configured (at least 2 required)"}
        )

    # 3. Cache configuration check
    if not settings.CACHE_ENABLED:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Cache is not enabled"}
        )

    return HealthResponse(
        status="ok",
        keys_configured=keys_count,
        cache_enabled=settings.CACHE_ENABLED
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send chat message",
    description="Processes user message with multi-turn context, key failover, and caching."
)
async def chat_endpoint(
    request: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure"),
    db: Session = Depends(get_db)
):
    """
    POST /chat endpoint:
    - Builds complete context (system prompt + history + new message).
    - Calls LLM service with sequential key failover.
    - Persists successful user and assistant messages in SQLite.
    - Never saves failed requests.
    """
    # 1. Assemble messages for LLM context
    messages = ConversationService.build_llm_messages(
        db=db,
        session_id=request.session_id,
        new_user_message=request.message,
        system_prompt=request.system_prompt
    )

    # 2. Execute with failover (and optional failure simulation)
    simulated_failures = parse_simulate_failure_header(x_simulate_failure)
    result = LLMService.execute_with_failover(
        messages=messages,
        key_manager=key_manager,
        simulated_failures=simulated_failures
    )

    metadata = ChatResponseMetadata(
        resolution_source=result.resolution_source,
        model=result.model,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        key_id=result.key_id,
        fallback_attempts=result.fallback_attempts
    )

    # 3. Save successful user and assistant messages to SQLite
    ConversationService.save_turn(
        db=db,
        session_id=request.session_id,
        user_content=request.message,
        assistant_content=result.reply,
        assistant_metadata=metadata.model_dump()
    )

    return ChatResponse(
        session_id=request.session_id,
        reply=result.reply,
        metadata=metadata
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=SessionHistoryResponse,
    summary="Get session history",
    description="Returns chronological message history for a given session."
)
async def get_session_messages(session_id: str, db: Session = Depends(get_db)):
    """
    GET /sessions/{session_id}/messages endpoint:
    Retrieves stored messages from SQLite database in chronological order.
    Returns 404 for unknown sessions. Never returns the system prompt.
    """
    if not ConversationService.session_exists(db, session_id):
        raise SessionNotFoundException("session not found")

    messages = ConversationService.get_session_messages(db, session_id)

    formatted_messages = []
    for msg in messages:
        formatted_messages.append(
            MessageItem(
                role=msg.role,
                content=msg.content,
                metadata=msg.parsed_metadata if msg.role == "assistant" else None
            )
        )

    return SessionHistoryResponse(
        session_id=session_id,
        messages=formatted_messages
    )
