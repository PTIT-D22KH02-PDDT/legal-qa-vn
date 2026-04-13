import pypandoc
import sys
from pathlib import Path

from .text_cleaner import clean_text


def extract_docx_text(input_file):
    input_path = Path(input_file)
    text = pypandoc.convert_file(
        str(input_path),
        "gfm",
        extra_args=["--wrap=none"],
    )
    text = clean_text(text)

    return text