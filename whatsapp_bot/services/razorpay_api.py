import razorpay
import os
import logging
import time

logger = logging.getLogger(__name__)

class RazorpayAPI:
    def __init__(self):
        self.key_id = os.getenv("RAZORPAY_KEY_ID")
        self.key_secret = os.getenv("RAZORPAY_KEY_SECRET")
        self.client = None
        
        if self.key_id and self.key_secret:
            self.client = razorpay.Client(auth=(self.key_id, self.key_secret))

    def create_payment_link(self, amount_in_paise, description, customer_phone, reference_id):
        if not self.client:
            logger.error("Razorpay Client not initialized. Check credentials.")
            return f"https://mock-payment-link.com/{reference_id}" # Fallback for demo

        try:
            # Expire in 15 mins
            expire_by = int(time.time()) + (15 * 60)
            
            payload = {
                "amount": amount_in_paise,
                "currency": "INR",
                "accept_partial": False,
                "description": description,
                "customer": {
                    "contact": customer_phone,
                },
                "notify": {
                    "sms": True,
                    "email": False
                },
                "reminder_enable": True,
                "notes": {
                    "booking_id": reference_id
                },
                "callback_url": "https://google.com", # Should be our webhook/callback
                "callback_method": "get"
            }
            
            payment_link = self.client.payment_link.create(payload)
            return payment_link.get('short_url')
            
        except Exception as e:
            logger.error(f"Razorpay Error: {e}")
            return None
