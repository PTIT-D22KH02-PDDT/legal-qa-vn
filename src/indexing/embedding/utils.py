"""Embedding utilities."""

from typing import Optional, List, Any
from src.core.models import DocumentNode
from .schemas import EmbeddingRequest
from ..chunker.schemas import ChunkMetadata

SECTION_TYPE_NAMES = {
    'modau': 'Mở đầu',
    'chinh': 'Chính',
    'dieu': 'Điều',
    'khoan': 'Khoản',
    'diem': 'Điểm',
    'chuong': 'Chương',
    'phan': 'Phần',
    'muc': 'Mục',
}

def _remove_chunk_suffix(level: str) -> str:
    """
    Xóa sufix counter ở cuối level nếu có (tình huống document có chunk_id trùng nhau và được đánh số đuôi __dup_N).
    Ví dụ: dieu_6__dup_0 -> dieu_6; khoan_1__dup_2 -> khoan_1
    """

    if '__dup_' in level:
        prefix, suffix = level.rsplit('__dup_', 1)
        if suffix.isdigit():
            return prefix
    return level

def _model_to_dict(model: Any) -> dict[str, Any]:
    """
    Chuyển Pydantic model sang dict, loại bỏ các trường = None
    """
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    
    return model.dict(exclude_none=True)

def decode_section_id(chunk_id: str) -> ChunkMetadata:
    """
    Chuyển đổi chunk_id thành ChunkMetadata.
    
    Ví dụ:
        91_2015_qh13.dieu_6.khoan_1.diem_a
    Thành:
        ChunkMetadata(
            van_ban="91_2015_qh13",
            dieu="Điều 6",
            khoan="Khoản 1",
            diem="Điểm a"
        )
    
    Args:
        chunk_id: ID của chunk
        
    Returns:
        ChunkMetadata object        
        
    Raises:
        ValueError: If chunk_id format is invalid
    """

    if not chunk_id:
        raise ValueError("chunk_id không được để trống")

    try:
        levels = chunk_id.strip().split('.')
    
    except Exception as e:
        raise ValueError(f"Invalid chunk_id format: {chunk_id}. Error: {e}") from e
    
    if not levels:
        raise ValueError(f"Invalid chunk_id format: {chunk_id}. No levels found.")
    
    metadata = ChunkMetadata(van_ban=levels[0])

    for raw_level in levels[1:]:
        level = _remove_chunk_suffix(raw_level)

        if "_" not in level:
            continue

        section_type, index = level.split("_", 1)
        index = ".".join(index.split("_"))

        if section_type not in SECTION_TYPE_NAMES:
            raise ValueError(
                f"Không nhận diện được loại section '{section_type}' trong chunk_id: {chunk_id}"
            )
        
        label = f'{SECTION_TYPE_NAMES[section_type]} {index}'

        try:
            setattr(metadata, section_type, label)
        except Exception as e:
            continue

    return metadata

def create_chunk_embedding_text(chunk: DocumentNode) -> str:
    """
    Tạo text embedding từ DocumentNode (chunk).
    
    Args:
        chunk: DocumentNode chứa dữ liệu chunk
        
    Returns:
        Text embedding được tạo từ chunk
    """
    texts: list[str] = []
    
    if chunk.parent_context:
        texts.append(chunk.parent_context)
    
    if chunk.title:
        texts.append(chunk.title)
    
    if chunk.content:
        texts.append(chunk.content)
    
    return '\n'.join(texts)

def create_chunk_embedding_metadata(chunk: DocumentNode) -> dict[str, Any]:
    """
    Tạo metadata để lưu cùng vector embedding trong vector database.
    Loại bỏ tất cả các trường rỗng (None, empty list, empty string) vì ChromaDB không cho phép.
    """
    metadata: dict[str, Any] = {}

    full_text_parts: list[str] = []

    if chunk.parent_context:
        full_text_parts.append(chunk.parent_context)
    
    if chunk.full_text:
        full_text_parts.append(chunk.full_text)
    
    metadata_base = {
        'full_text': '\n'.join(full_text_parts),
        'parent_id': chunk.parent_id,
        'section_type': chunk.type
    }
    
    for key, value in metadata_base.items():
        if value:
            metadata[key] = value
    
    if chunk.reference:
        metadata['reference'] = chunk.reference
    
    if chunk.id:
        section_metadata = decode_section_id(chunk.id)
        metadata.update(_model_to_dict(section_metadata))

    return metadata

def create_embedding_request(
        text: str, 
        chunk_id: str | None = None, 
        num_chunk: int | None = None,
        metadata: dict[str, Any] | None = None
    ) -> EmbeddingRequest:
    """
    Tạo EmbeddingRequest từ text (cho query hoặc chunk text).
    
    Args:
        text: Nội dung text cần embedding
        chunk_id: Optional ID (dùng cho chunks, query không cần)
        num_chunk: Số lượng chunks
        metadata: Metadata liên quan đến chunk

    Returns:
        EmbeddingRequest object
    """
    return EmbeddingRequest(chunk_id=chunk_id, text=text, num_chunk=num_chunk, metadata=metadata or {})

