#!/usr/bin/env python3
"""
LinkedIn Leads JSON to CSV Converter
Converts a JSON file containing LinkedIn leads data to a formatted CSV file.
"""

import json
import csv
import sys
from pathlib import Path


def extract_leads_from_json(json_data):
    """
    Extract relevant lead information from JSON data.
    
    Args:
        json_data: Dictionary containing the leads data
        
    Returns:
        List of dictionaries with extracted lead information
    """
    leads = []
    
    if isinstance(json_data, str):
        json_data = json.loads(json_data)
    
    leads_list = json_data.get('leads', [])
    
    for lead in leads_list:
        # Extract connection degree (how closely connected)
        connection_degree = 3  # default
        if 'linkedinAccountRelativeProperties' in lead and lead['linkedinAccountRelativeProperties']:
            connection_degree = lead['linkedinAccountRelativeProperties'][0].get('connectionDegree', 3)
        
        # Build LinkedIn profile URL
        linkedin_url = ""
        if 'linkedinProfileSlug' in lead:
            linkedin_url = f"https://linkedin.com/in/{lead['linkedinProfileSlug']}"
        
        lead_info = {
            'First Name': lead.get('firstName', ''),
            'Last Name': lead.get('lastName', ''),
            'Title': lead.get('linkedinJobTitle', ''),
            'Company': lead.get('companyName', ''),
            'Company Industry': lead.get('companyIndustry', ''),
            'Location': lead.get('location', ''),
            'LinkedIn Headline': lead.get('linkedinHeadline', ''),
            'Connection Degree': connection_degree,
            'LinkedIn Profile URL': linkedin_url,
            'Job Date Range': lead.get('linkedinJobDateRange', ''),
            'Company Website': lead.get('company', {}).get('properties', {}).get('websiteUrl', ''),
        }
        
        leads.append(lead_info)
    
    return leads


def json_file_to_csv(json_file_path, csv_file_path):
    """
    Read JSON file and convert to CSV.
    
    Args:
        json_file_path: Path to input JSON file
        csv_file_path: Path to output CSV file
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        leads = extract_leads_from_json(json_data)
        
        if not leads:
            print("❌ No leads found in JSON data")
            return False
        
        # Write to CSV
        fieldnames = [
            'First Name', 'Last Name', 'Title', 'Company', 'Company Industry',
            'Location', 'LinkedIn Headline', 'Connection Degree',
            'LinkedIn Profile URL', 'Job Date Range', 'Company Website'
        ]
        
        with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(leads)
        
        print(f"✅ Successfully converted {len(leads)} leads to CSV")
        print(f"📁 Output file: {csv_file_path}")
        return True
        
    except FileNotFoundError:
        print(f"❌ Error: File not found - {json_file_path}")
        return False
    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON format")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def json_string_to_csv(json_string, csv_file_path):
    """
    Convert JSON string directly to CSV.
    
    Args:
        json_string: JSON string containing leads data
        csv_file_path: Path to output CSV file
    """
    try:
        json_data = json.loads(json_string)
        leads = extract_leads_from_json(json_data)
        
        if not leads:
            print("❌ No leads found in JSON data")
            return False
        
        # Write to CSV
        fieldnames = [
            'First Name', 'Last Name', 'Title', 'Company', 'Company Industry',
            'Location', 'LinkedIn Headline', 'Connection Degree',
            'LinkedIn Profile URL', 'Job Date Range', 'Company Website'
        ]
        
        with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(leads)
        
        print(f"✅ Successfully converted {len(leads)} leads to CSV")
        print(f"📁 Output file: {csv_file_path}")
        return True
        
    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON format")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def main():
    """Main entry point for the script."""
    
    print("=" * 60)
    print("LinkedIn Leads JSON to CSV Converter")
    print("=" * 60)
    
    if len(sys.argv) < 2:
        print("\n📖 Usage:")
        print("   Option 1: python json_to_csv_leads.py <input_json_file> [output_csv_file]")
        print("   Option 2: python json_to_csv_leads.py --string <json_string> [output_csv_file]")
        print("\n📝 Examples:")
        print("   python json_to_csv_leads.py leads.json leads_output.csv")
        print("   python json_to_csv_leads.py --string '{\"leads\": [...]}' output.csv")
        sys.exit(1)
    
    # Check if using JSON string mode
    if sys.argv[1] == '--string':
        if len(sys.argv) < 3:
            print("❌ Error: JSON string required with --string option")
            sys.exit(1)
        
        json_string = sys.argv[2]
        csv_file = sys.argv[3] if len(sys.argv) > 3 else 'leads_output.csv'
        
        print(f"\n📥 Processing JSON string...")
        print(f"📤 Output file: {csv_file}")
        json_string_to_csv(json_string, csv_file)
    
    else:
        # File mode
        json_file = sys.argv[1]
        csv_file = sys.argv[2] if len(sys.argv) > 2 else 'leads_output.csv'
        
        if not Path(json_file).exists():
            print(f"❌ Error: File not found - {json_file}")
            sys.exit(1)
        
        print(f"\n📥 Input file: {json_file}")
        print(f"📤 Output file: {csv_file}")
        json_file_to_csv(json_file, csv_file)


if __name__ == '__main__':
    main()