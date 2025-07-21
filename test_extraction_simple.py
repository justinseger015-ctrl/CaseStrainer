import sys
import os
sys.path.insert(0, 'src')

try:
    from case_name_extraction_core import extract_case_name_and_date
    
    # Test the specific case that failed
    text = "Matter of Bourguignon v. Coordinated Behavioral Health Servs., Inc., 114 A.D.3d 947 (3d Dep't 2014)"
    citation = "114 A.D.3d 947"
    
    result = extract_case_name_and_date(text, citation)
    
    print("=== Test Results ===")
    print(f"Case Name: '{result['case_name']}'")
    print(f"Year: '{result['year']}'")
    print(f"Method: '{result['method']}'")
    print(f"Confidence: {result['confidence']:.2f}")
    
    # Check if it matches expected values
    expected_case = "Matter of Bourguignon v. Coordinated Behavioral Health Servs., Inc."
    expected_year = "2014"
    
    case_match = result['case_name'] == expected_case
    year_match = result['year'] == expected_year
    
    print(f"\nCase Name Match: {'✅' if case_match else '❌'}")
    print(f"Year Match: {'✅' if year_match else '❌'}")
    
    if case_match and year_match:
        print("🎉 SUCCESS: Both case name and year extracted correctly!")
    else:
        print("⚠️  PARTIAL/FAILED: Some extraction issues remain")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc() 