#!/usr/bin/env python3
"""
Script để in danh sách chunks từ một tài liệu cụ thể
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def print_chunks_list(file_path: str = None):
    """
    In danh sách chunks từ tài liệu
    
    Args:
        file_path: Đường dẫn file PDF/DOCX (nếu None sẽ dùng file mẫu)
    """
    
    if file_path is None:
        file_path = str(project_root / "data" / "91_2015_QH13_296215.docx")
    
    # Load config
    from src.indexing.config import IndexingConfig
    from src.indexing.chunker import create_chunker
    
    config = IndexingConfig.get_default_config()
    chunker_params = config.get_chunker_params()
    chunker_strategy = chunker_params.pop('strategy', 'fixed_size')
    
    # Create chunker
    print(f"\n📄 Document: {file_path}")
    print(f"🔪 Chunker Strategy: {chunker_strategy}")
    print()
    
    chunker = create_chunker(strategy=chunker_strategy, **chunker_params)
    
    # Process document
    print("⏳ Processing document...")
    tree, chunks = chunker.create_document_node(file_path=file_path)
    
    print(f"✓ Done! Total chunks: {len(chunks)}\n")
    
    # Print header
    print("=" * 180)
    print("CHUNKS DETAIL")
    print("=" * 180)
    print(f"{'#':<6} {'ID':<35} {'Type':<12} {'Title':<30} {'Content Preview':<60} {'Parent ID':<20}")
    print("-" * 180)
    
    # Print each chunk
    for idx, chunk in enumerate(chunks, start=1):
        content_preview = (chunk.content[:60] if chunk.content else "N/A").replace('\n', ' ')
        chunk_id = (chunk.id or "N/A")[:35]
        chunk_type = (chunk.type or "N/A")[:12]
        chunk_title = (chunk.title or "N/A")[:30]
        chunk_parent = (chunk.parent_id or "N/A")[:20]
        
        print(f"{idx:<6} {chunk_id:<35} {chunk_type:<12} {chunk_title:<30} {content_preview:<60} {chunk_parent:<20}")
    
    # Summary stats
    print("=" * 180)
    print("\nSUMMARY STATS:")
    print("-" * 50)
    
    type_counts = {}
    for chunk in chunks:
        chunk_type = chunk.type or "unknown"
        type_counts[chunk_type] = type_counts.get(chunk_type, 0) + 1
    
    for chunk_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {chunk_type:<15} : {count:>6} chunks")
    
    print("-" * 50)
    print(f"  {'TOTAL':<15} : {len(chunks):>6} chunks")
    print("=" * 50 + "\n")


def export_chunks_to_json(file_path: str = None, output_path: str = None):
    """
    Export chunks to JSON file
    
    Args:
        file_path: Đường dẫn file PDF/DOCX
        output_path: Đường dẫn file JSON output (nếu None sẽ tự tạo)
    """
    import json
    from pathlib import Path
    
    if file_path is None:
        file_path = str(project_root / "data" / "91_2015_QH13_296215.docx")
    
    # Load config
    from src.indexing.config import IndexingConfig
    from src.indexing.chunker import create_chunker
    
    config = IndexingConfig.get_default_config()
    chunker_params = config.get_chunker_params()
    chunker_strategy = chunker_params.pop('strategy', 'fixed_size')
    
    # Create chunker
    print(f"\n📄 Document: {file_path}")
    print(f"🔪 Chunker Strategy: {chunker_strategy}")
    print("⏳ Processing document...")
    
    chunker = create_chunker(strategy=chunker_strategy, **chunker_params)
    tree, chunks = chunker.create_document_node(file_path=file_path)
    
    # Prepare JSON data
    chunks_data = []
    for idx, chunk in enumerate(chunks, start=1):
        chunks_data.append({
            "index": idx,
            "id": chunk.id or "N/A",
            "type": chunk.type or "N/A",
            "title": chunk.title or "N/A",
            "content": chunk.content or "N/A",
            "parent_id": chunk.parent_id or "N/A",
            "reference": chunk.reference or "N/A"
        })
    
    # Generate output path if not provided
    if output_path is None:
        doc_name = Path(file_path).stem
        output_path = str(project_root / f"chunks_{doc_name}.json")
    
    # Write to JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "document": file_path,
            "strategy": chunker_strategy,
            "total_chunks": len(chunks),
            "chunks": chunks_data
        }, f, ensure_ascii=False, indent=2)
    
    print(f"✓ Done! Total chunks: {len(chunks)}")
    print(f"💾 JSON saved to: {output_path}\n")
    
    return output_path


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Print chunks list from a document")
    parser.add_argument("--file", "-f", type=str, default=None, help="Path to PDF/DOCX file")
    parser.add_argument("--json", "-j", action="store_true", help="Export to JSON format")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output JSON file path")
    
    args = parser.parse_args()
    
    try:
        if args.json:
            export_chunks_to_json(file_path=args.file, output_path=args.output)
        else:
            print_chunks_list(file_path=args.file)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
