import logging
import datetime
import uuid
from services.sheets import GoogleSheetsService
from services.whatsapp_api import WhatsAppAPI
from services.razorpay_api import RazorpayAPI

logger = logging.getLogger(__name__)

# Simple in-memory state management
# structure: { "phone_number": { "state": "STATE_NAME", "data": {...} } }
user_sessions = {}

# States
STATE_START = "START"
STATE_SELECT_COUNSELOR = "SELECT_COUNSELOR"
STATE_SELECT_DATE = "SELECT_DATE"
STATE_SELECT_SLOT = "SELECT_SLOT"
STATE_PAYMENT = "PAYMENT_PENDING"

class FlowHandler:
    def __init__(self, sheet_service: GoogleSheetsService):
        self.sheets = sheet_service
        self.sheets.connect()
        self.wa_api = WhatsAppAPI()
        self.rz_api = RazorpayAPI()

    def handle_message(self, user_phone, message_body):
        # Normalize state
        if user_phone not in user_sessions:
            user_sessions[user_phone] = {"state": STATE_START, "data": {}}
        
        current_state = user_sessions[user_phone]["state"]
        
        # 1. GLOBAL COMMANDS (Start/Reset)
        if message_body.lower() in ['hi', 'hello', 'start', 'reset', 'menu']:
            user_sessions[user_phone] = {"state": STATE_START, "data": {}}
            return self.send_welcome_menu(user_phone)

        # 2. STATE HANDLERS
        if current_state == STATE_START:
            # Expecting "Book Appointment" or similar selection
            if "book" in message_body.lower():
                return self.start_booking_flow(user_phone)
            # else: ignore non-commands in START state to avoid spam loop
            return {"status": "ignored_no_command"}

        elif current_state == STATE_SELECT_COUNSELOR:
            # Expecting Counselor Selection (ID or Name)
            selected_counselor_id = self.parse_counselor_selection(message_body)
            if selected_counselor_id:
                user_sessions[user_phone]["data"]["counselor_id"] = selected_counselor_id
                user_sessions[user_phone]["state"] = STATE_SELECT_DATE
                return self.send_date_selection(user_phone)
            else:
                self.wa_api.send_text(user_phone, "Invalid selection. Please reply with the ID of the counselor.")
                return {"status": "error", "msg": "invalid_selection"}

        elif current_state == STATE_SELECT_DATE:
            # Expecting Date (Today, Tomorrow, etc.)
            selected_date = self.parse_date_selection(message_body) # Returns YYYY-MM-DD
            if selected_date:
                user_sessions[user_phone]["data"]["date"] = selected_date
                user_sessions[user_phone]["state"] = STATE_SELECT_SLOT
                return self.send_slot_selection(user_phone, selected_date)
            else:
                self.wa_api.send_text(user_phone, "Please select a valid date (e.g. 2024-10-10 or Today).")
                return {"status": "error", "msg": "invalid_date"}

        elif current_state == STATE_SELECT_SLOT:
            # Expecting Time Slot
            slot = message_body.strip() 
            if slot:
                user_sessions[user_phone]["data"]["time_slot"] = slot
                user_sessions[user_phone]["state"] = STATE_PAYMENT
                return self.generate_payment_link(user_phone)
            else:
                self.wa_api.send_text(user_phone, "Please type a time slot.")
                return {"status": "error", "msg": "invalid_slot"}

        self.wa_api.send_text(user_phone, "I didn't understand that. Type 'Hi' to start over.")
        return {"status": "ignored"}

    # --- RESPONSES ---

    def send_welcome_menu(self, phone):
        msg = "Welcome to the Wellness Center! \nHow can we help you today?\n\nType 'Book' to book a counseling session."
        self.wa_api.send_text(phone, msg)
        return {"status": "sent_welcome"}

    def start_booking_flow(self, phone):
        counselors = self.sheets.get_active_counselors()
        if not counselors:
            self.wa_api.send_text(phone, "Sorry, no counselors are available right now.")
            return {"status": "no_counselors"}
            
        if not counselors:
            self.wa_api.send_text(phone, "Sorry, no counselors are available right now.")
            return {"status": "no_counselors"}
            
        # Send images for counselors with image URLs
        for c in counselors:
            if c.get('image_url'):
                caption = f"*{c['name']}*\n{c['description']}\nID: {c['id']}"
                self.wa_api.send_image(phone, c['image_url'], caption)
        
        # Then send interactive list for selection
        rows = []
        for c in counselors:
            rows.append({
                "id": str(c['id']),
                "title": c['name'][:24],
                "description": (c['description'][:72] if c['description'] else "Book Now")
            })
        
        sections = [{"title": "Select Counselor", "rows": rows}]
        self.wa_api.send_interactive_list(
            phone,
            "Tap below to choose your counselor:",
            "View Options",
            sections
        )
        
        user_sessions[phone]["state"] = STATE_SELECT_COUNSELOR
        return {"status": "sent_counselors"}

    def send_date_selection(self, phone):
        today = datetime.date.today()
        # Max 3 buttons allowed
        dates = [
            {"id": str(today), "title": "Today"},
            {"id": str(today + datetime.timedelta(days=1)), "title": "Tomorrow"},
            {"id": str(today + datetime.timedelta(days=2)), "title": "Day After"}
        ]
        
        self.wa_api.send_interactive_buttons(
            phone,
            "Please select a date for your appointment:",
            dates
        )
        return {"status": "sent_date_buttons"}

    def send_slot_selection(self, phone, date_str):
        counselor_id = user_sessions[phone]["data"].get("counselor_id")
        all_slots = ["09:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00"]
        booked = self.sheets.get_bookings_for_date(date_str, counselor_id)
        available = [s for s in all_slots if s not in booked]
        
        if not available:
            self.wa_api.send_text(phone, f"No slots available on {date_str}. Please choose another date.")
            return {"status": "no_slots"}
        
        # Interactive List for Slots
        rows = [{"id": slot, "title": slot, "description": ""} for slot in available]
        sections = [{"title": f"Slots for {date_str}", "rows": rows}]
        
        self.wa_api.send_interactive_list(
            phone,
            f"Available slots for {date_str}:",
            "Select Time",
            sections
        )
        return {"status": "sent_slots_list"}

    def generate_payment_link(self, phone):
        data = user_sessions[phone]["data"]
        booking_id = str(uuid.uuid4())[:8]
        amount_paise = 50000 
        
        # Razorpay Link
        link = self.rz_api.create_payment_link(
            amount_paise, 
            f"Booking {booking_id}", 
            phone, 
            booking_id
        )

        booking_record = {
            "booking_id": booking_id,
            "user_phone": phone,
            "counselor_id": data['counselor_id'],
            "date": data['date'],
            "time_slot": data['time_slot'],
            "razorpay_order_id": "", 
            "timestamp": str(datetime.datetime.now())
        }
        self.sheets.create_booking_hold(booking_record)
        
        self.wa_api.send_text(phone, f"Slot Held! Pay ₹500 to confirm:\n{link}")
        return {"status": "sent_payment_link"}

    # --- HELPERS ---
    def parse_counselor_selection(self, text):
        return text.split('.')[0].strip()

    def parse_date_selection(self, text):
        try:
            return text.split(' ')[0].strip()
        except:
            return None
