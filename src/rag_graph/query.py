import textwrap
from tabnanny import verbose

from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
from langchain_community.graphs import Neo4jGraph
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
load_dotenv()
import os
from langchain_classic.prompts import PromptTemplate

llm = ChatOpenAI(
    base_url="http://127.0.0.1:1234/v1",  # Lấy từ mục 'Reachable at'
    api_key="lm-studio",                 # Key mặc định cho LM Studio
    model_name="llama-3.2-3b-instruct",  # Lấy chính xác từ 'This model's API identifier'
    temperature=0.1
)

# Load lai graph da tao truoc do
graph=Neo4jGraph(
    url=os.getenv("NEO4J_URI"),
    username=os.getenv("NEO4J_USERNAME"),
    password=os.getenv("NEO4J_PASSWORD"),
    database=os.getenv("NEO4J_DATABASE")
)

# result=graph.query("""MATCH (a)-[r]->(b)
# RETURN a.name AS node_a, r, b.name AS node_b
# """)

# result=graph.query("""
# MATCH (phone) -[: CÓ_CÔNG_NGHỆ_MÀN_HÌNH]->(b)
# WHERE phone.name= 'Nokia 3210' RETURN b.name
# """)
#
# result1=graph.query(
#     """
#     MATCH (phone) -[: CÓ_MÀU_SẮC]->(color)
#     WHERE color.name='Màu Đen' RETURN phone.name
#     """
# )
# print(result1)
CYPHER_GENERATION_TEMPLATE = """Task: Generate a Cypher statement to query a graph database.
Instructions:
- Analyze the question and extract relevant graph components dynamically. Use this to construct the Cypher query.
- Use only the relationship types and properties from the provided schema. Do not include any other relationship types, properties, or assumptions not defined in the schema.
- The schema is based on a graph structure with nodes and relationships as follows:
{schema}
- Return only the generated Cypher query in your response. Do not include explanations, comments, or additional text.
- Ensure the Cypher query directly addresses the given question using the schema accurately.

Examples:
# Thiết bị nào sử dụng công nghệ IPS?
# Dien thoai nao nào sử dụng công nghệ IPS?
MATCH (device)-[:CÓ_CÔNG_NGHỆ]->(techNode)
    WHERE techNode.name = 'IPS'
RETURN device.name

# Dung lượng pin của Nokia 3210 4G là gì?
MATCH (device)-[:CÓ_DUNG_LƯỢNG_PIN]->(batteryCapacity)
    WHERE device.name = 'Nokia 3210 4G'
RETURN batteryCapacity.name

# Mạng di động nào được thiết bị hỗ trợ?
MATCH (device)-[:HỖ_TRỢ_MẠNG]->(networkType)
    WHERE device.name = 'Nokia 3210 4G'
RETURN networkType.name

# Bộ nhớ trong của Nokia 3210 4G là gì?
MATCH (device:Entity)-[:CÓ_BỘ_NHỚ_TRONG]->(memory:Entity)-[:LÀ]->(value:Entity)
    WHERE device.name = 'Nokia 3210 4G'
RETURN value.name

# vivo y03 có ram mấy GB?
MATCH (device)-[:CÓ_RAM]->(ram)
    WHERE device.name = 'vivo y03'
RETURN ram.name

# Cho tôi cấu hình của vivo y03?
MATCH (a:Entity)-[r]-(b)
    WHERE a.name = 'vivo y03' AND type(r) IN ['CÓ_DUNG_LƯỢNG_PIN', 'CÓ_SỐ_KHE_SIM', 'CÓ_RAM', 'CÓ_VI_XỬ_LÝ', 'CÓ_CAMERA_TRƯỚC']
RETURN a AS node_a, r AS relationship, b AS node_b;

# Nói cho tôi biết thông tin về RAM của Honor X7b?
MATCH (device)-[:CÓ_RAM]->(ram)
    WHERE device.name = 'Honor X7b'
RETURN ram.name

# điện thoại poco c65 pin là bao nhiêu?
MATCH (phone)-[:CÓ_DUNG_LƯỢNG_PIN]->(bateryCapaciy)
    WHERE phone.name = 'điện thoại poco c65'
RETURN bateryCapaciy.name

# Samsung Galaxy S23 FE 5G pin thế nào nhỉ?
MATCH (phone)-[:CÓ_DUNG_LƯỢNG_PIN]->(bateryCapaciy)
    WHERE phone.name = 'Samsung Galaxy S23 FE 5G'
RETURN bateryCapaciy.name


# Những điện thoại có cùng màu đen với điện thoại poco c65?
MATCH (start1)-[:CÓ_MÀU_SẮC]->(sharedNode)<-[:CÓ_MÀU_SẮC]-(targetDevice)
    WHERE phone.name = 'điện thoại poco c65' AND sharedNode.name = 'Màu Đen'
RETURN targetDevice.name

The question is:
{question}
"""
cypher_prompt = PromptTemplate(
    input_variables=["schema", "question"],
    template=CYPHER_GENERATION_TEMPLATE
)
# Tao Chain hoi dap

cypherChain=GraphCypherQAChain.from_llm(
    llm=llm, graph=graph, verbose=True, cypher_prompt=cypher_prompt,
    allow_dangerous_requests=True
)
def prettyCypherChain(question: str) -> str:
    response = cypherChain.run(question)
    print('---response', response)
    print('===', cypherChain.invoke(question))
    print(textwrap.fill(response, 60))
    return response
prettyCypherChain("Cấu hình của điện thoại samsung galaxy s23 fe 5g như thế nào ?")