#!/usr/bin/env python3
"""
Simple ingestion script to process the corpus file without API dependencies.
"""

import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.utils import chunk_text_markdown_aware, generate_doc_id, generate_chunk_id

def process_file(file_path):
    """Process a single markdown file."""
    print(f"Processing: {file_path}")
    
    # Read file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"File size: {len(content):,} characters")
    
    # Extract title
    lines = content.split('\n')
    title = "Veterans Benefits Knowledge Base"
    for line in lines[:10]:
        if line.startswith('# '):
            title = line[2:].strip()
            break
    
    # Generate metadata
    source_url = "https://veteransbenefits.ai/vbkb"
    doc_id = generate_doc_id(source_url, title)
    
    print(f"Title: {title}")
    print(f"Source URL: {source_url}")
    print(f"Doc ID: {doc_id}")
    
    # Chunk the document
    chunks = chunk_text_markdown_aware(content, chunk_size=700, overlap=90)
    
    print(f"\nChunking results:")
    print(f"Total chunks: {len(chunks)}")
    
    total_tokens = sum(chunk['token_count'] for chunk in chunks)
    print(f"Total tokens: {total_tokens:,}")
    
    # Show sample chunks
    print(f"\nSample chunks:")
    for i, chunk in enumerate(chunks[:3]):
        chunk_id = generate_chunk_id()
        print(f"\nChunk {i+1} (ID: {chunk_id}):")
        print(f"  Title: {chunk.get('title', 'N/A')}")
        print(f"  Section: {chunk.get('section', 'N/A')}")
        print(f"  Tokens: {chunk['token_count']}")
        print(f"  Text preview: {chunk['text'][:200]}...")
    
    print(f"\nIngestion would create {len(chunks)} chunks with uniform metadata:")
    print("- text: Full chunk content")
    print("- title: Document title")
    print("- section: Section heading (if any)")
    print("- source_url: Canonical URL")
    print("- doc_id: Stable document identifier")
    print("- chunk_id: Unique chunk identifier")
    print("- token_count: Estimated token count")
    
    return len(chunks), total_tokens

def main():
    corpus_dir = Path("corpus")
    
    if not corpus_dir.exists():
        print("Error: corpus directory not found")
        return
    
    md_files = list(corpus_dir.glob("*.md"))
    
    if not md_files:
        print("Error: no .md files found in corpus directory")
        return
    
    print(f"Found {len(md_files)} markdown files")
    print("=" * 60)
    
    total_chunks = 0
    total_tokens = 0
    
    for file_path in md_files:
        chunks, tokens = process_file(file_path)
        total_chunks += chunks
        total_tokens += tokens
        print("=" * 60)
    
    print(f"\nSUMMARY:")
    print(f"Files processed: {len(md_files)}")
    print(f"Total chunks: {total_chunks}")
    print(f"Total tokens: {total_tokens:,}")
    print(f"Average tokens per chunk: {total_tokens // total_chunks if total_chunks > 0 else 0}")
    
    print(f"\nTo run actual ingestion with Pinecone:")
    print("1. Set your OPENAI_API_KEY and PINECONE_API_KEY in .env")
    print("2. Run: python -m app.ingestion --src ./corpus --index your-index-name")

if __name__ == "__main__":
    main()
