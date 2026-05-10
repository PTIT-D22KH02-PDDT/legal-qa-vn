import uvicorn
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from main import build_search_service
from src.api import RemoteAPIClient
from src.rag import RAGService

app = FastAPI(title="Legal QA Frontend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    query: str
    top_k_retrieve: int = 10
    top_k_rerank: int = 5
    use_remote_embedding: bool = True
    use_remote_rerank: bool = True

class ChatResponse(BaseModel):
    query: str
    answer: str
    context: str

# Khởi tạo RAG service lazily
search_service = None
api_client = None
rag_service = None

def init_services(req: ChatRequest):
    global search_service, api_client, rag_service
    if not search_service:
        search_service = build_search_service(
            use_remote_embedding=req.use_remote_embedding,
            use_rerank=True,
            use_remote_rerank=req.use_remote_rerank,
        )
    if not api_client:
        api_client = RemoteAPIClient()
    
    rag_service = RAGService(
        search_service=search_service,
        api_client=api_client,
        top_k_retrieve=req.top_k_retrieve,
        top_k_rerank=req.top_k_rerank,
        use_rerank=True,
    )

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    try:
        init_services(req)
        result = rag_service.answer(query=req.query)
        
        # Trích xuất các source documents để làm citation
        context = ""
        if result.context:
            context = result.context
            
        return ChatResponse(
            query=result.query,
            answer=result.answer,
            context=context
        )
    except Exception as e:
        traceback.print_exc() # In chi tiết lỗi ra console của Kaggle
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    print("Starting API Server for Frontend at http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
