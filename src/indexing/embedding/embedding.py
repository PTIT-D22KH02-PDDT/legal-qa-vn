from typing import List, Callable, Optional, Dict, Any
from pydantic import BaseModel
from src.schemas import DocumentNode, EmbeddingRequest, EmbeddingResult
from src.indexing.embedding import decode_section_id

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

                # texts.append(f'Mã đoạn: {decode_section_id(section_id)}')
                # if chunk.title:
                #     texts.append(f'Tiêu đề: {chunk.title}')
                # if chunk.content:
                #     texts.append(f'Nội dung: {chunk.content}')
                # if chunk.reference:
                #     texts.append(f'Các viện dẫn: {", ".join(decode_section_id(ref) for ref in chunk.reference)}')
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