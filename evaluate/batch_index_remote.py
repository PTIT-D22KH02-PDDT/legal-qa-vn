import os
from pathlib import Path
import json
from datetime import datetime
from src.indexing.indexing import process_document

def batch_index_remote(folder_path: str):
    folder = Path(folder_path)
    files = list(folder.glob('*.doc*'))  
    print(f"Found {len(files)} files in {folder_path}")
    
    error_logs = []

    for idx, file_path in enumerate(files, 1):
        print(f"[{idx}/{len(files)}] Indexing: {file_path}")
        try:
            result = process_document(
                file_path=str(file_path),
                use_remote_api=True,
            )
            success = result.get('success', True)
            print(f"    Success: {success}")

            if not success:
                error_logs.append({
                    "file": str(file_path),
                    "error": result,
                    "timestamp": datetime.now().isoformat()
                })

        except Exception as exc:
            print(f"    Failed: {exc}")
            error_logs.append({
                "file": str(file_path),
                "error": str(exc),
                "timestamp": datetime.now().isoformat()
            })

    if error_logs:
        log_file = f"error_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(error_logs, f, ensure_ascii=False, indent=2)

        print(f"\nSaved {len(error_logs)} errors to {log_file}")
    else:
        print("\nNo errors found!")


if __name__ == "__main__":
    folder = "data/vbpl_1_4/20_3"   #đường dẫn vào thư mục chưa tài liệu để indexing
    batch_index_remote(folder)
