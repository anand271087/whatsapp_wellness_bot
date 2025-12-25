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
            # 1. Try Env Var (JSON Content)
            json_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")
            
            # 2. Try Render Secret File Path
            render_secret_path = "/etc/secrets/credentials.json"
            
            if json_creds:
                creds_dict = json.loads(json_creds)
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, self.scope)
            elif os.path.exists(render_secret_path):
                creds = ServiceAccountCredentials.from_json_keyfile_name(render_secret_path, self.scope)
            else:
                # 3. Fallback to local file (Development)
                creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_file, self.scope)
            
            self.client = gspread.authorize(creds)
            try:
                self.spreadsheet = self.client.open(self.sheet_name)
                # Ensure schema is up to date even if sheet exists
                self.ensure_bookings_schema()
            except gspread.SpreadsheetNotFound:
                # Auto-create if not found
                self.spreadsheet = self.client.create(self.sheet_name)
                self.setup_schema()
                print(f"Created new sheet: {self.sheet_name}")
            
            return True
        except Exception as e:
            print(f"Error connecting to Google Sheets: {e}")
            return False

    def ensure_bookings_schema(self):
        """Ensure Bookings sheet has all required columns."""
        try:
            b_sheet = self.spreadsheet.worksheet('Bookings')
            headers = b_sheet.row_values(1)
            if 'booking_status' not in headers:
                # Add the column header
                b_sheet.update_cell(1, 9, 'booking_status')
                # Optional: Backfill existing rows?
                # For now, our code defaults to ACTIVE so it's fine.
        except Exception as e:
            print(f"Error ensuring schema: {e}")

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
            b_sheet.append_row(['booking_id', 'user_phone', 'counselor_id', 'date', 'time_slot', 'payment_status', 'razorpay_order_id', 'timestamp', 'booking_status'])

    def get_active_counselors(self):
        sheet = self.spreadsheet.worksheet('Counselors')
        # get_all_records() fails if headers are duplicate/empty
        rows = sheet.get_all_values()
        
        # Skip header
        if len(rows) < 2:
            return []
            
        counselors = []
        # Columns: id(0), name(1), image_url(2), description(3), is_active(4)
        for r in rows[1:]:
            if len(r) < 5: continue
            
            # Check is_active (col 4)
            if str(r[4]).strip().upper() == 'TRUE':
                counselors.append({
                    'id': r[0],
                    'name': r[1],
                    'image_url': r[2],
                    'description': r[3],
                    'is_active': r[4]
                })
        return counselors

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
            booking_data.get('timestamp'),
            'ACTIVE' # booking_status
        ]
        sheet.append_row(row)

    def update_booking_payment(self, order_id, status='PAID'):
        # Legacy support or if order_id is known
        sheet = self.spreadsheet.worksheet('Bookings')
        cell = sheet.find(order_id)
        if cell:
            sheet.update_cell(cell.row, 6, status)
            return True
        return False

    def update_booking_status(self, booking_id, status, razorpay_order_id=None):
        """Updates booking status found by booking_id (Col 1)."""
        sheet = self.spreadsheet.worksheet('Bookings')
        cell = sheet.find(booking_id)
        if cell:
            # Update Payment Status (Col 6)
            sheet.update_cell(cell.row, 6, status)
            # Update Order ID (Col 7) if provided
            if razorpay_order_id:
                sheet.update_cell(cell.row, 7, razorpay_order_id)
            return True
        return False
    
    def get_user_booking_count(self, user_phone):
        """Count total PAID bookings for a user (lifetime limit)."""
        sheet = self.spreadsheet.worksheet('Bookings')
        records = sheet.get_all_records()
        count = sum(1 for r in records 
                   if r.get('user_phone') == user_phone and r.get('payment_status') == 'PAID')
        return count
    
    def get_user_active_bookings(self, user_phone):
        """Get all ACTIVE bookings with PAID status for a user."""
        sheet = self.spreadsheet.worksheet('Bookings')
        records = sheet.get_all_records()
        active_bookings = [
            r for r in records 
            if r.get('user_phone') == user_phone 
            and r.get('payment_status') == 'PAID'
            and r.get('booking_status', 'ACTIVE') in ['ACTIVE', '']  # Handle missing/empty column for backward compatibility
        ]
        return active_bookings
    
    def update_booking_datetime(self, booking_id, new_date, new_time_slot):
        """Update date and time for an existing booking (for rescheduling)."""
        sheet = self.spreadsheet.worksheet('Bookings')
        cell = sheet.find(booking_id)
        if cell:
            # Update Date (Col 4)
            sheet.update_cell(cell.row, 4, new_date)
            # Update Time Slot (Col 5)
            sheet.update_cell(cell.row, 5, new_time_slot)
            return True
        return False
    
    def cancel_booking(self, booking_id):
        """Mark a booking as CANCELLED."""
        sheet = self.spreadsheet.worksheet('Bookings')
        cell = sheet.find(booking_id)
        if cell:
            # Update Booking Status (Col 9)
            sheet.update_cell(cell.row, 9, 'CANCELLED')
            return True
        return False
