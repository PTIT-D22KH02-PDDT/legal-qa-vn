from src.indexing.parsing.extract_metadata import Extractor

text1 = """
CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc

THÔNG TƯ
Hướng dẫn thực hiện Đề án đào tạo cán bộ quân sự Ban chỉ huy quân sự cấp xã trình độ cao đẳng, đại học ngành quân sự cơ sở đến năm 2020 và những năm tiếp theo, theo Quyết định số 799/QĐ-TTg ngày 25 tháng 5 năm 2011 của Thủ tướng Chính phủ

Căn cứ Luật Dân quân tự vệ ngày 23 tháng 11 năm 2009;
"""

text2 = """
CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc

THÔNG TƯ
HƯỚNG DẪN HOẠT ĐỘNG VÀ QUẢN LÝ QUỸ ĐẦU TƯ CHỨNG KHOÁN

Căn cứ Luật Chứng khoán ngày 26 tháng 11 năm 2019;
"""

text3 = """
BỘ LUẬT
DÂN SỰ

Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;
Quốc hội ban hành Bộ luật dân sự.
"""

def test():
    extractor = Extractor()
    print("=== TEST 1 (Chữ thường, dài) ===")
    print(extractor._extract_ten_van_ban(text1, 'thong_tu'))
    
    print("\n=== TEST 2 (ALL CAPS, ngắn) ===")
    print(extractor._extract_ten_van_ban(text2, 'thong_tu'))
    
    print("\n=== TEST 3 (BỘ LUẬT DÂN SỰ) ===")
    print(extractor._extract_ten_van_ban(text3, 'bo_luat'))

if __name__ == '__main__':
    test()
