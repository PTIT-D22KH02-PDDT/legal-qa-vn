"""
Example usage của Legal QA Agent
Định nghĩa các ví dụ về cách sử dụng agent để trả lời các câu hỏi về pháp luật.
"""
import logging
from typing import Optional

from langchain_groq import ChatGroq  # Hoặc LLM khác

from src.indexing.vector_store import ChromaStore, ChromaConfig
from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel
from src.search.retrieval import RetrievalService

from . import LegalQAAgent


logger = logging.getLogger(__name__)


class LegalQAAgentRunner:
    """Wrapper để chạy Legal QA Agent dễ hơn"""
    
    def __init__(
        self,
        llm_model: str = "mixtral-8x7b-32768",  # Groq model
        chroma_db_dir: str = "chroma_db",
        embedding_model_dir: str = "models/vietnamese-embedding",
        enable_logging: bool = True,
    ):
        """
        Khởi tạo Legal QA Agent Runner
        
        Args:
            llm_model: Model LLM từ Groq
            chroma_db_dir: Đường dẫn ChromaDB
            embedding_model_dir: Đường dẫn embedding model
            enable_logging: Bật logging
        """
        self.enable_logging = enable_logging
        
        # Setup logging
        if enable_logging:
            logging.basicConfig(level=logging.INFO)
        
        logger.info("[LegalQARunner] Initializing...")
        
        # Initialize ChromaDB
        logger.info("[LegalQARunner] Loading ChromaDB...")
        chroma_config = ChromaConfig(persist_directory=chroma_db_dir)
        self.chroma_store = ChromaStore(config=chroma_config)
        
        # Initialize embedding model
        logger.info("[LegalQARunner] Loading embedding model...")
        self.embedding_model = OnnxEmbeddingModel(
            model_dir=embedding_model_dir
        )
        
        # Initialize retrieval service
        logger.info("[LegalQARunner] Initializing retrieval service...")
        self.retrieval_service = RetrievalService(
            chroma_store=self.chroma_store,
            embedding_model=self.embedding_model,
        )
        
        # Initialize LLM
        logger.info(f"[LegalQARunner] Loading LLM: {llm_model}...")
        self.llm = ChatGroq(
            model_name=llm_model,
            temperature=0.7,
            max_tokens=2048,
        )
        
        # Initialize Agent
        logger.info("[LegalQARunner] Creating agent...")
        self.agent = LegalQAAgent(
            llm=self.llm,
            chroma_store=self.chroma_store,
            embedding_model=self.embedding_model,
            retrieval_service=self.retrieval_service,
            enable_logging=enable_logging,
        )
        
        logger.info("[LegalQARunner] Ready!")
    
    def query(self, question: str) -> str:
        """
        Hỏi agent một câu hỏi
        
        Args:
            question: Câu hỏi từ người dùng
        
        Returns:
            Câu trả lời
        """
        logger.info(f"\n[Query] {question}")
        
        # Process query
        response = self.agent.process_query(question)
        
        # Log response
        logger.info(f"\n[Answer] {response.final_answer}")
        
        if response.sources:
            logger.info(f"[Sources] {', '.join(response.sources)}")
        
        return response.final_answer
    
    def interactive_mode(self):
        """Chế độ tương tác - chat với agent"""
        print("\n" + "="*60)
        print("Legal QA Agent - Chế độ tương tác")
        print("="*60)
        print("Nhập câu hỏi (hoặc 'exit' để thoát):\n")
        
        while True:
            try:
                question = input("Bạn: ").strip()
                
                if question.lower() in ['exit', 'quit', 'thoát']:
                    print("Tạm biệt!")
                    break
                
                if not question:
                    continue
                
                # Query agent
                answer = self.query(question)
                print(f"\nAgent: {answer}\n")
            
            except KeyboardInterrupt:
                print("\n\nTạm biệt!")
                break
            except Exception as e:
                logger.error(f"Error: {e}", exc_info=True)
                print(f"Lỗi: {str(e)}\n")


# Example queries
EXAMPLE_QUERIES = [
    # Tìm kiếm tổng quát
    "Quy định về bảo hiểm y tế là gì?",
    
    # Tìm điều cụ thể
    "Điều 5 của Luật 102/2017 nói gì?",
    
    # So sánh
    "Khác biệt giữa Luật 102/2017 và Luật 35/2024 là gì?",
    
    # Tìm quy trình
    "Quy trình cấp phép bảo hiểm xã hội là như thế nào?",
    
    # Tìm metadata
    "Có bao nhiêu luật về bảo hiểm xã hội?",
    
    # Bối cảnh pháp lý
    "Luật 102/2017 còn hiện hành không? Có luật nào thay thế nó?",
]


def run_examples():
    """Chạy các ví dụ"""
    runner = LegalQAAgentRunner(enable_logging=True)
    
    print("\n" + "="*60)
    print("Running Example Queries")
    print("="*60)
    
    for query in EXAMPLE_QUERIES[:3]:  # Chạy 3 query đầu tiên
        print(f"\n\n{'='*60}")
        print(f"Query: {query}")
        print(f"{'='*60}")
        
        try:
            answer = runner.query(query)
            print(f"\nAnswer: {answer}")
        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)


def main():
    """Main entry point"""
    import sys
    
    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        # Interactive mode
        runner = LegalQAAgentRunner(enable_logging=True)
        runner.interactive_mode()
    else:
        # Run examples
        run_examples()


if __name__ == "__main__":
    main()
