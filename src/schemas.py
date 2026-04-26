from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field, model_validator, ConfigDict
from enum import Enum

class HierarchicalChunkInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    payload: Dict[str, Any] | List[Dict[str, Any]] = Field(
        alias="json",
        description="Raw JSON đầu vào dùng cho hierarchical chunker."
    )

class RelationType(str, Enum):
    # Pho bien
    huong_dan_thi_hanh = "huong_dan_thi_hanh"  # NĐ/TT/NQ hướng dẫn Luật
    sua_doi_bo_sung    = "sua_doi_bo_sung"      # sửa một phần VB khác
    thay_the           = "thay_the"             # thay thế toàn bộ VB cũ
    bai_bo             = "bai_bo"               # bãi bỏ hoàn toàn VB cũ
    dinh_chi_hieu_luc  = "dinh_chi_hieu_luc"   # tạm đình chỉ

    # Đặc thù Nghị quyết
    tam_thoi_ap_dung   = "tam_thoi_ap_dung"    # thí điểm cơ chế chưa có trong Luật
    giai_thich         = "giai_thich"           # QH giải thích chính thức điều khoản Luật

    # Chung
    lien_quan          = "lien_quan"            # tham chiếu nhau, không trực tiếp
    #Quan he giua cac dieu/khoan trong van ban
    tham_chieu         = "tham_chieu"
class DocumentRelation(BaseModel):
    id : int=None
    entity_start:str=None
    entity_end:str=None
    relation_type:RelationType=None
    description : Optional[str]=None

class DocumentMetadata(BaseModel):
    so_hieu:str=""
    ten_van_ban:str=""
    loai:str=""
    co_quan_ban_hanh:str=""
    ngay_ban_hanh:str=""
    ngay_co_hieu_luc:str=""
    file_path:str=""
    md_path:str=""
    so_dieu:int=0


class TypeChunk(str, Enum):
    phan="phan"
    chuong="chuong"
    muc="muc"
    dieu="dieu"
    khoan="khoan"
    diem="diem"

# Giá trị từ `chunk_id` (dieu/khoan/chuong/...): ưu tiên int; có thể float (vd 1.2)
# hoặc str nếu mã có chữ; `diem` luôn là mã thuần (vd "a", "2") không gắn nhãn "Điểm ".
LevelIndex = int | float | str


class ChunkMetadata(BaseModel):
    so_hieu: str = ""
    dieu: LevelIndex | None = None
    khoan: LevelIndex | None = None
    diem: str | None = None
    phan: LevelIndex | None = None
    chuong: LevelIndex | None = None
    muc: LevelIndex | None = None

class DocumentNode(BaseModel):
    id: str=""
    type:str=None
    parent_id:Optional[str]=None
    parent_context:Optional[str]=None
    title:Optional[str]=None
    content:Optional[str]=None
    full_text:str|None=None
    reference:Optional[List[str]]=None


class EmbeddingRequest(BaseModel):
    """Một đơn vị chunk cần embedding, hoặc truy vấn của người dùng"""
    chunk_id: str | None = None  # Duy nhất, lấy từ ChunkMetadata.section_id hoặc tự tạo khi khởi tạo
    text: str
    metadata : dict   # Thông tin metadata của chunk, có thể dùng để lưu vào vector database cùng với vector embedding

class EmbeddingResult(BaseModel):
    """Kết quả embed 1 chunk"""
    chunk_id: str | None = None
    text: str
    vector: List[float]     # Vector embedding
    token_count: Optional[int] = None   # Số token của chunk để kiểm tra có vượt giới hạn mô hình hay không
    metadata : dict


# Store in vector database

class ChromaConfig(BaseModel):
    collection_name: str
    persist_directory: Optional[str] = None      # Nơi lưu trữ
    distance_metric: Literal["cosine", "l2", "ip"] = "cosine"  # Khoảng cách sử dụng trong ChromaDB
    is_persist: bool = False

    @model_validator(mode='after')
    def validate_persistence(self):
        if self.is_persist and not self.persist_directory:
            raise ValueError('persist_directory is required when is_persist=True')
        return self

class ChromaUpsertRequest(BaseModel):
    """Dữ liệu cần upsert vào ChromaDB"""
    chunk_id: str
    vector: List[float]         # Lấy từ EmbeddingResult.vector
    text: str                   
    metadata: dict   # Lấy từ ChunkMetadata tương ứng và có thể thêm thông tin khác nếu cần


class ChromaQueryResult(BaseModel):
    """Kết quả từ retrieval + reranking (unified schema)"""
    # Core fields
    chunk_id: str
    text: str
    metadata: Optional[dict] = None
    distance: float
    score_rerank: Optional[float] = None  # Điểm số từ reranker (nếu có rerank)