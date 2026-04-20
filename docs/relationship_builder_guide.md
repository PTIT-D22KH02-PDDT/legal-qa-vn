"""
DocumentRelationshipBuilder - Xây dựng quan hệ giữa các văn bản luật
dựa trên cấu trúc thư mục

Cấu trúc folder:
    luat_dan_su/
        ├── luat/
        │   └── bo_luat_dan_su.docx
        ├── sua_doi_bo_sung/
        │   ├── nghi_dinh_1.docx
        │   └── thong_tu_2.docx
        ├── nghi_dinh/
        │   ├── nghi_dinh_3.docx
        │   └── nghi_dinh_4.docx
        ├── nghi_quyet/
        │   └── nghi_quyet_5.docx
        ├── thong_tu/
        │   ├── thong_tu_6.docx
        │   └── thong_tu_7.docx
        └── thay_the/
            └── luat_cu.docx

Quan hệ sẽ được xây dựng:
- sửa_đổi_bổ_sung/*.docx → sua_doi_bo_sung → luật/*.docx
- nghị_định/*.docx → huong_dan_thi_hanh → luật/*.docx
- thông_tư/*.docx → huong_dan_thi_hanh → luật/*.docx
- thay_thế/*.docx → thay_the → luật/*.docx
"""

# DocumentRelationshipBuilder - Hướng dẫn sử dụng

## 📋 Mục đích

Pipeline này **tự động xây dựng quan hệ giữa các tài liệu luật** dựa trên cấu trúc thư mục.

Thay vì phải thủ công tạo các relations, bạn chỉ cần:
1. Tổ chức files theo cấu trúc thư mục có cấp
2. Gọi builder → tự động phát hiện quan hệ

## 🗂️ Cấu trúc thư mục

```
luat_dan_su/                      # Thư mục cha (tên luật)
├── luat/                         # Luật chính
│   └── bo_luat_dan_su.docx
├── sua_doi_bo_sung/              # Sửa đổi bổ sung
│   ├── nghi_dinh_01_2020.docx
│   └── thong_tu_02_2021.docx
├── nghi_dinh/                    # Nghị định hướng dẫn
│   ├── nghi_dinh_03_2019.docx
│   └── nghi_dinh_04_2020.docx
├── nghi_quyet/                   # Nghị quyết hướng dẫn
│   └── nghi_quyet_05_2019.docx
├── thong_tu/                     # Thông tư hướng dẫn
│   ├── thong_tu_06_2019.docx
│   └── thong_tu_07_2020.docx
├── thay_the/                     # Luật thay thế (cũ)
│   └── luat_dan_su_cu.docx
├── bai_bo/                       # Luật bị bãi bỏ
│   └── luat_cu_2.docx
└── dinh_chi_hieu_luc/            # Tạm đình chỉ
    └── luat_tam_dung.docx
```

## 🔗 Quan hệ tự động tạo

### Sửa đổi bổ sung
```
nghi_dinh_01_2020 --[sua_doi_bo_sung]--> bo_luat_dan_su
thong_tu_02_2021  --[sua_doi_bo_sung]--> bo_luat_dan_su
```

### Hướng dẫn thi hành
```
nghi_dinh_03_2019 --[huong_dan_thi_hanh]--> bo_luat_dan_su
thong_tu_06_2019  --[huong_dan_thi_hanh]--> bo_luat_dan_su
nghi_quyet_05_2019 --[huong_dan_thi_hanh]--> bo_luat_dan_su
```

### Thay thế
```
luat_dan_su_cu --[thay_the]--> bo_luat_dan_su
```

### Bãi bỏ
```
luat_cu_2 --[bai_bo]--> bo_luat_dan_su
```

### Tạm đình chỉ
```
luat_tam_dung --[dinh_chi_hieu_luc]--> bo_luat_dan_su
```

## 💻 Cách dùng

### 1. Quick Scan (không extract metadata)

```python
from pathlib import Path
from src.indexing.relationship_builder import build_relationships

# Scan folder structure
parent_folder = Path("path/to/luat_dan_su")
docs, relations = build_relationships(parent_folder)

print(f"Documents: {len(docs)}")
print(f"Relations: {len(relations)}")
```

**Ưu điểm**: Nhanh (chỉ scan thư mục)
**Nhược điểm**: doc_id là tên file, không có metadata đầy đủ

### 2. Extract Metadata (không index)

```python
docs, relations = build_relationships(
    parent_folder=parent_folder,
    extract_metadata=True,
)

# Giờ docs sẽ có metadata (so_hieu, ten_van_ban, loai, ngay_ban_hanh, ...)
for doc in docs:
    if doc.metadata:
        print(f"{doc.doc_id}: {doc.metadata.ten_van_ban}")
```

### 3. ⭐ Full Indexing Pipeline (NEW!)

**Khi duyệt file, tự động index (chunk + embed + save to ChromaDB)**

```python
from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel
from src.indexing.vector_store.chroma_store import ChromaStore, ChromaConfig

# Setup embedding model
embedding_model = OnnxEmbeddingModel(
    model_dir="models/vietnamese-embedding"
)

# Setup ChromaDB
chroma_config = ChromaConfig(
    collection_name="legal_documents",
    persist_directory="chroma_db",
    is_persist=True
)
chroma_store = ChromaStore(config=chroma_config)

# Run full pipeline: scan → extract → chunk → embed → save to DB → build relations
docs, relations = build_relationships(
    parent_folder=parent_folder,
    extract_metadata=True,
    index_documents=True,  # ← Enable indexing!
    embedding_model=embedding_model,
    chroma_store=chroma_store,
)

print(f"Documents indexed: {len(docs)}")
print(f"Relations created: {len(relations)}")
```

**Quy trình tự động:**
1. Duyệt từng file trong các thư mục con
2. Extract metadata (so_hieu, ten_van_ban, loai, ngay_ban_hanh, ...)
3. **Hierarchical chunking** (phần → chương → điều → khoản → điểm)
4. **Generate embeddings** (ONNX model)
5. **Upsert to ChromaDB** với metadata
6. Build relations dựa trên folder structure

**Ưu điểm**: 
- Tự động indexing toàn bộ documents một lần
- Đầy đủ metadata và embeddings
- Quan hệ được tạo tự động

**Nhược điểm**: 
- Chậm (phải xử lý từng file)
- Cần embedding model + ChromaDB

### 4. Sử dụng class trực tiếp

```python
from src.indexing.relationship_builder import DocumentRelationshipBuilder

builder = DocumentRelationshipBuilder(
    extract_metadata=True,
    index_documents=True,
    embedding_model=embedding_model,
    chroma_store=chroma_store,
)

# Step 1: Scan folder structure
documents = builder.scan_folder_structure(parent_folder)

# Step 2: Build relations
relations = builder.build_relations()

# Step 3: Xem statistics
stats = builder.get_stats()
print(f"Total documents: {stats['total_documents']}")
print(f"Total relations: {stats['total_relations']}")
print(f"Indexing stats: {stats['indexing']}")
```

## 📊 Output

### Documents
```python
DocumentInfo(
    file_path=Path("path/to/file.docx"),
    folder_type=FolderType.SUA_DOI_BO_SUNG,
    metadata=DocumentMetadata(...),  # Nếu extract_metadata=True
    doc_id="nghi_dinh_01_2020"
)
```

### Relations
```python
DocumentRelation(
    entity_start="nghi_dinh_01_2020",
    entity_end="bo_luat_dan_su",
    relation_type=RelationType.sua_doi_bo_sung,
    description="sua_doi_bo_sung → luat"
)
```

### Indexing Stats (khi index_documents=True)
```python
stats = builder.get_stats()
# {
#   'total_folders': 5,
#   'total_documents': 12,
#   'total_relations': 8,
#   'indexing': {
#       'total_files': 12,
#       'indexed_files': 12,
#       'failed_files': 0,
#       'total_chunks': 2493,
#       'total_embeddings': 2493,
#   }
# }
```

**ChromaDB Collections:**
```
collection: "legal_documents_relations"
├── id: "91_2015_qh13_chunk_1"
├── text: "Chương I: Những quy định chung..."
├── embedding: [0.123, -0.456, ...]  # 768-dimensional
└── metadata: {
    'doc_id': '91_2015_qh13',
    'chunk_id': 'chunk_1',
    'ten_van_ban': 'Bộ luật Dân sự',
    'loai': 'bo_luat',
    'ngay_ban_hanh': '01/01/2016',
    ...
}
```

## 🎯 Trường hợp sử dụng

### 1. Xây dựng knowledge graph
```python
docs, relations = build_relationships(parent_folder)

# Save to Neo4j, GraphDB, v.v.
for rel in relations:
    db.add_relation(
        source=rel.entity_start,
        target=rel.entity_end,
        type=rel.relation_type.value
    )
```

### 2. Tìm kiếm liên quan
```python
# Khi user tìm "bo_luat_dan_su", tìm tất cả docs có quan hệ
related = [r.entity_start for r in relations if r.entity_end == "bo_luat_dan_su"]
print(f"Documents liên quan: {related}")
# → ['nghi_dinh_01_2020', 'thong_tu_02_2021', ...]
```

### 3. Đẩy vào ChromaDB với metadata
```python
# Index documents với relation info
for doc in docs:
    metadata = {
        "doc_id": doc.doc_id,
        "folder_type": doc.folder_type.value,
        "file_path": str(doc.file_path),
    }
    
    if doc.metadata:
        metadata.update({
            "ten_van_ban": doc.metadata.ten_van_ban,
            "loai": doc.metadata.loai,
            "ngay_ban_hanh": doc.metadata.ngay_ban_hanh,
        })
    
    # Upsert to ChromaDB
    chroma_store.upsert(
        document=doc.doc_id,
        metadata=metadata,
        embedding=...
    )
```

### 4. Trực quan hóa quan hệ
```python
# Tạo graph visualization
import networkx as nx
import matplotlib.pyplot as plt

G = nx.DiGraph()

# Add nodes
for doc in docs:
    G.add_node(doc.doc_id, folder=doc.folder_type.value)

# Add edges
for rel in relations:
    G.add_edge(
        rel.entity_start,
        rel.entity_end,
        relation=rel.relation_type.value
    )

# Draw
pos = nx.spring_layout(G)
nx.draw(G, pos, with_labels=True, node_color='lightblue')
plt.savefig('legal_relations.png')
```

## ⚙️ Tuỳ chỉnh

### Thêm folder type mới

```python
# 1. Thêm vào enum
class FolderType(str, Enum):
    CUSTOMTYPE = "customtype"

# 2. Thêm vào mapping
FolderTypeDetector.FOLDER_MAPPING["customtype"] = FolderType.CUSTOMTYPE

# 3. Thêm vào relation logic
relation_map = {
    ...
    FolderType.CUSTOMTYPE: RelationType.lien_quan,  # Hoặc relation type khác
}
```

### Thêm relation type mới

```python
# 1. Thêm vào enum
class RelationType(str, Enum):
    custom_relation = "custom_relation"

# 2. Thêm vào RelationTypeDeterminer
relation_map = {
    ...
    FolderType.CUSTOM: RelationType.custom_relation,
}
```

## 🐛 Debugging

```python
import logging

# Set log level to DEBUG
logging.basicConfig(level=logging.DEBUG)

# Giờ sẽ thấy chi tiết từng bước
docs, relations = build_relationships(parent_folder)
```

## 📝 Lưu ý

1. **Folder type detection**: Dựa trên tên thư mục, nên đặt tên rõ ràng
2. **Metadata extraction**: Chỉ hoạt động nếu files là .docx/.doc/.pdf hợp lệ
3. **Relations chỉ tạo với "luat"**: Hiện tại, chỉ các folder khác có quan hệ với folder "luat"
4. **File recursion**: Tìm files cả trong các subfolder con (sử dụng rglob)
