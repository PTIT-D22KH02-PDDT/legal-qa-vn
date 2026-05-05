from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, List, Optional

class HierarchicalChunkInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    payload: Dict[str, Any] | List[Dict[str, Any]] = Field(
        alias="json",
        description="Raw JSON đầu vào dùng cho hierarchical chunker."
    )

class ChunkMetadata(BaseModel):
    so_hieu: Optional[str] = None
    modau: Optional[str] = None
    chinh: Optional[str] = None
    phan: Optional[str] = None
    chuong: Optional[str] = None
    muc: Optional[str] = None
    dieu: Optional[str] = None
    khoan: Optional[str] = None
    diem: Optional[str] = None
    phu_luc: Optional[str] = None
    phu_luc_phan: Optional[str] = None