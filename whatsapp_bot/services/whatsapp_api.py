import requests
import json
import os
import logging

logger = logging.getLogger(__name__)

class WhatsAppAPI:
    def __init__(self):
        self.token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.api_version = "v21.0"
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
                logger.error(f"Response Body: {e.response.text}")
                logger.error(f"Request Payload: {json.dumps(payload, indent=2)}")
            return None

    def send_text(self, to_phone, text):
        return self.send_message(to_phone, {
            "type": "text",
            "text": {"body": text}
        })

    def send_image(self, to_phone, image_url, caption=None):
        message_data = {
            "type": "image",
            "image": {"link": image_url}
        }
        if caption:
            message_data["image"]["caption"] = caption
        return self.send_message(to_phone, message_data)

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

    def send_interactive_buttons(self, to_phone, body_text, buttons, header_image_url=None, footer_text=None):
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

        interactive_obj = {
            "type": "button",
            "body": {
                "text": body_text
            },
            "action": {
                "buttons": formatted_buttons
            }
        }

        if header_image_url:
            interactive_obj["header"] = {
                "type": "image",
                "image": {"link": header_image_url}
            }
        
        if footer_text:
            interactive_obj["footer"] = {
                "text": footer_text
            }

        payload = {
            "type": "interactive",
            "interactive": interactive_obj
        }
        return self.send_message(to_phone, payload)
    
    def send_interactive_carousel(self, to_phone, body_text, cards):
        """
        cards structure:
        [
            {
                "image_url": "https://...",
                "body_text": "Counselor Name",
                "buttons": [{"id": "btn_id", "title": "Button Title"}]
            }
        ]
        """
        carousel_cards = []
        for i, card in enumerate(cards):
            c_buttons = []
            for btn in card.get('buttons', []):
                c_buttons.append({
                    "type": "reply",
                    "reply": {
                        "id": btn['id'],
                        "title": btn['title']
                    }
                })

            carousel_cards.append({
                "card_index": i,
                "header": {
                    "type": "image",
                    "image": {"link": card['image_url']}
                },
                "body": {
                    "text": card['body_text']
                },
                "action": {
                    "buttons": c_buttons
                }
            })

        payload = {
            "type": "interactive",
            "interactive": {
                "type": "carousel",
                "body": {
                    "text": body_text
                },
                "action": {
                    "cards": carousel_cards
                }
            }
        }
        return self.send_message(to_phone, payload)
    
    def send_flow_message(self, to_phone, flow_id, flow_cta, header_text, body_text, footer_text=None, flow_data=None):
        """
        Send a WhatsApp Flow message with optional data context
        """
        flow_action_payload = {
            "screen": "COUNSELLOR_SELECT" 
        }
        if flow_data:
            flow_action_payload["data"] = flow_data

        interactive_obj = {
            "type": "flow",
            "header": {
                "type": "text",
                "text": header_text
            },
            "body": {
                "text": body_text
            },
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_message_version": "3",
                    "flow_token": str(uuid.uuid4()),
                    "flow_id": flow_id,
                    "flow_cta": flow_cta,
                    "flow_action": "navigate",
                    "flow_action_payload": flow_action_payload
                }
            }
        }
        
        if footer_text:
            interactive_obj["footer"] = {
                "text": footer_text
            }
        
        payload = {
            "type": "interactive",
            "interactive": interactive_obj
        }
        return self.send_message(to_phone, payload)

