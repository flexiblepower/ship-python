import hashlib

import cryptography.x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509 import Certificate

with open('/home/fleursl/Downloads/test_client_cert_ship/certificate.pem', mode='rb') as \
        open_file:
    pubkey: Certificate = cryptography.x509.load_pem_x509_certificate(open_file.read())

print(hashlib.sha1(pubkey.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.PKCS1,
        )).hexdigest())

