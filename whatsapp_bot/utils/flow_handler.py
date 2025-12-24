import logging
import datetime
import uuid
import os
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
STATE_RESCHEDULE_SELECT = "RESCHEDULE_SELECT"
STATE_RESCHEDULE_DATE = "RESCHEDULE_DATE"
STATE_RESCHEDULE_SLOT = "RESCHEDULE_SLOT"

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
            # Expecting "Book Appointment" or "Talk to Us" selection
            if "book_btn" in message_body.lower() or "book" in message_body.lower():
                return self.start_booking_flow(user_phone)
            elif "talk_btn" in message_body.lower() or "talk" in message_body.lower():
                return self.send_contact_info(user_phone)
            elif "reschedule_btn" in message_body.lower() or "reschedule" in message_body.lower():
                return self.start_reschedule_flow(user_phone)
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
        
        elif current_state == STATE_RESCHEDULE_SELECT:
            # User selected a booking to reschedule
            booking_id = message_body.strip()
            # Validate booking belongs to user
            active_bookings = self.sheets.get_user_active_bookings(user_phone)
            if any(b['booking_id'] == booking_id for b in active_bookings):
                user_sessions[user_phone]["data"]["reschedule_booking_id"] = booking_id
                user_sessions[user_phone]["state"] = STATE_RESCHEDULE_DATE
                return self.send_reschedule_date_selection(user_phone)
            else:
                self.wa_api.send_text(user_phone, "Invalid booking selection. Please try again.")
                return {"status": "error", "msg": "invalid_booking"}
        
        elif current_state == STATE_RESCHEDULE_DATE:
            # User selected new date
            selected_date = self.parse_date_selection(message_body)
            if selected_date:
                user_sessions[user_phone]["data"]["new_date"] = selected_date
                user_sessions[user_phone]["state"] = STATE_RESCHEDULE_SLOT
                # Get counselor from original booking
                booking_id = user_sessions[user_phone]["data"]["reschedule_booking_id"]
                bookings = self.sheets.get_user_active_bookings(user_phone)
                original_booking = next((b for b in bookings if b['booking_id'] == booking_id), None)
                if original_booking:
                    counselor_id = original_booking['counselor_id']
                    return self.send_reschedule_slot_selection(user_phone, selected_date, counselor_id)
                else:
                    self.wa_api.send_text(user_phone, "Error finding booking. Please start over.")
                    return {"status": "error"}
            else:
                self.wa_api.send_text(user_phone, "Please select a valid date.")
                return {"status": "error", "msg": "invalid_date"}
        
        elif current_state == STATE_RESCHEDULE_SLOT:
            # User selected new time slot
            new_slot = message_body.strip()
            if new_slot:
                booking_id = user_sessions[user_phone]["data"]["reschedule_booking_id"]
                new_date = user_sessions[user_phone]["data"]["new_date"]
                return self.complete_reschedule(user_phone, booking_id, new_date, new_slot)
            else:
                self.wa_api.send_text(user_phone, "Please select a time slot.")
                return {"status": "error", "msg": "invalid_slot"}

        self.wa_api.send_text(user_phone, "I didn't understand that. Type 'Hi' to start over.")
        return {"status": "ignored"}

    # --- RESPONSES ---

    def send_welcome_menu(self, phone):
        # Check user status first
        user_status = self.check_user_status(phone)
        booking_count = user_status['booking_count']
        has_active = len(user_status['active_bookings']) > 0
        
        buttons = []
        body_text = "Welcome to Serenity Wellness Center! 🌿\n\nHow can we help you today?"
        
        # Logic: 
        # - If user has < 5 bookings, allow new bookings
        # - If user has active bookings, allow reschedule
        # - Always show Talk to Us
        
        if booking_count < 5:
            buttons.append({"id": "book_btn", "title": "📅 Book Appointment"})
        else:
            # User at limit
            body_text = "Welcome back! 🌿\n\nYou've reached your booking limit (5 bookings). You can reschedule existing appointments."
        
        if has_active:
            buttons.append({"id": "reschedule_btn", "title": "🔄 Reschedule"})
        
        buttons.append({"id": "talk_btn", "title": "💬 Talk to Us"})
        
        # WhatsApp allows max 3 buttons, we should be safe
        self.wa_api.send_interactive_buttons(
            phone,
            body_text,
            buttons,
            footer_text="Your wellness journey starts here"
        )
        return {"status": "sent_welcome"}

    def send_contact_info(self, phone):
        """Send contact information when user selects 'Talk to Us'"""
        contact_message = (
            "📞 *Contact Us*\\n\\n"
            "We'd love to hear from you! Reach us at:\\n\\n"
            "📧 Email: support@serenitywellness.com\\n"
            "📱 Phone: +91 98765 43210\\n\\n"
            "Our team is available Mon-Sat, 9 AM - 6 PM"
        )
        self.wa_api.send_text(phone, contact_message)
        # Reset to START state so they can choose again
        user_sessions[phone] = {"state": STATE_START, "data": {}}
        return {"status": "sent_contact_info"}
    
    def start_booking_flow(self, phone):
        # Check if user has reached booking limit
        booking_count = self.sheets.get_user_booking_count(phone)
        if booking_count >= 5:
            self.wa_api.send_text(
                phone, 
                "You've reached the maximum of 5 bookings. You can reschedule your existing appointments. Type 'Hi' to see options."
            )
            user_sessions[phone] = {"state": STATE_START, "data": {}}
            return {"status": "booking_limit_reached"}
        
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
    
    def process_flow_booking(self, phone, flow_data):
        """Process booking from WhatsApp Flow response"""
        counselor_id = flow_data.get('counselor_id')
        date_str = flow_data.get('appointment_date')
        time_slot = flow_data.get('time_slot')
        
        if not all([counselor_id, date_str, time_slot]):
            self.wa_api.send_text(phone, "Error: Incomplete booking data. Please try again.")
            return
        
        # Create booking
        booking_id = f"BK{int(datetime.datetime.now().timestamp())}"
        booking_data = {
            'booking_id': booking_id,
            'user_phone': phone,
            'counselor_id': counselor_id,
            'date': date_str,
            'time_slot': time_slot,
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        self.sheets.create_booking_hold(booking_data)
        
        # Generate payment link
        payment_link = self.rz_api.create_payment_link(
            amount_in_paise=50000,  # ₹500
            description=f"Booking {booking_id}",
            customer_phone=phone,
            reference_id=booking_id
        )
        
        if payment_link:
            self.wa_api.send_text(
                phone,
                f"✅ Booking Created!\n\n"
                f"ID: {booking_id}\n"
                f"Date: {date_str}\n"
                f"Time: {time_slot}\n\n"
                f"Complete payment: {payment_link}\n\n"
                f"Your slot is held for 15 minutes."
            )
        
        return {"status": "flow_booking_processed"}

    # --- HELPERS ---
    def parse_counselor_selection(self, text):
        return text.split('.')[0].strip()

    def parse_date_selection(self, text):
        try:
            return text.split(' ')[0].strip()
        except:
            return None
    
    def check_user_status(self, phone):
        """Check user's booking status and return relevant info."""
        booking_count = self.sheets.get_user_booking_count(phone)
        active_bookings = self.sheets.get_user_active_bookings(phone)
        
        return {
            'is_existing': booking_count > 0,
            'booking_count': booking_count,
            'active_bookings': active_bookings
        }
    
    def start_reschedule_flow(self, phone):
        """Start the reschedule flow by showing user's active bookings."""
        active_bookings = self.sheets.get_user_active_bookings(phone)
        
        if not active_bookings:
            self.wa_api.send_text(phone, "You don't have any active bookings to reschedule.")
            user_sessions[phone] = {"state": STATE_START, "data": {}}
            return {"status": "no_active_bookings"}
        
        # Create interactive list of bookings
        rows = []
        for booking in active_bookings:
            booking_id = booking.get('booking_id', '')
            date = booking.get('date', '')
            time_slot = booking.get('time_slot', '')
            counselor_id = booking.get('counselor_id', '')
            
            rows.append({
                "id": booking_id,
                "title": f"{date} @ {time_slot}"[:24],
                "description": f"Counselor ID: {counselor_id}"[:72]
            })
        
        sections = [{"title": "Your Active Bookings", "rows": rows}]
        self.wa_api.send_interactive_list(
            phone,
            "Select the booking you want to reschedule:",
            "View Bookings",
            sections
        )
        
        user_sessions[phone]["state"] = STATE_RESCHEDULE_SELECT
        return {"status": "sent_reschedule_options"}
    
    def send_reschedule_date_selection(self, phone):
        """Send date options for rescheduling."""
        today = datetime.date.today()
        dates = [
            {"id": str(today), "title": "Today"},
            {"id": str(today + datetime.timedelta(days=1)), "title": "Tomorrow"},
            {"id": str(today + datetime.timedelta(days=2)), "title": "Day After"}
        ]
        
        self.wa_api.send_interactive_buttons(
            phone,
            "Select a new date for your appointment:",
            dates
        )
        return {"status": "sent_reschedule_date"}
    
    def send_reschedule_slot_selection(self, phone, date_str, counselor_id):
        """Send available time slots for rescheduling."""
        all_slots = ["09:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00"]
        booked = self.sheets.get_bookings_for_date(date_str, counselor_id)
        available = [s for s in all_slots if s not in booked]
        
        if not available:
            self.wa_api.send_text(phone, f"No slots available on {date_str}. Please choose another date.")
            user_sessions[phone]["state"] = STATE_RESCHEDULE_DATE
            return {"status": "no_slots"}
        
        # Interactive List for Slots
        rows = [{"id": slot, "title": slot, "description": ""} for slot in available]
        sections = [{"title": f"Available Slots - {date_str}", "rows": rows}]
        
        self.wa_api.send_interactive_list(
            phone,
            f"Select a new time slot for {date_str}:",
            "Select Time",
            sections
        )
        return {"status": "sent_reschedule_slots"}
    
    def complete_reschedule(self, phone, booking_id, new_date, new_slot):
        """Complete the reschedule - update booking without payment."""
        success = self.sheets.update_booking_datetime(booking_id, new_date, new_slot)
        
        if success:
            self.wa_api.send_text(
                phone,
                f"✅ Appointment Rescheduled!\n\n"
                f"Booking ID: {booking_id}\n"
                f"New Date: {new_date}\n"
                f"New Time: {new_slot}\n\n"
                f"See you then! Type 'Hi' if you need anything else."
            )
            # Reset state
            user_sessions[phone] = {"state": STATE_START, "data": {}}
            return {"status": "reschedule_complete"}
        else:
            self.wa_api.send_text(phone, "Error rescheduling. Please try again or contact support.")
            user_sessions[phone] = {"state": STATE_START, "data": {}}
            return {"status": "reschedule_error"}

