"""Embedding utilities."""

import re
from typing import List, Optional

from src.core.models import DocumentNode
from src.schemas import ChunkMetadata, LevelIndex

from .schemas import EmbeddingRequest
dictionary = {
    'modau': 'Mở đầu',
    'chinh': 'Chính',
    'dieu': 'Điều',
    'khoan': 'Khoản',
    'diem': 'Điểm',
    'chuong': 'Chương',
    'phan': 'Phần',
    "muc": "Mục",
}


def _parse_level_index_for_metadata(level_key: str, index: str) -> LevelIndex:
    """
    Lưu metadata Chroma: dieu/khoan/chuong/... dạng số nếu được; diem là chuỗi mã thuần.
    `index` sau khi nối underscore (có thể '1', '1.2', 'a'...).
    """
    s = (index or "").strip()
    if level_key == "diem":
        return s
    if not s:
        return s
    if s.isdigit():
        return int(s)
    if re.fullmatch(r"\d+\.\d+", s):
        return float(s)
    return s


def format_chunk_id_for_embedding_text(chunk_id: str) -> str:
    """
    Chuỗi hiển thị cho text embedding (tiêu đề có nhãn), không dùng làm filter DB.
    Ví dụ: "x.dieu_6.diem_2" -> "Điểm 2 điều 6" (thứ tự đảo như bản cũ).
    """
    try:
        levels = chunk_id.strip().split(".")
    except Exception:
        return chunk_id
    result: List[str] = []
    for level in levels[1:]:
        if "_" not in level:
            continue
        le, raw = level.split("_", 1)
        raw = ".".join(raw.split("_"))
        if le in dictionary:
            result.append(f"{dictionary[le]} {raw}")
        else:
            result.append(f"{le}_{raw}")
    return " ".join(result[::-1]) if result else chunk_id

# def decode_section_id(chunk_id: str) -> str:
#     """
#     Chuyển đổi chunk_id về dạng dễ hiểu.
    
#     Ví dụ: "dieu_6.diem_2" -> "Điểm 2 điều 6"
#             "dieu_6.diem_2_0" -> "Điểm 2 điều 6" (removes suffix if present)
    
#     Args:
#         chunk_id: Section ID in format "level1_index1.level2_index2..." with optional _N suffix
        
#     Returns:
#         Human-readable section description
        
#     Raises:
#         ValueError: If chunk_id format is invalid
#     """
#     try:
#         parts = chunk_id.strip().split('.')
        
#         # Remove suffix from last level ONLY if it has 2+ underscores
#         # This means: section_type_index_suffix (last _suffix is counter to remove)
#         # vs: section_type_index (only one underscore - keep as is)
#         if parts and '_' in parts[-1]:
#             last_part = parts[-1]
#             underscore_count = last_part.count('_')
#             # If 2+ underscores, last one is likely the suffix counter
#             if underscore_count >= 2:
#                 # Remove only the last _N if N is digit
#                 potential_suffix = last_part.rsplit('_', 1)
#                 if len(potential_suffix) == 2 and potential_suffix[-1].isdigit():
#                     parts[-1] = potential_suffix[0]
        
#         levels = parts
#     except Exception as e:
#         raise ValueError(f"Invalid chunk_id format: {chunk_id}. Error: {e}")
    
#     result = []
#     for level in levels[1:]:
#         # Handle case when level doesn't contain '_'
#         if '_' not in level:
#             continue
#         le, index = level.split('_', 1)
#         index = '.'.join(index.split('_'))
#         if le in SECTION_TYPE_NAMES:
#             result.append(f"{SECTION_TYPE_NAMES[le]} {index}")
#         elif le.isdigit():
#             # Handle numeric law codes (e.g., "91" from "91_2015_qh13")
#             result.append(f"Luật {index}")
#         else:
#             raise ValueError(f"Không nhận diện được loại section {le} trong chunk_id {chunk_id}")
    
#     return ' '.join(result[::-1])


def create_chunk_embedding_text(chunk: DocumentNode) -> str:
    """
    Tạo text embedding từ DocumentNode (chunk).
    
    Kết hợp thông tin: mã đoạn, tiêu đề, nội dung, viện dẫn
    
    Args:
        chunk: DocumentNode chứa dữ liệu chunk
        
    Returns:
        Formatted text suitable for embedding
    """
    texts = []
    
    # Mã đoạn (decoded)
    if chunk.id:
        texts.append(
            f"Mã đoạn: {format_chunk_id_for_embedding_text(chunk.id)}"
        )
    
    # Tiêu đề
    if chunk.title:
        texts.append(f'Tiêu đề: {chunk.title}')
    
    # Nội dung
    if chunk.content:
        texts.append(f'Nội dung: {chunk.content}')
    
    # Viện dẫn
    if chunk.reference:
        refs_str = ", ".join(
            format_chunk_id_for_embedding_text(ref) for ref in chunk.reference
        )
        texts.append(f'Các viện dẫn: {refs_str}')
    
    return '\n'.join(texts)


def create_embedding_request(text: str, chunk_id: str | None = None) -> EmbeddingRequest:
    """
    Tạo EmbeddingRequest từ text (cho query hoặc chunk text).
    
    Args:
        text: Nội dung text cần embedding
        chunk_id: Optional ID (dùng cho chunks, query không cần)
        
    Returns:
        EmbeddingRequest object
    """
    return EmbeddingRequest(chunk_id=chunk_id, text=text)


def decode_section_id(chunk_id: str) -> ChunkMetadata:
    """
    Parse `chunk_id` thành ChunkMetadata. Các cấp dieu/khoan/chuong/... lưu **số**
    (int hoặc float nếu mã dạng 1.2); `diem` lưu chuỗi mã thuần (vd "a", "2").
    """
    try:
        levels = chunk_id.strip().split(".")
    except Exception as e:
        raise ValueError(f"Invalid chunk_id format: {chunk_id}. Error: {e}") from e

    metadata = ChunkMetadata(so_hieu=levels[0])
    for level in levels[1:]:
        if "_" not in level:
            continue
        le, index = level.split("_", 1)
        index = ".".join(index.split("_"))
        if le not in dictionary:
            raise ValueError(
                f"Không nhận diện được loại section {le} trong chunk_id {chunk_id}"
            )
        val = _parse_level_index_for_metadata(le, index)
        if le == "dieu":
            metadata.dieu = val
        elif le == "khoan":
            metadata.khoan = val
        elif le == "diem":
            s = str(val).strip() if val is not None else ""
            metadata.diem = s or None
        elif le == "phan":
            metadata.phan = val
        elif le == "chuong":
            metadata.chuong = val
        elif le == "muc":
            metadata.muc = val
    return metadata