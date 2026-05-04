import csv
import os
import re

# --- Cấu hình ---
INPUT_FILE = "vietnamese-legal-document-agency-distribution.csv"
OUTPUT_FILE = "filtered_agencies.csv"

def filter_agencies():
    if not os.path.exists(INPUT_FILE):
        print(f"Lỗi: Không tìm thấy file {INPUT_FILE}")
        return

    # 1. Định nghĩa logic lọc
    include_exact = {
        'ngân hàng nhà nước', 'ngân hàng nhà nước việt nam',
        'kiểm toán nhà nước', 'ủy ban dân tộc', 'uỷ ban dân tộc',
        'chính phủ', 'thủ tướng chính phủ', 'quốc hội', 
        'uỷ ban thường vụ quốc hội', 'ủy ban thường vụ quốc hội',
        'chủ tịch nước', 'tòa án nhân dân tối cao', 'toà án nhân dân tối cao',
        'viện kiểm sát nhân dân tối cao'
    }
    
    include_prefixes = [
        'bộ ', 'uỷ ban nhân dân', 'ủy ban nhân dân', 'hội đồng nhân dân',
        'hội đồng bộ trưởng', 'hội đồng chính phủ', 'hội đồng nhà nước',
        'chủ tịch hội đồng bộ trưởng'
    ]

    exclude_prefixes = ['ban ', 'cục ', 'tổng cục ', 'chi cục ', 'sở ', 'văn phòng ']

    results = []
    
    # 2. Đọc và lọc
    with open(INPUT_FILE, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader) # Bỏ qua header
        
        for row in reader:
            if not row or len(row) < 2: continue
            
            co_quan = row[0].strip().lower()
            try:
                count = int(row[1])
            except:
                continue

            # --- Logic Lọc ---
            
            # A. Include Logic
            is_included = (co_quan in include_exact) or any(co_quan.startswith(p) for p in include_prefixes)
            if not is_included:
                continue
                
            # B. Exclude Logic (Loại nhiễu)
            if any(co_quan.startswith(p) for p in exclude_prefixes):
                continue
            
            if "mặt trận" in co_quan or "đoàn" in co_quan:
                continue
                
            # Loại bỏ %hội% trừ trường hợp đặc biệt
            if "hội" in co_quan:
                if not ("hội đồng nhân dân" in co_quan or "quốc hội" in co_quan):
                    continue
            
            # C. Loại ngân hàng khác
            if co_quan.startswith("ngân hàng ") and co_quan not in ['ngân hàng nhà nước', 'ngân hàng nhà nước việt nam']:
                continue
                
            # D. Loại rác/nước ngoài
            if "triều tiên" in co_quan or "cộng hoà xã hội chủ nghĩa việt nam" in co_quan:
                continue
                
            # E. Lọc số lượng > 20
            if count <= 20:
                continue
                
            results.append([row[0], count])

    # 3. Sắp xếp theo số lượng giảm dần
    results.sort(key=lambda x: x[1], reverse=True)

    # 4. Lưu kết quả
    with open(OUTPUT_FILE, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(results)

    print(f"Đã lọc xong! Còn lại {len(results)} cơ quan.")
    print(f"Kết quả lưu tại: {OUTPUT_FILE}")
    print("\nTop 10 cơ quan nhiều văn bản nhất:")
    for r in results[:10]:
        print(f"{r[0]}: {r[1]}")

if __name__ == "__main__":
    filter_agencies()
