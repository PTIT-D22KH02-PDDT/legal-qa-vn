from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, List, Optional

class HierarchicalChunkInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    payload: Dict[str, Any] | List[Dict[str, Any]] = Field(
        alias="json",
        description="Raw JSON đầu vào dùng cho hierarchical chunker."
    )

class ChunkMetadata(BaseModel):
    van_ban: Optional[str] = None
    phan: Optional[str] = None
    chuong: Optional[str] = None
    muc: Optional[str] = None
    dieu: Optional[str] = None
    khoan: Optional[str] = None
    diem: Optional[str] = None
    
    def display(self) -> str:
        """
        Chuyển ChunkMetadata thành chuỗi hiển thị theo thứ tự từ cụ thể đến tổng quát.
        Ví dụ: ChunkMetadata(dieu="Điều 663", khoan="Khoản 1") -> "Khoản 1 Điều 663"
        """
        hierarchy_order = ['diem', 'khoan', 'dieu', 'muc', 'chuong', 'phan', 'van_ban']
        parts = [getattr(self, level, None) for level in hierarchy_order]
        result = " ".join(p for p in parts if p)
        return result or "N/A"
    
    def get_section_type(self) -> str:
        """
        Tìm cấp hiện tại của chunk
        Ví dụ: ChunkMetadata(dieu="Điều 663", khoan="Khoản 1") -> "khoan"
        """
        hierarchy_order = ['diem', 'khoan', 'dieu', 'muc', 'chuong', 'phan', 'van_ban']
        for level in hierarchy_order:
            if getattr(self, level, None):
                return level
        return "unknown"