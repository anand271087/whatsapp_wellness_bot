from services.sheets import GoogleSheetsService
import json

def debug_sheet():
    print("--- DEBUGGING COUNSELORS SHEET ---")
    service = GoogleSheetsService()
    if service.connect():
        try:
            sheet = service.spreadsheet.worksheet('Counselors')
            records = sheet.get_all_records()
            print(f"RAW RECORDS FETCHED ({len(records)}):")
            print(json.dumps(records, indent=2))
            
            print("\n--- FILTERING LOGIC CHECK ---")
            active = []
            for i, r in enumerate(records):
                is_active_val = r.get('is_active')
                print(f"Row {i+1}: 'is_active' raw value: '{is_active_val}' (Type: {type(is_active_val)})")
                
                if str(is_active_val).upper() == 'TRUE':
                    print(f"  -> MATCHED! Added to active list.")
                    active.append(r)
                else:
                    print(f"  -> FAILED FILTER. Expected 'TRUE' (string), but got '{str(is_active_val).upper()}'")
            
            print(f"\nTotal Active Counselors Found: {len(active)}")
        except Exception as e:
            print(f"Error accessing worksheet: {e}")
    else:
        print("Connection Failed")

if __name__ == "__main__":
    debug_sheet()
