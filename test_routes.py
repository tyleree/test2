<<<<<<< HEAD
#!/usr/bin/env python3
"""
Simple test script to verify Flask routes are working
Run this to test your Flask application
"""

import requests
import time

def test_flask_app():
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Flask Application...")
    print(f"📍 Testing against: {base_url}")
    print("=" * 50)
    
    # Test 1: Basic connectivity
    try:
        response = requests.get(f"{base_url}/ping", timeout=5)
        if response.status_code == 200:
            print("✅ /ping route working")
        else:
            print(f"❌ /ping route failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to Flask app: {e}")
        return False
    
    # Test 2: Home page
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        if response.status_code == 200:
            print("✅ Home page (/) working")
        else:
            print(f"❌ Home page failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Home page error: {e}")
    
    # Test 3: Debug route
    try:
        response = requests.get(f"{base_url}/debug", timeout=5)
        if response.status_code == 200:
            print("✅ Debug route working")
            data = response.json()
            print(f"   📁 Template folder: {data.get('template_folder', 'Unknown')}")
            print(f"   🛣️  Available routes: {len(data.get('routes', []))}")
        else:
            print(f"❌ Debug route failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Debug route error: {e}")
    
    # Test 4: Health check
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Health check working")
            data = response.json()
            print(f"   🟢 Status: {data.get('status', 'Unknown')}")
            print(f"   🤖 Pinecone: {data.get('pinecone_available', 'Unknown')}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Health check error: {e}")
    
    # Test 5: Ask endpoint (POST)
    try:
        test_data = {"prompt": "test question"}
        response = requests.post(f"{base_url}/ask", json=test_data, timeout=10)
        if response.status_code == 200:
            print("✅ /ask endpoint working")
        elif response.status_code == 500:
            print("⚠️  /ask endpoint responding but Pinecone may have issues")
        else:
            print(f"❌ /ask endpoint failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ /ask endpoint error: {e}")
    
    print("=" * 50)
    print("🎯 Testing complete!")
    return True

if __name__ == "__main__":
    print("Make sure your Flask app is running first!")
    print("Run: python app.py")
    print()
    input("Press Enter when Flask app is running...")
    test_flask_app()








=======
#!/usr/bin/env python3
"""
Simple test script to verify Flask routes are working
Run this to test your Flask application
"""

import requests
import time

def test_flask_app():
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Flask Application...")
    print(f"📍 Testing against: {base_url}")
    print("=" * 50)
    
    # Test 1: Basic connectivity
    try:
        response = requests.get(f"{base_url}/ping", timeout=5)
        if response.status_code == 200:
            print("✅ /ping route working")
        else:
            print(f"❌ /ping route failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to Flask app: {e}")
        return False
    
    # Test 2: Home page
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        if response.status_code == 200:
            print("✅ Home page (/) working")
        else:
            print(f"❌ Home page failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Home page error: {e}")
    
    # Test 3: Debug route
    try:
        response = requests.get(f"{base_url}/debug", timeout=5)
        if response.status_code == 200:
            print("✅ Debug route working")
            data = response.json()
            print(f"   📁 Template folder: {data.get('template_folder', 'Unknown')}")
            print(f"   🛣️  Available routes: {len(data.get('routes', []))}")
        else:
            print(f"❌ Debug route failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Debug route error: {e}")
    
    # Test 4: Health check
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Health check working")
            data = response.json()
            print(f"   🟢 Status: {data.get('status', 'Unknown')}")
            print(f"   🤖 Pinecone: {data.get('pinecone_available', 'Unknown')}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Health check error: {e}")
    
    # Test 5: Ask endpoint (POST)
    try:
        test_data = {"prompt": "test question"}
        response = requests.post(f"{base_url}/ask", json=test_data, timeout=10)
        if response.status_code == 200:
            print("✅ /ask endpoint working")
        elif response.status_code == 500:
            print("⚠️  /ask endpoint responding but Pinecone may have issues")
        else:
            print(f"❌ /ask endpoint failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ /ask endpoint error: {e}")
    
    print("=" * 50)
    print("🎯 Testing complete!")
    return True

if __name__ == "__main__":
    print("Make sure your Flask app is running first!")
    print("Run: python app.py")
    print()
    input("Press Enter when Flask app is running...")
    test_flask_app()








>>>>>>> b6374a9 (Add new features and fix bugs)
