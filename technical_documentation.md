# Serenity Wellness Bot - Technical Documentation

## 1. System Architecture
The bot acts as a middleware between **WhatsApp Users** and your **Backend Services** (Google Sheets, Razorpay).

```mermaid
graph TD
    User((WhatsApp User)) <-->|Messages/Flows| Meta[Meta Cloud API]
    Meta <-->|Webhooks| Server[Flask Server (Render)]
    Server <-->|Read/Write| DB[(Google Sheets)]
    Server -->|Generate Link| Payment[Razorpay]
```

## 2. Key Files & Responsibilities

| File | Purpose | Key Functions |
| :--- | :--- | :--- |
| **`app.py`** | **The Entry Point**. Receives all webhooks from WhatsApp. | - `webhook()`: Handles incoming messages.<br>- `flows()`: Handles encrypted Flow requests (INIT, data_exchange).<br>- `payment_webhook()`: Updates booking status when user pays. |
| **`utils/flow_handler.py`** | **The Brain/Logic**. Manages user state and decides what to reply. | - `start_booking_flow()`: Launches the WhatsApp Flow.<br>- `process_flow_booking()`: Handles the result from the Flow.<br>- `send_date_selection()`: Sends buttons for dates. |
| **`services/whatsapp_api.py`** | **The Messenger**. Handles low-level API calls to Meta. | - `send_message()`: Base sender.<br>- `send_flow_message()`: Sends the specific "Book Appointment" button. |
| **`utils/flow_encryption.py`** | **The Security Guard**. Decrypts Flow requests and encrypts responses. | - `decrypt_request()`: Unlocks incoming data.<br>- `encrypt_response()`: Locks outgoing data (IV Flipping). |

## 3. The Booking Flow (Step-by-Step)

### Phase 1: Initiation
1.  **User**: Sends "Hi" or clicks "Book Appointment".
2.  **Bot (`flow_handler.py`)**: Calls `start_booking_flow`.
3.  **Bot (`whatsapp_api.py`)**: Sends a special `send_flow_message` to the user.
    *   *Payload includes*: `flow_token` (unique ID), `screen: "COUNSELLOR_SELECT"`.

### Phase 2: Inside the Flow (The Blank Screen Handling)
When the user clicks the "Book" button, WhatsApp opens the native form. It talks to your server's `/flow` endpoint.

1.  **WhatsApp**: Sends explicit **INIT** request (Encrypted).
2.  **Server (`app.py`)**:
    *   Decrypts the request.
    *   Fetches Counselors from Google Sheets.
    *   Formats logic: `INIT` -> returns `department` list.
    *   **Crucial Step**: Returns encrypted JSON with `{ "screen": "COUNSELLOR_SELECT", "data": { "department": [...] } }`.
    *   *If this data is bad (e.g., list is empty or image URL invalid), the screen is blank.*

### Phase 3: Completion
1.  **User**: Selects Counselor -> Clicks "Confirm".
2.  **WhatsApp**: Sends **data_exchange** request with `{ "counsellor": "ID_SELECTED" }`.
3.  **Server**: Validates and returns `{ "screen": "SUCCESS", "data": ... }`.
4.  **Phone**: Flow closes.
5.  **Bot**: Receives `nfm_reply` webhook (in `app.py`).
6.  **Bot**: Extracts `counsellor_id` and asks for **Date** (via Chat Buttons).

## 4. Debugging "Blank Screen"

If the Flow opens but is blank, it means the **INIT Response** failed to render.
*   **Checkpoint**: Check Render Logs. Did `INIT` run?
*   **Data Check**: Is `department` list empty?
*   **Schema Check**: Does `flow_schema.json` match the data keys (`id`, `title`, `image`)?

---

## 5. Flow Encryption Details
Meta requires robust security. We use `AES-GCM` encryption.
*   **Request**: We receive `encrypted_flow_data`, `encrypted_aes_key`, `initial_vector`.
*   **Response**: We MUST use the **same AES Key** but **Flip the IV bits**.
*   **Format**: The response body must be a single Base64 string containing `IV + Ciphertext + Tag`.

---
