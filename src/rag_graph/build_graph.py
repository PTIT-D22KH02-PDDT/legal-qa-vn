from . import LLMLocal
import json
import time
import os
import uuid
import concurrent.futures


# API_KEY = "AIzaSyCXjzk_i30IBk5BJVybfmuH1P7h-VGSo5E"

# Chi trich xuat cac muc dieu (dieu co san full_text chua khoan + diem roi)
ALLOWED_CHUNK_TYPES = {"dieu"}

# Cache for entity extraction guide
_EXTRACTION_GUIDE_CACHE = None

def load_extraction_guide():
    """Load entity extraction guide từ file."""
    global _EXTRACTION_GUIDE_CACHE
    if _EXTRACTION_GUIDE_CACHE is not None:
        return _EXTRACTION_GUIDE_CACHE
    
    guide_path = os.path.join(os.path.dirname(__file__), "../../configs/prompts/entity_extraction_guide.txt")
    try:
        with open(guide_path, 'r', encoding='utf-8') as f:
            _EXTRACTION_GUIDE_CACHE = f.read()
        return _EXTRACTION_GUIDE_CACHE
    except FileNotFoundError:
        print(f"⚠️  Warning: Entity extraction guide not found at {guide_path}")
        return ""

def process_single_chunk_task(chunk, model):
    """Hàm wrapper để chạy đa luồng cho 1 chunk"""
    chunk_content = extract_chunk_text(chunk)
    if not chunk_content:
        return chunk, "SKIPPED_EMPTY"
    full_prompt = build_prompt_for_single_chunk(chunk_content)

    extracted_item = call_gemini_with_retry(model, full_prompt)

    if extracted_item in ["QUOTA_EXCEEDED", None]:
        return chunk, extracted_item  # Trả về lỗi

    extracted_item = normalize_graph_json(extracted_item)
    if not validate_graph_schema(extracted_item):
        return chunk, None

    chunk_uuid = get_chunk_uuid(chunk)
    extracted_item = deduplicate_graph_data(extracted_item)
    extracted_item = validate_and_clean_graph_data(extracted_item, chunk_uuid)

    extracted_item["metadata"] = chunk.get("metadata", {})
    extracted_item["metadata"]["chunk_uuid"] = chunk_uuid
    extracted_item["original_content"] = chunk_content

    return chunk, extracted_item

# 2. PROMPT HỆ THỐNG DÀNH CHO 1 CHUNK (KIẾN TRÚC 3 TẦNG)
def build_prompt_for_single_chunk(chunk_content):
    """Tạo Prompt trích xuất Đồ thị Tri thức Phân tầng với Chain-of-Thought."""
    extraction_guide = load_extraction_guide()
    
    return f"""Bạn là một Chuyên gia xây dựng Đồ thị Tri thức (Knowledge Graph) phân tầng cho hệ thống Pháp luật Việt Nam.

[NHIỆM VỤ]
Trích xuất các Thực thể (Entities) và Quan hệ (Edges) từ đoạn luật dưới đây, phân loại vào 3 tầng và trả về JSON.

[QUY TẮC CỐT LÕI]
1. Trường 'value' PHẢI GIỮ NGUYÊN VĂN từ văn bản, không tóm tắt
2. Trường 'name' rút gọn gọi tên cho entity (dùng tìm kiếm vector)
3. Các ID (e1, e2, e3...) phải DUY NHẤT và không trùng lặp
4. Mỗi entity PHẢI CÓ: "id", "label", "name", "value" - KHÔNG ĐƯỢC THIẾU
5. Mỗi relationship PHẢI CÓ: "source", "type", "target" - KHÔNG ĐƯỢC THIẾU
6. Chỉ nối relationship tới entity thực tế tồn tại (KHÔNG dangling edges)
7. MONEY_AMOUNT PHẢI CÓ min, max (số nguyên VND)
8. Chỉ dùng label và relationship type trong danh sách cho phép
9. Không trích xuất ngoài nội dung văn bản

[DANH SÁCH LABEL CHO PHÉP - XEM HƯỚNG DẪN CHI TIẾT BÊN DƯỚI]

{extraction_guide}

[CHAIN-OF-THOUGHT TRƯỚC KHI OUTPUT JSON]
Trước khi trả JSON, suy nghĩ theo thứ tự:
1. Văn bản nói về CHỦTHỂ nào? (SUBJECT) - TRÍCH TẤT CẢ
2. Chủ thể có QUYỀN/NGHĨA VỤ gì? (RIGHT_OBLIGATION)
3. Có VI PHẠM/BỊ CẤM nào? (VIOLATION, PROHIBITED_EXCLUDED)
4. Vi phạm có HẶI QUẢ gì? (PENALTY_MEASURE, MONEY_AMOUNT, TIME_DURATION)
5. Có KHÁI NIỆM/ĐIỀU KIỆN nào? (LEGAL_CONCEPT, DEFINITION, STANDARD_CONDITION)
6. Có THỦTỤC hay HÀNH ĐỘNG nào? (PROCEDURE_ACTION)
7. Có TÀI LIỆU hay QUYẾT ĐỊNH nào bị sửa/bãi bỏ? (DOCUMENT_RECORD, AMENDS, REPEALS)
8. Các quan hệ giữa chúng là gì? (Dùng bảng LƯỢC ĐỒ QUAN HỆ từ hướng dẫn)

⚠️  CẢNH BÁO: Không sử dụng format sai như {{"ENTITY": "...", "LABEL": "..."}} hoặc {{"ENTITY_1": "...", "RELATIONSHIP": "..."}}

Văn bản luật:
\"\"\"{chunk_content}\"\"\"

TRẢ VỀ JSON (duy nhất 1 khối JSON):
"""


# 3. CÁC HÀM QUẢN LÝ TIẾN ĐỘ & XỬ LÝ DỮ LIỆU
def validate_and_clean_graph_data(extracted_json, chunk_uuid):
    """Máy lọc rác: Xử lý ID trùng lặp, Node Ma, và Ép kiểu dữ liệu"""

    # Tập hợp các ID hợp lệ
    valid_ids = set()

    # Đổi tên ID thành Global ID (Tránh ghi đè) và Xử lý Min/Max
    for category in ["Level_3_Foundations", "Level_2_Rules_Actions", "Attributes_Measures"]:
        for entity in extracted_json.get(category, []):
            old_id = entity.get("id", "")

            # Gắn UUID của chunk vào trước ID để đảm bảo tính duy nhất
            new_id = f"{chunk_uuid}_{old_id}"
            entity["id"] = new_id
            valid_ids.add(new_id)

            # Ép kiểu dữ liệu Min/Max cho MONEY_AMOUNT
            if entity.get("label") == "MONEY_AMOUNT":
                for key in ["min", "max"]:
                    if key in entity:
                        try:
                            # Xóa các ký tự không phải số nếu LLM lỡ tay thêm vào (vd: "2000000 VND")
                            clean_num = ''.join(filter(str.isdigit, str(entity[key])))
                            entity[key] = int(clean_num) if clean_num else 0
                        except:
                            entity[key] = 0

    # Lọc bỏ các Quan hệ "Ma" (Dangling Edges)
    cleaned_relationships = []
    for rel in extracted_json.get("Relationships", []):
        # Cập nhật ID nguồn và đích thành Global ID
        rel["source"] = f"{chunk_uuid}_{rel.get('source', '')}"
        rel["target"] = f"{chunk_uuid}_{rel.get('target', '')}"

        # Chỉ giữ lại quan hệ nếu cả source và target đều TỒN TẠI trong danh sách valid_ids
        if rel["source"] in valid_ids and rel["target"] in valid_ids:
            cleaned_relationships.append(rel)
        else:
            print(f"   ⚠️ Đã lọc bỏ quan hệ lỗi (Thực thể ma): {rel}")

    extracted_json["Relationships"] = cleaned_relationships

    return extracted_json


def extract_chunk_text(chunk):
    """Lấy nội dung phù hợp để trích xuất thực thể từ chunk.
    
    Chỉ lấy chunk 'dieu', sử dụng parent_context + full_text (vì full_text của dieu
    đã chứa sẵn khoan + diem con của nó, tránh trích xuất lặp).
    """
    chunk_type = (chunk.get("type") or "").strip().lower()
    if chunk_type and chunk_type not in ALLOWED_CHUNK_TYPES:
        return ""

    parent_context = chunk.get("parent_context") or ""
    full_text = chunk.get("full_text") or ""

    # Ưu tiên: parent_context + full_text
    if full_text.strip():
        if parent_context.strip():
            combined = f"{parent_context}\n{full_text}"
        else:
            combined = full_text
        return normalize_chunk_text(combined)

    # Fallback nếu không có full_text
    if parent_context.strip():
        return normalize_chunk_text(parent_context)

    return ""


def get_chunk_uuid(chunk):
    """Lay chunk_uuid on dinh tu metadata hoac id."""
    metadata_uuid = chunk.get("metadata", {}).get("chunk_uuid")
    if metadata_uuid:
        return metadata_uuid
    chunk_id = chunk.get("id")
    if chunk_id:
        return str(chunk_id).replace("/", "_")
    return uuid.uuid4().hex


def normalize_chunk_text(text):
    """Làm sạch lỗi OCR và ký tự escape phổ biến trước khi đưa vào prompt."""
    cleaned = text.replace("\\)", ")").replace("\\(", "(")
    cleaned = cleaned.replace("..", ".")
    cleaned = cleaned.replace(";. ", ". ")
    cleaned = cleaned.replace(";.", ".")
    return cleaned.strip()


def normalize_graph_json(extracted_json):
    """Chuẩn hóa khung JSON để tránh lỗi thiếu key hoặc sai kiểu dữ liệu."""
    if not isinstance(extracted_json, dict):
        return {
            "Level_3_Foundations": [],
            "Level_2_Rules_Actions": [],
            "Attributes_Measures": [],
            "Relationships": []
        }

    normalized = {
        "Level_3_Foundations": extracted_json.get("Level_3_Foundations", []),
        "Level_2_Rules_Actions": extracted_json.get("Level_2_Rules_Actions", []),
        "Attributes_Measures": extracted_json.get("Attributes_Measures", []),
        "Relationships": extracted_json.get("Relationships", [])
    }

    for key in ["Level_3_Foundations", "Level_2_Rules_Actions", "Attributes_Measures", "Relationships"]:
        if not isinstance(normalized[key], list):
            normalized[key] = []

    return normalized


def validate_graph_schema(extracted_json):
    """Kiểm tra schema tối thiểu để tránh lỗi dữ liệu trước khi xử lý tiếp."""
    if not isinstance(extracted_json, dict):
        return False

    entity_keys = {"id", "label", "name", "value"}
    relationship_keys = {"source", "type", "target"}

    for category in ["Level_3_Foundations", "Level_2_Rules_Actions", "Attributes_Measures"]:
        for entity in extracted_json.get(category, []):
            if not isinstance(entity, dict):
                return False
            if not entity_keys.issubset(entity.keys()):
                return False

    for rel in extracted_json.get("Relationships", []):
        if not isinstance(rel, dict):
            return False
        if not relationship_keys.issubset(rel.keys()):
            return False

    return True


def deduplicate_graph_data(extracted_json):
    """Loại bỏ entity trùng lặp trong cùng 1 chunk để giảm nhiễu."""
    for category in ["Level_3_Foundations", "Level_2_Rules_Actions", "Attributes_Measures"]:
        seen = set()
        unique_entities = []
        for entity in extracted_json.get(category, []):
            label = str(entity.get("label", "")).strip().lower()
            name = str(entity.get("name", "")).strip().lower()
            value = str(entity.get("value", "")).strip().lower()
            signature = (label, name, value)
            if signature in seen:
                continue
            seen.add(signature)
            unique_entities.append(entity)
        extracted_json[category] = unique_entities

    seen_rel = set()
    unique_rels = []
    for rel in extracted_json.get("Relationships", []):
        signature = (
            str(rel.get("source", "")).strip(),
            str(rel.get("type", "")).strip(),
            str(rel.get("target", "")).strip()
        )
        if signature in seen_rel:
            continue
        seen_rel.add(signature)
        unique_rels.append(rel)
    extracted_json["Relationships"] = unique_rels

    return extracted_json


def get_processed_chunks(progress_file):
    if not os.path.exists(progress_file):
        return 0
    with open(progress_file, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        return int(content) if content.isdigit() else 0


def save_processed_count(progress_file, count):
    with open(progress_file, 'w', encoding='utf-8') as f:
        f.write(str(count))


def call_gemini_with_retry(model, full_prompt):
    """Gọi LLM xử lý 1 chunk duy nhất."""
    retries = 0
    max_retries = 3

    while retries < max_retries:
        try:
            response_text = call_model_for_text(model, full_prompt)
            extracted_item = safe_json_loads(response_text)
            return extracted_item

        except json.decoder.JSONDecodeError:
            print("   [!] Lỗi JSON Decode. Đang tự động thử lại...")
            retries += 1
            time.sleep(5)
        except Exception as e:
            error_msg = str(e).lower()
            if "504" in error_msg or "deadline" in error_msg or "timeout" in error_msg:
                print("   [!] Lỗi 504 Deadline Exceeded. Thử lại sau 10s...")
                retries += 1
                time.sleep(10)
            elif "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                print(f"   [!] API Key ĐÃ HẾT HẠN MỨC TRONG NGÀY.")
                return "QUOTA_EXCEEDED"
            else:
                print(f"   [!] Lỗi API: {e}. Thử lại sau 5s...")
                retries += 1
                time.sleep(5)

    return None


def call_model_for_text(model, prompt):
    """Gọi model và trả về text phản hồi để dùng chung cho nhiều backend."""
    if hasattr(model, "generate"):
        return model.generate(prompt)
    if hasattr(model, "generate_content"):
        response = model.generate_content(prompt)
        return response.text
    if hasattr(model, "invoke"):
        response = model.invoke(prompt)
        return getattr(response, "content", str(response))
    raise RuntimeError("Model không hỗ trợ generate_content hoặc invoke")


def safe_json_loads(text):
    try:
        return json.loads(text)
    except json.decoder.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


# 4. HÀM XỬ LÝ 1 FILE (TỪNG CHUNK 1)
def run_graph_pipeline(input_file, folder_save_output, max_workers=1):
    os.makedirs(folder_save_output, exist_ok=True)

    base_name, _ = os.path.splitext(os.path.basename(input_file))
    name_out_file = f"{base_name}_graph_3level.jsonl"
    output_file = os.path.join(folder_save_output, name_out_file)
    progress_file = os.path.join(folder_save_output, f"{base_name}_progress.txt")

    model = LLMLocal()

    if not os.path.exists(input_file):
        print(f"Lỗi: Không tìm thấy file {input_file}")
        return "ERROR"

    all_chunks = load_chunks(input_file)
    
    # Filter: Chỉ lấy chunks có type trong ALLOWED_CHUNK_TYPES
    filtered_chunks = [c for c in all_chunks if (c.get("type") or "").strip().lower() in ALLOWED_CHUNK_TYPES]

    total_chunks = len(filtered_chunks)
    processed_chunks = get_processed_chunks(progress_file)

    if processed_chunks >= total_chunks:
        return "COMPLETED"

    print(f"\nĐang xử lý file: {os.path.basename(input_file)} | Tiến độ: {processed_chunks}/{total_chunks} chunks.")

    # Cắt danh sách chunk thành các mảng nhỏ để chạy đa luồng (ví dụ 1 chunk 1 lúc với max_workers=1)
    remaining_chunks = filtered_chunks[processed_chunks:]
    chunk_batches = [remaining_chunks[i:i + max_workers] for i in range(0, len(remaining_chunks), max_workers)]

    with open(output_file, "a", encoding="utf-8") as f_out:
        for batch_idx, batch in enumerate(chunk_batches):
            print(f" Đang xử lý batch {batch_idx + 1}/{len(chunk_batches)} (gồm {len(batch)} chunks)...")

            batch_count = 0
            # Khởi tạo Đa luồng
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Bắn các chunk trong batch lên API cùng 1 lúc
                future_to_chunk = {executor.submit(process_single_chunk_task, chunk, model): chunk for chunk in batch}

                for future in concurrent.futures.as_completed(future_to_chunk):
                    original_chunk, extracted_item = future.result()
                    
                    # Xử lý kết quả và save ngay lập tức (không chờ batch xong)
                    if extracted_item == "QUOTA_EXCEEDED":
                        return "QUOTA_EXCEEDED"
                    elif extracted_item == "SKIPPED_EMPTY":
                        continue
                    elif extracted_item is None:
                        print(f"   Có Chunk bị sập liên tục. Chuyển file...")
                        return "CRASHED"

                    # Ghi kết quả thành công vào file NGAY LẬP TỨC
                    f_out.write(json.dumps(extracted_item, ensure_ascii=False) + "\n")
                    f_out.flush()  # Flush ngay để đảm bảo data được lưu
                    batch_count += 1
                    
                    if batch_count % 10 == 0:  # Progress mỗi 10 chunks
                        processed_chunks += batch_count
                        save_processed_count(progress_file, processed_chunks)
                        batch_count = 0

            # Lưu Checkpoint sau khi xong batch
            if batch_count > 0:
                processed_chunks += batch_count
                save_processed_count(progress_file, processed_chunks)

            # Thời gian nghỉ giữa các batch để tránh API Rate Limit (Lỗi 429)
            time.sleep(3)

    return "COMPLETED"


def load_chunks(input_file):
    """Đọc input dạng JSON array, JSON object với 'chunks' key, hoặc JSONL."""
    with open(input_file, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            # Nếu là array, return trực tiếp
            if isinstance(data, list):
                return data
            # Nếu là dict có 'chunks' key, return chunks
            if isinstance(data, dict) and "chunks" in data:
                chunks = data["chunks"]
                return chunks if isinstance(chunks, list) else []
            return []
        except json.JSONDecodeError:
            # Fallback: Đọc từng dòng như JSONL
            f.seek(0)
            chunks = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                chunks.append(json.loads(line))
            return chunks




# 5. HÀM DUYỆT THƯ MỤC
def run_call(folder_input, folder_output):
    os.makedirs(folder_output, exist_ok=True)
    error_log_path = os.path.join(folder_output, "error_log.txt")

    files = [
        f for f in os.listdir(folder_input)
        if f.endswith('.json') or f.endswith('.jsonl')
    ]

    if not files:
        print(f"Không tìm thấy file .json nào trong {folder_input}")
        return

    print(f"BẮT ĐẦU TRÍCH XUẤT GRAPHRAG (3-LEVEL) CHO {len(files)} FILE...")

    for file in files:
        input_path = os.path.join(folder_input, file)

        while True:
            # Không cần truyền num_chunk_per_batch nữa
            status = run_graph_pipeline(
                input_file=input_path,
                folder_save_output=folder_output
            )

            if status == "COMPLETED":
                print(f"\nTHÀNH CÔNG: Đã xuất xong Đồ thị (Graph) cho file {file}!")
                break
            elif status == "CRASHED":
                print(f"\nPHÁT HIỆN CRASH! Đang ghi log và cho Google API nghỉ 60s...")
                time.sleep(60)
            elif status == "QUOTA_EXCEEDED":
                print("\nBÁO ĐỘNG ĐỎ: ĐÃ HẾT HẠN MỨC API TRONG NGÀY!")
                return

    print("\nCHÚC MỪNG! ĐÃ TRÍCH XUẤT XONG TOÀN BỘ KNOWLEDGE GRAPH PHÂN TẦNG!")


# 6. KHỞI CHẠY
if __name__ == "__main__":
    FOLDER_INPUT = "chunk"
    FOLDER_OUTPUT = "outputs"
    os.makedirs(FOLDER_OUTPUT, exist_ok=True)

    run_call(
        folder_input=FOLDER_INPUT,
        folder_output=FOLDER_OUTPUT
    )