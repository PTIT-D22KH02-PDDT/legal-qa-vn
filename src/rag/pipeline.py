"""
RAG Pipeline - Kết hợp Search (retrieve + rerank) + Generate
"""

from typing import List, Optional, Dict, Any
import logging
import re

from .config import RAGConfig
from src.indexing.vector_store import ChromaStore
from src.indexing.vector_store.schemas import ChromaConfig
from src.search import SearchPipeline
from src.generate import GenerateService
from src.api import RemoteAPIClient

logger = logging.getLogger(__name__)


class RAGResult:
    """Kết quả từ RAG pipeline"""
    
    def __init__(
        self,
        query: str,
        answer: str,
        retrieved_documents: List[Dict[str, Any]],
        context: str,
    ):
        self.query = query
        self.answer = answer
        self.retrieved_documents = retrieved_documents
        self.context = context
    
    def __repr__(self) -> str:
        return f"RAGResult(query={self.query[:50]}..., answer_len={len(self.answer)})"


class RAGPipeline:
    """
    RAG Pipeline - Retrieval-Augmented Generation.
    
    Workflow:
    1. Nhận câu hỏi (query)
    2. Search: Retrieve + Rerank tài liệu liên quan
    3. Format context từ top-k documents
    4. Generate: LLM sinh câu trả lời dựa trên context
    
    Hỗ trợ cả local models và remote API.
    
    Config được load từ YAML file:
    - configs/rag_config.yaml: Parameters
    - configs/prompts/system_prompt.txt: System prompt
    - configs/prompts/answer_prompt.txt: Answer template
    """
    
    def __init__(
        self,
        chroma_store: ChromaStore,
        config: Optional[RAGConfig] = None,
        embedding_model=None,
        use_remote_api: bool = False,
    ):
        """
        Khởi tạo RAG Pipeline.
        
        Args:
            chroma_store: ChromaStore instance chứa indexed documents
            config: RAGConfig instance
                   Nếu None, load từ configs/rag_config.yaml (mặc định)
            embedding_model: OnnxEmbeddingModel or RemoteEmbeddingModel
                           (chỉ cần khi use_remote_api=False)
            use_remote_api: Sử dụng remote API cho embedding, rerank, generate
        
        Raises:
            ValueError: Nếu thiếu required parameters
        """
        # Load config từ YAML nếu không được cung cấp
        if config is None:
            logger.info("Loading config from YAML: configs/rag_config.yaml")
            config = RAGConfig.from_yaml("configs/rag_config.yaml")
        
        self.config = config
        self.use_remote_api = use_remote_api or self.config.use_remote_api
        
        # Load prompts từ files
        logger.info("Loading prompts from files")
        try:
            self.system_prompt, self.answer_prompt = self.config.load_prompts()
            logger.info("[OK] Prompts loaded successfully")
        except FileNotFoundError as e:
            logger.error(f"Failed to load prompts: {e}")
            raise
        
        logger.info(f"Initializing RAGPipeline (use_remote_api={self.use_remote_api})")
        
        # Initialize SearchPipeline
        try:
            self.search_pipeline = SearchPipeline(
                chroma_store=chroma_store,
                embedding_model=embedding_model,
                use_remote_api=use_remote_api,
            )
            logger.info("[OK] SearchPipeline initialized")
        except Exception as e:
            logger.error(f"Failed to initialize SearchPipeline: {e}")
            raise
        
        # Initialize GenerateService
        try:
            if use_remote_api:
                api_client = RemoteAPIClient()
            else:
                api_client = None
            
            self.generate_service = GenerateService(api_client=api_client)
            logger.info("[OK] GenerateService initialized")
        except Exception as e:
            logger.error(f"Failed to initialize GenerateService: {e}")
            raise
        
        logger.info("[OK] RAGPipeline ready")
    
    def _format_context(self, documents: List[Dict[str, Any]]) -> str:
        """
        Format context từ retrieved documents.
        
        Args:
            documents: List of retrieval results
        
        Returns:
            Formatted context string
        """
        context_parts = []
        
        for i, doc in enumerate(documents, 1):
            # Extract document info
            section_id = doc.get('id', doc.get('section_id', 'Unknown'))
            text = doc.get('document', doc.get('text', ''))
            score = doc.get('relevance_score', doc.get('score', 0))
            
            # Format as numbered item
            part = f"[{i}] {section_id}\nScore: {score:.4f}\n{text}"
            context_parts.append(part)
        
        # Join with separator
        context = self.config.context_separator.join(context_parts)
        
        # Truncate if too long
        if len(context) > self.config.max_context_length:
            context = context[:self.config.max_context_length] + "..."
            logger.warning(f"Context truncated to {self.config.max_context_length} chars")
        
        return context
    
    def run(
        self,
        query: str,
        retrieval_top_k: Optional[int] = None,
        rerank_top_k: Optional[int] = None,
        use_rerank: Optional[bool] = None,
        filter_by_type: Optional[List[str]] = None,
    ) -> RAGResult:
        """
        Chạy RAG pipeline với một câu hỏi.
        
        Args:
            query: Câu hỏi từ user
            retrieval_top_k: Override retrieval top-k từ config
            rerank_top_k: Override rerank top-k từ config
            use_rerank: Override use_rerank từ config
            filter_by_type: Lọc documents theo loại (optional)
        
        Returns:
            RAGResult instance
        
        Raises:
            Exception: Nếu search hoặc generate thất bại
        """
        logger.info(f"Processing query: {query}")
        
        # Step 1: Search
        print(f"\n{'='*70}")
        print(f"RAG Pipeline")
        print(f"{'='*70}")
        print(f"\n[Step 1] Searching for relevant documents...")
        
        retrieval_top_k = retrieval_top_k or self.config.retrieval_top_k
        rerank_top_k = rerank_top_k or self.config.rerank_top_k
        use_rerank = use_rerank if use_rerank is not None else self.config.use_rerank
        
        try:
            retrieved_docs = self.search_pipeline.search(
                query=query,
                top_k=rerank_top_k if use_rerank else retrieval_top_k,
                filter_by_type=filter_by_type,
                use_rerank=use_rerank,
            )
            
            print(f"  Retrieved: {len(retrieved_docs)} documents")
            
            if not retrieved_docs:
                logger.warning("No documents retrieved")
                return RAGResult(
                    query=query,
                    answer="Xin lỗi, không tìm thấy thông tin liên quan.",
                    retrieved_documents=[],
                    context="",
                )
        
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise
        
        # Step 2: Format context
        print(f"\n[Step 2] Formatting context...")
        context = self._format_context(retrieved_docs)
        print(f"  Context length: {len(context)} chars")
        
        # Step 3: Generate answer
        print(f"\n[Step 3] Generating answer...")
        
        try:
            # Build prompt using template from config
            prompt = self.answer_prompt.format(
                query=query,
                context=context,
            )
            
            logger.debug(f"Prompt:\n{prompt}")
            
            # Generate
            answer = self.generate_service.generate(
                prompt=prompt,
                max_length=self.config.max_answer_length,
                temperature=self.config.temperature,
                top_k=self.config.top_k,
                top_p=self.config.top_p,
            )
            
            print(f"  Answer generated: {len(answer)} chars")
            
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise
        
        # Step 4: Return result
        print(f"\n{'='*70}")
        
        result = RAGResult(
            query=query,
            answer=answer,
            retrieved_documents=retrieved_docs,
            context=context,
        )
        
        logger.info(f"[OK] RAG pipeline completed for: {query[:50]}...")
        
        return result
