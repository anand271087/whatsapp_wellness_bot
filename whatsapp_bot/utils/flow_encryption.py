import os
import json
import base64
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def decrypt_request(body, private_key_pem):
    try:
        encrypted_flow_data_b64 = body['encrypted_flow_data']
        encrypted_aes_key_b64 = body['encrypted_aes_key']
        initial_vector_b64 = body['initial_vector']
    except KeyError:
        raise ValueError("Missing required encryption fields")

    flow_data = base64.b64decode(encrypted_flow_data_b64)
    iv = base64.b64decode(initial_vector_b64)
    encrypted_aes_key = base64.b64decode(encrypted_aes_key_b64)

    # 1. Decrypt AES Key
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode('utf-8'), 
        password=None,
        backend=default_backend()
    )
    
    aes_key = private_key.decrypt(
        encrypted_aes_key, 
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()), 
            algorithm=hashes.SHA256(), 
            label=None
        )
    )

    # 2. Decrypt Flow Data
    encrypted_flow_data_body = flow_data[:-16]
    encrypted_flow_data_tag = flow_data[-16:]
    
    decryptor = Cipher(
        algorithms.AES(aes_key),
        modes.GCM(iv, encrypted_flow_data_tag),
        backend=default_backend()
    ).decryptor()
    
    decrypted_data_bytes = decryptor.update(encrypted_flow_data_body) + decryptor.finalize()
    decrypted_data = json.loads(decrypted_data_bytes.decode("utf-8"))
    
    return decrypted_data, aes_key, iv

def encrypt_response(response, aes_key, iv):
    # Flip the initialization vector (CRITICAL STEP from Docs)
    flipped_iv = bytearray()
    for byte in iv:
        flipped_iv.append(byte ^ 0xFF)

    # Encrypt the response data
    encryptor = Cipher(
        algorithms.AES(aes_key),
        modes.GCM(flipped_iv),
        backend=default_backend()
    ).encryptor()
    
    # Return Base64(Ciphertext + Tag) - NO IV PREPENDED
    return base64.b64encode(
        encryptor.update(json.dumps(response).encode("utf-8")) +
        encryptor.finalize() +
        encryptor.tag
    ).decode("utf-8")
