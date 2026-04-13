from typing import List, Callable, Optional, Dict, Any
from pydantic import BaseModel
from src.schemas import DocumentNode, EmbeddingRequest, EmbeddingResult
from src.core.embedding import decode_section_id

EmbeddingFunction = Callable[[List[EmbeddingRequest]], List[EmbeddingResult]]

class EmbeddingPipeline(BaseModel):
    """Kết nối chunking module và embedding module và triển khai embedding module """
    chunk_documents: List[DocumentNode]
    
    # full_payload: Optional[Dict[str, Any]] = None

    def _to_embedding_requests(self) -> List[EmbeddingRequest]:
        if not self.chunk_documents:
            return []
        if isinstance(self.chunk_documents[0], DocumentNode):
            requests = []
            for stt, chunk in enumerate(self.chunk_documents[1:]):
                section_id = chunk.id
                texts = []

                # if self.full_payload:
                #     # Duyet cay JSON tao ra context cho chunk hien tai dua vao section_id:
                #     # Text:
                #     # Tiêu đề: .....
                #     # Tiêu đề Đoạn: ........
                #     # Khoản:...
                #     #.............
                #     pass

                texts.append(f'Mã đoạn: {decode_section_id(section_id)}')
                if chunk.tittle:
                    texts.append(f'Tiêu đề: {chunk.tittle}')
                if chunk.content:
                    texts.append(f'Nội dung: {chunk.content}')
                if chunk.reference:
                    texts.append(f'Các viện dẫn: {", ".join(decode_section_id(ref) for ref in chunk.reference)}')

                requests.append(
                    EmbeddingRequest(
                        chunk_id=section_id,
                        num_chunk=stt+1,
                        text='\n'.join(texts)
                    )
                )           
            return requests
        else:
            raise ValueError(f"chunk_documents phải là List[DocumentNode], nhưng nhận {type(self.chunk_documents[0])}")

    def run(self, embed_fn: EmbeddingFunction) -> List[EmbeddingResult]:
        requests = self._to_embedding_requests()
        return embed_fn(requests)