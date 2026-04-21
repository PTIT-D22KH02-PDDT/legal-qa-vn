#!/usr/bin/env python3
"""
Quick test script để kiểm tra LLMQueryAnalyzer hoạt động
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agent.llm_query_analyzer import LLMQueryAnalyzer
from src.agent.llms import LLMFactory


def test_llm_analyzer():
    """Test LLMQueryAnalyzer với Groq API"""
    
    logger.info("=" * 80)
    logger.info("Testing LLMQueryAnalyzer")
    logger.info("=" * 80)
    
    # Create Groq LLM
    logger.info("\n1. Creating Groq LLM...")
    try:
        llm = LLMFactory.create_groq_llm(temperature=0)
        logger.info("   ✅ Groq LLM created successfully")
    except Exception as e:
        logger.error(f"   ❌ Failed to create Groq LLM: {e}")
        return False
    
    # Create analyzer
    logger.info("\n2. Creating LLMQueryAnalyzer...")
    try:
        analyzer = LLMQueryAnalyzer(llm=llm)
        logger.info("   ✅ LLMQueryAnalyzer created successfully")
    except Exception as e:
        logger.error(f"   ❌ Failed to create analyzer: {e}")
        return False
    
    # Test queries
    test_queries = [
        "Điều 5 của Luật 102/2017 nói gì?",
        "Bảo hiểm xã hội là gì?",
        "Khác biệt giữa Luật A và Luật B?",
    ]
    
    results = []
    for i, query in enumerate(test_queries, 1):
        logger.info(f"\n{i}. Testing query: {query[:50]}...")
        
        try:
            result = analyzer.analyze(query)
            
            logger.info(f"   ✅ Analysis successful")
            logger.info(f"      Query Type: {result.query_type}")
            logger.info(f"      Intent: {result.intent}")
            logger.info(f"      Entities: {len(result.extracted_entities)} items")
            logger.info(f"      Confidence: {result.confidence:.2f}")
            
            results.append((query, result, True))
        
        except Exception as e:
            logger.error(f"   ❌ Analysis failed: {e}")
            results.append((query, None, False))
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("Test Summary")
    logger.info("=" * 80)
    
    passed = sum(1 for _, _, success in results if success)
    total = len(results)
    
    logger.info(f"Passed: {passed}/{total}")
    
    if passed == total:
        logger.info("\n✅ All tests passed!")
        return True
    else:
        logger.warning(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = test_llm_analyzer()
    sys.exit(0 if success else 1)
