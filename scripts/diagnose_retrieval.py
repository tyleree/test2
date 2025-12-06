#!/usr/bin/env python3
"""
RAG Retrieval Diagnostic Tool

This script bypasses caching entirely and shows exactly what the RAG system
is retrieving for each query. Use this to diagnose retrieval issues.

Usage:
    python scripts/diagnose_retrieval.py "What is the GI Bill?"
    python scripts/diagnose_retrieval.py --all-failing  # Run all known failing queries
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force disable caching for diagnostics
os.environ["DISABLE_RESPONSE_CACHE"] = "true"

try:
    from dotenv import load_dotenv
    load_dotenv('env.txt')
except ImportError:
    # Load env vars manually if dotenv not available
    import os
    if os.path.exists('env.txt'):
        with open('env.txt', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

from src.rag_pipeline import RAGPipeline, DEFAULT_TOP_K, DEFAULT_MIN_SCORE
from src.embeddings import embed_query_cached, DEFAULT_EMBEDDING_MODEL
from src.vector_store import get_vector_store, initialize_vector_store

# Known failing queries for systematic testing
FAILING_QUERIES = [
    # GI Bill queries (all returning VR&E content)
    ("What is the GI Bill?", "GI Bill", "Should return GI Bill education benefits, NOT VR&E"),
    ("How do I apply for the Post-9/11 GI Bill?", "GI Bill", "Should return Post-9/11 application info"),
    ("What is Chapter 33?", "GI Bill", "Should return Post-9/11 GI Bill info"),
    ("What is the Montgomery GI Bill?", "GI Bill", "Should return MGIB Chapter 30 info"),
    
    # CHAMPVA queries (returning Agent Orange content)
    ("What is CHAMPVA?", "CHAMPVA", "Should return CHAMPVA healthcare program info"),
    ("What is the CHAMPVA deductible?", "CHAMPVA", "Should return CHAMPVA cost-sharing info"),
    ("Does CHAMPVA cover prescriptions?", "CHAMPVA", "Should return CHAMPVA pharmacy coverage"),
    
    # DC code lookups (failing)
    ("What is DC 7101?", "DC Code", "Should return hypertension info"),
    ("What is DC 7007?", "DC Code", "Should return hypertensive heart disease"),
    ("What is DC 6847?", "DC Code", "Should return sleep apnea info"),
    ("What is DC 6100?", "DC Code", "Should return hearing loss info"),
    
    # VR&E detail queries (returning only "how to apply")
    ("What is the VR&E subsistence allowance?", "VR&E", "Should return payment rates, not application info"),
    ("What disability rating do I need for VR&E?", "VR&E", "Should return 10%/20% requirements"),
    
    # Secondary conditions (returning wrong content)
    ("Can hypertension be secondary to PTSD?", "Secondary", "Should explain secondary service connection"),
    ("Can sleep apnea be secondary to PTSD?", "Secondary", "Should explain secondary service connection"),
]


def diagnose_single_query(query: str, pipeline: RAGPipeline, verbose: bool = True):
    """
    Run a single query through the RAG pipeline with detailed diagnostics.
    
    Returns dict with diagnostic info.
    """
    print(f"\n{'='*80}")
    print(f"QUERY: {query}")
    print(f"{'='*80}")
    
    # Get the vector store directly
    vector_store = pipeline.vector_store
    if vector_store is None:
        print("ERROR: Vector store not initialized!")
        return None
    
    # Step 1: Embed the query
    print("\n📊 STEP 1: Query Embedding")
    query_embedding = embed_query_cached(query, DEFAULT_EMBEDDING_MODEL)
    print(f"   Embedding dimension: {len(query_embedding)}")
    
    # Step 2: Search vector store (bypass all caching)
    print("\n🔍 STEP 2: Vector Store Search")
    results = vector_store.search(
        query_embedding, 
        k=10,  # Get more results for diagnostics
        min_score=0.3  # Lower threshold to see what's being retrieved
    )
    
    print(f"   Found {len(results)} chunks above min_score=0.3")
    
    # Step 3: Show retrieved chunks
    print("\n📄 STEP 3: Retrieved Chunks (ranked by similarity)")
    chunks_info = []
    for i, result in enumerate(results):
        doc = result.document
        score = result.score
        metadata = doc.metadata
        
        entry_id = metadata.get("entry_id", doc.id)
        topic = metadata.get("topic", "N/A")
        url = metadata.get("url", "N/A")
        content_preview = doc.text[:200].replace("\n", " ")
        
        print(f"\n   [{i+1}] Score: {score:.4f}")
        print(f"       Entry ID: {entry_id}")
        print(f"       Topic: {topic}")
        print(f"       URL: {url}")
        print(f"       Content: {content_preview}...")
        
        chunks_info.append({
            "rank": i + 1,
            "score": score,
            "entry_id": entry_id,
            "topic": topic,
            "url": url,
            "content_preview": content_preview
        })
    
    # Step 4: Run full RAG to see LLM response
    print("\n🤖 STEP 4: LLM Response (no caching)")
    response = pipeline.ask(query)
    
    print(f"\n   Model used: {response.model_used}")
    print(f"   Cache hit: {response.cache_hit}")
    print(f"   Chunks retrieved: {response.chunks_retrieved}")
    print(f"   Retrieval score: {response.retrieval_score}")
    print(f"   Weak retrieval: {response.weak_retrieval}")
    
    print(f"\n   ANSWER:")
    print(f"   {'-'*70}")
    # Print first 500 chars of answer
    answer_preview = response.answer[:500] if len(response.answer) > 500 else response.answer
    for line in answer_preview.split('\n'):
        print(f"   {line}")
    if len(response.answer) > 500:
        print(f"   ... (truncated, {len(response.answer)} chars total)")
    print(f"   {'-'*70}")
    
    print(f"\n   SOURCES CITED ({len(response.sources)}):")
    for src in response.sources[:5]:
        print(f"   - {src.get('title', 'N/A')}: {src.get('source_url', 'N/A')}")
    
    return {
        "query": query,
        "chunks_retrieved": chunks_info,
        "answer_preview": answer_preview,
        "model_used": response.model_used,
        "cache_hit": response.cache_hit,
        "retrieval_score": response.retrieval_score,
        "weak_retrieval": response.weak_retrieval,
        "sources": response.sources
    }


def run_all_failing_queries(pipeline: RAGPipeline):
    """Run all known failing queries and summarize issues."""
    print("\n" + "="*80)
    print("RUNNING ALL KNOWN FAILING QUERIES")
    print("="*80)
    
    results = []
    for query, category, expected in FAILING_QUERIES:
        print(f"\n{'─'*80}")
        print(f"Category: {category}")
        print(f"Expected: {expected}")
        
        result = diagnose_single_query(query, pipeline, verbose=True)
        if result:
            result["category"] = category
            result["expected"] = expected
            results.append(result)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    for r in results:
        top_topic = r["chunks_retrieved"][0]["topic"] if r["chunks_retrieved"] else "NONE"
        top_score = r["chunks_retrieved"][0]["score"] if r["chunks_retrieved"] else 0
        print(f"\n{r['category']}: {r['query'][:50]}...")
        print(f"   Expected: {r['expected'][:60]}...")
        print(f"   Top chunk: {top_topic} (score: {top_score:.3f})")
        print(f"   Cache hit: {r['cache_hit']}")
    
    return results


def search_corpus_for_content(pipeline: RAGPipeline, search_terms: list):
    """Search the corpus directly for specific terms to verify content exists."""
    print("\n" + "="*80)
    print("CORPUS CONTENT CHECK")
    print("="*80)
    
    # Load corpus directly
    corpus_path = Path("veteran-ai-spark/corpus/vbkb_restructured.json")
    with open(corpus_path, 'r') as f:
        corpus = json.load(f)
    
    for term in search_terms:
        print(f"\n🔎 Searching for: '{term}'")
        matches = []
        for entry in corpus:
            content = entry.get("content", "").lower()
            topic = entry.get("topic", "").lower()
            entry_id = entry.get("entry_id", "")
            
            if term.lower() in content or term.lower() in topic:
                matches.append({
                    "entry_id": entry_id,
                    "topic": entry.get("topic", ""),
                    "url": entry.get("url", ""),
                    "content_preview": entry.get("content", "")[:150]
                })
        
        print(f"   Found {len(matches)} entries containing '{term}'")
        for m in matches[:5]:
            print(f"   - {m['entry_id']}: {m['topic']}")
        if len(matches) > 5:
            print(f"   ... and {len(matches) - 5} more")


def main():
    parser = argparse.ArgumentParser(description="RAG Retrieval Diagnostic Tool")
    parser.add_argument("query", nargs="?", help="Single query to diagnose")
    parser.add_argument("--all-failing", action="store_true", help="Run all known failing queries")
    parser.add_argument("--check-corpus", nargs="+", help="Search corpus for specific terms")
    args = parser.parse_args()
    
    print("🔧 RAG Retrieval Diagnostic Tool")
    print("=" * 80)
    print("⚠️  Response caching is DISABLED for accurate diagnostics")
    print("=" * 80)
    
    # Initialize pipeline with caching disabled
    print("\nInitializing RAG pipeline...")
    pipeline = RAGPipeline(enable_response_cache=False)
    pipeline.initialize()
    print("✅ Pipeline initialized")
    
    if args.check_corpus:
        search_corpus_for_content(pipeline, args.check_corpus)
    elif args.all_failing:
        run_all_failing_queries(pipeline)
    elif args.query:
        diagnose_single_query(args.query, pipeline)
    else:
        # Default: run a few key failing queries
        print("\nNo query specified. Running sample failing queries...")
        sample_queries = [
            "What is the GI Bill?",
            "What is CHAMPVA?",
            "What is DC 7101?",
        ]
        for q in sample_queries:
            diagnose_single_query(q, pipeline)


if __name__ == "__main__":
    main()

