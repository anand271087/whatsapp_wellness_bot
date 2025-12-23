import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

class GoogleSheetsService:
    def __init__(self, credentials_file='credentials.json', sheet_name='WellnessCenterBot'):
        self.scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        self.credentials_file = credentials_file
        self.sheet_name = sheet_name
        self.client = None
        self.spreadsheet = None

    def connect(self):
        try:
            # Try Env Var first (Production)
            json_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")
            if json_creds:
                creds_dict = json.loads(json_creds)
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, self.scope)
            else:
                # Fallback to local file (Development)
                creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_file, self.scope)
            
            self.client = gspread.authorize(creds)
            try:
                self.spreadsheet = self.client.open(self.sheet_name)
            except gspread.SpreadsheetNotFound:
                # Auto-create if not found (requires Drive API enabled and shared manually or created here)
                # For simplicity, we'll assume it exists or throw an error. 
                # Ideally, we create it.
                self.spreadsheet = self.client.create(self.sheet_name)
                self.setup_schema()
                # Need to share this sheet with the user? 
                # self.spreadsheet.share('user_email@gmail.com', perm_type='user', role='owner')
                print(f"Created new sheet: {self.sheet_name}")
            
            return True
        except Exception as e:
            print(f"Error connecting to Google Sheets: {e}")
            return False

    def setup_schema(self):
        """Initializes the sheets with headers if they are empty."""
        # 1. Counselors Sheet
        try:
            c_sheet = self.spreadsheet.worksheet('Counselors')
        except:
            c_sheet = self.spreadsheet.add_worksheet(title='Counselors', rows=100, cols=10)
        
        if not c_sheet.get_all_values():
            c_sheet.append_row(['id', 'name', 'image_url', 'description', 'is_active'])
            # Add dummy data
            c_sheet.append_row(['1', 'Dr. Smith', 'https://example.com/dr_smith.jpg', 'Expert Psychologist', 'TRUE'])
            c_sheet.append_row(['2', 'Dr. Jane', 'https://example.com/dr_jane.jpg', 'Wellness Coach', 'TRUE'])

        # 2. Bookings Sheet
        try:
            b_sheet = self.spreadsheet.worksheet('Bookings')
        except:
            b_sheet = self.spreadsheet.add_worksheet(title='Bookings', rows=1000, cols=10)
        
        if not b_sheet.get_all_values():
            b_sheet.append_row(['booking_id', 'user_phone', 'counselor_id', 'date', 'time_slot', 'payment_status', 'razorpay_order_id', 'timestamp'])

    def get_active_counselors(self):
        sheet = self.spreadsheet.worksheet('Counselors')
        records = sheet.get_all_records()
        return [r for r in records if str(r.get('is_active')).upper() == 'TRUE']

    def get_bookings_for_date(self, date_str, counselor_id):
        sheet = self.spreadsheet.worksheet('Bookings')
        records = sheet.get_all_records()
        # Filter by date and counselor
        booked_slots = [
            r['time_slot'] for r in records 
            if r['date'] == date_str and str(r['counselor_id']) == str(counselor_id) and r['payment_status'] == 'PAID'
        ]
        return booked_slots

    def create_booking_hold(self, booking_data):
        """Creates a temporary booking or 'HOLD' status before payment."""
        sheet = self.spreadsheet.worksheet('Bookings')
        row = [
            booking_data.get('booking_id'),
            booking_data.get('user_phone'),
            booking_data.get('counselor_id'),
            booking_data.get('date'),
            booking_data.get('time_slot'),
            'PENDING', # payment_status
            booking_data.get('razorpay_order_id', ''),
            booking_data.get('timestamp')
        ]
        sheet.append_row(row)

    def update_booking_payment(self, order_id, status='PAID'):
        sheet = self.spreadsheet.worksheet('Bookings')
        # Find cell with order_id
        cell = sheet.find(order_id)
        if cell:
            # Payment status is column 6 ('F')
            sheet.update_cell(cell.row, 6, status)
            return True
        return False
