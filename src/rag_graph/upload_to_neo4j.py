import json
import re
from neo4j import GraphDatabase
from config import *


class Neo4jUploader:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        # Danh sách các Nhãn (Labels) chuẩn của Kiến trúc 3 Tầng
        self.entity_labels = [
            "SUBJECT", "LEGAL_CONCEPT", "DEFINITION", "RIGHT_OBLIGATION",
            "PROHIBITED_EXCLUDED", "VIOLATION", "PENALTY_MEASURE",
            "PROCEDURE_ACTION", "STANDARD_CONDITION", "MONEY_AMOUNT",
            "POINT_DEDUCTION", "OBJECT_EQUIPMENT", "DOCUMENT_RECORD",
            "PHYSICAL_DOCUMENT", "TIME_DURATION", "PERCENTAGE", "TEXT_SEGMENT"
        ]

    def close(self):
        self.driver.close()

    def create_schema_templates(self):
        """Tạo Khuôn mẫu (Constraints & Indexes) trước khi nạp data để tăng tốc MERGE và chống trùng"""
        print("⏳ ĐANG TẠO SCHEMA TEMPLATES (CONSTRAINTS & INDEXES)...")
        with self.driver.session() as session:
            # 1. Template cho trục Xương sống (Document Hierarchy)
            hierarchy_labels = ["Document", "Article", "Clause", "Point", "Chunk"]
            for label in hierarchy_labels:
                query = f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                session.run(query)

            # 2. Template cho các Thực thể Pháp lý
            # 🟢 SỬA CHUẨN 3 TẦNG: Dùng id_name (Tên viết thường) làm khóa chống trùng
            for label in self.entity_labels:
                query = f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id_name IS UNIQUE"
                session.run(query)

            # 3. Tạo Full-text Index cho Content của Chunk (Phục vụ Hybrid Search sau này)
            try:
                session.run("""
                    CREATE FULLTEXT INDEX chunk_content_index IF NOT EXISTS 
                    FOR (c:Chunk) ON EACH [c.content]
                """)
                print("✅ Đã tạo Full-text Index.")
            except Exception as e:
                print(f"Lưu ý: Không tạo được Full-text index: {e}")

            # 4. TẠO VECTOR INDEX (Mục lục siêu tốc cho Embedding)
            try:
                session.run("""
                    CREATE VECTOR INDEX chunk_vector_index IF NOT EXISTS
                    FOR (c:Chunk) ON (c.embedding)
                    OPTIONS {indexConfig: {
                     `vector.dimensions`: 1024, 
                     `vector.similarity_function`: 'cosine'
                    }}
                """)
                print("✅ Đã tạo Vector Index (chunk_vector_index).")
            except Exception as e:
                print(f"Lưu ý: Không tạo được Vector index: {e}")

        print("✅ TẠO TEMPLATES THÀNH CÔNG! SẴN SÀNG NẠP DATA.")

    def upload_data(self, jsonl_file):
        # Chạy hàm tạo khuôn mẫu trước
        self.create_schema_templates()

        print(f"🚀 ĐANG NẠP DỮ LIỆU TỪ: {jsonl_file}")
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line_idx, line in enumerate(f):
                line = line.strip()
                if not line: continue

                chunk = json.loads(line)
                with self.driver.session() as session:
                    session.execute_write(self._process_chunk, chunk, line_idx)

        print("✅ ĐÃ NẠP THÀNH CÔNG LÊN NEO4J!")

    def _process_chunk(self, tx, chunk, chunk_index):
        meta = chunk.get("metadata", {})
        doc_id = meta.get("document", "Văn bản không xác định").strip()
        dieu = str(meta.get("dieu", "")).strip()
        khoan = str(meta.get("khoan", "")).strip()
        diem = str(meta.get("diem", "")).strip()

        # 🟢 SỬA CHUẨN: Ưu tiên lấy original_content (văn bản thô đã được làm sạch)
        chunk_content = chunk.get("original_content", chunk.get("content", "")).strip()

        # Bỏ qua nếu dòng này không có nội dung chữ
        if not chunk_content: return

        # ==========================================
        # 1. XÂY DỰNG CẤU TRÚC CÂY (DOCUMENT HIERARCHY)
        # ==========================================
        year_match = re.search(r'(19|20)\d{2}', doc_id)
        extracted_year = int(year_match.group()) if year_match else 0
        extracted_type = meta.get("type", "LEGAL_RULE")

        tx.run("""
                    MERGE (d:Document {id: toLower($doc_id)})
                    ON CREATE SET d.name = $doc_id, d.type = $doc_type, d.year = $doc_year
                """,
               doc_id=doc_id, doc_type=extracted_type, doc_year=extracted_year)

        lowest_parent_label = "Document"
        lowest_parent_id = doc_id.lower()
        readable_path = doc_id

        if dieu and dieu.lower() != "none":
            dieu_name = f"Điều {dieu} của {doc_id}"
            readable_path = f"Điều {dieu} - {doc_id}"
            tx.run("""
                MERGE (child:Article {id: toLower($child_name)})
                ON CREATE SET child.name = $child_name
                WITH child MATCH (parent:Document {id: $parent_id})
                MERGE (parent)-[:HAS_ARTICLE]->(child)
            """, child_name=dieu_name, parent_id=lowest_parent_id)
            lowest_parent_label = "Article"
            lowest_parent_id = dieu_name.lower()

            if khoan and khoan.lower() != "none":
                khoan_name = f"Khoản {khoan} {dieu_name}"
                readable_path = f"Khoản {khoan} {readable_path}"
                tx.run("""
                    MERGE (child:Clause {id: toLower($child_name)})
                    ON CREATE SET child.name = $child_name
                    WITH child MATCH (parent:Article {id: $parent_id})
                    MERGE (parent)-[:HAS_CLAUSE]->(child)
                """, child_name=khoan_name, parent_id=lowest_parent_id)
                lowest_parent_label = "Clause"
                lowest_parent_id = khoan_name.lower()

                if diem and diem.lower() != "none":
                    diem_name = f"Điểm {diem} {khoan_name}"
                    readable_path = f"Điểm {diem} {readable_path}"
                    tx.run("""
                        MERGE (child:Point {id: toLower($child_name)})
                        ON CREATE SET child.name = $child_name
                        WITH child MATCH (parent:Clause {id: $parent_id})
                        MERGE (parent)-[:HAS_POINT]->(child)
                    """, child_name=diem_name, parent_id=lowest_parent_id)
                    lowest_parent_label = "Point"
                    lowest_parent_id = diem_name.lower()

        # ==========================================
        # 🚨 TẠO ID CHUNK ĐỘC NHẤT & LƯU SIÊU METADATA SẠCH
        # ==========================================
        doc_name_clean = doc_id.replace(" ", "_").replace("/", "_").replace("-", "_")

        # 🟢 Ưu tiên dùng chunk_uuid sinh ra từ file AI, nếu không có mới tự nối chuỗi
        chunk_node_id = meta.get("chunk_uuid", f"chunk_{doc_name_clean}_{chunk.get('chunk_id', chunk_index)}")

        tx.run(f"""
            MERGE (c:Chunk {{id: $chunk_id}})
            SET c.content = $content, 
                c.metadata_document = $doc_id,
                c.metadata_dieu = $dieu_meta,
                c.metadata_khoan = $khoan_meta,
                c.metadata_diem = $diem_meta,
                c.name = $readable_path
            WITH c MATCH (p:{lowest_parent_label} {{id: $parent_id}})
            MERGE (p)-[:HAS_CHUNK]->(c)
        """,
               chunk_id=chunk_node_id,
               content=chunk_content,
               parent_id=lowest_parent_id,
               doc_id=doc_id,
               dieu_meta=f"Điều {dieu}" if dieu and dieu.lower() != "none" else "",
               khoan_meta=f"Khoản {khoan}" if khoan and khoan.lower() != "none" else "",
               diem_meta=f"Điểm {diem}" if diem and diem.lower() != "none" else "",
               readable_path=f"[{readable_path}]"
               )

        # ==========================================
        # 2. TẠO THỰC THỂ (ENTITIES) 3 TẦNG
        # ==========================================
        # 🟢 Gộp cả 3 tầng lại để xử lý chung
        all_entities = (
                chunk.get("Level_3_Foundations", []) +
                chunk.get("Level_2_Rules_Actions", []) +
                chunk.get("Attributes_Measures", [])
        )

        id_mapping = {}

        for ent in all_entities:
            label = ent.get("label", "UNKNOWN").strip()
            if label not in self.entity_labels:
                # print(f"⚠️ AI sinh nhãn lỗi: '{label}' -> Đã ép về 'UNKNOWN'")
                label = "UNKNOWN"

            name = ent.get("name", "").strip()
            value = ent.get("value", "").strip()
            ent_id = ent.get("id")

            # Nếu AI quên sinh name, mượn value đắp vào
            if not name: name = value
            safe_name = name if len(name) <= 1000 else name[:1000]
            # 🟢 Dùng Tên viết thường làm Khóa gộp chung (Global Key) thay cho MD5
            global_key = safe_name.lower()
            id_mapping[ent_id] = {"label": label, "global_key": global_key}

            # Lấy min/max cho mức phạt tiền
            min_val = ent.get("min", 0) if isinstance(ent.get("min"), int) else 0
            max_val = ent.get("max", 0) if isinstance(ent.get("max"), int) else 0

            # 🟢 Tạo Thực thể và nối vào Chunk
            tx.run(f"""
                MERGE (e:`{label}` {{id_name: $global_key}})
                ON CREATE SET e.name = $name, e.value = $value, e.min = $min_val, e.max = $max_val
                WITH e MATCH (c:Chunk {{id: $chunk_id}})
                MERGE (e)-[:MENTIONED_IN]->(c)
            """,
                   global_key=global_key, name=name, value=value,
                   min_val=min_val, max_val=max_val, chunk_id=chunk_node_id
                   )

        # ==========================================
        # 3. TẠO QUAN HỆ (RELATIONSHIPS) CHÉO
        # ==========================================
        # 🟢 Sửa thành mảng Relationships
        for rel in chunk.get("Relationships", []):
            s_id = rel.get("source")
            t_id = rel.get("target")
            rel_type = rel.get("type", "RELATED_TO").upper().replace(" ", "_")

            if s_id in id_mapping and t_id in id_mapping:
                s_data = id_mapping[s_id]
                t_data = id_mapping[t_id]

                tx.run(f"""
                    MATCH (s:{s_data['label']} {{id_name: $s_val}})
                    MATCH (t:{t_data['label']} {{id_name: $t_val}})
                    MERGE (s)-[:{rel_type}]->(t)
                """, s_val=s_data['global_key'], t_val=t_data['global_key'])