#!/usr/bin/env python3
"""
Test the medical term expansion functionality.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.medical_terms import expand_medical_query

def test_medical_expansion():
    """Test medical term expansion with our problem queries."""
    
    test_cases = [
        {
            "query": "what is the rating for ulnar neuropathy",
            "expected_terms": ["ulnar", "neuropathy", "neuritis", "nerve", "paralysis"]
        },
        {
            "query": "carpal tunnel syndrome ratings",
            "expected_terms": ["carpal", "tunnel", "median", "nerve", "neuropathy", "neuritis"]
        },
        {
            "query": "ptsd rating schedule",
            "expected_terms": ["ptsd", "post", "traumatic", "stress", "disorder", "mental", "health"]
        }
    ]
    
    print("🧪 Testing Medical Term Expansion")
    print("=" * 50)
    
    for i, test_case in enumerate(test_cases, 1):
        query = test_case["query"]
        expected_terms = test_case["expected_terms"]
        
        print(f"\n📝 Test {i}: '{query}'")
        
        # Test expansion
        expanded = expand_medical_query(query)
        
        if expanded != query:
            print(f"✅ Expansion: '{expanded}'")
            
            # Check if expected terms are present
            expanded_lower = expanded.lower()
            found_terms = [term for term in expected_terms if term in expanded_lower]
            missing_terms = [term for term in expected_terms if term not in expanded_lower]
            
            print(f"✅ Found terms: {found_terms}")
            if missing_terms:
                print(f"⚠️  Missing terms: {missing_terms}")
            
            # Calculate success rate
            success_rate = len(found_terms) / len(expected_terms) * 100
            print(f"📊 Success rate: {success_rate:.1f}%")
            
        else:
            print(f"❌ No expansion applied")
    
    print("\n" + "=" * 50)
    print("🎯 Expected Results:")
    print("1. 'ulnar neuropathy' should expand to include 'ulnar neuritis' and 'ulnar nerve paralysis'")
    print("2. 'carpal tunnel' should expand to include 'median nerve' and 'median neuritis'") 
    print("3. This should help BM25 and vector search find relevant content")
    print("\n✅ Medical term expansion test completed!")

if __name__ == "__main__":
    test_medical_expansion()
