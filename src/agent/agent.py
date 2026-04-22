"""
LangChain Agent - Tiếp nhận câu hỏi, phân tích, định tuyến tools, và tổng hợp câu trả lời
"""

import logging
import time
from typing import List, Optional, Dict, Any
from datetime import datetime

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.agent.llms import LLMGroq
from src.search.retrieval import RetrievalService
from src.indexing.vector_store import ChromaStore
from src.indexing.embedding import OnnxEmbeddingModel

from .schemas import (
    QueryAnalysisResult, AgentResponse, AgentStep, ToolExecutionResult,
    QueryType, Intent
)
from .llm_query_analyzer import LLMQueryAnalyzer
from .query_analyzer import QueryAnalyzer
from .router import ToolRouter
from .tools import LegalDocumentTools


logger = logging.getLogger(__name__)

class LegalQAAgent:
    """
    LangChain Agent chính cho hệ thống Legal QA
    
    Workflow:
    1. Nhận query từ người dùng
    2. QueryAnalyzer: Phân tích & phân loại query
    3. ToolRouter: Xác định tools cần sử dụng
    4. Agent: Thực thi tools theo thứ tự
    5. Generate: Tổng hợp kết quả thành câu trả lời
    """
    SYSTEM_PROMPT_TEMPLATE = """Bạn là một trợ lý pháp lý thông minh, chuyên trả lời các câu hỏi về 
pháp luật Việt Nam. Bạn có quyền truy cập vào các công cụ tìm kiếm tài liệu pháp luật.

Khi trả lời:
1. Sử dụng thông tin từ các công cụ tìm kiếm
2. Luôn trích dẫn nguồn tài liệu cụ thể (số hiệu, điều khoản)
3. Giải thích một cách rõ ràng và dễ hiểu
4. Nếu có nhiều góc độ, hãy trình bày cân bằng
5. Nếu không chắc chắn, hãy nói rõ điều đó
Hãy tập trung vào câu hỏi của người dùng và sử dụng các công cụ một cách hiệu quả."""
    
    def __init__(
        self,
        llm: LLMGroq,
        chroma_store: ChromaStore,
        embedding_model: OnnxEmbeddingModel,
        retrieval_service: Optional[RetrievalService] = None,
        enable_logging: bool = True,
    ):
        """
        Khởi tạo LegalQAAgent
        Args:
            llm: LangChain LLM instance
            chroma_store: ChromaDB store instance
            embedding_model: Embedding model instance
            retrieval_service: Retrieval service (nếu có)
            enable_logging: Bật logging chi tiết
        """
        self.llm = llm
        self.chroma_store = chroma_store
        self.embedding_model = embedding_model
        self.enable_logging = enable_logging
        
        # Initialize components
        self.query_analyzer = LLMQueryAnalyzer(
            llm=llm,
            fallback_analyzer=QueryAnalyzer(),
        )
        self.tool_router = ToolRouter()
        self.tools_provider = LegalDocumentTools(
            chroma_store=chroma_store,
            embedding_model=embedding_model,
            retrieval_service=retrieval_service,
        )
        
        # Create LangChain agent
        self.agent_executor = self._create_agent_executor()
    
    def _create_agent_executor(self) -> AgentExecutor:
        """Tạo LangChain AgentExecutor"""
        # Get tools
        tools = self.tools_provider.get_tools_list()
        
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_PROMPT_TEMPLATE),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent
        agent = create_tool_calling_agent(
            llm=self.llm,
            tools=tools,
            prompt=prompt,
        )
        
        # Create executor
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=self.enable_logging,
            max_iterations=5,
            handle_parsing_errors=True,
        )
        
        return executor
    
    def process_query(self, query: str) -> AgentResponse:
        """
        Xử lý một câu hỏi từ người dùng
        Args:
            query: Câu hỏi từ người dùng
        Returns:
            AgentResponse chứa phân tích, các bước, và câu trả lời
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"[Agent] Processing query: {query}")
        logger.info(f"{'='*60}")
        
        start_time = time.time()
        steps: List[AgentStep] = []
        retrieved_documents = []
        final_answer = ""
        
        try:
            # Step 1: Analyze query
            logger.info("[Agent] Step 1: Analyzing query...")
            analysis = self._step_analyze(query)
            logger.info(f"  -> Type: {analysis.query_type}, Intent: {analysis.intent}")
            
            # Step 2: Route to tools
            logger.info("[Agent] Step 2: Routing to tools...")
            tool_calls = self._step_route(analysis)
            logger.info(f"  -> Selected tools: {[t[0] for t in tool_calls]}")
            
            # Step 3: Execute tools
            logger.info("[Agent] Step 3: Executing tools...")
            for tool_name, tool_input in tool_calls:
                step = self._step_execute_tool(
                    tool_name, tool_input, len(steps) + 1
                )
                steps.append(step)
                
                if step.result and step.result.success:
                    # Collect retrieved documents
                    if step.result.results:
                        retrieved_documents.extend(step.result.results)
            
            # Step 4: Generate final answer using LLM
            logger.info("[Agent] Step 4: Generating final answer...")
            final_answer = self._step_generate_answer(
                query, analysis, steps, retrieved_documents
            )
            
            # Build final response
            response = AgentResponse(
                query=query,
                analysis=analysis,
                steps=steps,
                retrieved_documents=retrieved_documents,
                final_answer=final_answer,
                sources=self._extract_sources(retrieved_documents),
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"[Agent] Completed in {elapsed_time:.2f}s")
            
            return response
        
        except Exception as e:
            logger.error(f"[Agent] Error: {e}", exc_info=True)
            
            # Return error response
            return AgentResponse(
                query=query,
                analysis=analysis if 'analysis' in locals() else QueryAnalysisResult(
                    original_query=query,
                    query_type=QueryType.SEMANTIC_SEARCH,
                    intent=Intent.LOOKUP,
                ),
                steps=steps,
                retrieved_documents=retrieved_documents,
                final_answer=f"Lỗi xử lý: {str(e)}",
                sources=[],
            )
    
    def _step_analyze(self, query: str) -> QueryAnalysisResult:
        """Step 1: Analyze query"""
        analysis = self.query_analyzer.analyze(query)
        
        if self.enable_logging:
            logger.info(f"    Query Type: {analysis.query_type}")
            logger.info(f"    Intent: {analysis.intent}")
            logger.info(f"    Extracted Blocks: {len(analysis.extracted_blocks)} blocks")
            for i, block in enumerate(analysis.extracted_blocks):
                logger.info(f"      Block {i+1}: Dieu={block.dieu}, Khoan={block.khoan}, "
                           f"Diem={block.diem}, Doc={block.document_name}")
            logger.info(f"    Keywords: {analysis.keywords}")
            logger.info(f"    Confidence: {analysis.confidence:.2f}")
        
        return analysis
    
    def _step_route(self, analysis: QueryAnalysisResult) -> List[tuple]:
        """Step 2: Route to tools"""
        tool_calls = self.tool_router.route(analysis)
        
        if self.enable_logging:
            for tool_name, tool_input in tool_calls:
                logger.info(f"    Tool: {tool_name}")
                logger.info(f"      Input: {tool_input}")
        
        return tool_calls
    
    def _step_execute_tool(
        self, tool_name: str, tool_input: Dict[str, Any], step_num: int, retry_count: int = 0
    ) -> AgentStep:
        """Step 3: Execute a tool with retry logic"""
        
        step = AgentStep(
            step_number=step_num,
            reasoning=self.tool_router.get_tool_explanation(tool_name),
            tool_name=tool_name,
            tool_input=tool_input,
        )
        
        try:
            logger.info(f"    Executing: {tool_name}")
            
            start_time = time.time()
            
            # Execute tool based on name
            # Note: @tool decorator converts methods to StructuredTool, use .invoke() to call
            if tool_name == "search_legal_documents":
                result = self.tools_provider.search_legal_documents.invoke(tool_input)
            elif tool_name == "search_document_metadata":
                result = self.tools_provider.search_document_metadata.invoke(tool_input)
            elif tool_name == "get_specific_article":
                result = self.tools_provider.get_specific_article.invoke(tool_input)
            elif tool_name == "find_related_documents":
                result = self.tools_provider.find_related_documents.invoke(tool_input)
            elif tool_name == "find_cross_references":
                result = self.tools_provider.find_cross_references.invoke(tool_input)
            else:
                result = f"Unknown tool: {tool_name}"
            
            execution_time = time.time() - start_time
            
            # Check if result is empty/error - potential retry candidate
            is_error = (isinstance(result, str) and 
                       ("Lỗi" in result or "không tìm thấy" in result or "Error" in result))
            
            # Build result
            step.result = ToolExecutionResult(
                tool_name=tool_name,
                success=not is_error,
                results=[{"content": result}],
                execution_time=execution_time,
            )
            
            if self.enable_logging:
                logger.info(f"      ✓ Success ({execution_time:.2f}s)")
                logger.info(f"      Result: {str(result)[:100]}...")
        
        except Exception as e:
            logger.error(f"      ✗ Error: {e}", exc_info=True)
            
            # Retry logic: Retry up to 2 times on failure
            if retry_count < 2:
                logger.warning(f"      [Retry {retry_count + 1}/2] Retrying {tool_name}...")
                return self._step_execute_tool(tool_name, tool_input, step_num, retry_count + 1)
            
            step.result = ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
            )
        
        return step
    
    def _step_generate_answer(
        self,
        query: str,
        analysis: QueryAnalysisResult,
        steps: List[AgentStep],
        retrieved_documents: List[Dict[str, Any]],
    ) -> str:
        """Step 4: Generate final answer using LLM"""
        
        # Prepare context from tool results
        context_parts = []
        
        for step in steps:
            if step.result and step.result.success and step.result.results:
                for result in step.result.results:
                    if isinstance(result, dict) and "content" in result:
                        context_parts.append(result["content"])
        
        context = "\n\n".join(context_parts) if context_parts else "Không tìm thấy thông tin liên quan."
        
        # Build prompt for LLM
        prompt = f"""Dựa trên thông tin tìm kiếm dưới đây, hãy trả lời câu hỏi của người dùng một cách rõ ràng và chính xác.

Câu hỏi: {query}

Thông tin tìm kiếm:
{context}

Hãy trả lời:"""
        
        # Call LLM
        try:
            response = self.agent_executor.invoke({"input": prompt})
            final_answer = response.get("output", "Không thể sinh câu trả lời.")
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            final_answer = f"Lỗi sinh câu trả lời: {str(e)}"
        
        if self.enable_logging:
            logger.info(f"    Generated answer: {final_answer[:100]}...")
        
        return final_answer
    
    def _extract_sources(self, documents: List[Dict[str, Any]]) -> List[str]:
        """Trích xuất danh sách nguồn từ tài liệu được truy xuất"""
        sources = []
        for doc in documents:
            if isinstance(doc, dict) and "title" in doc:
                sources.append(doc["title"])
        return list(set(sources))  # Remove duplicates
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Lấy thông tin về agent"""
        return {
            "name": "Legal QA Agent",
            "description": "Agent hỏi đáp pháp lý Việt Nam",
            "created_at": datetime.now().isoformat(),
            "components": {
                "query_analyzer": "QueryAnalyzer",
                "tool_router": "ToolRouter",
                "tools": [
                    "search_legal_documents",
                    "search_document_metadata",
                    "get_specific_article",
                    "find_related_documents",
                    "find_cross_references",
                ],
            },
        }
