#!/usr/bin/env python3
"""
Test script to check if the API is returning clusters in the response.
"""

import requests
import json
import time

def test_api_clusters():
    """Test that the API returns clusters in the response."""
    
    url = "http://localhost:5000/casestrainer/api/analyze"
    
    # Test data with parallel citations
    test_data = {
        "type": "text",
        "text": "A federal court may ask this court to answer a question of Washington law when a resolution of that question is necessary to resolve a case before the federal court. RCW 2.60.020; Convoyant, LLC v. DeepThink, LLC, 200 Wn.2d 72, 73, 514 P.3d 643 (2022). Certified questions are questions of law we review de novo. Carlson v. Glob. Client Sols., LLC, 171 Wn.2d 486, 493, 256 P.3d 321 (2011). We also review the meaning of a statute de novo. Dep't of Ecology v. Campbell & Gwinn, LLC, 146 Wn.2d 1, 9, 43 P.3d 4 (2003)."
    }
    
    print("🧪 Testing API clusters response...")
    print(f"URL: {url}")
    print(f"Text length: {len(test_data['text'])}")
    
    try:
        # Send request
        response = requests.post(url, json=test_data, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"\n✅ API Response Status: {data.get('status')}")
            print(f"📊 Citations: {len(data.get('citations', []))}")
            print(f"🔗 Clusters: {len(data.get('clusters', []))}")
            
            # Check if clusters are present
            clusters = data.get('clusters', [])
            if clusters:
                print(f"\n🎉 SUCCESS: Found {len(clusters)} clusters!")
                print("\n📦 Clusters:")
                for i, cluster in enumerate(clusters, 1):
                    print(f"  Cluster {i}:")
                    print(f"    Case: {cluster.get('canonical_name', 'N/A')}")
                    print(f"    Date: {cluster.get('canonical_date', 'N/A')}")
                    print(f"    Citations: {len(cluster.get('citations', []))}")
                    for j, citation in enumerate(cluster.get('citations', []), 1):
                        print(f"      {j}. {citation.get('citation', 'N/A')}")
                    print()
            else:
                print("\n❌ FAILURE: No clusters found in API response!")
                print("Available keys:", list(data.keys()))
                
                # Check if clusters might be in a different location
                if 'results' in data:
                    print(f"Results length: {len(data['results'])}")
                if 'citations' in data:
                    print(f"Citations length: {len(data['citations'])}")
                    
        else:
            print(f"\n❌ API Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request Error: {e}")
    except json.JSONDecodeError as e:
        print(f"\n❌ JSON Decode Error: {e}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    test_api_clusters() 