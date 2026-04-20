from typing import List, Callable, Optional, Dict, Any
from src.core.models import DocumentNode
from src.schemas import EmbeddingRequest, EmbeddingResult
from src.indexing.embedding.utils import decode_section_id

EmbeddingFunction = Callable[[List[EmbeddingRequest]], List[EmbeddingResult]]

class EmbeddingPipeline:
    """Kết nối chunking module và embedding module và triển khai embedding module """
    
    def __init__(self, chunk_documents: List[DocumentNode]):
        self.chunk_documents = chunk_documents

    def _to_embedding_requests(self) -> List[EmbeddingRequest]:
        if not self.chunk_documents:
            return []
        if isinstance(self.chunk_documents[0], DocumentNode):
            requests = []
            for stt, chunk in enumerate(self.chunk_documents[1:]):
                section_id = chunk.id
                texts = []
                if chunk.parent_context:
                    texts.append(f'{chunk.parent_context}')
                if chunk.title:
                    texts.append(f'{chunk.title}')
                if chunk.content:
                    texts.append(f'{chunk.content}')
                full_text=[]
                if chunk.parent_context:
                    full_text.append(chunk.parent_context)
                if chunk.full_text:
                    full_text.append(chunk.full_text)
                requests.append(
                    EmbeddingRequest(
                        chunk_id=section_id,
                        num_chunk=stt+1,
                        text='\n'.join(texts),
                        metadata = {
                        'full_text': "\n".join(full_text), 
                        'parent_id': chunk.parent_id,
                        'reference': chunk.reference,
                        'section_type': chunk.type,  # Dùng cho filter trong retrieval
                        **decode_section_id(section_id).dict()  # Add van_ban, dieu, khoan, etc
                        }
                    )
                )           
            return requests
        else:
            raise ValueError(f"chunk_documents phải là List[DocumentNode], nhưng nhận {type(self.chunk_documents[0])}")

    def run(self, embed_fn: EmbeddingFunction) -> List[EmbeddingResult]:
        requests = self._to_embedding_requests()
        return embed_fn(requests)