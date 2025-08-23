#!/usr/bin/env python3
"""
Test script to isolate the OpenAI + Pinecone direct query issue
"""
import os
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI

# Load environment variables
load_dotenv('env.txt')

def test_openai_direct():
    """Test the OpenAI + Pinecone direct query components individually"""
    
    # Check environment variables
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    print(f"🔍 PINECONE_API_KEY: {'✅ Set' if PINECONE_API_KEY else '❌ Missing'}")
    print(f"🔍 OPENAI_API_KEY: {'✅ Set' if OPENAI_API_KEY else '❌ Missing'}")
    
    if not PINECONE_API_KEY or not OPENAI_API_KEY:
        print("❌ Missing required API keys")
        return
    
    try:
        # Test Pinecone connection
        print("\n🧪 Testing Pinecone connection...")
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index("veterans-benefits-kb")
        
        # Test index stats
        stats = index.describe_index_stats()
        print(f"✅ Pinecone index stats: {stats}")
        
    except Exception as e:
        print(f"❌ Pinecone error: {e}")
        return
    
    try:
        # Test OpenAI connection
        print("\n🧪 Testing OpenAI connection...")
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Test embedding generation
        test_prompt = "What are VA disability benefits?"
        embed_response = client.embeddings.create(
            model="text-embedding-3-small",
            input=test_prompt,
            dimensions=1024
        )
        
        query_vector = embed_response.data[0].embedding
        print(f"✅ Generated embedding: {len(query_vector)} dimensions")
        
        # Test Pinecone query
        print("\n🧪 Testing Pinecone query...")
        results = index.query(
            vector=query_vector,
            top_k=3,
            include_metadata=True
        )
        
        print(f"✅ Pinecone query results: {len(results.matches)} matches")
        for i, match in enumerate(results.matches):
            print(f"  Match {i+1}: Score={match.score:.4f}, ID={match.id}")
            if match.metadata:
                print(f"    Metadata keys: {list(match.metadata.keys())}")
                
                # Test the same extraction logic as in query_direct_pinecone
                chunk_text = (
                    match.metadata.get('context', '') or 
                    match.metadata.get('text', '') or 
                    match.metadata.get('preview', '')
                )
                print(f"    Extracted chunk_text length: {len(chunk_text)} chars")
                print(f"    Chunk preview: {chunk_text[:100]}...")
                
                heading = match.metadata.get('heading', '')
                source_url = match.metadata.get('source_url', 'https://veteransbenefitskb.com')
                print(f"    Heading: {heading}")
                print(f"    Source URL: {source_url}")
                print("    ---")
        
        # Test GPT-4 call
        print("\n🧪 Testing GPT-4 call...")
        if results.matches:
            context_text = "Sample context for testing"
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": f"Context: {context_text}\n\nQuestion: {test_prompt}\n\nAnswer based on the context."}
                ],
                temperature=0.3,
                max_tokens=100
            )
            
            answer = response.choices[0].message.content
            print(f"✅ GPT-4 response: {answer[:100]}...")
            print(f"✅ Token usage: {response.usage}")
        
        print("\n🎉 All tests passed! The issue is likely in the error handling or return logic.")
        
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_openai_direct()
