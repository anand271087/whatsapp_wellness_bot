from services.sheets import GoogleSheetsService
import datetime

def test_connection():
    print("Testing Google Sheets Connection...")
    service = GoogleSheetsService()
    
    if service.connect():
        print("✅ Connection Successful!")
        
        # Test Read
        counselors = service.get_active_counselors()
        print(f"✅ Read Counselors: Found {len(counselors)} active counselors.")
        
        # Test Write
        try:
            test_booking = {
                "booking_id": "TEST_VERIFY",
                "user_phone": "1234567890",
                "counselor_id": "99",
                "date": str(datetime.date.today()),
                "time_slot": "10:00",
                "razorpay_order_id": "TEST_ORDER",
                "timestamp": str(datetime.datetime.now())
            }
            service.create_booking_hold(test_booking)
            print("✅ Write Booking: Successfully added test booking row.")
            return True
        except Exception as e:
            print(f"❌ Write Failed: {e}")
            return False
    else:
        print("❌ Connection Failed.")
        return False

if __name__ == "__main__":
    test_connection()
