"""Markdown output formatter for RAG results"""

from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path


class MarkdownFormatter:
    """Format and save RAG results to markdown files."""
    
    @staticmethod
    def format_rag_result(result: Any) -> str:
        """
        Format a single RAG result to markdown.
        
        Args:
            result: RAGResult instance
        
        Returns:
            Markdown formatted string
        """
        md = []
        
        # Header
        md.append(f"# Query: {result.query}\n")
        
        # Retrieved Documents
        md.append("## 📚 Retrieved Documents\n")
        for i, doc in enumerate(result.retrieved_documents, 1):
            section_id = doc.get('id', 'Unknown')
            score = doc.get('relevance_score', 0)
            text = doc.get('document', '')
            
            md.append(f"### {i}. {section_id}")
            md.append(f"**Score:** {score:.4f}\n")
            md.append(f"```\n{text}\n```\n")
        
        # Generated Answer
        md.append("## 🤖 Generated Answer\n")
        md.append(f"{result.answer}\n")
        
        # Context
        md.append("## 📄 Full Context Sent to LLM\n")
        md.append(f"```\n{result.context}\n```\n")
        
        return "\n".join(md)
    
    @staticmethod
    def save_results(
        results: List[Any],
        output_path: str = "rag_results.md",
        title: str = "RAG Pipeline Results"
    ) -> str:
        """
        Save multiple RAG results to a markdown file.
        
        Args:
            results: List of RAGResult instances
            output_path: Path to save markdown file
            title: Title for the document
        
        Returns:
            Path to saved file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        md = []
        
        # Document header
        md.append(f"# {title}\n")
        md.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        md.append(f"**Total Queries:** {len(results)}\n")
        md.append("---\n")
        
        # Table of contents
        md.append("## Table of Contents\n")
        for i, result in enumerate(results, 1):
            # Sanitize query for link
            query_link = result.query.replace(" ", "-").replace("?", "").replace(":", "")
            md.append(f"{i}. [Query {i}: {result.query[:50]}...](#{query_link})\n")
        
        md.append("---\n")
        
        # Results
        for i, result in enumerate(results, 1):
            md.append(f"\n## Query {i}\n")
            md.append(MarkdownFormatter.format_rag_result(result))
            md.append("\n---\n")
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(md))
        
        return str(output_path)


def save_rag_results_markdown(results: List[Any], output_file: str = "rag_results.md"):
    """
    Convenience function to save RAG results to markdown.
    
    Args:
        results: List of RAGResult instances
        output_file: Output markdown file path
    
    Returns:
        Path to saved file
    """
    formatter = MarkdownFormatter()
    saved_path = formatter.save_results(
        results=results,
        output_path=output_file,
        title="RAG Pipeline Results - Legal Document Q&A"
    )
    print(f"✓ Results saved to: {saved_path}")
    return saved_path
