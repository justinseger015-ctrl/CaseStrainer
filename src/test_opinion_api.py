#!/usr/bin/env python3
"""
Test script for CourtListener Opinion API
"""
import requests
import json
import sys

def test_opinion_api(api_key, opinion_id):
    """Test the CourtListener Opinion API with a specific opinion ID."""
    print(f"Testing CourtListener Opinion API with opinion ID: {opinion_id}")
    
    # API endpoint
    api_url = f'https://www.courtlistener.com/api/rest/v3/opinions/{opinion_id}/'
    
    # Prepare the request
    headers = {
        'Authorization': f'Token {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Make the request
    print(f"Sending request to {api_url}")
    try:
        response = requests.get(api_url, headers=headers)
        
        # Check the response
        print(f"Response status code: {response.status_code}")
        
        if response.status_code == 200:
            print("API request successful")
            result = response.json()
            
            # Save the API response to a file for inspection
            with open('test_opinion_response.json', 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
            print("API response saved to test_opinion_response.json")
            
            # Print a summary of the response
            print("\nResponse summary:")
            print(f"Case name: {result.get('case_name', 'N/A')}")
            print(f"Citation: {result.get('citation', 'N/A')}")
            print(f"Court: {result.get('court', 'N/A')}")
            print(f"Date filed: {result.get('date_filed', 'N/A')}")
            
            # Extract citation information
            cluster = result.get('cluster', {})
            if isinstance(cluster, dict):
                print("\nCitations:")
                citations = cluster.get('citations', [])
                for citation in citations:
                    print(f"  {citation.get('volume')} {citation.get('reporter')} {citation.get('page')}")
            elif cluster:
                print(f"\nCluster reference: {cluster}")
            
            return True
        else:
            print(f"API request failed with status code {response.status_code}")
            print(f"Response: {response.text}")
            return False
    
    except Exception as e:
        print(f"Error querying CourtListener API: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Load API key from config.json
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            api_key = config.get('courtlistener_api_key')
            if not api_key:
                print("No CourtListener API key found in config.json")
                sys.exit(1)
    except Exception as e:
        print(f"Error loading config.json: {e}")
        sys.exit(1)
    
    # Test opinion ID
    opinion_id = "4910901"  # Cutone v. Law
    if len(sys.argv) > 1:
        opinion_id = sys.argv[1]
    
    test_opinion_api(api_key, opinion_id)
