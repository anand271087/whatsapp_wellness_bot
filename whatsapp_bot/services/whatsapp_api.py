import requests
import json
import os
import logging

logger = logging.getLogger(__name__)

class WhatsAppAPI:
    def __init__(self):
        self.token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.api_version = "v17.0"
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
    
    def send_message(self, to_phone, message_data):
        if not self.token or not self.phone_number_id:
            logger.error("WhatsApp Credentials missing in .env")
            return None

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": message_data.get("type", "text"),
        }
        
        # Merge specific message type data (text, interactive, etc.)
        payload.update(message_data)
        
        try:
            response = requests.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            if e.response:
                logger.error(e.response.text)
            return None

    def send_text(self, to_phone, text):
        return self.send_message(to_phone, {
            "type": "text",
            "text": {"body": text}
        })

    def send_interactive_list(self, to_phone, body_text, button_text, sections):
        """
        sections structure:
        [
            {
                "title": "Section Title",
                "rows": [
                    {"id": "unique_id_1", "title": "Row Title 1", "description": "Row Desc 1"},
                    ...
                ]
            }
        ]
        """
        payload = {
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": body_text
                },
                "action": {
                    "button": button_text,
                    "sections": sections
                }
            }
        }
        return self.send_message(to_phone, payload)

    def send_interactive_buttons(self, to_phone, body_text, buttons):
        """
        buttons structure: [{"id": "btn_1", "title": "Button Title"}] (Max 3)
        """
        formatted_buttons = []
        for btn in buttons:
            formatted_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"]
                }
            })

        payload = {
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": formatted_buttons
                }
            }
        }
        return self.send_message(to_phone, payload)
