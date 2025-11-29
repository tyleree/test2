-- pgvector Setup for Veterans Benefits AI
-- This script sets up the PostgreSQL database with pgvector extension
-- for vector similarity search benchmarking

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop existing table if recreating
DROP TABLE IF EXISTS corpus_embeddings;

-- Create embeddings table with vector column
CREATE TABLE corpus_embeddings (
    id SERIAL PRIMARY KEY,
    chunk_id VARCHAR(128) UNIQUE NOT NULL,
    embedding vector(1536) NOT NULL,
    topic VARCHAR(256),
    subtopic VARCHAR(256),
    url TEXT,
    content_preview TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create standard B-tree index on chunk_id for fast lookups
CREATE INDEX idx_corpus_chunk_id ON corpus_embeddings(chunk_id);

-- Create index on topic for filtered queries
CREATE INDEX idx_corpus_topic ON corpus_embeddings(topic);

-- HNSW Index will be created separately during benchmarking
-- Example syntax for HNSW index:
-- CREATE INDEX idx_corpus_hnsw ON corpus_embeddings 
-- USING hnsw (embedding vector_cosine_ops)
-- WITH (m = 16, ef_construction = 64);

-- Verify setup
SELECT 
    extname, 
    extversion 
FROM pg_extension 
WHERE extname = 'vector';

-- Show table structure
\d corpus_embeddings

