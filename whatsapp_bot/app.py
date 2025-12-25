from flask import Flask, request, jsonify
import json
from services.sheets import GoogleSheetsService
from utils.flow_handler import FlowHandler
import os
import logging
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Services
# Please ensure credentials.json is in the root or specified path
sheets_service = GoogleSheetsService()
flow_handler = FlowHandler(sheets_service)

# WhatsApp Configuration
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secure_token_123") 

@app.route("/", methods=["GET"])
def home():
    return "WhatsApp Wellness Bot is Running!"

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        # Verification verification
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode and token:
            if mode == "subscribe" and token == VERIFY_TOKEN:
                logger.info("Webhook Verified!")
                return challenge, 200
            else:
                return "Forbidden", 403
        return "Hello World", 200

    if request.method == "POST":
        # Handle Incoming Message
        data = request.json
        if data:
            logger.info(f"Received JSON: {data}")
            # Process standard WhatsApp Message Structure
            # Note: This parsing depends on the specific API provider structure (Meta Cloud API).
            try:
                entry = data.get('entry', [])[0]
                changes = entry.get('changes', [])[0]
                value = changes.get('value', {})
                messages = value.get('messages', [])
                
                if messages:
                    msg = messages[0]
                    from_number = msg.get('from') # User Phone
                    msg_type = msg.get('type')
                    if msg_type == 'text':
                        msg_body = msg.get('text', {}).get('body', '')
                    elif msg_type == 'interactive':
                        interactive = msg.get('interactive', {})
                        if interactive.get('type') == 'button_reply':
                            msg_body = interactive.get('button_reply', {}).get('id')
                        elif interactive.get('type') == 'list_reply':
                            msg_body = interactive.get('list_reply', {}).get('id')
                        elif interactive.get('type') == 'nfm_reply':
                            # WhatsApp Flow response - process directly
                            nfm_reply = interactive.get('nfm_reply', {})
                            flow_response = json.loads(nfm_reply.get('body', '{}'))
                            logger.info(f"Flow Response: {flow_response}")
                            flow_handler.process_flow_booking(from_number, flow_response)
                            # Don't process as regular message
                            msg_body = None
                        else:
                            msg_body = ""
                    else:
                        msg_body = ""
                    
                    # Pass to Flow Handler (skip if Flow already processed)
                    if msg_body is not None:
                        response = flow_handler.handle_message(from_number, msg_body)
                    
                    # For MVP: Log the response we WOULD send
                    # In real app: call send_message(from_number, response)
                    logger.info(f"TO USER {from_number}: {response}")
                    
            except Exception as e:
                logger.error(f"Error processing webhook: {e}")

        return jsonify({"status": "success"}), 200

@app.route("/payment-webhook", methods=["POST"])
def payment_webhook():
    # 1. Get Signature and Secret
    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    signature = request.headers.get('X-Razorpay-Signature')
    
    # 2. Verify Signature (Only if secret is configured)
    if webhook_secret and signature:
        try:
            flow_handler.rz_api.client.utility.verify_webhook_signature(
                request.data.decode('utf-8'),
                signature,
                webhook_secret
            )
        except Exception as e:
            logger.error(f"Webhook Signature Verification Failed: {e}")
            return jsonify({"error": "Invalid Signature"}), 400
    else:
        logger.warning("Skipping Webhook Signature Verification (Secret or Signature missing)")
    
    # 3. Process Event
    event = request.json
    if event.get('event') == 'payment_link.paid':
        try:
            payload = event.get('payload', {})
            payment_link = payload.get('payment_link', {})
            entity = payment_link.get('entity', {})
            
            # We stored booking_id in 'notes' -> 'booking_id' OR in 'reference_id'
            # Let's check 'notes'
            notes = entity.get('notes', {})
            booking_id = notes.get('booking_id')
            
            # Also get order_id if available
            order_id = entity.get('order_id') or entity.get('id') # fallback to plink id
            
            if booking_id:
                logger.info(f"Payment Received for Booking: {booking_id}")
                # Update Sheet
                # Note: our sheets function expects 'order_id' to find the row. 
                # But we might have stored a temporary ID or nothing.
                # Let's assume create_booking_hold used booking_id as reference or we search by booking_id
                
                # REFACTOR SHEET UPDATE: We need to update BY booking_id, not order_id, 
                # because we didn't have a real order_id when we created the row.
                # Since we don't have a 'update_by_booking_id' method, let's add logic to sheets.py or modify app.py
                # For now, let's assume update_booking_payment searches by booking_id if we pass it? 
                # Wait, sheets.py strictly searches 'order_id' column 6? No, wait.
                # update_booking_payment(order_id, status) -> searches for 'order_id'.
                # In create_booking_hold, we put 'razorpay_order_id' which was empty?
                # Ah, we need to fix sheets.py to allow finding by booking_id (Col 1).
                
                # Let's implement a direct update here assuming we fix sheets.py next step
                sheets_service.update_booking_status(booking_id, 'PAID', order_id)
                
                # Optional: Send WhatsApp Confirmation
                phone = entity.get('customer', {}).get('contact')
                if phone:
                    flow_handler.wa_api.send_text(phone, f"✅ Payment Received! Your Booking {booking_id} is Confirmed.")
                    
        except Exception as e:
            logger.error(f"Error processing payment event: {e}")

    return jsonify({"status": "ok"}), 200

from utils.flow_encryption import decrypt_request, encrypt_response
import base64

@app.route("/flow", methods=["POST"])
def flows():
    # 1. Get Private Key
    # In production, store this securely (Secret Manager or Env Var)
    # For now, we'll look for 'private.pem' in root or env var
    private_key = os.getenv("FLOW_PRIVATE_KEY")
    if private_key:
        # Fix formatting: Replace literal \n with actual newlines if pasted as single string
        private_key = private_key.replace('\\n', '\n')
    
    if not private_key:
        # Try reading from file
        try:
            with open("private.pem", "r") as f:
                private_key = f.read()
        except FileNotFoundError:
            logger.error("Private Key not found!")
            return jsonify({"error": "Configuration error"}), 500

    # 2. Decrypt Request
    try:
        body = request.json
        decrypted_payload, aes_key, iv = decrypt_request(body, private_key)
        logger.info(f"Decrypted Flow Request: {json.dumps(decrypted_payload, indent=2)}")
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return jsonify({"error": "Decryption failed"}), 401

    action = decrypted_payload.get("action")
    
    response_payload = {}
    
    # 3. Handle Actions
    if action == "ping":
        response_payload = {
            "data": {
                "status": "active"
            }
        }

    elif action == "INIT":
        # Fetch counselors for 'COUNSELLOR_SELECT' screen
        counselors = sheets_service.get_active_counselors()
        
        # Format for Flow Schema (id, title, image)
        department_data = []
        for c in counselors:
            department_data.append({
                "id": str(c['id']),
                "title": c['name'],
                "image": c['image_url'] if c.get('image_url') else "https://via.placeholder.com/150"
            })
            
        response_payload = {
            "screen": "COUNSELLOR_SELECT", 
            "data": {
                "department": department_data
            }
        }
        
    elif action == "data_exchange":
        # Handle actions from the Flow
        request_data = decrypted_payload.get("data", {})
        
        # New Schema Transition: COUNSELLOR_SELECT -> CONFIRM
        # Client sends: { "counsellor": "${form.department}" }
        # Note: 'department' is the ID selected in dropdown
        
        response_payload = {
            "screen": "SUCCESS", # Close Flow
            "data": {
                "extension_message_response": {
                    "params": {
                        "flow_token": decrypted_payload.get("flow_token"),
                        "counsellor_id": request_data.get("counsellor")
                    }
                }
            }
        }
        
    else:
        logger.warning(f"Unknown Flow Action: {action}")
        return jsonify({"error": "Unknown action"}), 400

    # 4. Encrypt Response
    try:
        # Returns single base64 string (IV + Ciphertext + Tag)
        encrypted_b64 = encrypt_response(response_payload, aes_key, iv)
        
        # Return as raw text/plain
        from flask import Response
        return Response(encrypted_b64, status=200, mimetype='text/plain')
        
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return jsonify({"error": "Encryption failed"}), 500

if __name__ == "__main__":
    app.run(port=5000, debug=True)
