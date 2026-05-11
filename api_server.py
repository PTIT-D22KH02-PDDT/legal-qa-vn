import uvicorn
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from main import build_search_service, setup_workflow_dependencies, run_workflow_query
from src.api import RemoteAPIClient
from src.rag import RAGService
from fastapi import UploadFile, File, Form
from system.replace_file_service import ReplaceFileService
from system.database.db_service import DocumentDatabaseService
from src.core.enums import RelationType
import shutil
import os
from sqlalchemy import text

app = FastAPI(title="Legal QA Frontend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    """Request cho /api/chat endpoint.
    
    Luôn sử dụng Workflow (Agent) mode để xử lý:
    - Intent classification (CHITCHAT, LEGAL_QUERY, GENERAL, DOC_RELATION)
    - Tự động quyết định search hay không
    
    Parameters:
        query: Câu hỏi/tin nhắn từ user
        top_k_retrieve: Số chunks để lấy từ vector search (default=50)
        top_k_rerank: Số chunks sau khi rerank (default=5)
        use_remote_embedding: Dùng remote API cho embedding (default=True)
        use_remote_rerank: Dùng remote API cho rerank (default=True)
    """
    query: str
    top_k_retrieve: int = 30
    top_k_rerank: int = 5
    use_remote_embedding: bool = True
    use_remote_rerank: bool = True

class ChatResponse(BaseModel):
    query: str
    answer: str
    context: str

# Khởi tạo Workflow dependencies lazily (used by /api/chat)
workflow_deps = None

# NOTE: RAG mode dưới đây không còn dùng vì /api/chat luôn dùng workflow
# Để backup, chúng tôi giữ lại nhưng không active
# search_service = None
# api_client = None
# rag_service = None

# def init_services(req: ChatRequest):
#     global search_service, api_client, rag_service
#     if not search_service:
#         search_service = build_search_service(
#             use_remote_embedding=req.use_remote_embedding,
#             use_rerank=True,
#             use_remote_rerank=req.use_remote_rerank,
#         )
#     if not api_client:
#         api_client = RemoteAPIClient()
#     
#     rag_service = RAGService(
#         search_service=search_service,
#         api_client=api_client,
#         top_k_retrieve=req.top_k_retrieve,
#         top_k_rerank=req.top_k_rerank,
#         use_rerank=True,
#     )

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    global workflow_deps
    try:
        # ⭐ LUÔN DÙNG WORKFLOW MODE để xử lý intent trước khi search
        # Điều này đảm bảo greeting/chitchat không bị search embedding vô nghĩa
        if not workflow_deps:
            workflow_deps = setup_workflow_dependencies()
        
        result = run_workflow_query(req.query, workflow_deps)
        
        if not result:
            return ChatResponse(
                query=req.query,
                answer="Xin lỗi, tôi gặp lỗi khi xử lý yêu cầu của bạn.",
                context=""
            )
        
        # Trích xuất context từ agent results
        context = ""
        if result.get("context_text"):
            # context_text là List[str] tích lũy từ các tool
            context = "\n---\n".join(result["context_text"])
            
        return ChatResponse(
            query=req.query,
            answer=result.get("answer", "Không tìm thấy câu trả lời."),
            context=context
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents")
def list_documents():
    db_service = None
    try:
        db_service = DocumentDatabaseService()
        documents = db_service.get_all_documents(limit=1000)
        
        # Chuẩn hóa dữ liệu trả về cho FE: lọc bỏ _sa_instance_state và xử lý null
        sanitized_docs = []
        for doc in documents:
            clean_doc = {
                "so_hieu": doc.get("so_hieu") or "",
                "ten_van_ban": doc.get("ten_van_ban") or "Chưa xác định",
                "loai": doc.get("loai") or "",
                "co_quan_ban_hanh": doc.get("co_quan_ban_hanh") or "",
                "ngay_ban_hanh": doc.get("ngay_ban_hanh") or "",
                "ngay_co_hieu_luc": doc.get("ngay_co_hieu_luc") or "",
                "trang_thai": doc.get("trang_thai", 1)
            }
            sanitized_docs.append(clean_doc)
            
        return sanitized_docs
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if db_service:
            db_service.close()

@app.get("/api/documents/search")
def search_documents(query: str = ""):
    """Tìm kiếm văn bản theo số hiệu hoặc tên để chọn quan hệ."""
    from src.indexing.parsing.extract_metadata import Extractor
    extractor = Extractor()
    so_hieu = extractor._slug_so_hieu(query)
    
    db_service = None
    try:
        db_service = DocumentDatabaseService()
        # Tìm kiếm trong SQLite
        from sqlalchemy import or_
        from system.database.db import DocumentMetadataDB
        
        session = db_service.metadata_repo.session
        results = session.query(DocumentMetadataDB).filter(
            or_(
                DocumentMetadataDB.so_hieu.ilike(f"%{so_hieu}%"),
                DocumentMetadataDB.ten_van_ban.ilike(f"%{query}%")
            )
        ).limit(20).all()
        
        return [
            {"so_hieu": doc.so_hieu, "ten_van_ban": doc.ten_van_ban} 
            for doc in results
        ]
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if db_service:
            db_service.close()

@app.get("/api/relation-types")
def get_relation_types():
    """Lấy danh sách 3 loại quan hệ chính từ enum."""
    try:
        # Ánh xạ từ enum value → display text
        type_mappings = {
            RelationType.huong_dan_thi_hanh: "Hướng dẫn thi hành",
            RelationType.thay_the: "Thay thế",
            RelationType.can_cu: "Căn cứ",
        }
        
        # Trả về danh sách 3 loại này (đã sắp xếp)
        return list(type_mappings.values())
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/replace-document")
async def replace_document(
    file: UploadFile = File(...),
    replaced_so_hieu: str = Form(...),
    relation_type: str = Form("Thay thế"),
    description: str = Form("")
):
    replace_service = None
    try:
        # Create temp directory if not exists
        temp_dir = os.path.join(os.getcwd(), "temp_uploads")
        os.makedirs(temp_dir, exist_ok=True)
        
        file_path = os.path.join(temp_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Build ChromaStore for ReplaceFileService
        from main import build_chroma_store
        chroma_store = build_chroma_store()
        
        replace_service = ReplaceFileService(chroma_store=chroma_store)
        # Cập nhật loại quan hệ tùy chỉnh
        result = replace_service.process(
            new_file_path=file_path, 
            replaced_so_hieu=replaced_so_hieu,
            relation_type=relation_type
        )
        
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if replace_service:
            replace_service.close()

def run_migrations():
    """Tự động chạy migration cho SQLite và ChromaDB khi khởi động server."""
    print("--- Running Auto-Migrations ---")
    try:
        # 1. SQLite Migration
        from system.database.db_respository import get_database
        db_manager = get_database()
        with db_manager.engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(document_metadata)"))
            columns = [row[1] for row in result.fetchall()]
            if "trang_thai" not in columns:
                print("Adding 'trang_thai' column to SQLite...")
                conn.execute(text("ALTER TABLE document_metadata ADD COLUMN trang_thai INTEGER DEFAULT 1"))
                conn.execute(text("UPDATE document_metadata SET trang_thai = 1 WHERE trang_thai IS NULL"))
                conn.commit()
                print("SQLite migration completed.")
            else:
                print("SQLite 'trang_thai' column already exists.")

        # 2. ChromaDB Migration
        from main import build_chroma_store
        chroma_store = build_chroma_store()
        collection = chroma_store.collection
        total = collection.count()
        if total > 0:
            print(f"Checking ChromaDB migration for {total} chunks...")
            # Lấy batch đầu tiên để kiểm tra xem đã có trang_thai chưa
            batch = collection.get(limit=10, include=["metadatas"])
            needs_update = False
            for meta in batch.get("metadatas", []):
                if meta and "trang_thai" not in meta:
                    needs_update = True
                    break
            
            if needs_update:
                print("Updating 'trang_thai' in ChromaDB (batch processing)...")
                offset = 0
                batch_size = 500
                while offset < total:
                    b = collection.get(limit=batch_size, offset=offset, include=["metadatas"])
                    ids = b["ids"]
                    metas = b["metadatas"]
                    if not ids: break
                    
                    ids_to_up = []
                    metas_to_up = []
                    for i, m in zip(ids, metas):
                        if m is None: m = {}
                        if "trang_thai" not in m:
                            m["trang_thai"] = 1
                            ids_to_up.append(i)
                            metas_to_up.append(m)
                    
                    if ids_to_up:
                        collection.update(ids=ids_to_up, metadatas=metas_to_up)
                    offset += len(ids)
                print("ChromaDB migration completed.")
            else:
                print("ChromaDB chunks already have 'trang_thai'.")
        # 3. Sync ChromaDB -> SQLite if SQLite is empty
        print("Checking if SQLite needs re-sync from ChromaDB...")
        from system.database.db_service import DocumentDatabaseService
        db_service = DocumentDatabaseService()
        stats = db_service.get_stats()
        if stats['total_documents'] == 0 and total > 0:
            print(f"SQLite is empty but ChromaDB has {total} chunks. Starting re-sync...")
            # Lấy toàn bộ unique so_hieu từ ChromaDB
            # Vì số lượng chunk lớn, ta lấy theo lô
            unique_docs = {} # so_hieu -> metadata
            offset = 0
            batch_size = 1000
            while offset < total:
                b = collection.get(limit=batch_size, offset=offset, include=["metadatas"])
                for m in b["metadatas"]:
                    if not m or not m.get("so_hieu"): continue
                    
                    so_hieu = m.get("so_hieu")
                    
                    # Nếu chưa có hoặc thông tin hiện tại đang là "Chưa xác định", hãy cập nhật
                    current = unique_docs.get(so_hieu, {})
                    
                    # Kiểm tra xem metadata mới có "tốt" hơn không
                    new_ten = m.get('ten_van_ban') or ""
                    new_co_quan = m.get('co_quan_ban_hanh') or ""
                    
                    is_better = (
                        so_hieu not in unique_docs or 
                        (current.get('ten_van_ban') == "Chưa xác định" and new_ten != "" and new_ten != "Chưa xác định") or
                        (current.get('co_quan_ban_hanh') == "" and new_co_quan != "")
                    )
                    
                    if is_better:
                        unique_docs[so_hieu] = {
                            'so_hieu': so_hieu,
                            'ten_van_ban': new_ten if new_ten else (current.get('ten_van_ban') or "Chưa xác định"),
                            'loai': m.get('loai') or current.get('loai') or "Văn bản",
                            'co_quan_ban_hanh': new_co_quan if new_co_quan else (current.get('co_quan_ban_hanh') or ""),
                            'ngay_ban_hanh': m.get('ngay_ban_hanh') or current.get('ngay_ban_hanh') or "",
                            'ngay_co_hieu_luc': m.get('ngay_co_hieu_luc') or current.get('ngay_co_hieu_luc') or "",
                            'file_path': m.get('file_path') or current.get('file_path') or "",
                            'indexed': 1,
                            'trang_thai': m.get('trang_thai', 1)
                        }
                offset += len(b["ids"])
                print(f"  Scanned {offset}/{total} chunks, collected metadata for {len(unique_docs)} documents.")
            
            if unique_docs:
                print(f"Syncing {len(unique_docs)} documents to SQLite (Create or Update)...")
                from src.core.models import DocumentMetadata
                from system.database.db_respository import DocumentMetadataRepository
                
                session = db_manager.get_session()
                repo = DocumentMetadataRepository(session)
                
                updated_count = 0
                created_count = 0
                
                for doc_meta in unique_docs.values():
                    try:
                        meta = DocumentMetadata.model_validate(doc_meta)
                        if repo.exists(doc_meta['so_hieu']):
                            # Nếu đã tồn tại nhưng tên đang là "Chưa xác định", hãy update
                            db_record = repo.get_by_so_hieu(doc_meta['so_hieu'])
                            if db_record.ten_van_ban == "Chưa xác định" and doc_meta['ten_van_ban'] != "Chưa xác định":
                                repo.update(meta)
                                updated_count += 1
                        else:
                            repo.create(meta)
                            created_count += 1
                    except Exception as e:
                        pass
                
                session.close()
                print(f"Sync finished: Created {created_count}, Updated {updated_count} documents.")
        else:
            print(f"SQLite already has {stats['total_documents']} documents. No re-sync needed.")
        
    except Exception as e:
        print(f"Error during migration/sync: {e}")
        traceback.print_exc()
    print("--- Migrations & Sync Finished ---\n")

if __name__ == "__main__":
    run_migrations()
    print("Starting API Server for Frontend at http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
