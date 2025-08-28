#!/usr/bin/env python3
"""
Simple Corpus Ingestion Script for Pinecone
Uses standard vector upsert without requiring OpenAI embeddings
"""

import os
import re
import time
import itertools
from typing import List, Dict, Any, Generator
from dataclasses import dataclass
from dotenv import load_dotenv
from pinecone import Pinecone
import random
import hashlib

# Load environment variables
load_dotenv('../env.txt')
load_dotenv('.env')

@dataclass
class ChunkData:
    """Represents a parsed chunk from the corpus"""
    chunk_id: str
    content: str
    heading: str
    chunk_number: int
    total_chunks: int
    word_count: int
    metadata: Dict[str, Any]

class SimpleCorpusIngester:
    """Simple corpus ingester that uses dummy vectors for testing"""
    
    def __init__(self):
        # Initialize Pinecone
        pinecone_api_key = os.getenv('PINECONE_API_KEY')
        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY not found in environment")
            
        self.pc = Pinecone(api_key=pinecone_api_key)
        
        # Index configuration - use the actual index name
        self.index_name = os.getenv('PINECONE_INDEX_NAME', 'veterans-benefits-kb')
        self.namespace = "production"
        
        # Connect to index using index name (not host)
        try:
            self.index = self.pc.Index(self.index_name)
            print(f"✅ Connected to Pinecone index: {self.index_name}")
            
            # Get index stats
            stats = self.index.describe_index_stats()
            print(f"📊 Index stats: {stats.total_vector_count} vectors, dimension: {stats.dimension}")
            
        except Exception as e:
            print(f"❌ Failed to connect to Pinecone index: {e}")
            raise
    
    def parse_corpus(self, file_path: str) -> Generator[ChunkData, None, None]:
        """Parse the corpus file and extract chunks with metadata"""
        print(f"📖 Parsing corpus file: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract total chunks from header
        total_chunks_match = re.search(r'Total chunks: (\d+)', content)
        total_chunks = int(total_chunks_match.group(1)) if total_chunks_match else 0
        
        # Split content by chunk separators
        chunk_pattern = r'<!-- Chunk (\d+)/(\d+) \| Heading: ([^|]+) \| Words: (\d+) -->'
        chunks = re.split(chunk_pattern, content)
        
        chunk_count = 0
        
        # Process chunks (skip first element which is header)
        for i in range(1, len(chunks), 5):
            if i + 4 >= len(chunks):
                break
                
            try:
                chunk_num = int(chunks[i])
                total = int(chunks[i + 1])
                heading = chunks[i + 2].strip()
                word_count = int(chunks[i + 3])
                chunk_content = chunks[i + 4].strip()
                
                # Skip empty chunks
                if not chunk_content or len(chunk_content.strip()) < 50:
                    continue
                    
                # Clean content
                chunk_content = self._clean_content(chunk_content)
                
                # Create chunk data
                chunk_data = ChunkData(
                    chunk_id=f"chunk_{chunk_num:04d}",
                    content=chunk_content,
                    heading=heading,
                    chunk_number=chunk_num,
                    total_chunks=total,
                    word_count=word_count,
                    metadata={
                        "heading": heading,
                        "chunk_number": chunk_num,
                        "total_chunks": total,
                        "word_count": word_count,
                        "source_url": "https://veteransbenefitskb.com",
                        "document_type": "va_benefits_guide",
                        "version": "v1",
                        "content_preview": chunk_content[:200] + "..." if len(chunk_content) > 200 else chunk_content
                    }
                )
                
                chunk_count += 1
                yield chunk_data
                
            except (ValueError, IndexError) as e:
                print(f"⚠️ Skipping malformed chunk at position {i}: {e}")
                continue
        
        print(f"✅ Parsed {chunk_count} valid chunks from corpus")
    
    def _clean_content(self, content: str) -> str:
        """Clean and normalize chunk content"""
        # Remove excessive whitespace
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        content = re.sub(r'[ \t]+', ' ', content)
        
        # Remove markdown artifacts
        content = re.sub(r'^\s*\*\s*\*\s*\*\s*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'^---+$', '', content, flags=re.MULTILINE)
        
        return content.strip()
    
    def generate_dummy_vector(self, text: str, dimension: int = 1024) -> List[float]:
        """
        Generate a deterministic dummy vector based on text content
        This is for testing purposes - in production you'd use real embeddings
        """
        # Create a deterministic seed from text
        seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        random.seed(seed)
        
        # Generate normalized random vector
        vector = [random.gauss(0, 1) for _ in range(dimension)]
        
        # Normalize the vector
        magnitude = sum(x*x for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x/magnitude for x in vector]
        
        return vector
    
    def chunks_generator(self, iterable, batch_size: int = 100):
        """Helper function to break an iterable into chunks"""
        it = iter(iterable)
        chunk = tuple(itertools.islice(it, batch_size))
        while chunk:
            yield chunk
            chunk = tuple(itertools.islice(it, batch_size))
    
    def upsert_corpus(self, file_path: str, batch_size: int = 100, dry_run: bool = False):
        """Main function to upsert corpus to Pinecone"""
        if dry_run:
            print("🧪 DRY RUN MODE - No actual upserts will be made")
        
        print(f"🚀 Starting corpus ingestion...")
        print(f"📊 Batch size: {batch_size}")
        print(f"🎯 Target index: {self.index_name}")
        print(f"📂 Namespace: {self.namespace}")
        
        # Parse all chunks first
        all_chunks = list(self.parse_corpus(file_path))
        total_chunks = len(all_chunks)
        
        if total_chunks == 0:
            print("❌ No chunks found in corpus file")
            return
        
        print(f"📦 Total chunks to process: {total_chunks}")
        
        # Process in batches
        batch_count = 0
        total_upserted = 0
        
        for chunk_batch in self.chunks_generator(all_chunks, batch_size):
            batch_count += 1
            batch_size_actual = len(chunk_batch)
            
            print(f"\n📦 Processing batch {batch_count} ({batch_size_actual} chunks)...")
            
            try:
                # Prepare vectors for upsert
                vectors = []
                for chunk in chunk_batch:
                    # Generate dummy vector (deterministic based on content)
                    vector = self.generate_dummy_vector(chunk.content)
                    
                    vector_data = {
                        "id": chunk.chunk_id,
                        "values": vector,
                        "metadata": chunk.metadata
                    }
                    vectors.append(vector_data)
                
                # Upsert to Pinecone
                if not dry_run:
                    print(f"⬆️ Upserting {len(vectors)} vectors to Pinecone...")
                    upsert_response = self.index.upsert(
                        vectors=vectors,
                        namespace=self.namespace
                    )
                    print(f"✅ Upserted {upsert_response.upserted_count} vectors")
                    total_upserted += upsert_response.upserted_count
                else:
                    print(f"🧪 Would upsert {len(vectors)} vectors (dry run)")
                    total_upserted += len(vectors)
                
                # Small delay to avoid rate limiting
                time.sleep(0.2)
                
            except Exception as e:
                print(f"❌ Error processing batch {batch_count}: {e}")
                continue
        
        print(f"\n🎉 Ingestion complete!")
        print(f"📊 Total chunks processed: {total_upserted}/{total_chunks}")
        
        if not dry_run and total_upserted > 0:
            # Wait for indexing to complete
            print("⏳ Waiting for indexing to complete...")
            time.sleep(10)
            
            try:
                # Verify ingestion
                stats = self.index.describe_index_stats()
                print(f"📈 Index stats after ingestion:")
                print(f"   Total vectors: {stats.total_vector_count}")
                namespace_stats = stats.namespaces.get(self.namespace, {})
                print(f"   Namespace '{self.namespace}': {namespace_stats.get('vector_count', 0)} vectors")
            except Exception as e:
                print(f"⚠️ Could not verify ingestion stats: {e}")

def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Simple corpus ingestion into Pinecone')
    parser.add_argument('--corpus', default='corpus/vbkb_CG.md', help='Path to corpus file')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for upserts')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode - no actual upserts')
    
    args = parser.parse_args()
    
    try:
        ingester = SimpleCorpusIngester()
        ingester.upsert_corpus(
            file_path=args.corpus,
            batch_size=args.batch_size,
            dry_run=args.dry_run
        )
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
