from src.indexing.parsing.extract_metadata import Extractor
ex=Extractor()
text="19/2019/NĐ-CP"
print(ex._extract_so_hieu(text))