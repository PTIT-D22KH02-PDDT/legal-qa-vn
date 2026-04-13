"""
- Sửa giá trị `INPUT_PATH`.
- Chạy: `python extractor.py`.
Luồng dữ liệu:
- `extract_file(INPUT_PATH)`:
    - Nếu là .pdf  -> `extract_pdf_text` 
    - Nếu là .docx -> `extract_docx_text`
"""
from pathlib import Path


def extract_file(path):
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File không tồn tại: {file_path}")

    ext = file_path.suffix.lower()

    if ext == ".pdf":
        from src.indexing.ingestion.pdf_extractor import extract_pdf_text
        return extract_pdf_text(str(file_path))
    
    elif ext == ".docx":
        from src.indexing.ingestion.docx_extractor import extract_docx_text
        return extract_docx_text(str(file_path))
    
    elif ext == ".doc":
        from tempfile import TemporaryDirectory
        from doc2docx import convert
        from src.indexing.ingestion.docx_extractor import extract_docx_text

        with TemporaryDirectory() as tmp_dir:
            temp_docx = Path(tmp_dir) / f"{file_path.stem}.docx"
            try:
                convert(str(file_path), str(temp_docx))
            except Exception as err:
                raise ValueError(f"Không thể chuyển đổi .doc sang .docx: {err}") from err

            return extract_docx_text(str(temp_docx))

    else:
        raise ValueError(
            f"Định dạng file không được hỗ trợ: {ext} (chỉ hỗ trợ .pdf, .docx, .doc)"
        )