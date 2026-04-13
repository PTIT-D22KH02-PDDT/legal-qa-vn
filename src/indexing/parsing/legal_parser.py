import re
import unicodedata
from .constants import VIETNAMESE_NUM_MAP, ROMAN_NUM_MAP

class ParseLegal:
    def __init__(self,max_tokens=1000):
        self.max_tokens = max_tokens
        self.vietnamese_num_map=VIETNAMESE_NUM_MAP
        self.roman_num_map=ROMAN_NUM_MAP

    def normalize_id(self,raw_id, only_vietnamese=False):
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
        if raw_id_lower in self.vietnamese_num_map:
            return self.vietnamese_num_map[raw_id_lower]

        # Try Roman numeral map (chỉ nếu not only_vietnamese)
        if not only_vietnamese and raw_id_lower in self.roman_num_map:
            return self.roman_num_map[raw_id_lower]

        # Return as-is if no match (e.g., already numeric or other format)
        return raw_id_lower

    def parse_heading(self, line):
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
            ('so_cap_3', r'^(\d+\.\d+\.\d+)[\\\.\)]?\s*(.*)$'),
            ('so_cap_2', r'^(\d+\.\d+)[\\\.\)]?\s*(.*)$'),
            ('so_cap_1', r'^(\d+)[\\\.\)]\s*(.*)$'),

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
                    normalized_id = self.normalize_id(raw_id, only_vietnamese=True)
                else:
                    normalized_id = raw_id.replace('.', '_') if '.' in raw_id else raw_id

                return {
                    "type": normalized_type,
                    "id_raw": normalized_id,
                    "content": line
                }

        return None

    def chunk_text_approx(self,text):
        """
        Hàm chia nhỏ văn bản (chunking) nhưng vẫn giữ nguyên trọn vẹn câu
        :param text:
        :return:
        """
        sentences = text.split(". ")
        chunks = []
        current_chunk = []
        current_len = 0
        for sentence in sentences:
            sentence_len = len(sentence.split())
            if current_len + sentence_len > self.max_tokens and current_chunk:
                chunks.append(". ".join(current_chunk) + ("." if not current_chunk[-1].endswith(".") else ""))
                current_chunk = [sentence]
                current_len = sentence_len
            else:
                current_chunk.append(sentence)
                current_len += sentence_len
        if current_chunk:
            chunks.append(". ".join(current_chunk) + ("." if not current_chunk[-1].endswith(".") else ""))
        return chunks

    def build_json_tree(self, doc_id: str, text:str):
        """
        Hàm phân tích văn bản luật thành cấu trúc cây JSON:
        Mở đầu > Phần > Chương > Mục > Điều > Khoản > Điểm
        """
        lines=[line.strip() for line in text.strip().split("\n") if line.strip()]
        tree=[]
        #Phase 1 : Parse cac dong va xac dinh loai cua cac dong
        """
        -Dong thi co cac loai sau : 
            +heading : type=dieu/khoan/muc/phan/diem (trich xuat tu ham parse_heading)
            +text : noi dung binh thuong
        """
        parsed_lines=[]
        for line in lines:
            parsed=self.parse_heading(line)
            if parsed:
                parsed_lines.append(('heading', parsed['type'], parsed['id_raw'], line))
            else:
                parsed_lines.append(('text', None, None, line))
        #Phase 2 : Scan de trich xuat ra phan mo dau
        mo_dau_lines=[]
        i=0
        while i<len(parsed_lines) and parsed_lines[i][0]!='heading':
            mo_dau_lines.append(parsed_lines[i][3])
            i+=1

        if mo_dau_lines:
            mo_dau_text=". ".join(mo_dau_lines)
            chunks=self.chunk_text_approx(mo_dau_text)
            for idx, chunk in enumerate(chunks, 1):
                node={
                    "type_id": f"{doc_id}.modau_{idx}",
                    "parent_id": doc_id,
                    "type": "mo_dau",
                    "content":chunk,
                    "ref": None
                }
                tree.append(node)
        #Phase 3 : Scan tung Phan hoac tung Dieu, xay cay phan cap
        while i<len(parsed_lines):
            ptype, pid, praw, pline=parsed_lines[i]
            #Xu ly Phan
            if ptype=='heading' and pid=='phan':
                phan_id=f"{doc_id}.phan_{praw}"
                i+=1
                phan_con=[]
                phan_tieu_de=""
                phan_content=[]
                """Xu li phan tieu de cho Phan"""
                if i<len(parsed_lines) and parsed_lines[i][0]=='text':
                    phan_tieu_de=parsed_lines[i][3]
                    i+=1
                '''Phase 3.1 Scan Chuong/Muc/Dieu trong Phan'''
                while i<len(parsed_lines):
                    dtype, did, draw, dline=parsed_lines[i]

                    #Neu gap phan khac , thoat
                    if dtype=='heading' and did=='phan':
                        break
                    if dtype=='heading' and did=='chuong':
                        chuong_id=f"{phan_id}.chuong_{draw}"
                        i+=1
                        chuong_con=[]
                        chuong_tieu_de=""
                        chuong_content=[]
                        #Xu ly tieu de chuong
                        if i<len(parsed_lines) and parsed_lines[i][0]=='text':
                            chuong_tieu_de=parsed_lines[i][3]
                            i+=1
                        #Phase 3.1.1 Scan Muc/Dieu trong chuong
                        while i<len(parsed_lines):
                            etype,eid, eraw, eline=parsed_lines[i]

                            #Neu gap level cao hon , thoat
                            if etype=='heading' and eid in ["phan", "chuong"]:
                                break
                            #Neu la muc
                            if etype=="heading" and eid=='muc':
                                muc_id=f"{chuong_id}.muc_{eraw}"
                                muc_con=[]
                                muc_tieu_de=eline
                                muc_content=[]
                                i+=1

                                #Xu li tieu de cua muc
                                # if i<len(parsed_lines) and parsed_lines[i][0]=='text':
                                #     muc_tieu_de=parsed_lines[i][3]
                                #     i+=1
                                #Scan Dieu trong muc
                                while i<len(parsed_lines):
                                    ftype, fid, fraw, fline=parsed_lines[i]

                                    #Neu gap level cao hown-->thoat
                                    if ftype=='heading' and fid in ['phan', 'chuong', 'muc']:
                                        break
                                    #Neu la dieu
                                    if ftype=='heading' and fid=='dieu':
                                        context={'luat_id':doc_id, 'phan_id':phan_id, 'chuong_id':chuong_id, 'muc_id':muc_id, 'dieu_id':f"{muc_id}.dieu_{fraw}"}
                                        dieu_node=self._extract_dieu(parsed_lines, i, context)
                                        muc_con.append(dieu_node)
                                        i=dieu_node["_end_idx"]
                                    else:
                                        if ftype=="text":
                                            muc_content.append(fline)
                                        i+=1

                                muc_node={
                                    "type_id": muc_id,
                                    "parent_id": chuong_id,
                                    'type': "muc",
                                    "title": muc_tieu_de,
                                    "content": ". ".join(muc_content),
                                    "ref":self.extract_refs(". ".join(muc_content), {'muc_id': muc_id, 'chuong_id': chuong_id, 'phan_id': phan_id}),
                                    "con": muc_con
                                }
                                chuong_con.append(muc_node)


                            #Neu Dieu truc tiep trong Chuong ko co Muc
                            elif etype=="heading" and eid=='dieu':
                                context={'luat_id':doc_id, 'chuong_id':chuong_id, 'phan_id':phan_id, 'dieu_id':f"{chuong_id}.dieu_{eraw}"}
                                dieu_node=self._extract_dieu(parsed_lines, i, context)
                                chuong_con.append(dieu_node)
                                i=dieu_node["_end_idx"]
                            else:
                                if etype=='text':
                                    chuong_content.append(eline)
                                i+=1
                        #Build Chuong node
                        chuong_node={
                            'type_id':chuong_id,
                            'parent_id':phan_id,
                            "type":"chuong",
                            'title': chuong_tieu_de,
                            "content":". ".join(chuong_content),
                            "ref":self.extract_refs(". ".join(chuong_content), {'chuong_id': chuong_id, 'phan_id': phan_id}),
                            "con": chuong_con
                        }
                        phan_con.append(chuong_node)
                    #Neu la Muc truc tiep trong Phan
                    elif dtype=='heading' and did=='muc':
                        muc_id=f"{phan_id}.muc_{draw}"
                        muc_con=[]
                        muc_content=[]
                        muc_tieu_de=dline
                        i+=1

                        # # Try to capture tiêu đề for Mục
                        # if i < len(parsed_lines) and parsed_lines[i][0] == 'text':
                        #     muc_tieu_de = parsed_lines[i][3]
                        #     i += 1

                        #Scan Dieu trong Muc
                        while i<len(parsed_lines):
                            ftype,fid, fraw,fline=parsed_lines[i]
                            if ftype=='heading' and fid in ['phan', 'chuong', 'muc']:
                                break
                            if ftype=='heading' and fid=='dieu':
                                context={'luat_id':doc_id,  'phan_id':phan_id,'muc_id':muc_id, 'dieu_id': f"{muc_id}.dieu_{fraw}"}
                                dieu_node=self._extract_dieu(parsed_lines, i, context)
                                muc_con.append(dieu_node)
                                i=dieu_node['_end_idx']
                            else:
                                if dtype=="text":
                                    muc_content.append(fline)
                                i+=1

                        muc_node={
                            "type_id": muc_id,
                            "parent_id": phan_id,
                            'type': "muc",
                            "title": muc_tieu_de,
                            "content": ". ".join(muc_content),
                            "ref": self.extract_refs(". ".join(muc_content), {'muc_id': muc_id, 'phan_id': phan_id}),
                            "con": muc_con
                        }
                        phan_con.append(muc_node)

                    #Neu Dieu truc tiep trong Phan
                    elif dtype == 'heading' and did == 'dieu':
                        context={'luat_id':doc_id, 'phan_id':phan_id,'dieu_id':f"{phan_id}.dieu_{draw}"}
                        dieu_node = self._extract_dieu(parsed_lines, i, context)
                        phan_con.append(dieu_node)
                        i = dieu_node['_end_idx']

                    else :
                        if dtype=="text":
                            phan_content.append(dline)
                        i+=1

                #Build Phan node
                phan_node={
                    'type_id':phan_id,
                    'parent_id':doc_id,
                    'type':'phan',
                    'title': phan_tieu_de,
                    'content':". ".join(phan_content),
                    'ref':self.extract_refs(". ".join(phan_content), {'luat_id':doc_id, 'phan_id': phan_id}),
                    "con": phan_con
                }
                tree.append(phan_node)
            #Case 2 : Xu ly các van ban ma tu mo dau->chuong->điều.
            elif ptype=='heading' and pid=='chuong':
                chuong_id = f"{doc_id}.chuong_{praw}"
                i += 1
                chuong_con = []
                chuong_tieu_de = ""
                chuong_content = []
                # Xu ly tieu de chuong
                if i < len(parsed_lines) and parsed_lines[i][0] == 'text':
                    chuong_tieu_de = parsed_lines[i][3]
                    i += 1
                # Phase 3.1.1 Scan Muc/Dieu trong chuong
                while i < len(parsed_lines):
                    etype, eid, eraw, eline = parsed_lines[i]

                    # Neu gap level cao hon , thoat
                    if etype == 'heading' and eid in ["phan", "chuong"]:
                        break
                    # Neu la muc
                    if etype == "heading" and eid == 'muc':
                        muc_id = f"{chuong_id}.muc_{eraw}"
                        muc_con = []
                        muc_tieu_de = eline
                        muc_content = []
                        i += 1

                        # Xu li tieu de cua muc
                        # if i<len(parsed_lines) and parsed_lines[i][0]=='text':
                        #     muc_tieu_de=parsed_lines[i][3]
                        #     i+=1
                        # Scan Dieu trong muc
                        while i < len(parsed_lines):
                            ftype, fid, fraw, fline = parsed_lines[i]

                            # Neu gap level cao hown-->thoat
                            if ftype == 'heading' and fid in ['phan', 'chuong', 'muc']:
                                break
                            # Neu la dieu
                            if ftype == 'heading' and fid == 'dieu':
                                context={'luat_id':doc_id, 'chuong_id':chuong_id,'muc_id':muc_id ,'dieu_id':f"{muc_id}.dieu_{fraw}"}
                                dieu_node = self._extract_dieu(parsed_lines, i, context)
                                muc_con.append(dieu_node)
                                i = dieu_node["_end_idx"]
                            else:
                                if ftype == "text":
                                    muc_content.append(fline)
                                i += 1

                        muc_node = {
                            "type_id": muc_id,
                            "parent_id": chuong_id,
                            'type': "muc",
                            "title": muc_tieu_de,
                            "content": ". ".join(muc_content),
                            "ref": self.extract_refs(". ".join(muc_content), {'muc_id': muc_id, 'chuong_id': chuong_id}),
                            "con": muc_con
                        }
                        chuong_con.append(muc_node)


                    # Neu Dieu truc tiep trong Chuong ko co Muc
                    elif etype == "heading" and eid == 'dieu':
                        context = {'luat_id': doc_id, 'chuong_id': chuong_id,'dieu_id': f"{chuong_id}.dieu_{eraw}"}
                        dieu_node = self._extract_dieu(parsed_lines, i, context)
                        chuong_con.append(dieu_node)
                        i = dieu_node["_end_idx"]
                    else:
                        if etype == 'text':
                            chuong_content.append(eline)
                        i += 1
                # Build Chuong node
                chuong_node = {
                    'type_id': chuong_id,
                    'parent_id': doc_id,
                    "type": "chuong",
                    'title': chuong_tieu_de,
                    "content": ". ".join(chuong_content),
                    "ref": self.extract_refs(". ".join(chuong_content), {'luat_id':doc_id, 'chuong_id': chuong_id}),
                    "con": chuong_con
                }
                tree.append(chuong_node)
            #Case 3 : Xu ly cac van ban nhu thong tu, nghi dinh, truc tiep vao Dieu luon khong co Phan/Chuong
            elif ptype=='heading' and pid=='dieu':
                context={'luat_id':doc_id , 'dieu_id':f"{doc_id}.dieu_{praw}"}
                dieu_node=self._extract_dieu(parsed_lines, i, context)
                tree.append(dieu_node)
                i=dieu_node['_end_idx']

            #Case 3 : skip cac dong khac
            else :
                i+=1

        #Clean up end_idx from all nodes
        def cleanup_end_idx(nodes):
            for n in nodes:
                if n is not None:
                    n.pop('_end_idx', None)
                    if 'con' in n:
                        cleanup_end_idx(n['con'])

        cleanup_end_idx(tree)
        return tree


    def _extract_dieu(self,parsed_lines, start_idx: int, context: dict):
        """
        Extract Điều node từ parsed_lines, bắt đầu từ start_idx
        Return node với _end_idx để biết vị trí kế tiếp

        Khoản types: 'khoan', 'so_cap_3', 'so_cap_2', 'so_cap_1'
        Điểm types: 'diem', 'chu_thuong'
        """
        dieu_id=context["dieu_id"]
        _,_, dieu_id_raw, dieu_line=parsed_lines[start_idx]
        i=start_idx+1
        dieu_content=[]
        dieu_full_text=[]
        dieu_con=[] #Chua khoan co the co Diem con
        khoan_type={'khoan','so_cap_3', 'so_cap_2', 'so_cap_1'}
        diem_types={'diem', 'chu_thuong'}
        khoan_pattern=None
        diem_pattern=None
        current_khoan=None
        current_diem=None

        #Scan noi dung Dieu
        while i<len(parsed_lines):
            ptype, pid, praw, pline=parsed_lines[i]
            #Neu gap heading cap cao hon-->thoat
            if ptype=='heading' and pid in ['phan', 'chuong', 'muc', 'dieu']:
                break
            #Neu la text
            if ptype=='text':
                if current_diem is not None:
                    current_diem['lines'].append(pline)
                elif current_khoan is not None:
                    current_khoan['lines'].append(pline)
                else :
                    dieu_content.append(pline)
                dieu_full_text.append(pline)
                i+=1
                continue

            #Neu la Khoan hoac Diem
            if ptype=='heading' and pid not in ['phan', 'chuong', 'muc', 'dieu']:
                dieu_full_text.append(pline)
                #Xac dinh day la khoan hay diem
                is_khoan=pid in khoan_type
                is_diem=pid in diem_types
                if is_khoan:
                    #Xac dinh pattern_khoan neu chua co
                    if khoan_pattern is None:
                        khoan_pattern=pid
                    #Neu dung khoan_pattern
                    if pid==khoan_pattern:
                        #Hoan thanh Diem cu o tren
                        if current_diem is not None:
                            diem_text=". ".join(current_diem['lines'])
                            current_diem['content']=diem_text
                            if current_khoan is not None:
                                current_khoan['full_text'].extend(current_diem['lines'])
                                context.update({'khoan_id': current_khoan['type_id']})
                            current_diem['ref']=self.extract_refs(diem_text, context)
                            del current_diem['lines']
                            if current_khoan is not None:
                                current_khoan['con'].append(current_diem)
                            current_diem=None

                        if current_khoan is not None:
                            khoan_text=". ".join(current_khoan['lines'])
                            current_khoan['content']=khoan_text
                            current_khoan['ref']=self.extract_refs(khoan_text, context)
                            current_khoan['full_text']=". ".join(current_khoan['full_text'])
                            del current_khoan['lines']
                            if not current_khoan['con']:
                                del current_khoan['con']
                            dieu_con.append(current_khoan)

                        #Tao Khoan moi
                        current_khoan={
                            'type':'khoan',
                            'type_id': f"{dieu_id}.khoan_{praw}",
                            'parent_id':dieu_id,
                            
                            'lines':[pline],
                            'full_text':[pline],
                            'con':[]
                        }
                    else:
                        #Pattern khac -->coi nhu text
                        if current_diem is not None:
                            current_diem['lines'].append(pline)
                        elif current_khoan is not None:
                            current_khoan['lines'].append(pline)
                            current_khoan['full_text'].append(pline)

                elif is_diem:
                    #Xac dinh pattern Diem neu chua co
                    if diem_pattern is None:
                        diem_pattern=pid

                    #Neu dung pattern Diem
                    if pid==diem_pattern:
                        #Hoan thanh Diem cu
                        if current_diem is not None:
                            diem_text=". ".join(current_diem['lines'])
                            current_diem['content']=diem_text
                            if current_khoan is not None:
                                current_khoan['full_text'].extend(current_diem['lines'])
                                context.update({'khoan_id': current_khoan['type_id']})
                            current_diem['ref']=self.extract_refs(diem_text, context)
                            del current_diem['lines']
                            if current_khoan is not None:
                                current_khoan['con'].append(current_diem)
                            else :
                                dieu_con.append(current_diem)

                        #Tao Diem moi
                        parent_id=current_khoan['type_id'] if current_khoan is not None else dieu_id
                        current_diem={
                            'type':'diem',
                            'type_id': f"{parent_id}.diem_{praw}",
                            'parent_id':parent_id,
                            'lines':[pline]
                        }
                    else :
                        #Pattern khac-->coi nhu text thuong
                        if current_diem is not None:
                            current_diem['lines'].append(pline)
                        elif current_khoan is not None:
                            current_khoan['full_text'].append(pline)
                            current_khoan['lines'].append(pline)
                else:
                    if current_diem is not None:
                        current_diem['lines'].append(pline)
                    elif current_khoan is not None:
                        current_khoan['full_text'].append(pline)
                        current_khoan['lines'].append(pline)

            i+=1

        #Hoan thanh cac item cuoi
        if current_diem is not None:
            diem_text=". ".join(current_diem['lines'])
            current_diem['content']=diem_text
            if current_khoan is not None:
                current_khoan['full_text'].extend(current_diem['lines'])
                context.update({'khoan_id': current_khoan['type_id']})
            current_diem['ref']=self.extract_refs(diem_text, context)
            del current_diem['lines']
            if current_khoan is not None:
                current_khoan['con'].append(current_diem)
            else :
                dieu_con.append(current_diem)
        if current_khoan is not None:
            khoan_text=". ".join(current_khoan['lines'])
            current_khoan['content']=khoan_text
            current_khoan['ref']=self.extract_refs(khoan_text, context)
            current_khoan['full_text']=". ".join(current_khoan['full_text'])
            del current_khoan['lines']
            if not current_khoan['con']:
                del current_khoan['con']
            dieu_con.append(current_khoan)
        #Build Dieu node
        dieu_text=". ".join(dieu_content)
        dieu_node={
            "type": 'dieu',
            'type_id': dieu_id,
            'title': dieu_line,
            'content': dieu_text,
            'full_text': ". ".join(dieu_full_text),
            'ref': self.extract_refs(dieu_text, context)
        }
        if dieu_con is not None:
            dieu_node['con'] = dieu_con

        #Them _end_idx de xac dinh vi tri ke tiep
        dieu_node['_end_idx']=i

        return dieu_node

    #Ham nay giai quyet cac truong hop la : Bo luat/Luat nay, Diem nay/Khoan nay

    def _format_id(self, s: str) -> str:
        # Xử lý Đ/đ riêng — giữ lại dạng thường
        s = s.replace("Đ", "đ")

        # Bỏ dấu các ký tự còn lại (trừ đ)
        # Tách từng ký tự, nếu là đ thì giữ, còn lại normalize bình thường
        result = []
        for ch in s:
            if ch == "đ":
                result.append("đ")
            else:
                normalized = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode("utf-8")
                result.append(normalized)
        s = "".join(result)

        s = s.lower().strip()
        s = re.sub(r"[^a-z0-9đ\-]+", "_", s)  # ← thêm đ vào whitelist
        return s.strip("_")

    def _parse_list_items(self, prefix: str, search_text: str) -> list[str]:
        """Nhặt danh sách ID từ cụm như 'các khoản 1, 2 và 3'.
        
        ID hợp lệ trong văn bản luật VN chỉ là:
        - Chữ cái đơn hoặc đôi: a, b, c, đ, gg
        - Số ngắn: 1, 2, 10, 99
        - Kết hợp số+chữ: 1a, 2b
        - Dạng phân cấp: 1.1, 1.2.3
        Không match từ tiếng Việt thông thường như 'tiền', 'vay', 'trình', 'có'
        """
        items = []

        # ID hợp lệ: tối đa 3 chữ số + tùy chọn 1 chữ cái, HOẶC tối đa 2 chữ cái đơn
        # Có thể theo sau bởi phân cấp dạng .1 .2
        id_regex = r"(?:[0-9]{1,3}[a-zđ]?|[a-zđ]{1,2})(?:\.[0-9]{1,3})*"

        # Lookahead: sau ID phải là dấu câu, khoảng trắng, hoặc hết chuỗi
        # — loại trừ trường hợp ID là phần đầu của một từ dài hơn (vd: "c" trong "có")
        id_with_boundary = rf"(?:{id_regex})(?=\s|,|;|\)|$)"

        pattern = rf"(?i)(?:các\s+)?\b{prefix}\b\s+" \
                rf"({id_with_boundary}(?:\s*,\s*{id_with_boundary})*(?:\s+và\s+{id_with_boundary})?)"

        for m in re.finditer(pattern, search_text):
            raw_str = m.group(1)
            parts = re.split(r"\s*,\s*|\s+và\s+", raw_str)
            for p in parts:
                p = p.strip()
                if p:
                    items.append(p)

        return items

    def _build_luat_position_map(self,text: str, fallback_luat_id: str | None) -> list[tuple[int, str]]:
        """
        Quét toàn bộ câu, tìm tất cả các đề cập đến văn bản luật kèm vị trí ký tự.
        Bỏ qua các cụm tự chỉ thị như "luật này", "bộ luật này".
        Trả về list[(start_pos, luat_id)] đã sắp xếp theo start_pos tăng dần.
        """
        entries: list[tuple[int, str]] = []

        # Loại trừ cụm tự chỉ thị (chúng không định danh văn bản cụ thể)
        SELF_REF_LUAT = re.compile(
            r"(?i)\b(?:bộ\s+luật|luật|nghị\s+định|thông\s+tư|quyết\s+định|pháp\s+lệnh)\s+này\b"
        )
        self_ref_spans = {m.span() for m in re.finditer(SELF_REF_LUAT, text)}

        def _in_self_ref(start: int) -> bool:
            return any(s <= start < e for s, e in self_ref_spans)

        # Pattern 1: có số hiệu kiểu "số 45/2019/QH14"
        # Giới hạn .{0,60}? để tránh kéo sang câu khác
        doc_num_pattern = (
            r"(?i)(?:lệnh|luật|bộ\s+luật|nghị\s+quyết|nghị\s+định"
            r"|thông\s+tư|quyết\s+định)\s+.{0,60}?(?:số\s+)?([0-9]+/[0-9a-zđ/\-]+)"
        )
        #dùng để tránh thêm trùng lặp vào entries
        #Xử lí trường hợp mà như sau : có cả tên luật và số hiệu : Bộ luật Hình sự năm 2015 số 100/2015/QH13
        seen_positions: set[int] = set()
        pos_scan = 0
        while pos_scan < len(text):
            m = re.search(doc_num_pattern, text[pos_scan:])
            if not m:
                break
            abs_start = pos_scan + m.start()
            if _in_self_ref(abs_start):
                # Bỏ qua match này, nhảy qua khoảng self-ref
                pos_scan = abs_start + 1
                continue
            if abs_start not in seen_positions:
                luat_id = self._format_id(m.group(1))
                entries.append((abs_start, luat_id))
                seen_positions.add(abs_start)
            pos_scan = abs_start + len(m.group())

        # Pattern 2: gọi tên theo năm kiểu "Bộ luật Hình sự năm 2015"
        nam_pattern = (
            r"(?i)(bộ\s+luật|luật|nghị\s+định|thông\s+tư|nghị\s+quyết|hiến\s+pháp)\s+"
            r"([A-ZĐÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÉÈẺẼẸÊẾỀỂỄỆa-zđáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệ\s]{2,70}?)"
            r"(?:\s+năm\s+(\d{4}))?"
            r"(?=\s*[,.;]|\s+của|\s+được|\s+có|\s+về|$)"
        )
        for m in re.finditer(nam_pattern, text):
            if _in_self_ref(m.start()):
                continue
            full_name = f"{m.group(1)} {m.group(2)} {m.group(3)}"
            luat_id = self._format_id(full_name)
            already = any(abs(pos - m.start()) < 10 for pos, _ in entries)
            if not already:
                entries.append((m.start(), luat_id))

        entries.sort(key=lambda x: x[0])

        if not entries and fallback_luat_id:
            entries.append((0, fallback_luat_id))

        return entries

    def _assign_luat_id(self,ref_pos: int, luat_map: list[tuple[int, str]], text: str = "") -> str | None:
        """
        Với một tham chiếu tại vị trí `ref_pos`, tìm luật phù hợp nhất.

        Chiến lược kép:
        1. Tìm cụm "của [LuậtX]" hoặc "theo [LuậtX]" gần nhất PHÍA SAU ref
           trong vòng 120 ký tự — đây là dấu hiệu mạnh nhất.
        2. Nếu không có → lấy luật xuất hiện GẦN NHẤT (trước hoặc sau) theo khoảng cách ký tự.
        """
        if not luat_map:
            return None

        #Chiến lược 1: anchor từ "của/theo" ngay sau ref
        # Tìm cụm dẫn xuất kiểu "... Điều 4 của Bộ luật LĐ ..."
        # window: 120 ký tự sau vị trí bắt đầu của ref (đủ để bao cụm "của Luật X số Y")
        WINDOW = 120
        snippet = text[ref_pos: ref_pos + WINDOW] if text else ""

        anchor_pattern = r"(?i)\b(?:của|theo|trong|tại)\s+(?:bộ\s+)?(?:luật|nghị\s+định|thông\s+tư|quyết\s+định)"
        anchor_match = re.search(anchor_pattern, snippet)
        if anchor_match:
            # Vị trí tuyệt đối của anchor trong text
            anchor_abs = ref_pos + anchor_match.start()
            # Tìm luật có start_pos gần nhất VÀ >= anchor_abs
            forward_candidates = [(pos, lid) for pos, lid in luat_map if pos >= anchor_abs]
            if forward_candidates:
                return min(forward_candidates, key=lambda x: x[0])[1]

        # Chiến lược 2: luật gần nhất theo khoảng cách
        return min(luat_map, key=lambda x: abs(x[0] - ref_pos))[1]

    def resolve_self_refs(self,text: str, context: dict) -> list[str]:
        """
                Hàm tổng quát giải mã các cụm tự chỉ thị trong văn bản pháp luật.
                Chuyển đổi các cụm như "khoản này", "điều này", "luật này", "bộ luật này"
                thành ID chuẩn hóa tương ứng với vị trí hiện tại của đoạn văn đó trong cây cấu trúc.

                Args:
                    text (str): Đoạn văn bản cần quét.
                    context (dict): Từ điển chứa các ID ngữ cảnh hiện tại. Các key hợp lệ:
                        - "diem_id"   (str | None): ID của Điểm đang chứa đoạn text, vd "dieu_3.khoan_1.diem_a"
                        - "khoan_id"  (str | None): ID của Khoản đang chứa đoạn text, vd "dieu_3.khoan_1"
                        - "dieu_id"   (str | None): ID của Điều đang chứa đoạn text, vd "dieu_3"
                        - "muc_id"    (str | None): ID của Mục đang chứa, vd "phan_1.chuong_2.muc_1"
                        - "chuong_id" (str | None): ID của Chương đang chứa, vd "phan_1.chuong_2"
                        - "phan_id"   (str | None): ID của Phần đang chứa, vd "phan_1"
                        - "luat_id"   (str | None): ID định danh của toàn bộ văn bản luật, vd "luat_45_2019"

                Returns:
                    list[str]: Danh sách các ID tham chiếu đã được giải mã từ cụm tự chỉ thị.
                               Trả về [] nếu không tìm thấy cụm nào.

                Examples:
                    >>> context = {
                    ...     "diem_id":   "dieu_3.khoan_1.diem_a",
                    ...     "khoan_id":  "dieu_3.khoan_1",
                    ...     "dieu_id":   "dieu_3",
                    ...     "muc_id":    None,
                    ...     "chuong_id": "chuong_2",
                    ...     "phan_id":   "phan_1",
                    ...     "luat_id":   "luat_45_2019",
                    ... }
                    >>> resolve_self_refs("Trừ trường hợp quy định tại khoản này và điều này", context)
                    ['dieu_3.khoan_1', 'dieu_3']
                    >>> resolve_self_refs("Tuân thủ quy định của bộ luật này", context)
                    ['luat_45_2019']
        """
        if not text:
            return []

        refs = []

        SELF_REF_PATTERNS = [
            (r"(?i)(?:(\w+)\s+)?\b(điểm\s+này)\b", "diem_id"),
            (r"(?i)(?:(\w+)\s+)?\b(khoản\s+này)\b", "khoan_id"),
            (r"(?i)(?:(\w+)\s+)?\b(điều\s+này)\b", "dieu_id"),
            (r"(?i)(?:(\w+)\s+)?\b(mục\s+này)\b", "muc_id"),
            (r"(?i)(?:(\w+)\s+)?\b(chương\s+này)\b", "chuong_id"),
            (r"(?i)(?:(\w+)\s+)?\b(phần\s+này)\b", "phan_id"),
            (
                r"(?i)(?:(\w+)\s+)?\b(bộ\s+luật\s+này|luật\s+này|nghị\s+định\s+này"
                r"|thông\s+tư\s+này|quyết\s+định\s+này|pháp\s+lệnh\s+này)\b",
                "luat_id",
            ),
        ]

        EXCLUDED_PREFIXES = {
            "diem_id": {"thời", "địa", "đặc", "ưu", "nhược", "quan", "khuyết", "trọng", "nhiệm", "tiêu", "tâm", "nhận",
                        "giao"},
            "khoan_id": {"điều", "tài"},
            "muc_id": {"danh", "hạng", "thư", "chuyên", "tiết"},
            "phan_id": {"thành", "cổ", "một", "đóng"},
            "dieu_id": set(),
            "chuong_id": set(),
            "luat_id": set(),
        }

        for pattern, context_key in SELF_REF_PATTERNS:
            for match in re.finditer(pattern, text):
                if match.group(1):
                    prev_word = match.group(1).lower()
                    if prev_word in EXCLUDED_PREFIXES.get(context_key, set()):
                        continue
                resolved_id = context.get(context_key)
                if resolved_id and resolved_id not in refs:
                    refs.append(resolved_id)

        return refs

    def extract_refs(self, text: str, context: dict | None = None) -> list[str]:
        if not text:
            return []
        fallback_luat_id = context.get("luat_id") if context else None
        if not fallback_luat_id and context:
            for key in ["diem_id", "khoan_id", "dieu_id", "muc_id", "chuong_id", "phan_id"]:
                full_id = context.get(key)
                if full_id and "." in full_id:
                    fallback_luat_id = full_id.split(".")[0]
                    break

        current_dieu_id = context.get("dieu_id") if context else None
        current_khoan_id = context.get("khoan_id") if context else None

        luat_map = self._build_luat_position_map(text, fallback_luat_id)
        refs_with_pos: list[tuple[str, int]] = []

        #1. Dải Điều
        for m in re.finditer(r"(?i)từ\s+(?:các\s+)?điều\s+(\d+)\s+đến\s+(?:điều\s+)?(\d+)", text):
            try:
                s, e = int(m.group(1)), int(m.group(2))
                if s <= e < s + 500:
                    for idx in range(s, e + 1):
                        refs_with_pos.append((f"dieu_{idx}", m.start()))
            except ValueError:
                pass

        #1.1 Dải Khoản
        for m in re.finditer(
                r"(?i)từ\s+(?:các\s+)?khoản\s+(\d+)\s+đến\s+(?:khoản\s+)?(\d+)\s+điều\s+(\d+[a-zđ]?)", text
        ):
            try:
                s, e = int(m.group(1)), int(m.group(2))
                dieu_raw = m.group(3).lower()
                if s <= e < s + 100:
                    for idx in range(s, e + 1):
                        refs_with_pos.append((f"dieu_{dieu_raw}.khoan_{idx}", m.start()))
            except ValueError:
                pass

        #2. Chương / Mục
        for m in re.finditer(r"(?i)chương\s+([ivxlcdm]+|\d+)", text):
            refs_with_pos.append((f"chuong_{m.group(1).lower()}", m.start()))

        for m in re.finditer(r"(?i)mục\s+([a-zđ0-9\.]+)\s+(?:của\s+)?chương\s+([ivxlcdm]+|\d+)", text):
            refs_with_pos.append((f"chuong_{m.group(2).lower()}.muc_{m.group(1).lower()}", m.start()))

        #3. Điều + Khoản/Điểm (bao gồm cả "Điều này")
        # Quy tắc gán pos:
        #   pos >= 0 : ref thường → gắn luat theo vị trí
        #   pos == -2: "Điều X luật này" → gắn fallback_luat_id
        #   pos == -1: self-ref đã có full path → giữ nguyên (dùng ở bước 4)
        #
        SELF_REF_LUAT_NEAR = re.compile(
            r"(?i)^\s*(?:của\s+)?(?:bộ\s+luật|luật|nghị\s+định|thông\s+tư)\s+này\b"
        )

        dieu_pattern = r"(?i)điều\s+(\d+[a-zđ]?|này)"
        dieu_matches = [(m.group(1), m.start(), m.end()) for m in re.finditer(dieu_pattern, text)]
        prev_dieu_end = 0

        for dieu_value, dieu_start, dieu_end in dieu_matches:
            after_snippet = text[dieu_end: dieu_end + 60]
            is_self_luat = bool(SELF_REF_LUAT_NEAR.match(after_snippet))

            if dieu_value.lower() == "này":
                if not current_dieu_id:
                    prev_dieu_end = dieu_end
                    continue
                dieu_ref_id = current_dieu_id  # đã là full path: "luat_dan_su.dieu_123"
            else:
                dieu_ref_id = f"dieu_{dieu_value.lower()}"

            search_text = text[max(prev_dieu_end, dieu_start - 300): dieu_start]
            recent_khoans = self._parse_list_items("khoản", search_text)
            recent_diems = self._parse_list_items("điểm", search_text)
            effective_pos = -2 if is_self_luat else dieu_start

            if recent_khoans and recent_diems:
                for k in recent_khoans:
                    for d in recent_diems:
                        refs_with_pos.append((
                            f"{dieu_ref_id}.khoan_{k.replace('.', '_')}.diem_{d.replace('.', '_')}",
                            effective_pos
                        ))
            elif recent_khoans:
                for k in recent_khoans:
                    refs_with_pos.append((f"{dieu_ref_id}.khoan_{k.replace('.', '_')}", effective_pos))
            elif recent_diems:
                for d in recent_diems:
                    refs_with_pos.append((f"{dieu_ref_id}.diem_{d.replace('.', '_')}", effective_pos))
            else:
                refs_with_pos.append((dieu_ref_id, effective_pos))

            prev_dieu_end = dieu_end

        #3.5 Không có "Điều" trong câu — xử lý "khoản này / điểm này"
        # VD: "Theo điểm a,b và c khoản này"
        if not dieu_matches and context:
            all_khoans = self._parse_list_items("khoản", text)
            all_diems = self._parse_list_items("điểm", text)

            has_khoan_nay = bool(re.search(r"(?i)khoản\s+này", text))
            has_diem_nay = bool(re.search(r"(?i)điểm\s+này", text))

            # Base ref: ưu tiên khoan_nay > dieu_id
            base_khoan = current_khoan_id if has_khoan_nay else None
            base_dieu = current_dieu_id

            if all_diems and base_khoan:
                # "điểm a,b,c khoản này" → gắn vào khoan hiện tại
                for d in all_diems:
                    refs_with_pos.append((f"{base_khoan}.diem_{d}", -1))
            elif all_diems and base_dieu:
                # "điểm a,b,c" không có khoản cụ thể → gắn vào điều hiện tại
                for d in all_diems:
                    refs_with_pos.append((f"{base_dieu}.diem_{d}", -1))
            elif all_khoans and base_dieu:
                # "khoản 1,2,3" không có điều → gắn vào điều hiện tại
                for k in all_khoans:
                    refs_with_pos.append((f"{base_dieu}.khoan_{k}", -1))
            elif has_khoan_nay and base_khoan:
                # Chỉ "khoản này" đơn thuần, không có danh sách
                refs_with_pos.append((base_khoan, -1))
            elif has_diem_nay and base_dieu:
                # Chỉ "điểm này" đơn thuần
                diem_id = context.get("diem_id")
                if diem_id:
                    refs_with_pos.append((diem_id, -1))

        #4. Self-refs cấp cao (mục/chương/phần/luật)
        # CHỈ xử lý: mục này, chương này, phần này, luật này
        # KHÔNG xử lý: điều này, khoản này, điểm này (đã xử lý ở bước 3/3.5)
        #
        if context:
            HIGH_LEVEL_SELF_REFS = [
                (r"(?i)(?:(\w+)\s+)?\b(mục\s+này)\b", "muc_id"),
                (r"(?i)(?:(\w+)\s+)?\b(chương\s+này)\b", "chuong_id"),
                (r"(?i)(?:(\w+)\s+)?\b(phần\s+này)\b", "phan_id"),
                (
                    r"(?i)(?:(\w+)\s+)?\b(bộ\s+luật\s+này|luật\s+này|nghị\s+định\s+này"
                    r"|thông\s+tư\s+này|quyết\s+định\s+này|pháp\s+lệnh\s+này)\b",
                    "luat_id",
                ),
            ]
            EXCLUDED_PREFIXES = {
                "muc_id": {"danh", "hạng", "thư", "chuyên", "tiết"},
                "phan_id": {"thành", "cổ", "một", "đóng"},
                "chuong_id": set(),
                "luat_id": set(),
            }
            PRECEDED_BY_DIEU = re.compile(r"(?i)điều\s+\d+[a-zđ]?\s*")
            for pattern, ctx_key in HIGH_LEVEL_SELF_REFS:
                for match in re.finditer(pattern, text):
                    if match.group(1):
                        if match.group(1).lower() in EXCLUDED_PREFIXES.get(ctx_key, set()):
                            continue

                     # THÊM: nếu là luat_id, kiểm tra xem có "Điều X" ngay trước không
                    if ctx_key == "luat_id":
                        before_snippet = text[max(0, match.start() - 80): match.start()]
                        if PRECEDED_BY_DIEU.search(before_snippet):
                                continue  # Đã được bước 3 xử lý rồi, bỏ qua

                    resolved = context.get(ctx_key)
                    if not resolved:
                        continue
                    full_ref = (
                        f"{fallback_luat_id}.{resolved}"
                        if fallback_luat_id and not resolved.startswith(fallback_luat_id)
                        else resolved
                    )
                    if (full_ref, -1) not in refs_with_pos:
                        refs_with_pos.append((full_ref, -1))

        #5. Gắn luat_id và deduplicate
        unique_refs= []

        for ref_str, pos in refs_with_pos:
            if not ref_str:
                continue

            if pos == -1:
                # Self-ref: đã có full path
                full_ref = ref_str

            elif pos == -2:
                # "Điều X luật này" → fallback_luat_id
                full_ref = (
                    f"{fallback_luat_id}.{ref_str}"
                    if fallback_luat_id and not ref_str.startswith(fallback_luat_id)
                    else ref_str
                )

            else:
                # Ref thường → gắn luat theo vị trí trong câu
                luat_id = self._assign_luat_id(pos, luat_map, text)
                full_ref = (
                    f"{luat_id}.{ref_str}"
                    if luat_id and not ref_str.startswith(luat_id)
                    else ref_str
                )

            if full_ref and full_ref not in unique_refs:
                unique_refs.append(full_ref)

        return unique_refs