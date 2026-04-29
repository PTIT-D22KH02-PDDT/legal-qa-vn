# legal-qa-vn
BT nhóm - Xử lý ngôn ngữ tự nhiên - Xây dựng hệ thống hỏi đáp pháp lý có trích dẫn điều luật cho văn bản quy phạm pháp luật Việt Nam

## Prerequisites
- Python 3.11+
- uv

## Directory structure

Cấu trúc thư mục chính của dự án:

```bash
.
|-- main.py
|-- prompt.txt
|-- pyproject.toml
|-- README.md
|-- docs/
|   |-- setup.md
|-- data/
|-- models/
|   |-- Vietnamese_Embedding_v2/
|   |-- Vietnamese_Reranker/
|-- chroma_db/
|-- notebooks/
|-- src/
|   |-- api/
|   |-- core/
|   |-- indexing/
|   |-- rag/
|   |-- search/
```

## Setup
[Hướng dẫn setup](./docs/setup.md)