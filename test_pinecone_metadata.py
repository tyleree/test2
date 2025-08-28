#!/usr/bin/env python3
"""
Test what's actually stored in the Pinecone index to debug search issues.
"""

import os
from dotenv import load_dotenv
from pinecone import Pinecone

# Load environment variables
load_dotenv('env.txt')

def test_pinecone_metadata():
    """Check what's actually in the Pinecone index."""
    
    try:
        # Initialize Pinecone
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        index = pc.Index("veterans-benefits-kb")
        
        print("🔍 TESTING PINECONE INDEX METADATA")
        print("=" * 60)
        
        # Get index stats
        stats = index.describe_index_stats()
        print(f"📊 Total vectors: {stats.total_vector_count}")
        print(f"📊 Dimensions: {stats.dimension}")
        print(f"📊 Namespaces: {stats.namespaces}")
        
        # Try to fetch some specific chunks to see their metadata
        test_chunk_ids = [
            "chunk_1102", "chunk_1051", "chunk_0997", "chunk_0998", "chunk_1097"  # From the failed search
        ]
        
        print(f"\n🔍 CHECKING METADATA FOR RETURNED CHUNKS:")
        print("-" * 40)
        
        try:
            # Fetch the chunks that were returned in the failed search
            fetch_response = index.fetch(ids=test_chunk_ids)
            
            for chunk_id, vector_data in fetch_response.vectors.items():
                print(f"\n📄 Chunk ID: {chunk_id}")
                if 'metadata' in vector_data:
                    metadata = vector_data['metadata']
                    print(f"   Title: {metadata.get('title', 'N/A')}")
                    print(f"   Section: {metadata.get('section', 'N/A')}")
                    print(f"   Text preview: {metadata.get('text', 'N/A')[:100]}...")
                    print(f"   Source URL: {metadata.get('source_url', 'N/A')}")
                else:
                    print("   ❌ No metadata found!")
                    
        except Exception as e:
            print(f"❌ Error fetching chunks: {e}")
        
        # Try to search for chunks that should contain mental health content
        print(f"\n🔍 SEARCHING FOR MENTAL HEALTH CHUNKS:")
        print("-" * 40)
        
        # Create a simple query vector (we can't generate embeddings due to OpenAI issue)
        # But we can try to find chunks by filtering metadata if it exists
        try:
            # Try a query with filter (if metadata supports it)
            # This is a dummy vector - we just want to see what's available
            dummy_vector = [0.1] * 1024  # 1024-dimensional dummy vector
            
            query_response = index.query(
                vector=dummy_vector,
                top_k=10,
                include_metadata=True
            )
            
            print(f"Found {len(query_response.matches)} results:")
            for i, match in enumerate(query_response.matches[:5]):
                print(f"\n📄 Match {i+1} (Score: {match.score:.4f}):")
                print(f"   ID: {match.id}")
                if hasattr(match, 'metadata') and match.metadata:
                    print(f"   Title: {match.metadata.get('title', 'N/A')}")
                    print(f"   Section: {match.metadata.get('section', 'N/A')}")
                    print(f"   Text: {match.metadata.get('text', 'N/A')[:100]}...")
                else:
                    print("   ❌ No metadata!")
                    
        except Exception as e:
            print(f"❌ Error querying index: {e}")
        
        print(f"\n" + "=" * 60)
        print("🔍 ANALYSIS:")
        print("- Check if the chunks that were returned contain mental health content")
        print("- Verify if metadata includes proper titles and sections")
        print("- See if the content matches what we expect from the corpus")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_pinecone_metadata()
