<<<<<<< HEAD
#!/usr/bin/env python3
"""
Test script for MCP server integration
Run this to test your MCP server connection
"""

import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('env.txt')

# Configuration
BASE_URL = "http://localhost:5000"  # Change if your Flask app runs on different port
MCP_SERVER_URL = "https://prod-1-data.ke.pinecone.io/mcp/assistants/vb"

def test_health():
    """Test the health endpoint"""
    print("🏥 Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print("✅ Health check passed!")
            print(f"   Status: {data['status']}")
            print(f"   MCP Endpoint: {data['mcp_endpoint']}")
            print(f"   MCP API Key: {'✅ Configured' if data['mcp_api_key_configured'] else '❌ Missing'}")
            print(f"   Pinecone SDK: {'✅ Available' if data['pinecone_available'] else '❌ Unavailable'}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_mcp_status():
    """Test the MCP status endpoint"""
    print("\n🔍 Testing MCP status endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/mcp/status")
        if response.status_code == 200:
            data = response.json()
            print("✅ MCP status check passed!")
            print(f"   MCP Server URL: {data['mcp_server_url']}")
            print(f"   API Key: {'✅ Configured' if data['api_key_configured'] else '❌ Missing'}")
            print(f"   Connection Test: {data['connection_test']}")
            if 'mcp_response_sample' in data:
                sample = data['mcp_response_sample']
                print(f"   Response Sample: Content={sample['has_content']}, Citations={sample['has_citations']}")
            return True
        else:
            print(f"❌ MCP status check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ MCP status check error: {e}")
        return False

def test_mcp_chat():
    """Test the MCP chat functionality"""
    print("\n💬 Testing MCP chat functionality...")
    try:
        test_prompt = "What are the basic eligibility requirements for VA disability compensation?"
        
        response = requests.post(f"{BASE_URL}/mcp/test", 
                               json={"prompt": test_prompt},
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print("✅ MCP chat test passed!")
                print(f"   Status: {data['mcp_server_status']}")
                if 'response' in data:
                    resp = data['response']
                    print(f"   Content Length: {len(resp['content']) if resp['content'] else 0} characters")
                    print(f"   Citations: {len(resp['citations'])} found")
                return True
            else:
                print(f"❌ MCP chat test failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ MCP chat test failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ MCP chat test error: {e}")
        return False

def test_main_ask():
    """Test the main ask endpoint"""
    print("\n❓ Testing main ask endpoint...")
    try:
        test_prompt = "How do I apply for VA healthcare benefits?"
        
        response = requests.post(f"{BASE_URL}/ask", 
                               json={"prompt": test_prompt},
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Main ask test passed!")
            print(f"   Source: {data.get('source', 'unknown')}")
            print(f"   Content Length: {len(data['content']) if data['content'] else 0} characters")
            print(f"   Citations: {len(data['citations'])} found")
            return True
        else:
            print(f"❌ Main ask test failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Main ask test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting MCP Integration Tests...")
    print(f"📍 Testing against: {BASE_URL}")
    print(f"🔗 MCP Server: {MCP_SERVER_URL}")
    print("=" * 60)
    
    tests = [
        ("Health Check", test_health),
        ("MCP Status", test_mcp_status),
        ("MCP Chat Test", test_mcp_chat),
        ("Main Ask Endpoint", test_main_ask)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your MCP integration is working correctly.")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

=======
#!/usr/bin/env python3
"""
Test script for MCP server integration
Run this to test your MCP server connection
"""

import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('env.txt')

# Configuration
BASE_URL = "http://localhost:5000"  # Change if your Flask app runs on different port
MCP_SERVER_URL = "https://prod-1-data.ke.pinecone.io/mcp/assistants/vb"

def test_health():
    """Test the health endpoint"""
    print("🏥 Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print("✅ Health check passed!")
            print(f"   Status: {data['status']}")
            print(f"   MCP Endpoint: {data['mcp_endpoint']}")
            print(f"   MCP API Key: {'✅ Configured' if data['mcp_api_key_configured'] else '❌ Missing'}")
            print(f"   Pinecone SDK: {'✅ Available' if data['pinecone_available'] else '❌ Unavailable'}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_mcp_status():
    """Test the MCP status endpoint"""
    print("\n🔍 Testing MCP status endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/mcp/status")
        if response.status_code == 200:
            data = response.json()
            print("✅ MCP status check passed!")
            print(f"   MCP Server URL: {data['mcp_server_url']}")
            print(f"   API Key: {'✅ Configured' if data['api_key_configured'] else '❌ Missing'}")
            print(f"   Connection Test: {data['connection_test']}")
            if 'mcp_response_sample' in data:
                sample = data['mcp_response_sample']
                print(f"   Response Sample: Content={sample['has_content']}, Citations={sample['has_citations']}")
            return True
        else:
            print(f"❌ MCP status check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ MCP status check error: {e}")
        return False

def test_mcp_chat():
    """Test the MCP chat functionality"""
    print("\n💬 Testing MCP chat functionality...")
    try:
        test_prompt = "What are the basic eligibility requirements for VA disability compensation?"
        
        response = requests.post(f"{BASE_URL}/mcp/test", 
                               json={"prompt": test_prompt},
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                print("✅ MCP chat test passed!")
                print(f"   Status: {data['mcp_server_status']}")
                if 'response' in data:
                    resp = data['response']
                    print(f"   Content Length: {len(resp['content']) if resp['content'] else 0} characters")
                    print(f"   Citations: {len(resp['citations'])} found")
                return True
            else:
                print(f"❌ MCP chat test failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ MCP chat test failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ MCP chat test error: {e}")
        return False

def test_main_ask():
    """Test the main ask endpoint"""
    print("\n❓ Testing main ask endpoint...")
    try:
        test_prompt = "How do I apply for VA healthcare benefits?"
        
        response = requests.post(f"{BASE_URL}/ask", 
                               json={"prompt": test_prompt},
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Main ask test passed!")
            print(f"   Source: {data.get('source', 'unknown')}")
            print(f"   Content Length: {len(data['content']) if data['content'] else 0} characters")
            print(f"   Citations: {len(data['citations'])} found")
            return True
        else:
            print(f"❌ Main ask test failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Main ask test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting MCP Integration Tests...")
    print(f"📍 Testing against: {BASE_URL}")
    print(f"🔗 MCP Server: {MCP_SERVER_URL}")
    print("=" * 60)
    
    tests = [
        ("Health Check", test_health),
        ("MCP Status", test_mcp_status),
        ("MCP Chat Test", test_mcp_chat),
        ("Main Ask Endpoint", test_main_ask)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your MCP integration is working correctly.")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

>>>>>>> b6374a9 (Add new features and fix bugs)
