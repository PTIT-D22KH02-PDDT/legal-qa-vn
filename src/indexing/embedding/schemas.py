"""Schemas for embedding module."""

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
    """Mot don vi chunk can embedding, hoac truy van cua nguoi dung.

    Attributes:
        chunk_id: Duy nhat, lay tu DocumentNode.id.
        chunk_index: Vi tri/thu tu cua chunk trong van ban.
        text: Noi dung can embedding.
        metadata: Metadata cua chunk, dung de luu vao vector database.
    """

    chunk_id: str | None = None
    chunk_index: Optional[int] = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingResult(BaseModel):
    """Ket qua embed 1 chunk.

    Attributes:
        chunk_id: ID cua chunk.
        chunk_index: Vi tri/thu tu cua chunk.
        text: Noi dung duoc embed.
        vector: Vector embedding.
        metadata: Metadata cua chunk, dung de luu vao vector database.
    """

    chunk_id: str | None = None
    chunk_index: Optional[int] = None
    text: str
    vector: List[float]
    metadata: dict[str, Any] = Field(default_factory=dict)
