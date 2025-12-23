from flask import Flask, request, jsonify
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
                        else:
                            msg_body = ""
                    else:
                        msg_body = ""
                    
                    # Pass to Flow Handler
                    response = flow_handler.handle_message(from_number, msg_body)
                    
                    # For MVP: Log the response we WOULD send
                    # In real app: call send_message(from_number, response)
                    logger.info(f"TO USER {from_number}: {response}")
                    
            except Exception as e:
                logger.error(f"Error processing webhook: {e}")

        return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)
