#!/usr/bin/env python3
"""
Analyze Bandit Security Report
"""

import json
from collections import defaultdict

def analyze_bandit_report(report_file):
    """Analyze the bandit security report and provide a summary."""
    
    with open(report_file, 'r') as f:
        data = json.load(f)
    
    results = data.get('results', [])
    metrics = data.get('metrics', {}).get('_totals', {})
    
    print("🔒 BANDIT SECURITY ANALYSIS REPORT")
    print("=" * 50)
    
    # Overall metrics
    print(f"\n📊 OVERALL METRICS:")
    print(f"   Total Lines of Code: {metrics.get('loc', 0):,}")
    print(f"   Total Issues Found: {len(results)}")
    print(f"   High Severity: {metrics.get('SEVERITY.HIGH', 0)}")
    print(f"   Medium Severity: {metrics.get('SEVERITY.MEDIUM', 0)}")
    print(f"   Low Severity: {metrics.get('SEVERITY.LOW', 0)}")
    
    # Severity breakdown
    severity_counts = defaultdict(int)
    confidence_counts = defaultdict(int)
    test_types = defaultdict(int)
    
    for result in results:
        severity_counts[result.get('issue_severity', 'UNKNOWN')] += 1
        confidence_counts[result.get('issue_confidence', 'UNKNOWN')] += 1
        test_types[result.get('test_name', 'UNKNOWN')] += 1
    
    print(f"\n🚨 SEVERITY BREAKDOWN:")
    for severity, count in sorted(severity_counts.items()):
        print(f"   {severity}: {count}")
    
    print(f"\n🎯 CONFIDENCE BREAKDOWN:")
    for confidence, count in sorted(confidence_counts.items()):
        print(f"   {confidence}: {count}")
    
    # Top issues by type
    print(f"\n🔍 TOP ISSUE TYPES:")
    for test_name, count in sorted(test_types.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   {test_name}: {count}")
    
    # High severity issues
    high_severity = [r for r in results if r.get('issue_severity') == 'HIGH']
    if high_severity:
        print(f"\n⚠️  HIGH SEVERITY ISSUES ({len(high_severity)}):")
        for i, issue in enumerate(high_severity[:5], 1):
            print(f"   {i}. {issue.get('filename', 'Unknown')}:{issue.get('line_number', 'Unknown')}")
            print(f"      Test: {issue.get('test_name', 'Unknown')}")
            print(f"      Issue: {issue.get('issue_text', 'Unknown')}")
            print()
    
    # Files with most issues
    file_issues = defaultdict(int)
    for result in results:
        file_issues[result.get('filename', 'Unknown')] += 1
    
    print(f"\n📁 FILES WITH MOST ISSUES:")
    for filename, count in sorted(file_issues.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   {filename}: {count} issues")
    
    # Security recommendations
    print(f"\n💡 SECURITY RECOMMENDATIONS:")
    if high_severity:
        print("   ⚠️  Address HIGH severity issues immediately")
    if severity_counts.get('MEDIUM', 0) > 10:
        print("   ⚠️  Review MEDIUM severity issues")
    if len(results) > 50:
        print("   ⚠️  Consider implementing additional security measures")
    
    print("   ✅ Continue regular security scanning")
    print("   ✅ Implement automated security testing in CI/CD")
    print("   ✅ Regular dependency vulnerability scanning")
    
    return {
        'total_issues': len(results),
        'high_severity': severity_counts.get('HIGH', 0),
        'medium_severity': severity_counts.get('MEDIUM', 0),
        'low_severity': severity_counts.get('LOW', 0)
    }

def compare_reports():
    """Compare the original and fixed security reports."""
    
    print("🔄 COMPARING SECURITY REPORTS")
    print("=" * 50)
    
    try:
        # Read original report
        with open('bandit_security_report.json', 'r') as f:
            original_data = json.load(f)
        
        # Read fixed report
        with open('bandit_security_report_fixed.json', 'r') as f:
            fixed_data = json.load(f)
        
        original_results = original_data.get('results', [])
        fixed_results = fixed_data.get('results', [])
        
        original_high = sum(1 for r in original_results if r.get('issue_severity') == 'HIGH')
        fixed_high = sum(1 for r in fixed_results if r.get('issue_severity') == 'HIGH')
        
        original_medium = sum(1 for r in original_results if r.get('issue_severity') == 'MEDIUM')
        fixed_medium = sum(1 for r in fixed_results if r.get('issue_severity') == 'MEDIUM')
        
        print(f"\n📊 COMPARISON RESULTS:")
        print(f"   Original HIGH severity issues: {original_high}")
        print(f"   Fixed HIGH severity issues: {fixed_high}")
        print(f"   HIGH severity reduction: {original_high - fixed_high}")
        
        print(f"\n   Original MEDIUM severity issues: {original_medium}")
        print(f"   Fixed MEDIUM severity issues: {fixed_medium}")
        print(f"   MEDIUM severity reduction: {original_medium - fixed_medium}")
        
        print(f"\n   Original total issues: {len(original_results)}")
        print(f"   Fixed total issues: {len(fixed_results)}")
        print(f"   Total reduction: {len(original_results) - len(fixed_results)}")
        
        if fixed_high == 0:
            print(f"\n🎉 SUCCESS: All HIGH severity issues have been resolved!")
        else:
            print(f"\n⚠️  WARNING: {fixed_high} HIGH severity issues remain")
            
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
    except Exception as e:
        print(f"❌ Error comparing reports: {e}")

if __name__ == "__main__":
    try:
        # Analyze the fixed report
        results = analyze_bandit_report('bandit_security_report_fixed.json')
        print(f"\n✅ Analysis complete!")
        
        # Compare with original
        compare_reports()
        
    except FileNotFoundError:
        print("❌ bandit_security_report_fixed.json not found. Run bandit first.")
    except Exception as e:
        print(f"❌ Error analyzing report: {e}") 