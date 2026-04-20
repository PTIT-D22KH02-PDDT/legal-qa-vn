from pydantic import BaseModel
from typing import Optional, List
from .enums import RelationType

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

class DocumentNode(BaseModel):
    id: str=""
    type:str=None
    parent_id:Optional[str]=None
    parent_context:Optional[str]=None
    title:Optional[str]=None
    content:Optional[str]=None
    full_text:str|None=None
    reference:Optional[List[str]]=None