#!/usr/bin/env python3
"""
Simple test script to verify analytics functionality
"""
import os
import sys
import requests
import json
from datetime import datetime

def test_analytics_endpoints():
    """Test analytics endpoints without database dependency"""
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Analytics System")
    print("=" * 50)
    
    # Test 1: Analytics event collection
    print("\n1. Testing event collection...")
    try:
        response = requests.post(
            f"{base_url}/api/analytics/event",
            json={
                "type": "pageview",
                "path": "/test-page",
                "ref": "https://test.com"
            },
            timeout=5
        )
        print(f"   Event collection: {response.status_code} - {'✅ OK' if response.status_code == 200 else '❌ FAILED'}")
        if response.status_code != 200:
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"   Event collection: ❌ FAILED - {e}")
    
    # Test 2: Chat question event
    print("\n2. Testing chat question event...")
    try:
        response = requests.post(
            f"{base_url}/api/analytics/event",
            json={
                "type": "chat_question",
                "path": "/",
                "meta": json.dumps({"prompt_length": 25})
            },
            timeout=5
        )
        print(f"   Chat event: {response.status_code} - {'✅ OK' if response.status_code == 200 else '❌ FAILED'}")
    except Exception as e:
        print(f"   Chat event: ❌ FAILED - {e}")
    
    # Test 3: Statistics endpoint
    print("\n3. Testing statistics endpoint...")
    try:
        response = requests.get(f"{base_url}/api/analytics/stats?days=7", timeout=5)
        print(f"   Statistics: {response.status_code} - {'✅ OK' if response.status_code in [200, 503] else '❌ FAILED'}")
        if response.status_code == 200:
            data = response.json()
            print(f"   📊 Pageviews: {data.get('totals', {}).get('pageviews', 0)}")
            print(f"   👥 Unique visitors: {data.get('totals', {}).get('uniques', 0)}")
            print(f"   💬 Chat questions: {data.get('totals', {}).get('chat_questions', 0)}")
        elif response.status_code == 503:
            print("   ⚠️ Database not available (expected for local testing)")
    except Exception as e:
        print(f"   Statistics: ❌ FAILED - {e}")
    
    # Test 4: Static analytics.js file
    print("\n4. Testing analytics.js file...")
    try:
        response = requests.get(f"{base_url}/static/analytics.js", timeout=5)
        print(f"   Analytics.js: {response.status_code} - {'✅ OK' if response.status_code == 200 else '❌ FAILED'}")
        if response.status_code == 200:
            content = response.text
            if "window.analyticsTrack" in content and "window.analyticsChatHit" in content:
                print("    Analytics functions found in script")
            else:
                print("    Missing analytics functions")
    except Exception as e:
        print(f"   Analytics.js:  FAILED - {e}")
    
    # Test 5: Admin dashboard (without token)
    print("\n5. Testing admin dashboard...")
    try:
        response = requests.get(f"{base_url}/admin/analytics", timeout=5)
        print(f"   Admin dashboard: {response.status_code} - {'✅ OK' if response.status_code == 401 else '❌ FAILED'}")
        if response.status_code == 401:
            print("   ✅ Properly protected (401 Unauthorized)")
        else:
            print(f"   ⚠️ Expected 401, got {response.status_code}")
    except Exception as e:
        print(f"   Admin dashboard:  FAILED - {e}")
    
    print("\n" + "=" * 50)
    print("🏁 Analytics test completed!")
    print("\n Next steps:")
    print("1. Set DATABASE_URL to enable full analytics functionality")
    print("2. Set ADMIN_TOKEN to access the dashboard")
    print("3. Deploy to Render with PostgreSQL database")
    print("4. Visit /admin/analytics?token=YOUR_TOKEN to see the dashboard")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Usage: python test_analytics.py")
        print("Ensure Flask app is running on localhost:5000")
        sys.exit(0)
    
    test_analytics_endpoints()
