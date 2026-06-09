"""Chat router: the main message endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.security import require_api_key
from app.dependencies import get_chat_service
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.chat import ChatService

router = APIRouter(
    prefix="/api",
    tags=["chat"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "/chat/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    payload: ChatMessageRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatMessageResponse:
    """Create a chat message, query the LLM, persist and return the answer."""
    return await service.handle(payload)
