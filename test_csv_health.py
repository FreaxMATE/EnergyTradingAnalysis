#!/usr/bin/env python3
"""Test script to diagnose CSV file health and issues."""

import os
import csv
import sys
from pathlib import Path

DATA_DIR = Path("data")
COUNTRIES = [
    "AT", "BE", "CH", "CZ", "DE_LU", "DK_1", "DK_2", "EE", "ES",
    "FI", "FR", "GR", "LT", "LV", "NL", "NO_1", "NO_2", "RO", "SE_3", "SE_4", "SK"
]

def check_csv_file(filepath):
    """Check a single CSV file for issues."""
    try:
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []
        
        return {
            "exists": True,
            "size_bytes": os.path.getsize(filepath),
            "total_lines": len(rows),
            "headers": headers,
            "data_rows": len(data_rows),
            "columns": len(headers),
            "error": None
        }
    except Exception as e:
        return {
            "exists": True,
            "error": str(e),
            "size_bytes": os.path.getsize(filepath) if os.path.exists(filepath) else 0,
        }

def main():
    print("=" * 80)
    print("CSV HEALTH CHECK REPORT")
    print("=" * 80)
    
    # Check features.csv
    print("\n📋 FEATURES.CSV")
    print("-" * 80)
    features_path = DATA_DIR / "features.csv"
    if features_path.exists():
        result = check_csv_file(features_path)
        print(f"  Size: {result['size_bytes']} bytes")
        print(f"  Total lines: {result['total_lines']}")
        print(f"  Headers: {result['headers']}")
        print(f"  Data rows: {result['data_rows']}")
        if result['error']:
            print(f"  ❌ ERROR: {result['error']}")
        elif result['data_rows'] == 0:
            print(f"  ⚠️  WARNING: File has headers but NO DATA!")
    else:
        print(f"  ❌ File not found!")
    
    # Check country files
    print("\n🌍 COUNTRY FILES SUMMARY")
    print("-" * 80)
    
    issues = []
    all_files = []
    
    for country in COUNTRIES:
        country_dir = DATA_DIR / country
        if not country_dir.exists():
            issues.append(f"  ❌ {country}: Directory not found")
            continue
        
        files = {
            f"{country}.csv": country_dir / f"{country}.csv",
            f"{country}_ma.csv": country_dir / f"{country}_ma.csv",
            f"{country}_forecast.csv": country_dir / f"{country}_forecast.csv",
            f"{country}_ml_forecast.csv": country_dir / f"{country}_ml_forecast.csv",
            f"{country}_generation.csv": country_dir / f"{country}_generation.csv",
        }
        
        country_status = []
        for file_type, filepath in files.items():
            if filepath.exists():
                result = check_csv_file(filepath)
                all_files.append((country, file_type, result))
                
                status = "✅"
                if result.get('error'):
                    status = "❌"
                    country_status.append(f"{status} {file_type}: {result['error']}")
                elif result.get('data_rows', 0) == 0:
                    status = "⚠️"
                    country_status.append(f"{status} {file_type}: {result['total_lines']} lines (headers only)")
                else:
                    country_status.append(f"{status} {file_type}: {result['data_rows']} rows")
            else:
                country_status.append(f"❌ {file_type}: NOT FOUND")
        
        if country_status:
            print(f"\n  {country}:")
            for status_line in country_status:
                print(f"    {status_line}")
    
    # Summary statistics
    print("\n📊 STATISTICS")
    print("-" * 80)
    
    problem_files = [
        (c, f, r) for c, f, r in all_files 
        if r.get('error') or r.get('data_rows', 0) == 0
    ]
    
    healthy_files = [
        (c, f, r) for c, f, r in all_files 
        if not r.get('error') and r.get('data_rows', 0) > 0
    ]
    
    print(f"  Total files checked: {len(all_files)}")
    print(f"  Healthy files: {len(healthy_files)}")
    print(f"  Problem files: {len(problem_files)}")
    
    if problem_files:
        print(f"\n  ⚠️  PROBLEM FILES:")
        for country, file_type, result in problem_files:
            if result.get('error'):
                print(f"    - {country}/{file_type}: {result['error']}")
            else:
                print(f"    - {country}/{file_type}: Has headers but NO DATA ({result['total_lines']} lines)")
    
    print("\n" + "=" * 80)
    
    return len(problem_files) == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
