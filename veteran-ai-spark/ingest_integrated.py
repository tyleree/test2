#!/usr/bin/env python3
"""
Integrated Embedding Corpus Ingestion Script for Pinecone
Uses Pinecone's integrated embedding feature - no OpenAI API required
"""

import os
import re
import time
import itertools
from typing import List, Dict, Any, Generator
from dataclasses import dataclass
from dotenv import load_dotenv
from pinecone import Pinecone

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

class IntegratedEmbeddingIngester:
    """Corpus ingester using Pinecone's integrated embedding feature"""
    
    def __init__(self, index_name: str = "thriving-walnut"):
        # Initialize Pinecone
        pinecone_api_key = os.getenv('PINECONE_API_KEY')
        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY not found in environment")
            
        self.pc = Pinecone(api_key=pinecone_api_key)
        
        # Index configuration
        self.index_name = index_name
        self.namespace = "production"
        
        # Connect to index using index name
        try:
            self.index = self.pc.Index(self.index_name)
            print(f"✅ Connected to Pinecone index: {self.index_name}")
            
            # Get index stats
            stats = self.index.describe_index_stats()
            print(f"📊 Index stats: {stats.total_vector_count} vectors")
            if hasattr(stats, 'dimension'):
                print(f"📐 Dimension: {stats.dimension}")
            
        except Exception as e:
            print(f"❌ Failed to connect to Pinecone index '{self.index_name}': {e}")
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
                        "version": "v1"
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
    
    def chunks_generator(self, iterable, batch_size: int = 96):
        """
        Helper function to break an iterable into chunks
        Using 96 as per Pinecone guide for text records with integrated embedding
        """
        it = iter(iterable)
        chunk = tuple(itertools.islice(it, batch_size))
        while chunk:
            yield chunk
            chunk = tuple(itertools.islice(it, batch_size))
    
    def upsert_corpus(self, file_path: str, batch_size: int = 96, dry_run: bool = False):
        """
        Main function to upsert corpus using Pinecone's integrated embedding
        Following the official guide: https://docs.pinecone.io/guides/index-data/upsert-data
        """
        if dry_run:
            print("🧪 DRY RUN MODE - No actual upserts will be made")
        
        print(f"🚀 Starting corpus ingestion with integrated embedding...")
        print(f"📊 Batch size: {batch_size} (optimal for text records)")
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
                # Prepare records for integrated embedding
                # Following the guide format exactly
                records = []
                for chunk in chunk_batch:
                    record = {
                        "_id": chunk.chunk_id,
                        "text": chunk.content,  # This field will be embedded automatically
                        **chunk.metadata  # Include all metadata
                    }
                    records.append(record)
                
                if not dry_run:
                    print(f"⬆️ Upserting {len(records)} records with integrated embedding...")
                    
                    # Try the new upsert_records method first
                    try:
                        # Method 1: Direct upsert_records call
                        response = self.index.upsert_records(
                            records=records,
                            namespace=self.namespace
                        )
                        print(f"✅ Upserted {len(records)} records using upsert_records")
                        total_upserted += len(records)
                        
                    except AttributeError:
                        # Method 2: Try alternative API call format
                        print("🔄 Trying alternative integrated embedding format...")
                        try:
                            response = self.index.upsert(
                                vectors=[],  # Empty vectors for integrated embedding
                                records=records,
                                namespace=self.namespace
                            )
                            print(f"✅ Upserted {len(records)} records using alternative format")
                            total_upserted += len(records)
                            
                        except Exception as e2:
                            print(f"❌ Alternative format failed: {e2}")
                            print("🔄 Falling back to text field approach...")
                            
                            # Method 3: Try with 'chunk_text' field name
                            records_alt = []
                            for chunk in chunk_batch:
                                record = {
                                    "_id": chunk.chunk_id,
                                    "chunk_text": chunk.content,  # Try this field name
                                    **chunk.metadata
                                }
                                records_alt.append(record)
                            
                            response = self.index.upsert_records(
                                records=records_alt,
                                namespace=self.namespace
                            )
                            print(f"✅ Upserted {len(records)} records using chunk_text field")
                            total_upserted += len(records)
                            
                else:
                    print(f"🧪 Would upsert {len(records)} records with integrated embedding (dry run)")
                    total_upserted += len(records)
                
                # Small delay to avoid rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                print(f"❌ Error processing batch {batch_count}: {e}")
                print(f"📝 Error type: {type(e).__name__}")
                
                # If this is the first batch, show more details
                if batch_count == 1:
                    print(f"🔍 First record structure: {records[0] if 'records' in locals() else 'N/A'}")
                
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
    
    parser = argparse.ArgumentParser(description='Ingest corpus using Pinecone integrated embedding')
    parser.add_argument('--index', default='thriving-walnut', help='Pinecone index name')
    parser.add_argument('--corpus', default='corpus/vbkb_CG.md', help='Path to corpus file')
    parser.add_argument('--batch-size', type=int, default=96, help='Batch size for text records (max 96)')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode - no actual upserts')
    
    args = parser.parse_args()
    
    try:
        ingester = IntegratedEmbeddingIngester(index_name=args.index)
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
