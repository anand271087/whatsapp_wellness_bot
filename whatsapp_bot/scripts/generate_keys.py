from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import os

def generate_keys():
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # Save private key to PEM file
    with open("../private.pem", "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Generate public key
    public_key = private_key.public_key()
    
    # Save public key to PEM file
    with open("../public.pem", "wb") as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

    print("✅ Keys generated successfully!")
    print(f"Private Key: {os.path.abspath('../private.pem')}")
    print(f"Public Key: {os.path.abspath('../public.pem')}")
    print("\n👉 Upload 'public.pem' to WhatsApp Flow Settings.")
    print("👉 Keep 'private.pem' secure on your server.")

if __name__ == "__main__":
    generate_keys()
