import json
from src.core.chunker.legal_parser import ParseLegal

# Sample legal document text
sample_text = """
LỜI NÓI ĐẦU
Bộ luật này được ban hành nhằm quy định về các vấn đề pháp lý cơ bản.
Nó áp dụng cho tất cả các cá nhân, tổ chức trong nước.

Phần thứ nhất
NHỮNG QUY ĐỊNH CHUNG

Chương I
NHỮNG QUY ĐỊNH CƠ BẢN
Chương này quy định các nguyên tắc cơ bản về luật và trách nhiệm.

Mục 1
ĐỊNH NGHĨA CÁC THUẬT NGỮ
Trong chương này, các thuật ngữ được sử dụng với ý nghĩa sau:

Điều 1
Người là một cá nhân tự nhiên có năng lực hành động.

Khoản 1
Người phải có tuổi đủ 18 để được coi là có đầy đủ năng lực.

1.1
Trường hợp vị thành niên được phép hành động sớm hơn.

Khoản 2
Người bị hạn chế năng lực do bệnh tâm thần phải được bảo vệ.

Điều 2
Tổ chức là một nhóm cá nhân hoặc thực thể pháp lý.

Khoản 1
Tổ chức phải được thành lập theo đúng quy trình pháp lý.

a)
Tổ chức kinh tế được thành lập bằng quyết định của cơ quan nhà nước có thẩm quyền.

b)
Tổ chức phi lợi nhuận được thành lập theo quy định của Luật Hội.

Chương II
CÁC QUYỀN VÀ NGHĨA VỤ
Chương này quy định chi tiết về các quyền và nghĩa vụ.

Điều 3
Mọi người có quyền bình đẳng trước pháp luật.

Mục 2
QUYỀN CƠ BẢN

Điều 4
Mỗi cá nhân có quyền sống, quyền tự do cá nhân.

Khoản 1
Quyền sống được bảo vệ bởi pháp luật từ khi sinh ra.

Phần thứ hai
NHỮNG QUYỀN CÓ LIÊN QUAN ĐẾN TÀI SẢN

Chương III
QUY ĐỊNH VỀ TÀI SẢN VÀ QUYỀN SỬ DỤNG

Điều 5
Tài sản là những vật phẩm, quyền có giá trị của người.

Khoản 1
Tài sản có thể là bất động sản hoặc động sản.

Khoản 2
Bất động sản bao gồm đất đai, nhà cửa, và các công trình xây dựng.
"""

# Create parser
parser = ParseLegal()

# Parse the document
print("=" * 80)
print("TESTING build_json_tree")
print("=" * 80)

tree = parser.build_json_tree(doc_id="luat_test", text=sample_text)

# Pretty print the result
print(json.dumps(tree, indent=2, ensure_ascii=False))

# Optional: Print summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Total top-level nodes: {len(tree)}")
for i, node in enumerate(tree):
    node_type = node.get('type')
    node_id = node.get('type_id')
    print(f"{i+1}. [{node_type}] {node_id}")
    if 'con' in node and node['con']:
        for j, child in enumerate(node['con']):
            child_type = child.get('type')
            child_id = child.get('type_id')
            print(f"   {j+1}. [{child_type}] {child_id}")
