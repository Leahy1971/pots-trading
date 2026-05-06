"""
generate_certs.py
=================
Generates the SSL certificate files required for Betfair API login.
Run once with:  python generate_certs.py
"""

import os
import sys

# Install cryptography if needed
try:
    from cryptography import x509
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "cryptography"], check=True)
    from cryptography import x509

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime

CERT_DIR = "C:/certs"
KEY_FILE  = f"{CERT_DIR}/client-2048.key"
CERT_FILE = f"{CERT_DIR}/client-2048.crt"

os.makedirs(CERT_DIR, exist_ok=True)

print("Generating 2048-bit RSA key...")
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

print("Building self-signed certificate...")
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "betfair"),
])
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow())
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
    .sign(key, hashes.SHA256())
)

with open(KEY_FILE, "wb") as f:
    f.write(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))

with open(CERT_FILE, "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print(f"\nDone!")
print(f"  Key:  {KEY_FILE}")
print(f"  Cert: {CERT_FILE}")
print("\nYou can now run:  python main.py")
