"""
This module defines the data models used in the chat application.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from semantic_kernel.contents.chat_message_content import ChatMessageContent

@dataclass
class ChatbotMessage:
    """Represents a message in the chat history."""

    role: str = ""
    content: str | None = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ChatRequest:
    """Represents a chat request."""

    message: str = ""
    history: List[ChatbotMessage]| None = field(default_factory=list)
    thread_id: Optional[str] = None


@dataclass
class ChatResponse:
    """Represents a chat response."""

    message: str |None = ""
    history: List[ChatbotMessage] | None = field(default_factory=list)
    thread_id: Optional[str] = None
