#!/usr/bin/env python3
"""
Comprehensive test of the complete backend pipeline to ensure all fields are populated.
This tests the full flow from text input to verified citations with complete metadata.
"""

import sys
import os
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_complete_backend():
    """Test the complete backend pipeline end-to-end."""
    print("🧪 Testing Complete Backend Pipeline")
    print("=" * 60)
    
    # Set Redis URL for async verification
    os.environ['REDIS_URL'] = 'redis://:caseStrainerRedis123@localhost:6380/0'
    
    try:
        # Import the enhanced sync processor
        from enhanced_sync_processor import EnhancedSyncProcessor
        
        # Initialize the processor
        processor = EnhancedSyncProcessor()
        
        # Test paragraph with multiple parallel citations
        test_text = """A federal court may ask this court to answer a question of Washington law when a resolution of that question is necessary to resolve a case before the federal court. RCW 2.60.020; Convoyant, LLC v. DeepThink, LLC, 200 Wn.2d 72, 73, 514 P.3d 643 (2022). Certified questions are questions of law we review de novo. Carlson v. Glob. Client Sols., LLC, 171 Wn.2d 486, 493, 256 P.3d 321 (2011). We also review the meaning of a statute de novo. Dep't of Ecology v. Campbell & Gwinn, LLC, 146 Wn.2d 1, 9, 43 P.3d 4 (2003)"""
        
        print(f"📝 Test Text:")
        print(f"   {test_text[:100]}...")
        print()
        
        print("🔄 Processing through Enhanced Sync Processor...")
        
        # Process the text through the complete pipeline
        result = processor.process_any_input_enhanced(
            input_data=test_text,
            input_type="text",
            options={
                "enable_enhanced_verification": True,
                "enable_clustering": True,
                "request_id": "test_complete_backend_001"
            }
        )
        
        print("✅ Processing completed!")
        print()
        
        # Analyze the results
        print("📊 COMPLETE BACKEND ANALYSIS:")
        print("=" * 60)
        
        # Check overall success
        print(f"🎯 Overall Success: {result.get('success', 'N/A')}")
        print(f"🔄 Processing Strategy: {result.get('processing_strategy', 'N/A')}")
        print(f"📊 Extraction Method: {result.get('extraction_method', 'N/A')}")
        print(f"⏱️  Processing Time: {result.get('processing_time', 'N/A')}")
        print(f"📏 Text Length: {result.get('text_length', 'N/A')}")
        print()
        
        # Check citations
        if 'citations' in result:
            citations = result['citations']
            print(f"📋 Citations Found: {len(citations)}")
            print()
            
            # Analyze each citation for field completeness
            for i, citation in enumerate(citations, 1):
                print(f"🔍 Citation {i}: {citation.get('citation', 'N/A')}")
                print(f"   📝 Extracted Case Name: {citation.get('extracted_case_name', 'N/A')}")
                print(f"   📅 Extracted Date: {citation.get('extracted_date', 'N/A')}")
                print(f"   🎯 Canonical Case Name: {citation.get('canonical_name', 'N/A')}")
                print(f"   📅 Canonical Date: {citation.get('canonical_date', 'N/A')}")
                print(f"   🔗 Canonical URL: {citation.get('canonical_url', 'N/A')}")
                print(f"   ✅ Verified: {citation.get('verified', 'N/A')}")
                print(f"   🎯 Confidence: {citation.get('confidence_score', 'N/A')}")
                print(f"   🏷️  Extraction Method: {citation.get('extraction_method', 'N/A')}")
                print(f"   📚 Source: {citation.get('source', 'N/A')}")
                print(f"   🔍 Validation Method: {citation.get('validation_method', 'N/A')}")
                print(f"   📊 Verification Confidence: {citation.get('verification_confidence', 'N/A')}")
                print()
                
                # Check for missing critical fields
                missing_fields = []
                if not citation.get('extracted_case_name'):
                    missing_fields.append('extracted_case_name')
                if not citation.get('extracted_date'):
                    missing_fields.append('extracted_date')
                if not citation.get('canonical_name'):
                    missing_fields.append('canonical_name')
                if not citation.get('canonical_date'):
                    missing_fields.append('canonical_date')
                if not citation.get('canonical_url'):
                    missing_fields.append('canonical_url')
                
                if missing_fields:
                    print(f"   ⚠️  Missing Critical Fields: {', '.join(missing_fields)}")
                else:
                    print(f"   ✅ All Critical Fields Present")
                print()
        
        # Check clusters
        if 'clusters' in result:
            clusters = result['clusters']
            print(f"🎯 Clusters Created: {len(clusters)}")
            print()
            
            for i, cluster in enumerate(clusters, 1):
                print(f"📦 Cluster {i}: {cluster.get('case_name', 'N/A')} ({cluster.get('year', 'N/A')})")
                print(f"   📊 Size: {cluster.get('size', 'N/A')} citations")
                print(f"   🏷️  Type: {cluster.get('cluster_type', 'N/A')}")
                print(f"   🎯 Confidence: {cluster.get('confidence_score', 'N/A')}")
                print(f"   📝 Extracted Case Name: {cluster.get('extracted_case_name', 'N/A')}")
                print(f"   📅 Extracted Date: {cluster.get('extracted_date', 'N/A')}")
                print(f"   🎯 Canonical Case Name: {cluster.get('canonical_name', 'N/A')}")
                print(f"   📅 Canonical Date: {cluster.get('canonical_date', 'N/A')}")
                print(f"   ✅ Verified: {cluster.get('verified', 'N/A')}")
                print(f"   📚 Source: {cluster.get('source', 'N/A')}")
                print(f"   🔍 Validation Method: {cluster.get('validation_method', 'N/A')}")
                print(f"   🎯 Citations: {', '.join(cluster.get('citations', []))}")
                print()
        
        # Check verification status
        if 'verification_status' in result:
            verification_status = result['verification_status']
            print(f"🔍 Verification Status:")
            print(f"   📋 Queued: {verification_status.get('verification_queued', 'N/A')}")
            print(f"   🆔 Job ID: {verification_status.get('verification_job_id', 'N/A')}")
            print(f"   📚 Queue: {verification_status.get('verification_queue', 'N/A')}")
            print(f"   💬 Message: {verification_status.get('message', 'N/A')}")
            if 'error' in verification_status:
                print(f"   ❌ Error: {verification_status.get('error', 'N/A')}")
            print()
        
        # Check processing metadata
        if 'metadata' in result:
            metadata = result['metadata']
            print(f"📊 Processing Metadata:")
            for key, value in metadata.items():
                print(f"   {key}: {value}")
            print()
        
        # Summary analysis
        print("📈 FIELD COMPLETENESS ANALYSIS:")
        print("=" * 60)
        
        total_citations = len(result.get('citations', []))
        verified_citations = sum(1 for c in result.get('citations', []) if c.get('verified'))
        citations_with_names = sum(1 for c in result.get('citations', []) if c.get('extracted_case_name'))
        citations_with_dates = sum(1 for c in result.get('citations', []) if c.get('extracted_date'))
        citations_with_canonical_names = sum(1 for c in result.get('citations', []) if c.get('canonical_name'))
        citations_with_canonical_dates = sum(1 for c in result.get('citations', []) if c.get('canonical_date'))
        citations_with_urls = sum(1 for c in result.get('citations', []) if c.get('canonical_url'))
        
        print(f"📊 Total Citations: {total_citations}")
        print(f"✅ Verified Citations: {verified_citations}/{total_citations} ({verified_citations/total_citations*100:.1f}%)")
        print(f"📝 With Extracted Names: {citations_with_names}/{total_citations} ({citations_with_names/total_citations*100:.1f}%)")
        print(f"📅 With Extracted Dates: {citations_with_dates}/{total_citations} ({citations_with_dates/total_citations*100:.1f}%)")
        print(f"🎯 With Canonical Names: {citations_with_canonical_names}/{total_citations} ({citations_with_canonical_names/total_citations*100:.1f}%)")
        print(f"📅 With Canonical Dates: {citations_with_canonical_dates}/{total_citations} ({citations_with_canonical_dates/total_citations*100:.1f}%)")
        print(f"🔗 With Canonical URLs: {citations_with_urls}/{total_citations} ({citations_with_urls/total_citations*100:.1f}%)")
        print()
        
        # Overall assessment
        if verified_citations == total_citations and citations_with_canonical_names == total_citations:
            print("🎉 EXCELLENT: All citations verified with complete metadata!")
        elif verified_citations > total_citations * 0.5:
            print("✅ GOOD: Most citations verified, some metadata missing")
        else:
            print("⚠️  NEEDS IMPROVEMENT: Many citations not verified or missing metadata")
        
        print(f"\n🔍 FULL RESULT STRUCTURE:")
        print("=" * 60)
        print(json.dumps(result, indent=2, default=str))
        
    except Exception as e:
        print(f"❌ Complete backend test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_complete_backend()
