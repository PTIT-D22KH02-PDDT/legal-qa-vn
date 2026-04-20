# legal-qa-vn
BT nhóm - Xử lý ngôn ngữ tự nhiên - Xây dựng hệ thống hỏi đáp pháp lý có trích dẫn điều luật cho văn bản quy phạm pháp luật Việt Nam

## Prerequisites
- Python 3.10+
- uv (package manager)
- Models: `models/vietnamese-embedding/` (ONNX embedding model)

## Directory structure

```bash
legal-qa-vn
|-- .env
|-- .env.example
|-- .gitignore
|-- .python-version
|-- README.md
|-- pyproject.toml                # Dependencies & project config
|-- legal_documents.db            # SQLite database (tạo sau lần chạy đầu tiên)
|-- chroma_db/                    # ChromaDB vector store
|-- configs/
|   |-- indexing_config.yaml
|   |-- rag_config.yaml
|   |-- retrieval_config.yaml
|   `-- prompts/
|-- models/
|   `-- vietnamese-embedding/     # ONNX embedding model (768-dim)
|-- data/                         # Input documents
|-- json/                         # Document JSON files
|-- src/
|   |-- core/                     # Core modules
|   |   |-- enums.py              # RelationType, DocumentType enums
|   |   |-- models.py             # Pydantic models
|   |   `-- config.py
|   |-- indexing/
|   |   |-- indexing.py           # Main indexing pipeline
|   |   |-- config.py
|   |   |-- chunker/              # Hierarchical & fixed-size chunkers
|   |   |-- embedding/            # OnnxEmbeddingModel, embedding logic
|   |   |-- ingestion/            # PDF/DOCX/text extraction
|   |   `-- parsing/
|   |       `-- extract_metadata.py  # Document metadata extraction
|   |-- search/
|   |   |-- pipeline.py           # Search + reranking pipeline
|   |   `-- retrieval/
|   |-- generate/
|   |   `-- service.py
|   |-- rag/
|   |   `-- pipeline.py           # RAG orchestration
|   `-- system/
|       |-- relationship_builder.py   # Auto relationship detection
|       `-- database/
|           |-- db.py             # SQLAlchemy ORM models
|           |-- db_respository.py  # Repository pattern, DB config
|           |-- db_service.py      # High-level service layer
|           `-- db_test.py         # Example workflow
```

## Setup
[Hướng dẫn setup](./docs/setup.md)