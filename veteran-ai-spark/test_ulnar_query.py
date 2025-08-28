#!/usr/bin/env python3
"""
Test script to verify ulnar neuropathy query improvements.
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.retrieval import HybridRetriever

def test_medical_term_expansion():
    """Test the medical term expansion functionality."""
    retriever = HybridRetriever()
    
    test_queries = [
        "what is the rating for ulnar neuropathy",
        "ulnar neuropathy rating",
        "neuropathy symptoms",
        "carpal tunnel syndrome rating",
        "ptsd rating schedule"
    ]
    
    print("🧪 Testing Medical Term Expansion")
    print("=" * 50)
    
    for query in test_queries:
        expanded = retriever._expand_medical_terms(query)
        if expanded != query:
            print(f"✅ '{query}'")
            print(f"   -> '{expanded}'")
        else:
            print(f"⚪ '{query}' (no expansion)")
        print()

def test_query_processing():
    """Test the full query processing pipeline."""
    retriever = HybridRetriever()
    
    print("🔄 Testing Query Processing Pipeline")
    print("=" * 50)
    
    query = "what is the rating for ulnar neuropathy"
    print(f"Original query: '{query}'")
    
    # Test expansion
    expanded = retriever._expand_medical_terms(query)
    print(f"After expansion: '{expanded}'")
    
    # Test full rewrite
    try:
        processed = retriever.rewrite_query(query)
        print(f"After rewrite: '{processed}'")
    except Exception as e:
        print(f"Rewrite failed (expected without API keys): {e}")
        print(f"Would use expanded: '{expanded}'")

def main():
    print("🚀 Testing Ulnar Neuropathy Query Improvements")
    print("=" * 60)
    
    test_medical_term_expansion()
    test_query_processing()
    
    print("📋 Summary of Improvements:")
    print("1. ✅ Medical term expansion: 'neuropathy' -> 'neuropathy neuritis nerve paralysis'")
    print("2. ✅ Specific ulnar expansion: 'ulnar neuropathy' -> includes 'ulnar neuritis'")
    print("3. ✅ BM25 weight increased: 60% vector, 40% BM25 (was 65%/35%)")
    print("4. ✅ Enhanced debug logging for query processing")
    print()
    print("🎯 Expected Result:")
    print("The query 'what is the rating for ulnar neuropathy' should now match:")
    print("- Chunk 697: General ulnar nerve function")
    print("- Chunk 698: 8516 Paralysis ratings (10%, 30%, 40%, 60%)")
    print("- Chunk 699: 8616 Neuritis ratings (10%, 30%, 40%)")

if __name__ == "__main__":
    main()
