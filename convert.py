"""
JSON to CSV Converter
Converts all scraped JSON outputs to CSV format for easy spreadsheet viewing
"""

import pandas as pd
import json
import os

def convert_json_to_csv(file_list):
    """Convert JSON files to CSV"""
    for file_name in file_list:
        # Check if file exists
        if not os.path.exists(file_name):
            print(f"⚠️ File not found: {file_name}")
            continue
            
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handling different JSON structures
            if isinstance(data, list):
                # Standard list of dictionaries (events, news)
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                # Nested structure (specifically for yearly_holidays.json)
                # This flattens the dictionary where years are keys
                all_records = []
                for year, holidays in data.items():
                    if isinstance(holidays, list):
                        for holiday in holidays:
                            holiday['year_category'] = year
                            all_records.append(holiday)
                df = pd.DataFrame(all_records)
            else:
                print(f"Unsupported data type in {file_name}")
                continue
            
            # Generate output filename
            output_csv = file_name.replace('.json', '.csv')
            df.to_csv(output_csv, index=False, encoding='utf-8-sig')
            print(f"✅ Successfully converted: {file_name} -> {output_csv}")
            print(f"   Rows: {len(df)}, Columns: {len(df.columns)}")
            
        except Exception as e:
            print(f"❌ Error processing {file_name}: {e}")

def main():
    """Main function - convert all JSON files in outputs directory"""
    
    # Create outputs directory if it doesn't exist
    if not os.path.exists('outputs'):
        os.makedirs('outputs')
        print("📁 Created outputs directory")
    
    # List of your specific files
    files_to_convert = [
        'outputs/lebanon_events_all.json',
        'outputs/lebanon_events_filtered.json',
        'outputs/final_nna_news.json',
        'outputs/yearly_holidays.json'
    ]
    
    print("\n🔄 Starting JSON to CSV conversion...")
    print("=" * 50)
    
    convert_json_to_csv(files_to_convert)
    
    print("=" * 50)
    print("✅ Conversion complete!")
    print("\nGenerated files:")
    for json_file in files_to_convert:
        csv_file = json_file.replace('.json', '.csv')
        if os.path.exists(csv_file):
            file_size = os.path.getsize(csv_file) / 1024
            print(f"  ✓ {csv_file} ({file_size:.1f} KB)")

if __name__ == "__main__":
    main()
