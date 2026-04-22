"""
Example usage của Legal QA Agent
Định nghĩa các ví dụ về cách sử dụng agent để trả lời các câu hỏi về pháp luật.
"""
import logging
import os
from typing import Optional
from pathlib import Path
from .llms import LLMGroq

from src.indexing.vector_store import ChromaStore, ChromaConfig
from src.indexing.embedding.onnx_embedding import OnnxEmbeddingModel
from src.search.retrieval import RetrievalService
from src.agent.config import get_agent_config
from src.search.config import PipelineConfig
from src.search.pipeline import SearchPipeline
from . import LegalQAAgent


logger = logging.getLogger(__name__)


class LegalQAAgentRunner:
    """Wrapper để chạy Legal QA Agent dễ hơn"""
    
    def __init__(
        self,
        use_config: bool = True,
        llm_model: Optional[str] = None,
        chroma_db_dir: Optional[str] = None,
        embedding_model_dir: Optional[str] = None,
        enable_logging: bool = True,
    ):
        """
        Khởi tạo Legal QA Agent Runner
        
        Args:
            use_config: Lấy config từ agent_config.yaml và search_config.yaml (default: True)
            llm_model: Override LLM model name (nếu use_config=False)
            chroma_db_dir: Override ChromaDB directory (nếu use_config=False)
            embedding_model_dir: Override embedding model directory (nếu use_config=False)
            enable_logging: Bật logging
        """
        self.enable_logging = enable_logging
        
        # Setup logging
        if enable_logging:
            logging.basicConfig(level=logging.INFO)
        
        logger.info("[LegalQARunner] Initializing...")
        
        # Default values for chroma config
        collection_name = "legal_documents"
        is_persist = True
        distance_metric = "ip"
        llm_params = {}  # Default empty dict
        
        # Load configs
        if use_config:
            logger.info("[LegalQARunner] Loading configuration from YAML...")
            agent_config = get_agent_config()
            pipeline_config = PipelineConfig.get_default_config()
            
            # Get LLM params
            llm_provider = agent_config.get_query_analyzer_params().get('llm_provider', 'groq')
            llm_params = agent_config.get_llm_provider_params(llm_provider)
            llm_model = llm_model or llm_params.get('model_name')
            
            # Get vector store params
            vs_params = pipeline_config.get_vector_store_params()
            chroma_db_dir = chroma_db_dir or vs_params.get('persist_directory')
            collection_name = vs_params.get('collection_name', 'legal_documents')
            is_persist = vs_params.get('is_persist', True)
            distance_metric = vs_params.get('distance_metric', 'ip')
            
            # Get embedding model dir
            embedding_model_dir = embedding_model_dir or pipeline_config.get_embedding_model_dir()
            
            logger.info(f"  LLM: {llm_model}")
            logger.info(f"  ChromaDB: {chroma_db_dir}")
            logger.info(f"  Embedding: {embedding_model_dir}")
        else:
            # Use provided values or defaults
            llm_model = llm_model or "llama-3.1-8b-instant"
            chroma_db_dir = chroma_db_dir or "chroma_db"
            embedding_model_dir = embedding_model_dir or "models/vietnamese-embedding"
        
        # Initialize ChromaDB
        logger.info("[LegalQARunner] Loading ChromaDB...")
        chroma_config = ChromaConfig(
            collection_name=collection_name,
            persist_directory=chroma_db_dir,
            is_persist=is_persist,
            distance_metric=distance_metric
        )
        self.chroma_store = ChromaStore(config=chroma_config)
        
        # Initialize embedding model
        logger.info("[LegalQARunner] Loading embedding model...")
        self.embedding_model = OnnxEmbeddingModel(
            model_dir=str(embedding_model_dir)
        )
        
        # Initialize retrieval service
        logger.info("[LegalQARunner] Initializing retrieval service...")
        self.retrieval_service = SearchPipeline(
            chroma_store=self.chroma_store,
            embedding_model=self.embedding_model,
        )
        
        # Initialize LLM
        logger.info(f"[LegalQARunner] Loading LLM: {llm_model}...")
        if use_config:
            # Use config-based LLM initialization
            api_key = llm_params.get('api_key') or os.getenv('GROQ_API_KEY')
            temperature = llm_params.get('temperature', 0.0)
            self.llm = LLMGroq(
                api_key=api_key,
                model_name=llm_model,
            )
            self.llm.temperature = temperature
        else:
            # Use default initialization
            api_key = os.getenv('GROQ_API_KEY')
            self.llm = LLMGroq(
                api_key=api_key,
                model_name=llm_model,
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
    runner = LegalQAAgentRunner(use_config=True, enable_logging=True)
    
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
    if len(sys.argv) > 1:
        if sys.argv[1] == "--interactive":
            # Interactive mode with config
            runner = LegalQAAgentRunner(use_config=True, enable_logging=True)
            runner.interactive_mode()
        elif sys.argv[1] == "--no-config":
            # Run examples without config (hardcoded params)
            runner = LegalQAAgentRunner(use_config=False, enable_logging=True)
            print("\n[INFO] Running in NO-CONFIG mode (hardcoded parameters)")
            print("       Use: python -m src.agent.agents --interactive  (with config)")
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print("Usage:")
            print("  python -m src.agent.agents              # Run examples (with config)")
            print("  python -m src.agent.agents --interactive # Interactive mode (with config)")
            return
    
    # Default: Run examples with config
    run_examples()

def input_query():
    runner = LegalQAAgentRunner(use_config=True, enable_logging=True)
    runner.interactive_mode()

if __name__ == "__main__":
    input_query()
