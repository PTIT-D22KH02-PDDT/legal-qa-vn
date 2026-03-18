import re
from pathlib import Path
import json

# Bộ từ điển chuyển đổi từ Việt sang số
VIETNAMESE_NUM_MAP = {
    'nhất': '1', 'một': '1',
    'hai': '2',
    'ba': '3',
    'bốn': '4', 'tư': '4',
    'năm': '5',
    'sáu': '6',
    'bảy': '7',
    'tám': '8',
    'chín': '9',
    'mười': '10',
    'mười một': '11',
    'mười hai': '12',
    'mười ba': '13',
    'mười bốn': '14',
    'mười năm': '15',
    'mười sáu': '16',
    'mười bảy': '17',
    'mười tám': '18',
    'mười chín': '19',
    'hai mươi': '20',
    'ba mươi': '30',
    'bốn mươi': '40',
    'tư mươi': '40',
    'năm mươi': '50',
    'sáu mươi': '60',
    'bảy mươi': '70',
    'tám mươi': '80',
    'chín mươi': '90',
}

# Map Roman numerals
ROMAN_NUM_MAP = {
    'i': '1', 'I': '1',
    'ii': '2', 'II': '2',
    'iii': '3', 'III': '3',
    'iv': '4', 'IV': '4',
    'v': '5', 'V': '5',
    'vi': '6', 'VI': '6',
    'vii': '7', 'VII': '7',
    'viii': '8', 'VIII': '8',
    'ix': '9', 'IX': '9',
    'x': '10', 'X': '10',
}

def normalize_id(raw_id, only_vietnamese=False):
    """
    Chuyển đổi ID từ dạng Việt sang số
    VD: 'nhất' → '1', 'hai' → '2'
    
    Args:
        only_vietnamese: Nếu True, chỉ normalize từ Việt, bỏ qua La Mã
    """
    raw_id_lower = raw_id.lower().strip()
    
    # Normalize khoảng trắng thừa
    raw_id_lower = re.sub(r'\s+', ' ', raw_id_lower)
    
    # Try Vietnamese number map (có thể chứa khoảng trắng)
    if raw_id_lower in VIETNAMESE_NUM_MAP:
        return VIETNAMESE_NUM_MAP[raw_id_lower]
    
    # Try Roman numeral map (chỉ nếu not only_vietnamese)
    if not only_vietnamese and raw_id_lower in ROMAN_NUM_MAP:
        return ROMAN_NUM_MAP[raw_id_lower]
    
    # Return as-is if no match (e.g., already numeric or other format)
    return raw_id_lower

def parse_heading(line):
    """
    Phân tích dòng và xác định loại heading (Phần, Chương, Mục, Điều, Khoản, Điểm)
    
    Quy tắc phân biệt:
    - Phần: Phần + (từ Việt đếm | số La Mã I-XX | số 1-20)
    - Chương: Chương + (số La Mã I-XX | số)
    - Mục: Mục + (số La Mã I-XX | số)
    - Điều: Điều + (số | chữ cái)
    - Khoản: Khoản + (số | chữ cái) - hoặc dạng số 1.1, 1.2
    - Điểm: Điểm + (số | chữ cái) - hoặc dạng chữ cái a), b)
    
    Dấu câu theo sau ID có thể là: [:.)], dấu ; v.v.
    """
    if not line: return None

    # Roman numerals: sắp xếp từ dài nhất đến ngắn nhất để regex alternation hoạt động đúng
    # Tối đa ~20 phần: roman_1_20_short (i-xx)
    # Chương/Mục có thể tới 30+: roman_1_30 (i-xxx) để hỗ trợ Chương XXV, XXVI, XXVII, v.v.
    roman_1_30 = r'(?:xxx|xxix|xxviii|xxvii|xxvi|xxv|xxiv|xxiii|xxii|xxi|xx|xix|xviii|xvii|xvi|xv|xiv|xiii|xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i)'
    roman_1_20_short = r'(?:xx|xix|xviii|xvii|xvi|xv|xiv|xiii|xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i)'
    
    # Phần: từ Việt hoặc số La Mã (tối đa XX) hoặc số arab
    phan_viet = r'nhất|một|hai|ba|bốn|tư|năm|sáu|bảy|tám|chín|mười(?:\s+\w+)?|hai\s+mươi'
    phan_id_pattern = f'(?:{phan_viet}|{roman_1_20_short}|\\d+)'

    # Chương/Mục: số La Mã (tới 30) hoặc số arab
    chuong_muc_pattern = f'(?:{roman_1_30}|\\d+)'
    
    # Điều/Khoản/Điểm: có thể là số hoặc chữ cái, có thể có dấu chấm (1.1, 1.1.1, etc.)
    dieu_khoan_diem_id = r'[0-9a-zđ]+(?:\.[0-9a-zđ]+)*'

    PATTERNS = [
        # Phần: MUST be one of:
        # 1. "Phần thứ {Vietnamese}" - MUST have "thứ" + lowercase Vietnamese word
        # 2. "Phần {Roman|Digit}" - uppercase Roman or digit, NO Vietnamese word
        # This prevents matching false positives like "phần ba", "phần tương ứng", etc.
        ('phan', rf'(?i)^phần\s+thứ\s+({phan_viet})(?:[\.\:\)]|$|\s|,)'),
        ('phan_num', rf'(?i)^phần\s+({roman_1_20_short}|\d+)(?:[\.\:\)]|$|\s|,)'),
        
        # Chương: Chương + ID + (end of line OR punctuation)
        ('chuong', rf'(?i)^chương\s+({chuong_muc_pattern})(?:[\.\:\)]|$|\s|,)'),
        
        # Mục: Mục + ID
        ('muc', rf'(?i)^mục\s+({chuong_muc_pattern})(?:[\.\:\)]|$|\s)'),
        
        # Điều: "Điều 1", "Điều a", "Điều 1a", etc.
        ('dieu', rf'(?i)^điều\s+({dieu_khoan_diem_id})(?:[\.\:\)\;]|$|\s)'),
        
        # Khoản: "Khoản 1", "Khoản a", "Khoản 1.1", "Khoản 1.1.1", etc.
        ('khoan', rf'(?i)^khoản\s+({dieu_khoan_diem_id})(?:[\.\:\)\;]|$|\s)'),
        
        # Điểm: "Điểm 1", "Điểm a", etc.
        ('diem', rf'(?i)^điểm\s+({dieu_khoan_diem_id})(?:[\.\:\)\;]|$|\s)'),
        
        # Khoản/Điểm dạng số có dấu chấm: 1.1, 1.2, 1.1.1 (khi không có từ "Khoản")
        # Handle both ) and \) from docx conversion
        ('so_cap_3',   r'^(\d+\.\d+\.\d+)[\\\.\)]?\s*(.*)$'),
        ('so_cap_2',   r'^(\d+\.\d+)[\\\.\)]?\s*(.*)$'),
        ('so_cap_1',   r'^(\d+)[\\\.\)]\s*(.*)$'),

        # Khoản/Điểm dạng chữ cái: a), b), đ), v.v. (khi không có từ "Điểm")
        # Handle both ) and \) from docx conversion
        ('chu_thuong', r'^([a-zđ])[\\\.\)\,\;]\s*(.*)$')
    ]

    for p_type, pattern in PATTERNS:
        match = re.match(pattern, line)
        if match:
            raw_id = match.group(1).lower().strip()
            
            # Normalize phan_num back to phan for consistency
            normalized_type = 'phan' if p_type == 'phan_num' else p_type
            
            # Chỉ normalize ID cho Phần (từ Việt -> số, bỏ La Mã)
            # Còn lại giữ nguyên, chỉ replace dấu chấm thành gạch dưới nếu có
            if normalized_type == 'phan':
                normalized_id = normalize_id(raw_id, only_vietnamese=True)
            else:
                normalized_id = raw_id.replace('.', '_') if '.' in raw_id else raw_id
            
            return {
                "type": normalized_type,
                "id_raw": normalized_id,
                "content": line
            }

    return None

def chunk_text_approx(text, max_tokens=1000):
    """
    Hàm chia nhỏ văn bản (chunking) nhưng vẫn giữ trọn vẹn câu.
    """
    sentences = text.split('. ')
    chunks = []
    current_chunk = []
    current_len = 0

    for sentence in sentences:
        sentence_len = len(sentence.split())
        if current_len + sentence_len > max_tokens and current_chunk:
            chunks.append(". ".join(current_chunk) + ("." if not current_chunk[-1].endswith(".") else ""))
            current_chunk = [sentence]
            current_len = sentence_len
        else:
            current_chunk.append(sentence)
            current_len += sentence_len

    if current_chunk:
        chunks.append(". ".join(current_chunk))

    return chunks

def extract_refs(text, current_dieu_id=None):
    """
    Hàm bắt tham chiếu chéo - improved to capture multiple khoản before one Điều.
    - current_dieu_id: ID của Điều hiện tại (để giải quyết trường hợp "Điều này")
    
    Handles cases like: "khoản 1 và khoản 2 Điều 3" → captures both khoan_1 and khoan_2 with dieu_3
    """
    if not text:
        return []
    
    refs = []
    
    # Strategy: Find all "Điều N" or "Điều này", then for each one, look backward
    # to find all Khoản/Điểm mentioned before it
    
    # Pattern to find Điều references
    dieu_pattern = r'(?i)điều\s+(\d+[a-zđ]?|này)'
    dieu_matches = [(m.group(1), m.start(), m.end()) for m in re.finditer(dieu_pattern, text)]
    
    for dieu_value, dieu_start, dieu_end in dieu_matches:
        # Determine the Điều ID
        if dieu_value.lower() == 'này':
            if not current_dieu_id:
                continue
            dieu_ref_id = current_dieu_id
        else:
            dieu_ref_id = f"dieu_{dieu_value.lower()}"
        
        # Look backward from this Điều to find preceding Khoản/Điểm
        # Search in the text before this Điều
        preceding_text = text[:dieu_start]
        
        # Find all Khoản in preceding text (non-greedy, should be close to Điều)
        # Look for patterns like "khoản 1" or "khoản 2" or "khoản 1.1"
        khoan_pattern = r'(?i)khoản\s+([a-zđ0-9\.]+)'
        khoan_matches_all = list(re.finditer(khoan_pattern, preceding_text))
        
        # Get the khoản mentions that are likely part of this reference
        # (closest ones before the Điều - within ~200 chars is a heuristic)
        recent_khoans = []
        if khoan_matches_all:
            # Look at recent khoản mentions (within the last part of preceding_text)
            search_start = max(0, dieu_start - 300)  # Search within 300 chars before Điều
            search_text = text[search_start:dieu_start]
            
            for m in re.finditer(khoan_pattern, search_text):
                khoan_num = m.group(1)
                recent_khoans.append(khoan_num)
        
        
        # Check for Điểm before the Điều
        diem_pattern = r'(?i)điểm\s+([a-zđ0-9\.]+)'
        diem_matches = list(re.finditer(diem_pattern, text[:dieu_start]))
        
        recent_diems = []
        if diem_matches:
            # Get the most recent Điểm
            search_start = max(0, dieu_start - 300)
            search_text = text[search_start:dieu_start]
            
            for m in re.finditer(diem_pattern, search_text):
                diem_num = m.group(1)
                recent_diems.append(diem_num)
        
        # Create references - prefer most specific level
        if recent_khoans and recent_diems:
            # If there are BOTH Khoán and Điểm, only add most specific (khoan+diem)
            for khoan in recent_khoans:
                for diem in recent_diems:
                    safe_khoan = khoan.replace('.', '_').lower()
                    safe_diem = diem.replace('.', '_').lower()
                    ref_id = f"{dieu_ref_id}.khoan_{safe_khoan}.diem_{safe_diem}"
                    if ref_id not in refs:
                        refs.append(ref_id)
        elif recent_khoans:
            # Only Khoán, add khoan references
            for khoan in recent_khoans:
                safe_khoan = khoan.replace('.', '_').lower()
                ref_id = f"{dieu_ref_id}.khoan_{safe_khoan}"
                if ref_id not in refs:
                    refs.append(ref_id)
        elif recent_diems:
            # Only Điểm without Khoán
            for diem in recent_diems:
                safe_diem = diem.replace('.', '_').lower()
                ref_id = f"{dieu_ref_id}.diem_{safe_diem}"
                if ref_id not in refs:
                    refs.append(ref_id)
        
        # If no Khoán/Điểm found before, just add the Điều reference
        if not recent_khoans and not (diem_matches and recent_diems):
            if dieu_ref_id not in refs:
                refs.append(dieu_ref_id)
    
    # If no Điều found, try the old pattern for backward compatibility
    if not refs:
        pattern = r'(?i)(?:điểm\s+([a-zđ0-9\.]+)\s+)?(?:khoản\s+([a-zđ0-9\.]+)\s+)?điều\s+(\d+[a-zđ]?|này)'
        matches = re.findall(pattern, text)
        
        for diem, khoan, dieu in matches:
            
            # 1. Xử lý cấp ĐIỀU
            if dieu.lower() == 'này':
                if current_dieu_id:
                    ref_id = current_dieu_id
                else:
                    continue
            else:
                ref_id = f"dieu_{dieu.lower()}"
                
            # 2. Xử lý cấp KHOẢN
            if khoan:
                safe_khoan = khoan.replace('.', '_').lower()
                ref_id += f".khoan_{safe_khoan}"
                
            # 3. Xử lý cấp ĐIỂM
            if diem:
                safe_diem = diem.replace('.', '_').lower()
                ref_id += f".diem_{safe_diem}"
                
            # Tránh trùng lặp ID
            if ref_id not in refs:
                refs.append(ref_id)
            
    return refs

def build_json_tree(text):
    """
    Hàm phân tích văn bản luật thành cấu trúc cây JSON:
    Mở đầu > Phần > Chương > Mục > Điều > Khoản > Điểm
    
    NOTE: Removed aggressive preprocessing that added newlines before headings.
    This caused false positives when heading references appeared mid-sentence.
    Instead, trust parse_heading() with its strict pattern matching.
    """
    # Simple split: keep existing newlines from source document
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    tree = []
    
    # === PHASE 1: Parse các dòng và xác định loại ===
    parsed_lines = []
    for line in lines:
        parsed = parse_heading(line)
        if parsed:
            parsed_lines.append(('heading', parsed['type'], parsed['id_raw'], line))
        else:
            parsed_lines.append(('text', None, None, line))
    
    # === PHASE 2: Scan lần đầu lấy Mở đầu ===
    mo_dau_lines = []
    i = 0
    while i < len(parsed_lines) and parsed_lines[i][0] != 'heading':
        mo_dau_lines.append(parsed_lines[i][3])
        i += 1
    
    if mo_dau_lines:
        mo_dau_text = ". ".join(mo_dau_lines)
        chunks = chunk_text_approx(mo_dau_text, max_tokens=1000)
        for idx, chunk in enumerate(chunks, 1):
            tree.append({
                "id": f"modau_{idx}",
                "loai": "mo_dau",
                "noi_dung": chunk,
                "ref": extract_refs(chunk, current_dieu_id=None)
            })
    
    # === PHASE 3: Scan từng Phần hoặc Điều trực tiếp ===
    while i < len(parsed_lines):
        ptype, pid, praw, pline = parsed_lines[i]
        
        # === Case 1: Xử lý Phần ===
        if ptype == 'heading' and pid == 'phan':
            phan_id = f"phan_{praw}"
            i += 1
            phan_con = []
            phan_tieu_de = ""
            phan_content = []
            
            # Try to capture tiêu đề for Phần (next non-heading text line)
            if i < len(parsed_lines) and parsed_lines[i][0] == 'text':
                phan_tieu_de = parsed_lines[i][3]
                i += 1
            
            # === PHASE 3.1: Scan Chương/Mục/Điều trong Phần ===
            while i < len(parsed_lines):
                dtype, did, draw, dline = parsed_lines[i]
                
                # Nếu gặp Phần khác, thoát
                if dtype == 'heading' and did == 'phan':
                    break
                
                # Nếu là Chương
                if dtype == 'heading' and did == 'chuong':
                    chuong_id = f"{phan_id}.chuong_{draw}"
                    i += 1
                    chuong_con = []
                    chuong_tieu_de = ""
                    chuong_content = []
                    
                    # Try to capture tiêu đề (next non-heading text line)
                    if i < len(parsed_lines) and parsed_lines[i][0] == 'text':
                        chuong_tieu_de = parsed_lines[i][3]
                        i += 1
                    
                    # === PHASE 3.1.1: Scan Mục/Điều trong Chương ===
                    while i < len(parsed_lines):
                        etype, eid, eraw, eline = parsed_lines[i]
                        
                        # Nếu gặp level cao hơn, thoát
                        if etype == 'heading' and eid in ['phan', 'chuong']:
                            break
                        
                        # Nếu là Mục
                        if etype == 'heading' and eid == 'muc':
                            muc_id = f"{chuong_id}.muc_{eraw}"
                            i += 1
                            muc_con = []
                            muc_tieu_de = ""
                            muc_content = []
                            
                            # Try to capture tiêu đề for Mục
                            if i < len(parsed_lines) and parsed_lines[i][0] == 'text':
                                muc_tieu_de = parsed_lines[i][3]
                                i += 1
                            
                            # Scan Điều trong Mục
                            while i < len(parsed_lines):
                                ftype, fid, fraw, fline = parsed_lines[i]
                                
                                # Nếu gặp level cao hơn, thoát
                                if ftype == 'heading' and fid in ['phan', 'chuong', 'muc']:
                                    break
                                
                                # Nếu là Điều
                                if ftype == 'heading' and fid == 'dieu':
                                    dieu_node = _extract_dieu(parsed_lines, i, f"{muc_id}.dieu_{fraw}")
                                    muc_con.append(dieu_node)
                                    i = dieu_node['_end_idx']
                                else:
                                    if ftype == 'text':
                                        muc_content.append(fline)
                                    i += 1
                            
                            # Build Mục node
                            muc_node = {
                                'id': muc_id,
                                'loai': 'muc',
                                'tieu_de': muc_tieu_de,
                                'noi_dung': ". ".join(muc_content),
                                'ref': extract_refs(". ".join(muc_content), None),
                                'con': muc_con
                            }
                            # Remove empty tieu_de if not needed
                            if not muc_node['tieu_de']:
                                muc_node.pop('tieu_de')
                            if not muc_node['con']:
                                muc_node.pop('con')
                            chuong_con.append(muc_node)
                        
                        # Nếu là Điều trực tiếp trong Chương
                        elif etype == 'heading' and eid == 'dieu':
                            dieu_node = _extract_dieu(parsed_lines, i, f"{chuong_id}.dieu_{eraw}")
                            chuong_con.append(dieu_node)
                            i = dieu_node['_end_idx']
                        
                        else:
                            if etype == 'text':
                                chuong_content.append(eline)
                            i += 1
                    
                    # Build Chương node
                    chuong_node = {
                        'id': chuong_id,
                        'loai': 'chuong',
                        'tieu_de': chuong_tieu_de,
                        'noi_dung': ". ".join(chuong_content),
                        'ref': extract_refs(". ".join(chuong_content), None),
                        'con': chuong_con
                    }
                    # Remove empty tieu_de if not needed
                    if not chuong_node['tieu_de']:
                        chuong_node.pop('tieu_de')
                    if not chuong_node['con']:
                        chuong_node.pop('con')
                    phan_con.append(chuong_node)
                
                # Nếu là Mục trực tiếp trong Phần
                elif dtype == 'heading' and did == 'muc':
                    muc_id = f"{phan_id}.muc_{draw}"
                    i += 1
                    muc_con = []
                    muc_tieu_de = ""
                    muc_content = []
                    
                    # Try to capture tiêu đề for Mục
                    if i < len(parsed_lines) and parsed_lines[i][0] == 'text':
                        muc_tieu_de = parsed_lines[i][3]
                        i += 1
                    
                    # Scan Điều trong Mục
                    while i < len(parsed_lines):
                        ftype, fid, fraw, fline = parsed_lines[i]
                        
                        if ftype == 'heading' and fid in ['phan', 'chuong', 'muc']:
                            break
                        
                        if ftype == 'heading' and fid == 'dieu':
                            dieu_node = _extract_dieu(parsed_lines, i, f"{muc_id}.dieu_{fraw}")
                            muc_con.append(dieu_node)
                            i = dieu_node['_end_idx']
                        else:
                            if ftype == 'text':
                                muc_content.append(fline)
                            i += 1
                    
                    muc_node = {
                        'id': muc_id,
                        'loai': 'muc',
                        'tieu_de': muc_tieu_de,
                        'noi_dung': ". ".join(muc_content),
                        'ref': extract_refs(". ".join(muc_content), None),
                        'con': muc_con
                    }
                    # Remove empty tieu_de if not needed
                    if not muc_node['tieu_de']:
                        muc_node.pop('tieu_de')
                    if not muc_node['con']:
                        muc_node.pop('con')
                    phan_con.append(muc_node)
                
                # Nếu là Điều trực tiếp trong Phần (CASE 2 MỚI: xử lý Điều không có Phần)
                elif dtype == 'heading' and did == 'dieu':
                    dieu_node = _extract_dieu(parsed_lines, i, f"{phan_id}.dieu_{draw}")
                    phan_con.append(dieu_node)
                    i = dieu_node['_end_idx']
                
                # Else: skip các dòng khác
                else:
                    if dtype == 'text':
                        phan_content.append(dline)
                    i += 1
            
            # Build Phần node
            phan_node = {
                'id': phan_id,
                'loai': 'phan',
                'tieu_de': phan_tieu_de,
                'noi_dung': ". ".join(phan_content),
                'ref': extract_refs(". ".join(phan_content), None),
                'con': phan_con
            }
            # Remove empty tieu_de if not needed
            if not phan_node['tieu_de']:
                phan_node.pop('tieu_de')
            if not phan_node['con']:
                phan_node.pop('con')
            tree.append(phan_node)
        
        # === Case 2: Xử lý Điều trực tiếp (không có Phần) ===
        elif ptype == 'heading' and pid == 'dieu':
            dieu_node = _extract_dieu(parsed_lines, i, f"dieu_{praw}")
            tree.append(dieu_node)
            i = dieu_node['_end_idx']
        
        # === Case 3: Skip các dòng khác ===
        else:
            i += 1
    
    # Clean up _end_idx from all nodes
    def cleanup_end_idx(nodes):
        for node in nodes:
            node.pop('_end_idx', None)
            if 'con' in node:
                cleanup_end_idx(node['con'])
    
    cleanup_end_idx(tree)
    return tree


def _extract_dieu(parsed_lines, start_idx, dieu_id):
    """
    Extract Điều node từ parsed_lines, bắt đầu từ start_idx
    Return node với _end_idx để biết vị trí kế tiếp
    
    Khoản types: 'khoan', 'so_cap_3', 'so_cap_2', 'so_cap_1'
    Điểm types: 'diem', 'chu_thuong'
    """
    _, _, dieu_id_raw, dieu_line = parsed_lines[start_idx]
    
    i = start_idx + 1
    dieu_content = []
    dieu_con = []  # Chứa Khoản có thể có Điểm con
    khoan_types = {'khoan', 'so_cap_3', 'so_cap_2', 'so_cap_1'}
    diem_types = {'diem', 'chu_thuong'}
    
    khoan_pattern = None
    diem_pattern = None
    current_khoan = None
    current_diem = None
    
    # Scan nội dung Điều
    while i < len(parsed_lines):
        ptype, pid, praw, pline = parsed_lines[i]
        
        # Nếu gặp heading cấp cao, thoát
        if ptype == 'heading' and pid in ['phan', 'chuong', 'muc', 'dieu']:
            break
        
        # Nếu là text
        if ptype == 'text':
            if current_diem is not None:
                current_diem['lines'].append(pline)
            elif current_khoan is not None:
                current_khoan['lines'].append(pline)
            else:
                dieu_content.append(pline)
            i += 1
            continue
        
        # Nếu là heading (Khoản hoặc Điểm)
        if ptype == 'heading' and pid not in ['phan', 'chuong', 'muc', 'dieu']:
            # Xác định đây là Khoản hay Điểm
            is_khoan = pid in khoan_types
            is_diem = pid in diem_types
            
            if is_khoan:
                # Xác định pattern Khoản nếu chưa có
                if khoan_pattern is None:
                    khoan_pattern = pid
                
                # Nếu đúng pattern Khoản
                if pid == khoan_pattern:
                    # Finalize Điểm cũ
                    if current_diem is not None:
                        diem_text = ". ".join(current_diem['lines'])
                        current_diem['noi_dung'] = diem_text
                        current_diem['ref'] = extract_refs(diem_text, dieu_id)
                        del current_diem['lines']
                        current_khoan['con'].append(current_diem)
                        current_diem = None
                    
                    # Finalize Khoản cũ
                    if current_khoan is not None:
                        khoan_text = ". ".join(current_khoan['lines'])
                        current_khoan['noi_dung'] = khoan_text
                        current_khoan['ref'] = extract_refs(khoan_text, dieu_id)
                        del current_khoan['lines']
                        if not current_khoan['con']:
                            del current_khoan['con']
                        dieu_con.append(current_khoan)
                    
                    # Tạo Khoản mới
                    current_khoan = {
                        'id': f"{dieu_id}.khoan_{praw}",
                        'loai': 'khoan',
                        'lines': [pline],
                        'con': []
                    }
                else:
                    # Pattern khác, coi như text
                    if current_diem is not None:
                        current_diem['lines'].append(pline)
                    elif current_khoan is not None:
                        current_khoan['lines'].append(pline)
                    else:
                        dieu_content.append(pline)
            
            elif is_diem:
                # Xác định pattern Điểm nếu chưa có
                if diem_pattern is None:
                    diem_pattern = pid
                
                # Nếu đúng pattern Điểm
                if pid == diem_pattern:
                    # Finalize Điểm cũ
                    if current_diem is not None:
                        diem_text = ". ".join(current_diem['lines'])
                        current_diem['noi_dung'] = diem_text
                        current_diem['ref'] = extract_refs(diem_text, dieu_id)
                        del current_diem['lines']
                        if current_khoan is not None:
                            current_khoan['con'].append(current_diem)
                        else:
                            dieu_con.append(current_diem)
                    
                    # Tạo Điểm mới
                    parent_id = current_khoan['id'] if current_khoan is not None else dieu_id
                    current_diem = {
                        'id': f"{parent_id}.diem_{praw}",
                        'loai': 'diem',
                        'lines': [pline]
                    }
                else:
                    # Pattern khác, coi như text
                    if current_diem is not None:
                        current_diem['lines'].append(pline)
                    elif current_khoan is not None:
                        current_khoan['lines'].append(pline)
                    else:
                        dieu_content.append(pline)
            else:
                # Không phải Khoản/Điểm, coi như text
                if current_diem is not None:
                    current_diem['lines'].append(pline)
                elif current_khoan is not None:
                    current_khoan['lines'].append(pline)
                else:
                    dieu_content.append(pline)
        
        i += 1
    
    # Finalize các item cuối
    if current_diem is not None:
        diem_text = ". ".join(current_diem['lines'])
        current_diem['noi_dung'] = diem_text
        current_diem['ref'] = extract_refs(diem_text, dieu_id)
        del current_diem['lines']
        if current_khoan is not None:
            current_khoan['con'].append(current_diem)
        else:
            dieu_con.append(current_diem)
    
    if current_khoan is not None:
        khoan_text = ". ".join(current_khoan['lines'])
        current_khoan['noi_dung'] = khoan_text
        current_khoan['ref'] = extract_refs(khoan_text, dieu_id)
        del current_khoan['lines']
        if not current_khoan['con']:
            del current_khoan['con']
        dieu_con.append(current_khoan)
    
    # Build Điều node
    dieu_noi_dung = ". ".join(dieu_content)
    dieu_node = {
        'id': dieu_id,
        'loai': 'dieu',
        'tieu_de': dieu_line.split(None, 1)[1] if len(dieu_line.split(None, 1)) > 1 else '',
        'noi_dung': dieu_noi_dung,
        'ref': extract_refs(dieu_noi_dung, dieu_id)
    }
    
    if dieu_con:
        dieu_node['con'] = dieu_con
    
    # Thêm _end_idx để xác định vị trí kế tiếp (internal use)
    dieu_node['_end_idx'] = i
    
    return dieu_node

# from src.core.ingestion.extractor import extract_file

# test
# if __name__ == "__main__":
#     # file_path = Path("D:/PTIT/BTL/NLP/data/test.pdf")
#     file_path = Path("D:\\PTIT\\BTL\\NLP\\.temp\\Bộ-luật-45-2019-QH14.docx")
#     text = extract_file(file_path)
#     tree = build_json_tree(text)
#     with open("output_tree.json", "w", encoding="utf-8") as f:
#         json.dump(tree, f, ensure_ascii=False, indent=2)