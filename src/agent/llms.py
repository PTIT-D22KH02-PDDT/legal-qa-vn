from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Type, Union

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from src.api.remote_client import RemoteAPIClient

logger = logging.getLogger(__name__)


class RemoteChatModel(BaseChatModel):
    """
    Wrapper cho server host.py (endpoint /generate).
    Sử dụng ChatML format chuẩn Qwen (<|im_start|>).
    Hỗ trợ with_structured_output bằng regex/JSON parsing thủ công.
    """
    api_client: RemoteAPIClient
    model_name: str = "custom-remote-llm"
    temperature: float = 0.0
    max_length: int = 4000

    @property
    def _llm_type(self) -> str:
        return "remote_hosted_llm"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"model_name": self.model_name, "endpoint": "/generate"}

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> ChatResult:
        prompt_parts = []
        for m in messages:
            if isinstance(m, SystemMessage):
                prompt_parts.append(f"<|im_start|>system\n{m.content}<|im_end|>")
            elif isinstance(m, HumanMessage):
                prompt_parts.append(f"<|im_start|>user\n{m.content}<|im_end|>")
            elif isinstance(m, AIMessage):
                prompt_parts.append(f"<|im_start|>assistant\n{m.content}<|im_end|>")
            else:
                prompt_parts.append(str(m.content))

        prompt = "\n".join(prompt_parts)
        if not isinstance(messages[-1], AIMessage):
            prompt += "\n<|im_start|>assistant\n"

        temp = kwargs.get("temperature", self.temperature)
        if temp > 0.5:
            temp = 0.0
        max_l = kwargs.get("max_length", self.max_length)

        try:
            response_text = self.api_client.generate(
                prompt=prompt, max_length=max_l, temperature=temp,
            )
            response_text = self._clean_response(response_text)
        except Exception as e:
            logger.error("Remote LLM call failed: %s", e)
            response_text = f"Lỗi gọi LLM: {e}"

        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=response_text))])

    def _clean_response(self, text: str) -> str:
        """Xoá bỏ rác: lặp lại prompt, ChatML tokens, v.v."""
        if not text:
            return ""
        # Xoá các block ChatML nếu model lỡ trả về
        text = re.sub(r"<\|im_start\|>(?:system|user|assistant)\n", "", text)
        text = text.replace("<|im_end|>", "").strip()
        
        # Nếu model lặp lại hệ thống prompt (phổ biến ở model yếu)
        prefixes_to_strip = [
            "system\n Bạn là trọng tài",
            "system\nBạn là trọng tài",
            "Bạn là trọng tài chấm chất lượng",
            "Nhiệm vụ: so sánh câu trả lời"
        ]
        for p in prefixes_to_strip:
            if text.startswith(p):
                # Cố gắng lấy phần sau cùng của response nếu bị lặp
                parts = text.split("\n\n")
                if len(parts) > 1:
                    text = parts[-1].strip()
        
        return text

    def with_structured_output(
        self, schema: Union[Dict, Type[BaseModel]], **kwargs,
    ) -> Runnable[Any, Any]:
        """Fallback structured output: inject JSON schema vào prompt, parse kết quả."""
        def _invoke_and_parse(input_messages: List[BaseMessage]) -> Any:
            messages = list(input_messages)
            json_schema = schema.model_json_schema() if (isinstance(schema, type) and issubclass(schema, BaseModel)) else schema

            instruction = (
                f"\n\nIMPORTANT: RESPONSE ONLY WITH A VALID JSON OBJECT MATCHING THIS SCHEMA:\n"
                f"{json.dumps(json_schema, ensure_ascii=False)}\n"
                f"DO NOT include any thinking process (<think> blocks), preamble, or markdown formatting. ONLY THE JSON."
            )
            if messages and isinstance(messages[0], SystemMessage):
                messages[0] = SystemMessage(content=messages[0].content + instruction)
            else:
                messages.insert(0, SystemMessage(content=instruction))

            text = self.invoke(messages).content
            last_err = None

            # 1. Tìm block JSON { ... } cuối cùng (để bỏ qua phần lặp lại prompt ở đầu)
            all_blocks = re.findall(r"\{[\s\S]*?\}", text)
            if all_blocks:
                for block in reversed(all_blocks):
                    try:
                        # Validate JSON format cơ bản trước
                        data = json.loads(block.strip())
                        # Nếu là schema cụ thể, validate tiếp
                        if isinstance(schema, type) and issubclass(schema, BaseModel):
                            return schema.model_validate(data)
                        return data
                    except Exception as e:
                        last_err = e

            # 2. Markdown ```json ... ```
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if m:
                try:
                    data = json.loads(m.group(1).strip())
                    if isinstance(schema, type) and issubclass(schema, BaseModel):
                        return schema.model_validate(data)
                    return data
                except Exception as e:
                    last_err = e

            logger.error("Failed to parse structured output. Raw: %s", text[:1000])
            # Fallback nếu model trả về Grade nhãn thuần tuý (cho node Grade)
            if "SUFFICIENT" in text.upper(): return {"faithful": True, "has_citation": True, "score": 1.0} if not isinstance(schema, type) else None
            
            raise ValueError(f"Could not parse LLM response as JSON. Text: {text[:200]}")

        return RunnableLambda(_invoke_and_parse)


def build_llm(api_client: Optional[RemoteAPIClient] = None) -> BaseChatModel:
    """
    Factory tạo LLM theo AGENT_LLM_PROVIDER trong .env:
    - "groq"   → ChatGroq (Llama 3.1 8B, cần GROQ_API_KEY)
    - "remote" → RemoteChatModel (Qwen host riêng, cần api_client)
    """
    provider = os.getenv("AGENT_LLM_PROVIDER", "groq").lower()

    if provider == "groq":
        from langchain_groq import ChatGroq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY không tìm thấy trong env.")
        logger.info("[llms] Using Groq (llama-3.1-8b-instant)")
        return ChatGroq(model_name="llama-3.1-8b-instant", groq_api_key=api_key, temperature=0.0)

    if api_client is None:
        raise ValueError("api_client bắt buộc khi AGENT_LLM_PROVIDER=remote")
    logger.info("[llms] Using Remote LLM (host.py)")
    return RemoteChatModel(api_client=api_client)


def ask_text(
    llm: BaseChatModel,
    user_prompt: str,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    """Helper text-in / text-out cho các node (grade, rewrite, generate, validate)."""
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=user_prompt))

    if temperature is not None:
        llm = llm.bind(temperature=temperature)

    response = llm.invoke(messages)
    return response.content or ""
