"""
Ta dùng `langchain-openai.ChatOpenAI` trỏ vào endpoint OpenAI-compatible
của Groq (https://api.groq.com/openai/v1). Lý do:
- `langchain-openai` bám sát `langchain-core` → không còn version conflict
  mà `langchain-groq` gặp phải.
- Support đầy đủ `with_structured_output`, `bind_tools`, streaming, async.
- Dùng được mọi model Groq (Llama, Mixtral, ...) qua `model=...`.
"""

from __future__ import annotations

import os
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.1-8b-instant"


def build_llm(
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
    max_tokens: Optional[int] = None,
    **kwargs,
) -> ChatOpenAI:
    """
    Tạo ChatOpenAI nối tới Groq.

    Args:
        model: tên model Groq (vd `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`).
        temperature: mặc định 0 (deterministic) — node nào cần khác thì override
            qua `ask_text(..., temperature=...)` hoặc `.bind(temperature=...)`.
        api_key: nếu None, đọc `GROQ_API_KEY` từ env.
        max_tokens: tuỳ chọn.
    """
    resolved_key = api_key or os.getenv("GROQ_API_KEY")
    if not resolved_key:
        raise ValueError("GROQ_API_KEY không tìm thấy trong env và không truyền vào.")

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=resolved_key,
        base_url=GROQ_BASE_URL,
        max_tokens=max_tokens,
        **kwargs,
    )


def ask_text(
    llm: BaseChatModel,
    user_prompt: str,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Helper text-in / text-out cho các node (grade, rewrite, generate, validate).

    - Build SystemMessage + HumanMessage từ string.
    - Nếu có `temperature`, bind runtime override.
    - Trả thẳng `response.content` (string).
    """
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=user_prompt))

    if temperature is not None:
        llm = llm.bind(temperature=temperature)

    response = llm.invoke(messages)
    return response.content or ""
