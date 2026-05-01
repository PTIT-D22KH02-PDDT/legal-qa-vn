import os
import sys
import json
import re
import time

sys.path.insert(0, '.')
from src.rag_graph.llm_local import LLMLocal
from src.rag_graph.build_graph import build_prompt_for_single_chunk

# Initialize LLM
llm = LLMLocal()

# Điều 1 text
dieu_1_text = """Phần thứ nhất : QUY ĐỊNH CHUNG
Chương I : NHỮNG QUY ĐỊNH CHUNG
Điều 1. Phạm vi điều chỉnh. Bộ luật này quy định địa vị pháp lý, chuẩn mực pháp lý về cách ứng xử của cá nhân, pháp nhân; quyền, nghĩa vụ về nhân thân và tài sản của cá nhân, pháp nhân trong các quan hệ được hình thành trên cơ sở bình đẳng, tự do ý chí, độc lập về tài sản và tự chịu trách nhiệm (sau đây gọi chung là quan hệ dân sự)."""

# Use the actual prompt from build_graph.py
prompt = build_prompt_for_single_chunk(dieu_1_text)

print("📝 PROMPT ĐƯỢC GỬI ĐI (UPDATED):")
print("=" * 80)
print(prompt[:500] + "...\n")

print("📞 CALLING LLM WITH UPDATED PROMPT...")
print("=" * 80)

try:
    # Call LLM (with timeout awareness)
    start_time = time.time()
    print(f"⏱️  LLM Call Started at {time.strftime('%H:%M:%S')}")
    response = llm.generate(prompt)
    elapsed = time.time() - start_time
    print(f"✅ LLM Responded in {elapsed:.1f}s\n")

    print("✅ RAW RESPONSE FROM LLM:")
    print("=" * 80)
    print(response[:2000])  # Print first 2000 chars
    print("..." if len(response) > 2000 else "")
    print("=" * 80)

    # Try to extract JSON - use simple method instead of complex regex
    start_json = response.find('{')
    end_json = response.rfind('}')
    
    if start_json != -1 and end_json != -1 and end_json > start_json:
        json_str = response[start_json:end_json + 1]
        try:
            parsed = json.loads(json_str)
            print("\n✅ PARSED & FORMATTED JSON:")
            print("=" * 80)
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
            
            # Check if entities were extracted
            total_entities = (
                len(parsed.get("Level_3_Foundations", [])) +
                len(parsed.get("Level_2_Rules_Actions", [])) +
                len(parsed.get("Attributes_Measures", []))
            )
            print(f"\n📊 EXTRACTION SUMMARY:")
            print(f"   - Level_3_Foundations: {len(parsed.get('Level_3_Foundations', []))}")
            print(f"   - Level_2_Rules_Actions: {len(parsed.get('Level_2_Rules_Actions', []))}")
            print(f"   - Attributes_Measures: {len(parsed.get('Attributes_Measures', []))}")
            print(f"   - Total Entities: {total_entities}")
            print(f"   - Relationships: {len(parsed.get('Relationships', []))}")
            
            if total_entities > 1:
                print("\n✅ SUCCESS! LLM extracted multiple entities!")
                print("   Prompt improvement IS WORKING! 🎉")
            elif total_entities == 1:
                print("\n⚠️  PARTIAL SUCCESS: Only 1 entity extracted (should be 5-6)")
                print("   Need further prompt refinement")
            else:
                print("\n❌ FAILED: No entities extracted")
                
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON Parse Error: {e}")
            print(f"   Attempted to parse: {json_str[:200]}...")
    else:
        print("\n❌ NO VALID JSON FOUND IN RESPONSE")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
