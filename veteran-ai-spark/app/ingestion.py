"""
Document ingestion system with uniform metadata schema for Pinecone.
Supports markdown-aware chunking and stable metadata generation.
"""

import os
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
from dataclasses import dataclass

import openai
from pinecone import Pinecone
import markdown

from .config import config
from .utils import (
    chunk_text_markdown_aware, 
    generate_doc_id, 
    generate_chunk_id,
    get_token_count,
    format_timestamp
)

logger = logging.getLogger(__name__)

@dataclass
class DocumentChunk:
    """Represents a document chunk with uniform metadata."""
    text: str
    title: str
    section: str
    source_url: str
    doc_id: str
    chunk_id: str
    token_count: int
    embedding: Optional[List[float]] = None

class DocumentIngester:
    """Handles document ingestion with uniform metadata schema."""
    
    def __init__(self):
        try:
            self.openai_client = openai.OpenAI(
                api_key=config.openai_api_key,
                timeout=60.0,
                max_retries=3
            )
        except Exception as e:
            print(f"Warning: OpenAI client initialization failed: {e}")
            self.openai_client = None
        
        try:
            self.pc = Pinecone(api_key=config.pinecone_api_key)
            self.index = self.pc.Index(config.pinecone_index)
        except Exception as e:
            print(f"Warning: Pinecone client initialization failed: {e}")
            self.pc = None
            self.index = None
        
    def extract_metadata_from_path(self, file_path: Path) -> Dict[str, str]:
        """Extract metadata from file path and content."""
        # Generate source URL from file path
        # This should be customized based on your URL structure
        relative_path = file_path.relative_to(file_path.parents[1])  # Adjust depth as needed
        source_url = f"https://veteransbenefits.ai/{relative_path}".replace('\\', '/')
        source_url = source_url.replace('.md', '').replace('.txt', '')
        
        return {
            'source_url': source_url,
            'file_path': str(file_path)
        }
    
    def extract_title_from_content(self, content: str) -> str:
        """Extract document title from content."""
        lines = content.split('\n')
        
        # Look for markdown h1 header
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
        
        # Fallback to first non-empty line
        for line in lines[:5]:
            line = line.strip()
            if line and not line.startswith('#'):
                return line[:100]  # Truncate long titles
        
        return "Untitled Document"
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        try:
            response = self.openai_client.embeddings.create(
                model=config.embed_model,
                input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise
    
    def process_document(self, file_path: Path) -> List[DocumentChunk]:
        """Process a single document into chunks with metadata."""
        logger.info(f"Processing document: {file_path}")
        
        # Read file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return []
        
        # Extract metadata
        metadata = self.extract_metadata_from_path(file_path)
        title = self.extract_title_from_content(content)
        doc_id = generate_doc_id(metadata['source_url'], title)
        
        # Convert markdown to text if needed
        if file_path.suffix.lower() == '.md':
            # Keep markdown for chunking, but clean for processing
            text_content = content
        else:
            text_content = content
        
        # Chunk the document
        chunks = chunk_text_markdown_aware(
            text_content, 
            chunk_size=700, 
            overlap=90
        )
        
        # Create DocumentChunk objects
        document_chunks = []
        for chunk_data in chunks:
            chunk = DocumentChunk(
                text=chunk_data['text'],
                title=title,
                section=chunk_data.get('section', ''),
                source_url=metadata['source_url'],
                doc_id=doc_id,
                chunk_id=generate_chunk_id(),
                token_count=chunk_data['token_count']
            )
            document_chunks.append(chunk)
        
        logger.info(f"Created {len(document_chunks)} chunks from {file_path}")
        return document_chunks
    
    def batch_embed_chunks(self, chunks: List[DocumentChunk], batch_size: int = 100) -> None:
        """Generate embeddings for chunks in batches."""
        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [chunk.text for chunk in batch]
            
            try:
                embeddings = self.generate_embeddings(texts)
                for chunk, embedding in zip(batch, embeddings):
                    chunk.embedding = embedding
                    
                logger.info(f"Generated embeddings for batch {i//batch_size + 1}")
                
            except Exception as e:
                logger.error(f"Failed to generate embeddings for batch {i//batch_size + 1}: {e}")
                raise
    
    def upsert_to_pinecone(self, chunks: List[DocumentChunk], namespace: str = None) -> None:
        """Upsert chunks to Pinecone with uniform metadata."""
        if not namespace:
            namespace = config.pinecone_namespace
            
        logger.info(f"Upserting {len(chunks)} chunks to Pinecone namespace '{namespace}'")
        
        # Prepare vectors for upsert
        vectors = []
        for chunk in chunks:
            if not chunk.embedding:
                logger.warning(f"Chunk {chunk.chunk_id} has no embedding, skipping")
                continue
                
            # Ensure all required metadata fields are present
            metadata = {
                'text': chunk.text,
                'title': chunk.title,
                'section': chunk.section,
                'source_url': chunk.source_url,
                'doc_id': chunk.doc_id,
                'chunk_id': chunk.chunk_id,
                'token_count': chunk.token_count,
                'ingested_at': format_timestamp()
            }
            
            vectors.append({
                'id': chunk.chunk_id,
                'values': chunk.embedding,
                'metadata': metadata
            })
        
        # Upsert in batches
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            try:
                self.index.upsert(vectors=batch, namespace=namespace)
                logger.info(f"Upserted batch {i//batch_size + 1}/{(len(vectors)-1)//batch_size + 1}")
            except Exception as e:
                logger.error(f"Failed to upsert batch {i//batch_size + 1}: {e}")
                raise
    
    def ingest_directory(self, source_dir: Path, namespace: str = None, dry_run: bool = False) -> Dict[str, Any]:
        """Ingest all documents from a directory."""
        logger.info(f"Starting ingestion from {source_dir}")
        
        # Find all supported files
        supported_extensions = {'.md', '.txt'}
        files = []
        for ext in supported_extensions:
            files.extend(source_dir.rglob(f'*{ext}'))
        
        logger.info(f"Found {len(files)} files to process")
        
        if dry_run:
            logger.info("DRY RUN - No data will be uploaded")
        
        # Process all documents
        all_chunks = []
        stats = {
            'files_processed': 0,
            'files_failed': 0,
            'chunks_created': 0,
            'total_tokens': 0
        }
        
        for file_path in files:
            try:
                chunks = self.process_document(file_path)
                all_chunks.extend(chunks)
                stats['files_processed'] += 1
                stats['chunks_created'] += len(chunks)
                stats['total_tokens'] += sum(chunk.token_count for chunk in chunks)
                
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                stats['files_failed'] += 1
        
        if not dry_run and all_chunks:
            # Generate embeddings
            self.batch_embed_chunks(all_chunks)
            
            # Upsert to Pinecone
            self.upsert_to_pinecone(all_chunks, namespace)
        
        logger.info(f"Ingestion complete: {stats}")
        return stats

def dry_run_ingest(source_dir: Path) -> Dict[str, Any]:
    """Dry run ingestion without API calls."""
    print(f"Analyzing files in {source_dir}")
    
    # Find all supported files
    supported_extensions = {'.md', '.txt'}
    files = []
    for ext in supported_extensions:
        files.extend(source_dir.rglob(f'*{ext}'))
    
    print(f"Found {len(files)} files to process")
    
    stats = {
        'files_processed': 0,
        'files_failed': 0,
        'chunks_created': 0,
        'total_tokens': 0
    }
    
    for file_path in files:
        try:
            print(f"Processing: {file_path}")
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print(f"  File size: {len(content):,} characters")
            
            # Extract title
            title = "Document"
            lines = content.split('\n')
            for line in lines[:10]:
                if line.startswith('# '):
                    title = line[2:].strip()
                    break
            
            print(f"  Title: {title}")
            
            # Chunk the document
            chunks = chunk_text_markdown_aware(content, chunk_size=700, overlap=90)
            total_tokens = sum(chunk['token_count'] for chunk in chunks)
            
            print(f"  Chunks: {len(chunks)}")
            print(f"  Tokens: {total_tokens:,}")
            
            stats['files_processed'] += 1
            stats['chunks_created'] += len(chunks)
            stats['total_tokens'] += total_tokens
            
        except Exception as e:
            print(f"  ERROR: {e}")
            stats['files_failed'] += 1
    
    return stats

def main():
    """CLI entry point for document ingestion."""
    parser = argparse.ArgumentParser(description='Ingest documents into Pinecone')
    parser.add_argument('--src', type=Path, required=True, help='Source directory')
    parser.add_argument('--index', type=str, help='Pinecone index name')
    parser.add_argument('--namespace', type=str, help='Pinecone namespace')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Override config if provided
    if args.index:
        config.pinecone_index = args.index
    if args.namespace:
        config.pinecone_namespace = args.namespace
    
    # For dry-run, use simplified processing
    if args.dry_run:
        print("DRY RUN MODE - No API calls will be made")
        stats = dry_run_ingest(args.src)
    else:
        # Run full ingestion
        ingester = DocumentIngester()
        stats = ingester.ingest_directory(
            source_dir=args.src,
            namespace=args.namespace,
            dry_run=args.dry_run
        )
    
    print(f"\nIngestion Results:")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Files failed: {stats['files_failed']}")
    print(f"Chunks created: {stats['chunks_created']}")
    print(f"Total tokens: {stats['total_tokens']:,}")

if __name__ == '__main__':
    main()

