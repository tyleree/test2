<<<<<<< HEAD
#!/usr/bin/env python3
"""
Clean JSON-based test script for MCP server integration
Demonstrates the new JSON API structure
"""

import requests
import json
import time

# Configuration
BASE_URL = "http://localhost:5000"  # Change if your Flask app runs on different port

def test_basic_health():
    """Test basic health endpoint"""
    print("🏥 Testing basic health...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print("✅ Health check passed!")
            print(f"   Status: {data['status']}")
            print(f"   MCP Endpoint: {data['mcp_endpoint']}")
            print(f"   Available endpoints: {', '.join(data['endpoints'].keys())}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_mcp_status():
    """Test MCP status endpoint"""
    print("\n🔍 Testing MCP status...")
    try:
        response = requests.get(f"{BASE_URL}/mcp/status")
        if response.status_code == 200:
            data = response.json()
            print("✅ MCP status check passed!")
            print(f"   Server URL: {data['mcp_server_url']}")
            print(f"   API Key: {'✅ Configured' if data['api_key_configured'] else '❌ Missing'}")
            print(f"   Connection: {data['connection_test']}")
            return True
        else:
            print(f"❌ MCP status check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ MCP status check error: {e}")
        return False

def test_simple_ask():
    """Test simple ask endpoint"""
    print("\n❓ Testing simple ask...")
    try:
        payload = {
            "prompt": "What are the basic eligibility requirements for VA disability compensation?"
        }
        
        response = requests.post(f"{BASE_URL}/ask", 
                               json=payload,
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Simple ask test passed!")
                print(f"   Source: {data.get('source', 'unknown')}")
                print(f"   Content: {len(data['content'])} characters")
                print(f"   Citations: {len(data['citations'])} found")
                if data.get('metadata'):
                    print(f"   Metadata: {list(data['metadata'].keys())}")
                return True
            else:
                print(f"❌ Simple ask failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ Simple ask failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Simple ask error: {e}")
        return False

def test_advanced_mcp_chat():
    """Test advanced MCP chat with options"""
    print("\n🚀 Testing advanced MCP chat...")
    try:
        payload = {
            "prompt": "Explain the VA healthcare enrollment process in detail",
            "options": {
                "temperature": 0.7,
                "max_tokens": 1500,
                "include_highlights": True
            }
        }
        
        response = requests.post(f"{BASE_URL}/mcp/chat", 
                               json=payload,
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Advanced MCP chat test passed!")
                print(f"   Source: {data.get('source', 'unknown')}")
                print(f"   Content: {len(data['content'])} characters")
                print(f"   Citations: {len(data['citations'])} found")
                if data.get('metadata'):
                    print(f"   Metadata: {list(data['metadata'].keys())}")
                return True
            else:
                print(f"❌ Advanced MCP chat failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ Advanced MCP chat failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Advanced MCP chat error: {e}")
        return False

def test_mcp_test_endpoint():
    """Test the MCP test endpoint"""
    print("\n🧪 Testing MCP test endpoint...")
    try:
        payload = {
            "prompt": "What is the VA rating schedule?"
        }
        
        response = requests.post(f"{BASE_URL}/mcp/test", 
                               json=payload,
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ MCP test endpoint passed!")
                print(f"   Status: {data.get('mcp_server_status', 'unknown')}")
                if 'response' in data:
                    resp = data['response']
                    print(f"   Content: {len(resp.get('content', ''))} characters")
                    print(f"   Citations: {len(resp.get('citations', []))} found")
                return True
            else:
                print(f"❌ MCP test endpoint failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ MCP test endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ MCP test endpoint error: {e}")
        return False

def test_error_handling():
    """Test error handling with invalid requests"""
    print("\n⚠️ Testing error handling...")
    try:
        # Test with no prompt
        payload = {}
        
        response = requests.post(f"{BASE_URL}/ask", 
                               json=payload,
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 400:
            data = response.json()
            print("✅ Error handling test passed!")
            print(f"   Expected error: {data.get('error', 'Unknown error')}")
            return True
        else:
            print(f"❌ Error handling test failed: Expected 400, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error handling test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting Clean JSON MCP Integration Tests...")
    print(f"📍 Testing against: {BASE_URL}")
    print("=" * 70)
    
    tests = [
        ("Basic Health", test_basic_health),
        ("MCP Status", test_mcp_status),
        ("Simple Ask", test_simple_ask),
        ("Advanced MCP Chat", test_advanced_mcp_chat),
        ("MCP Test Endpoint", test_mcp_test_endpoint),
        ("Error Handling", test_error_handling)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            start_time = time.time()
            result = test_func()
            end_time = time.time()
            
            status = "✅ PASS" if result else "❌ FAIL"
            duration = f"({end_time - start_time:.2f}s)"
            print(f"   {test_name}: {status} {duration}")
            
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 70)
    print("📊 Test Results Summary:")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your clean JSON MCP integration is working perfectly.")
        print("\n📋 Available endpoints:")
        print("   • POST /ask - Simple question asking")
        print("   • POST /mcp/chat - Advanced MCP chat with options")
        print("   • GET /mcp/status - MCP server status")
        print("   • POST /mcp/test - Test MCP functionality")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

=======
#!/usr/bin/env python3
"""
Clean JSON-based test script for MCP server integration
Demonstrates the new JSON API structure
"""

import requests
import json
import time

# Configuration
BASE_URL = "http://localhost:5000"  # Change if your Flask app runs on different port

def test_basic_health():
    """Test basic health endpoint"""
    print("🏥 Testing basic health...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print("✅ Health check passed!")
            print(f"   Status: {data['status']}")
            print(f"   MCP Endpoint: {data['mcp_endpoint']}")
            print(f"   Available endpoints: {', '.join(data['endpoints'].keys())}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def test_mcp_status():
    """Test MCP status endpoint"""
    print("\n🔍 Testing MCP status...")
    try:
        response = requests.get(f"{BASE_URL}/mcp/status")
        if response.status_code == 200:
            data = response.json()
            print("✅ MCP status check passed!")
            print(f"   Server URL: {data['mcp_server_url']}")
            print(f"   API Key: {'✅ Configured' if data['api_key_configured'] else '❌ Missing'}")
            print(f"   Connection: {data['connection_test']}")
            return True
        else:
            print(f"❌ MCP status check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ MCP status check error: {e}")
        return False

def test_simple_ask():
    """Test simple ask endpoint"""
    print("\n❓ Testing simple ask...")
    try:
        payload = {
            "prompt": "What are the basic eligibility requirements for VA disability compensation?"
        }
        
        response = requests.post(f"{BASE_URL}/ask", 
                               json=payload,
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Simple ask test passed!")
                print(f"   Source: {data.get('source', 'unknown')}")
                print(f"   Content: {len(data['content'])} characters")
                print(f"   Citations: {len(data['citations'])} found")
                if data.get('metadata'):
                    print(f"   Metadata: {list(data['metadata'].keys())}")
                return True
            else:
                print(f"❌ Simple ask failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ Simple ask failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Simple ask error: {e}")
        return False

def test_advanced_mcp_chat():
    """Test advanced MCP chat with options"""
    print("\n🚀 Testing advanced MCP chat...")
    try:
        payload = {
            "prompt": "Explain the VA healthcare enrollment process in detail",
            "options": {
                "temperature": 0.7,
                "max_tokens": 1500,
                "include_highlights": True
            }
        }
        
        response = requests.post(f"{BASE_URL}/mcp/chat", 
                               json=payload,
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Advanced MCP chat test passed!")
                print(f"   Source: {data.get('source', 'unknown')}")
                print(f"   Content: {len(data['content'])} characters")
                print(f"   Citations: {len(data['citations'])} found")
                if data.get('metadata'):
                    print(f"   Metadata: {list(data['metadata'].keys())}")
                return True
            else:
                print(f"❌ Advanced MCP chat failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ Advanced MCP chat failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Advanced MCP chat error: {e}")
        return False

def test_mcp_test_endpoint():
    """Test the MCP test endpoint"""
    print("\n🧪 Testing MCP test endpoint...")
    try:
        payload = {
            "prompt": "What is the VA rating schedule?"
        }
        
        response = requests.post(f"{BASE_URL}/mcp/test", 
                               json=payload,
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ MCP test endpoint passed!")
                print(f"   Status: {data.get('mcp_server_status', 'unknown')}")
                if 'response' in data:
                    resp = data['response']
                    print(f"   Content: {len(resp.get('content', ''))} characters")
                    print(f"   Citations: {len(resp.get('citations', []))} found")
                return True
            else:
                print(f"❌ MCP test endpoint failed: {data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ MCP test endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ MCP test endpoint error: {e}")
        return False

def test_error_handling():
    """Test error handling with invalid requests"""
    print("\n⚠️ Testing error handling...")
    try:
        # Test with no prompt
        payload = {}
        
        response = requests.post(f"{BASE_URL}/ask", 
                               json=payload,
                               headers={"Content-Type": "application/json"})
        
        if response.status_code == 400:
            data = response.json()
            print("✅ Error handling test passed!")
            print(f"   Expected error: {data.get('error', 'Unknown error')}")
            return True
        else:
            print(f"❌ Error handling test failed: Expected 400, got {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error handling test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting Clean JSON MCP Integration Tests...")
    print(f"📍 Testing against: {BASE_URL}")
    print("=" * 70)
    
    tests = [
        ("Basic Health", test_basic_health),
        ("MCP Status", test_mcp_status),
        ("Simple Ask", test_simple_ask),
        ("Advanced MCP Chat", test_advanced_mcp_chat),
        ("MCP Test Endpoint", test_mcp_test_endpoint),
        ("Error Handling", test_error_handling)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            start_time = time.time()
            result = test_func()
            end_time = time.time()
            
            status = "✅ PASS" if result else "❌ FAIL"
            duration = f"({end_time - start_time:.2f}s)"
            print(f"   {test_name}: {status} {duration}")
            
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 70)
    print("📊 Test Results Summary:")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your clean JSON MCP integration is working perfectly.")
        print("\n📋 Available endpoints:")
        print("   • POST /ask - Simple question asking")
        print("   • POST /mcp/chat - Advanced MCP chat with options")
        print("   • GET /mcp/status - MCP server status")
        print("   • POST /mcp/test - Test MCP functionality")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

>>>>>>> b6374a9 (Add new features and fix bugs)
