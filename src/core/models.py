from pydantic import BaseModel
from typing import Optional, List
from .enums import RelationType

class DocumentMetadata(BaseModel):
    document_id: Optional[int] = None
    so_hieu:str=""
    ten_van_ban:str=""
    loai:str=""
    co_quan_ban_hanh:str=""
    ngay_ban_hanh:str=""
    ngay_co_hieu_luc:str=""
    file_path:str=""
    md_path:str=""
    so_dieu:int=0

class DocumentRelation(BaseModel):
    id : Optional[int]=None
    entity_start: Optional[str]=None
    entity_end: Optional[str]=None
    relation_type: Optional[RelationType]=None
    description : Optional[str]=None

class DocumentNode(BaseModel):
    id: Optional[str]=None
    type:Optional[str]=None
    parent_id:Optional[str]=None
    title:Optional[str]=None
    content:Optional[str]=None
    full_text:Optional[str]=None
    reference:Optional[List[str]]=None