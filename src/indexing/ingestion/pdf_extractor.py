import subprocess
import tempfile
import pypandoc
from pathlib import Path

from src.indexing.ingestion.text_cleaner import clean_text

def extract_pdf_text(file_path):
    """
    PDF -> any2md -> pandoc normalize -> clean_text -> output.md
    """
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        subprocess.run(
            ["any2md", str(file_path), "-o", str(tmpdir_path), "-f"],
            check=True,
        )

        md_file = next(tmpdir_path.glob("*.md"))
        raw_text = md_file.read_text(encoding="utf-8")

        formatted_text = pypandoc.convert_text(
            raw_text,
            to="gfm",
            format="markdown-fancy_lists",
            extra_args=["--wrap=none", "--strip-comments"],
        )

    cleaned_text = clean_text(formatted_text)
    return cleaned_text