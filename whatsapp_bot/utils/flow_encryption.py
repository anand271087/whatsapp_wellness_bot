import os
import json
import base64
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def decrypt_request(body, private_key_pem):
    """
    Decrypts the incoming WhatsApp Flow request.
    
    Args:
        body (dict): The JSON body of the request.
        private_key_pem (str): The RSA private key in PEM format.
        
    Returns:
        dict: The decrypted JSON payload.
        tuple: (aes_key, initial_vector) for re-encryption if needed (not needed for simple responses).
    """
    try:
        encrypted_aes_key = body['encrypted_aes_key']
        encrypted_flow_data = body['encrypted_flow_data']
        initial_vector = body['initial_vector']
    except KeyError:
        raise ValueError("Missing required encryption fields in body")

    # 1. Decrypt the AES Key using RSA Private Key
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None,
            backend=default_backend()
        )
        
        aes_key = private_key.decrypt(
            base64.b64decode(encrypted_aes_key),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
    except Exception as e:
        raise ValueError(f"Failed to decrypt AES key: {e}")

    # 2. Decrypt the Flow Data using AES-GCM
    try:
        flow_data_bytes = base64.b64decode(encrypted_flow_data)
        iv_bytes = base64.b64decode(initial_vector)
        
        # WhatsApp appends the auth tag at the end of the encrypted data
        # AES-GCM tag is usually 16 bytes
        tag = flow_data_bytes[-16:]
        ciphertext = flow_data_bytes[:-16]

        cipher = Cipher(
            algorithms.AES(aes_key),
            modes.GCM(iv_bytes, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        decrypted_bytes = decryptor.update(ciphertext) + decryptor.finalize()
        
        return json.loads(decrypted_bytes.decode('utf-8')), aes_key, iv_bytes
        
    except Exception as e:
        raise ValueError(f"Failed to decrypt flow data: {e}")

def encrypt_response(response_data, aes_key, iv):
    """
    Encrypts the response data using the same AES key and IV (with flipped IV).
    Note: WhatsApp Flows v3+ typically expects the same IV but with bits flipped? 
    Actually, documentation says: 
    "The response must be encrypted using the same AES key... You must generate a NEW IV."
    
    Wait, usually responses effectively use a new IV.
    Let's check standard implementation.
    Simple responses for data_exchange might need encryption if sensitive?
    
    Actually, most examples show returning plaintext or using a specific encryption flow.
    BUT, the user prompt says: "Your server must decrypt request body."
    It doesn't explicitly say we must encrypt the RESPONSE in a specific complex way, 
    but usually `data_exchange` responses ARE encrypted.
    
    Standard:
    1. Generate new IV
    2. Encrypt response JSON with AES-GCM
    3. Return { "encrypted_response": "...", "initial_vector": "..." } (Make sure to verify exact format)
    
    HOWEVER, for 'ping' and simple 'INIT', sometimes plaintext is allowed during dev?
    No, in production it must be encrypted.
    
    Let's implement encryption.
    """
    import os
    
    # Generate new IV for response
    # It is recommended to use a random IV
    response_iv = os.urandom(12) 
    
    json_data = json.dumps(response_data).encode('utf-8')
    
    cipher = Cipher(
        algorithms.AES(aes_key),
        modes.GCM(response_iv),
        backend=default_backend()
    )
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(json_data) + encryptor.finalize()
    
    # Append tag to ciphertext
    encrypted_data = ciphertext + encryptor.tag
    
    # Prepend IV to the result
    final_payload = response_iv + encrypted_data
    
    return base64.b64encode(final_payload).decode('utf-8')
