from dataclasses import dataclass

@dataclass
class RankedResult:
    """
    Kết quả từ cross-encoder re-ranking
    
    Attributes:
        ids: ID của document chunk, lấy từ ChromaQueryResult.ids
        documents: Nội dung của document chunk, lấy từ ChromaQueryResult.text
        metadatas: Metadata của document chunk, lấy từ ChromaQueryResult.metadata
        distances: Khoảng cách ban đầu từ ChromaDB, lấy từ ChromaQueryResult.distance
        relevance_score: Điểm số mới sau khi re-rank, được tính từ cross-encoder
        rank: Thứ hạng sau khi re-rank, 1 là cao nhất
    """
    
    ids: str
    documents: str
    metadatas: dict
    distances: float
    relevance_score: float
    rank: int
