# Database Integration Guide

## Overview

Sistema de persistência para DocumentMetadata e DocumentRelation usando SQLAlchemy + SQLite (ou PostgreSQL).

## Arquitetura

### 1. Database Models (`db.py`)

**DocumentMetadataDB**
- Armazena informações de documentos (Luật, Nghị định, etc.)
- PK: `so_hieu` (numero do documento)
- Campos: `ten_van_ban`, `loai`, `co_quan_ban_hanh`, `ngay_ban_hanh`, `ngay_co_hieu_luc`, `so_dieu`, `file_path`, `md_path`
- Relationships: `document_files` (1→N), `relations_from` (1→N), `relations_to` (1→N)

**DocumentRelationDB**
- Armazena relações entre documentos
- PK: `id` (auto-increment)
- FKs: `entity_start` → DocumentMetadataDB, `entity_end` → DocumentMetadataDB
- Campos: `relation_type` (Enum: sua_doi_bo_sung, huong_dan_thi_hanh, etc.), `description`, `created_at`

**DocumentFileDB**
- Rastreia arquivo source para cada documento
- FK: `so_hieu` → DocumentMetadataDB
- Campos: `file_path`, `chroma_collection` (se indexado em ChromaDB)

### 2. Repository Pattern (`db.py`)

**DocumentMetadataRepository**
- `create()` - Salvar novo document
- `get_by_so_hieu()` - Buscar por ID
- `get_by_loai()` - Buscar por tipo
- `get_all()` - Listar com paginação
- `update()` - Atualizar documento
- `delete()` - Remover documento
- `exists()` - Verificar existência

**DocumentRelationRepository**
- `create()` - Salvar nova relação
- `get_by_id()` - Buscar por ID
- `get_relations_from()` - Relações saindo do documento
- `get_relations_to()` - Relações entrando no documento
- `get_by_type()` - Buscar por tipo de relação
- `get_related_documents()` - Tudo relacionado a um documento
- `get_all()` - Listar com paginação
- `count_all()` - Contar total

### 3. Service Layer (`db_service.py`)

**DocumentDatabaseService**
- Interface de alto nível para salvar/consultar
- `save_documents()` - Salvar lista de DocumentInfo
- `save_relations()` - Salvar lista de DocumentRelation
- `get_related_documents()` - Buscar relacionados com JSON
- `get_documents_by_type()` - Buscar por tipo
- `get_all_documents()` - Listar todos
- `get_all_relations()` - Listar relações
- `get_stats()` - Estatísticas do DB

## Setup

### Instalação de dependências

```bash
uv add sqlalchemy
```

### Inicializar Database

```python
from src.system.db import init_database

# Usar SQLite (default)
db_manager = init_database()

# Ou PostgreSQL
db_manager = init_database(
    db_path="postgresql://user:password@localhost/legal_db",
    db_type="postgresql"
)
```

## Uso

### 1. Salvar Documents e Relations

```python
from src.system.relationship_builder import build_relationships
from src.system.db import init_database
from src.system.db_service import DocumentDatabaseService

# Initialize DB
db_manager = init_database()

# Build relationships
docs, relations = build_relationships(
    parent_folder=Path("path/to/data"),
    extract_metadata=True,
    index_documents=False
)

# Save to database
service = DocumentDatabaseService()
saved_docs, saved_so_hieu = service.save_documents(docs)
saved_rels, skipped_rels = service.save_relations(relations)

print(f"Saved {saved_docs} documents")
print(f"Saved {saved_rels} relations")
```

### 2. Query Documents

```python
service = DocumentDatabaseService()

# Get specific document
doc_with_relations = service.get_related_documents("35/2024/QH15")
print(doc_with_relations)
# {
#   'document': {...},
#   'related_from': [relation1, relation2, ...],
#   'related_to': [relation3, relation4, ...]
# }

# Get all documents of type
luat_docs = service.get_documents_by_type("Luật")

# Get all documents with pagination
all_docs = service.get_all_documents(limit=50, offset=0)

# Get all relations with pagination
all_relations = service.get_all_relations(limit=50, offset=0)

# Get database stats
stats = service.get_stats()
# {'total_documents': 100, 'indexed_documents': 50, 'total_relations': 250}
```

### 3. Direct Repository Access

```python
from src.system.db import get_session, DocumentMetadataRepository

session = get_session()
repo = DocumentMetadataRepository(session)

# CRUD operations
metadata_obj = repo.get_by_so_hieu("35/2024/QH15")
repo.update("35/2024/QH15", indexed=1)
all_docs = repo.get_all()

session.close()
```

## Database Schema

### SQLite

Arquivo: `legal_documents.db` (raiz do projeto)

Tables:
- `document_metadata` (so_hieu VARCHAR PK, ...)
- `document_relation` (id INTEGER PK, entity_start FK, entity_end FK, ...)
- `document_file` (id INTEGER PK, so_hieu FK, ...)

### PostgreSQL

Connection String:
```
postgresql://user:password@host:5432/legal_qa_db
```

Tables: Mesmas como SQLite

## Example Complete Workflow

```python
from pathlib import Path
from src.system.relationship_builder import build_relationships
from src.system.db import init_database
from src.system.db_service import DocumentDatabaseService

# 1. Initialize
db_manager = init_database()

# 2. Build relationships
parent_folder = Path("C:/Users/LAPTOP HP/Downloads/data_raw_law/dan_su")
docs, relations = build_relationships(
    parent_folder=parent_folder,
    extract_metadata=True
)

# 3. Save to DB
service = DocumentDatabaseService()
saved_docs, _ = service.save_documents(docs)
saved_rels, _ = service.save_relations(relations)

# 4. Query
print(f"Total: {saved_docs} documents, {saved_rels} relations")

# 5. Get related documents
related = service.get_related_documents("35/2024/QH15")
if related:
    print(f"Document: {related['document']['ten_van_ban']}")
    print(f"Related From: {len(related['related_from'])} relations")
    
    for rel in related['related_from']:
        print(f"  {rel['source']} --[{rel['type']}]--> {rel['target']}")

service.close()
```

## Migrações (Futuro)

Para mudanças de schema em produção, considerar usar Alembic:

```bash
uv add alembic

# Initialize Alembic
alembic init migrations

# Auto-generate migration
alembic revision --autogenerate -m "Add new field"

# Apply migration
alembic upgrade head
```

## Performance Tips

1. **Indexação**: Adicionar índices em colunas frequentemente queryadas
   ```python
   Index('idx_loai', DocumentMetadataDB.loai)
   Index('idx_relation_type', DocumentRelationDB.relation_type)
   ```

2. **Batch Operations**: Para salvar muitos documents/relations
   ```python
   # Usar session.bulk_insert_mappings() em vez de add() um a um
   ```

3. **Paginação**: Sempre usar limit/offset para consultas grandes

4. **Connection Pooling**: Configure em DatabaseConfig para produção

## Troubleshooting

### "Column already exists" error
Deletar `legal_documents.db` e reinicializar

### Foreign Key violations
Garantir que `entity_start` e `entity_end` existem em `document_metadata` antes de salvar relations

### Session timeout
Chamar `service.close()` após terminar operações para liberar conexão

## Próximos Passos

1. Adicionar suporte para Neo4j para visualização de grafo
2. Implementar full-text search em `ten_van_ban` e `file_path`
3. Adicionar caching com Redis
4. Implementar migrations com Alembic
