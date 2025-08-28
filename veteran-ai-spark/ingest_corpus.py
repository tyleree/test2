#!/usr/bin/env python3
"""
Corpus Ingestion Script for Pinecone
Following: https://docs.pinecone.io/guides/index-data/upsert-data

Ingests vbkb_CG.md corpus into Pinecone index with proper chunking and metadata.
"""

import os
import re
import time
import itertools
from typing import List, Dict, Any, Generator, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI

# Load environment variables
load_dotenv('env.txt')
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

class CorpusIngester:
    """Handles corpus parsing and Pinecone ingestion following official guidelines"""
    
    def __init__(self):
        # Initialize Pinecone
        self.pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
        
        # Initialize OpenAI for embeddings
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Index configuration
        self.index_host = "thriving-walnut"  # As specified by user
        self.index_name = os.getenv('PINECONE_INDEX_NAME', 'veterans-benefits-kb')
        self.namespace = "production"  # Use production namespace
        
        # Connect to index
        try:
            self.index = self.pc.Index(host=self.index_host)
            print(f"✅ Connected to Pinecone index: {self.index_host}")
        except Exception as e:
            print(f"❌ Failed to connect to Pinecone index: {e}")
            raise
            
        # Embedding configuration
        self.embedding_model = "text-embedding-3-large"
        self.embedding_dimensions = 1024  # Match your index dimensions
        
    def parse_corpus(self, file_path: str) -> Generator[ChunkData, None, None]:
        """
        Parse the corpus file and extract chunks with metadata
        """
        print(f"📖 Parsing corpus file: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract total chunks from header
        total_chunks_match = re.search(r'Total chunks: (\d+)', content)
        total_chunks = int(total_chunks_match.group(1)) if total_chunks_match else 0
        
        # Split content by chunk separators
        chunk_pattern = r'<!-- Chunk (\d+)/(\d+) \| Heading: ([^|]+) \| Words: (\d+) -->'
        chunks = re.split(chunk_pattern, content)
        
        current_heading = "Unknown"
        chunk_count = 0
        
        # Process chunks (skip first element which is header)
        for i in range(1, len(chunks), 5):  # Every 5th element starts a new chunk
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
        
        # Clean up table formatting
        content = re.sub(r'\|\s*-+\s*\|', '|---|', content)
        
        return content.strip()
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for text chunks using OpenAI
        """
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=texts,
                dimensions=self.embedding_dimensions
            )
            return [embedding.embedding for embedding in response.data]
        except Exception as e:
            print(f"❌ Failed to generate embeddings: {e}")
            # Fallback to ada-002 if 3-large fails
            try:
                print("🔄 Trying fallback embedding model...")
                response = self.openai_client.embeddings.create(
                    model="text-embedding-ada-002",
                    input=texts
                )
                embeddings = [embedding.embedding for embedding in response.data]
                # Truncate to 1024 dimensions if needed
                return [emb[:self.embedding_dimensions] for emb in embeddings]
            except Exception as e2:
                print(f"❌ Fallback embedding also failed: {e2}")
                raise
    
    def chunks_generator(self, iterable, batch_size: int = 100):
        """
        Helper function to break an iterable into chunks of size batch_size
        Following Pinecone best practices from the guide
        """
        it = iter(iterable)
        chunk = tuple(itertools.islice(it, batch_size))
        while chunk:
            yield chunk
            chunk = tuple(itertools.islice(it, batch_size))
    
    def upsert_corpus(self, file_path: str, batch_size: int = 96, dry_run: bool = False, use_integrated_embedding: bool = True):
        """
        Main function to upsert corpus to Pinecone following official guide
        Supports both integrated embedding and manual embedding generation
        """
        if dry_run:
            print("🧪 DRY RUN MODE - No actual upserts will be made")
        
        print(f"🚀 Starting corpus ingestion...")
        print(f"📊 Batch size: {batch_size}")
        print(f"🎯 Target index: {self.index_host}")
        print(f"📂 Namespace: {self.namespace}")
        print(f"🔮 Using integrated embedding: {use_integrated_embedding}")
        
        # Parse all chunks first
        all_chunks = list(self.parse_corpus(file_path))
        total_chunks = len(all_chunks)
        
        if total_chunks == 0:
            print("❌ No chunks found in corpus file")
            return
        
        print(f"📦 Total chunks to process: {total_chunks}")
        
        # Process in batches following Pinecone guide
        batch_count = 0
        total_upserted = 0
        
        for chunk_batch in self.chunks_generator(all_chunks, batch_size):
            batch_count += 1
            batch_size_actual = len(chunk_batch)
            
            print(f"\n📦 Processing batch {batch_count} ({batch_size_actual} chunks)...")
            
            try:
                if use_integrated_embedding:
                    # Use Pinecone's integrated embedding (recommended approach)
                    print(f"🔮 Using Pinecone integrated embedding...")
                    
                    # Prepare records for integrated embedding
                    records = []
                    for chunk in chunk_batch:
                        record = {
                            "_id": chunk.chunk_id,
                            "chunk_text": chunk.content,  # This field will be embedded automatically
                            **chunk.metadata  # Include all metadata
                        }
                        records.append(record)
                    
                    # Upsert using integrated embedding
                    if not dry_run:
                        print(f"⬆️ Upserting {len(records)} records with integrated embedding...")
                        upsert_response = self.index.upsert_records(
                            namespace=self.namespace,
                            records=records
                        )
                        print(f"✅ Upserted {len(records)} records")
                        total_upserted += len(records)
                    else:
                        print(f"🧪 Would upsert {len(records)} records with integrated embedding (dry run)")
                        total_upserted += len(records)
                
                else:
                    # Manual embedding generation (fallback)
                    print(f"🔮 Generating embeddings manually...")
                    texts = [chunk.content for chunk in chunk_batch]
                    embeddings = self.generate_embeddings(texts)
                    
                    # Prepare vectors for upsert
                    vectors = []
                    for chunk, embedding in zip(chunk_batch, embeddings):
                        vector_data = {
                            "id": chunk.chunk_id,
                            "values": embedding,
                            "metadata": chunk.metadata
                        }
                        vectors.append(vector_data)
                    
                    # Upsert to Pinecone (following the guide format)
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
                time.sleep(0.1)
                
            except Exception as e:
                print(f"❌ Error processing batch {batch_count}: {e}")
                # If integrated embedding fails, try manual embedding
                if use_integrated_embedding and "upsert_records" in str(e):
                    print("🔄 Integrated embedding failed, falling back to manual embedding...")
                    use_integrated_embedding = False
                    continue
                else:
                    continue
        
        print(f"\n🎉 Ingestion complete!")
        print(f"📊 Total chunks processed: {total_upserted}/{total_chunks}")
        
        if not dry_run:
            # Wait for indexing to complete
            print("⏳ Waiting for indexing to complete...")
            time.sleep(10)
            
            # Verify ingestion
            stats = self.index.describe_index_stats()
            print(f"📈 Index stats after ingestion:")
            print(f"   Total vectors: {stats.total_vector_count}")
            print(f"   Namespace '{self.namespace}': {stats.namespaces.get(self.namespace, {}).get('vector_count', 0)} vectors")

def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ingest corpus into Pinecone following official guide')
    parser.add_argument('--corpus', default='corpus/vbkb_CG.md', help='Path to corpus file')
    parser.add_argument('--batch-size', type=int, default=96, help='Batch size for upserts (96 for text, 1000 for vectors)')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode - no actual upserts')
    parser.add_argument('--manual-embedding', action='store_true', help='Use manual embedding instead of integrated')
    
    args = parser.parse_args()
    
    try:
        ingester = CorpusIngester()
        ingester.upsert_corpus(
            file_path=args.corpus,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            use_integrated_embedding=not args.manual_embedding
        )
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
