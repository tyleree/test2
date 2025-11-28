#!/usr/bin/env python3
"""
Corpus URL Audit Script

Generates a report of all URLs in the corpus for manual review.
Helps identify potentially incorrect URL mappings and hallucination risks.

Usage:
    python scripts/audit_corpus_urls.py [--output report.json]

Output:
    - URL summary with chunk counts
    - Flagged suspicious mappings (homepage URLs for specific topics)
    - Topic-to-URL mapping inconsistencies
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any
from datetime import datetime

CORPUS_PATH = "veteran-ai-spark/corpus/vbkb_restructured.json"
HOMEPAGE_URL = "https://veteransbenefitskb.com"

# Topics that should NOT link to homepage (likely mapping errors)
TOPICS_REQUIRING_SPECIFIC_URLS = [
    "mental disorder ratings", "ptsd", "anxiety", "depression",
    "filing a claim", "va claim", "bdd", "intent to file",
    "appeal", "higher level review", "board of veterans appeals",
    "presumptive conditions", "agent orange", "burn pit",
    "tdiu", "individual unemployability",
    "effective date", "back pay",
    "hypertension", "blood pressure",
    "tinnitus", "hearing loss",
    "sleep apnea",
    "diabetes",
    "migraines",
    "knee", "back", "shoulder", "ankle",
]

# Keywords that suggest content should link to specific pages
TOPIC_URL_HINTS = {
    "mental": ["mental", "ptsd", "anxiety", "depression", "bipolar", "schizophren"],
    "vaclaim": ["filing", "claim", "intent to file", "bdd", "application"],
    "appeal": ["appeal", "higher level", "hlr", "board", "bva"],
    "presumptive": ["presumptive", "agent orange", "burn pit", "gulf war"],
    "tdiu": ["tdiu", "unemployability", "iu"],
    "effective": ["effective date", "back pay", "retro"],
}


def load_corpus(corpus_path: str) -> List[Dict[str, Any]]:
    """Load the corpus JSON file."""
    with open(corpus_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_corpus(corpus: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze the corpus and generate URL audit report.
    
    Returns:
        Dictionary containing audit results
    """
    # Group chunks by URL
    url_to_chunks: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    topic_to_urls: Dict[str, List[str]] = defaultdict(list)
    
    for chunk in corpus:
        url = chunk.get("url", HOMEPAGE_URL)
        topic = chunk.get("topic", "Unknown")
        entry_id = chunk.get("entry_id", "unknown")
        content_preview = chunk.get("content", "")[:150]
        
        url_to_chunks[url].append({
            "entry_id": entry_id,
            "topic": topic,
            "content_preview": content_preview
        })
        
        if url not in topic_to_urls[topic]:
            topic_to_urls[topic].append(url)
    
    # Find suspicious mappings
    suspicious = []
    
    # 1. Homepage URLs for topics that should have specific pages
    homepage_chunks = url_to_chunks.get(HOMEPAGE_URL, [])
    for chunk in homepage_chunks:
        topic_lower = chunk["topic"].lower()
        for required_topic in TOPICS_REQUIRING_SPECIFIC_URLS:
            if required_topic.lower() in topic_lower:
                suspicious.append({
                    "type": "homepage_for_specific_topic",
                    "entry_id": chunk["entry_id"],
                    "topic": chunk["topic"],
                    "url": HOMEPAGE_URL,
                    "expected": f"Specific page for '{required_topic}'",
                    "content_preview": chunk["content_preview"]
                })
                break
    
    # 2. Topics with multiple different URLs (inconsistency)
    for topic, urls in topic_to_urls.items():
        unique_urls = list(set(urls))
        if len(unique_urls) > 2:  # Allow some variation, flag if > 2
            suspicious.append({
                "type": "topic_url_inconsistency",
                "topic": topic,
                "urls": unique_urls,
                "count": len(unique_urls)
            })
    
    # 3. Check for potential mismatches using keyword hints
    for chunk in corpus:
        url = chunk.get("url", "")
        content_lower = chunk.get("content", "").lower()
        
        for page, keywords in TOPIC_URL_HINTS.items():
            if any(kw in content_lower for kw in keywords):
                if page not in url.lower() and HOMEPAGE_URL not in url:
                    # Content mentions a topic but URL doesn't match
                    suspicious.append({
                        "type": "content_url_mismatch",
                        "entry_id": chunk.get("entry_id"),
                        "topic": chunk.get("topic"),
                        "url": url,
                        "expected_page": page,
                        "matched_keywords": [kw for kw in keywords if kw in content_lower]
                    })
                break
    
    # Generate summary statistics
    url_stats = []
    for url, chunks in sorted(url_to_chunks.items(), key=lambda x: -len(x[1])):
        topics = list(set(c["topic"] for c in chunks))
        url_stats.append({
            "url": url,
            "chunk_count": len(chunks),
            "topics": topics[:5],  # Top 5 topics
            "total_topics": len(topics)
        })
    
    return {
        "generated_at": datetime.now().isoformat(),
        "corpus_path": CORPUS_PATH,
        "total_chunks": len(corpus),
        "unique_urls": len(url_to_chunks),
        "homepage_chunks": len(homepage_chunks),
        "suspicious_count": len(suspicious),
        "url_summary": url_stats[:50],  # Top 50 URLs by chunk count
        "suspicious_mappings": suspicious[:100],  # First 100 suspicious items
        "topic_url_mapping": {t: urls for t, urls in topic_to_urls.items() if len(urls) > 1}
    }


def print_report(report: Dict[str, Any]) -> None:
    """Print a human-readable summary of the audit report."""
    print("\n" + "="*70)
    print("CORPUS URL AUDIT REPORT")
    print("="*70)
    print(f"Generated: {report['generated_at']}")
    print(f"Corpus: {report['corpus_path']}")
    print()
    
    print("SUMMARY:")
    print(f"  Total chunks: {report['total_chunks']}")
    print(f"  Unique URLs: {report['unique_urls']}")
    print(f"  Homepage-only chunks: {report['homepage_chunks']}")
    print(f"  Suspicious mappings: {report['suspicious_count']}")
    print()
    
    print("TOP 10 URLs BY USAGE:")
    for i, url_info in enumerate(report['url_summary'][:10], 1):
        print(f"  {i}. {url_info['url']}")
        print(f"     Chunks: {url_info['chunk_count']}, Topics: {url_info['total_topics']}")
    print()
    
    if report['suspicious_mappings']:
        print("SUSPICIOUS MAPPINGS (first 10):")
        for i, issue in enumerate(report['suspicious_mappings'][:10], 1):
            print(f"\n  {i}. Type: {issue['type']}")
            if 'entry_id' in issue:
                print(f"     Entry: {issue['entry_id']}")
            if 'topic' in issue:
                print(f"     Topic: {issue['topic']}")
            if 'url' in issue:
                print(f"     URL: {issue['url']}")
            if 'expected' in issue:
                print(f"     Expected: {issue['expected']}")
            if 'expected_page' in issue:
                print(f"     Expected page: {issue['expected_page']}")
    
    print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(description="Audit corpus URLs for potential issues")
    parser.add_argument("--corpus", default=CORPUS_PATH, help="Path to corpus JSON")
    parser.add_argument("--output", "-o", help="Output JSON report file")
    parser.add_argument("--quiet", "-q", action="store_true", help="Only output JSON")
    args = parser.parse_args()
    
    # Load and analyze corpus
    corpus = load_corpus(args.corpus)
    report = analyze_corpus(corpus)
    
    # Print human-readable report
    if not args.quiet:
        print_report(report)
    
    # Save JSON report if requested
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        print(f"\nFull report saved to: {output_path}")
    
    # Return exit code based on suspicious items
    if report['suspicious_count'] > 20:
        print(f"\nWARNING: {report['suspicious_count']} suspicious mappings found!")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())

