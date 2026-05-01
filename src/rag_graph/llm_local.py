from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file


class LLMLocal:
    def __init__(self):
        self.llm = ChatOpenAI(
            base_url=os.getenv("LOCAL_LLM"),
            api_key="none",
            model="qwen2.5-7b", 
            temperature=0,
            max_tokens=4096
        )

    def generate(self, prompt):
        return self.llm.invoke(prompt).content


if __name__ == "__main__":
    llm = LLMLocal()
    result = llm.generate("Đội bóng giàu thành tích nhất của Việt Nam là đội nào?")
    print(result)
    # uv run -m src.rag_graph.llm_local