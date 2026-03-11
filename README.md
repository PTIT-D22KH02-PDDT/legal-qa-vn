# legal-qa-vn
BT nhóm - Xử lý ngôn ngữ tự nhiên - Xây dựng hệ thống hỏi đáp pháp lý có trích dẫn điều luật cho văn bản quy phạm pháp luật Việt Nam

## Prerequisites
- Python 3.11+
- uv

## Directory structure

Cấu trúc của dự án được tổ chức như sau (giai đoạn indexing):

```bash
legal-qa-vn
|-- .env
|-- .env.example
|-- .gitignore
|-- .python-version
|-- README.md
|-- data
|-- main.py
|-- docs
|   |-- setup.md            # Hướng dẫn thiết lập môi trường và cài đặt dependencies
|-- models                  # Chứa các mô hình được tải về, sử dụng trong project
|-- notebooks               # Chứa các notebook cần thử nghiệm
|-- pyproject.toml          # Gồm dependencies và cấu hình dự án
|-- src                     # Chứa mã nguồn chính của dự án
|   |-- core                # Chứa các module lõi, không thay đổi nhiều ở các phương pháp triển khai
|   |   |-- chunking        # Chứa code về chunking
|   |   |-- embedding       # Chứa code về embedding
|   |   |-- ingestion       # Chứa code về xử lý đầu vào
|   |   `-- vector_store    # Chứa code xử lý lưu trữ embedding
|   |-- pipeline            # Chứa các pipeline cụ thể
|   `-- schemas.py          # Định nghĩa các schema dùng chung trong dự án
```

## Setup
[Hướng dẫn setup](./docs/setup.md)