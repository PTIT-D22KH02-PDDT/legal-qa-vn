from src.indexing.parsing.legal_parser import ParseLegal

parser=ParseLegal()
text1="Khoản 1 Điều 31 Luật số 28/2023/QH15 quy định về trách nhiệm nào của tổ chức và cá nhân liên quan đến giếng bị hỏng hoặc không còn sử dụng ?"
text2="Theo Điều 100 Luật Đất đai, trường hợp của tôi có được cấp sổ đỏ không?"
result=parser.extract_refs_regex_legacy(text2)
print(result)
