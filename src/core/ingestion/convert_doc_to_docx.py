import sys
from pathlib import Path
import pypandoc
if sys.platform=="win32":
    import win32com.client

def convert_doc_to_docx(doc_path: Path, output_dir:Path):
    # Khởi tạo Word
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = False  # Chặn các thông báo pop-up của Word

    try:
        # 1. Mở file
        abs_doc_path = str(doc_path.resolve())
        doc = word.Documents.Open(abs_doc_path)

        docx_path = output_dir/(doc_path.stem+".docx")
        abs_docx_path = str(docx_path.resolve())

        # 2. Kiểm tra và xóa file cũ nếu tồn tại
        if docx_path.exists():
            os.remove(docx_path)

        # 3. Lưu file
        doc.SaveAs(abs_docx_path, FileFormat=16)

        # 4. ĐÓNG FILE TRƯỚC
        doc.Close(False)  # False nghĩa là không lưu thay đổi thêm

        return docx_path

    except Exception as e:
        print(f"Lỗi: {e}")
        return None

    finally:
        # 5. THOÁT ỨNG DỤNG VÀ GIẢI PHÓNG BỘ NHỚ
        word.Quit()
        del word  # Xóa biến để Python giải phóng COM object ngay lập tức

