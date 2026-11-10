from base64 import urlsafe_b64encode
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


key = ec.generate_private_key(ec.SECP256R1())
private_pem = key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
public_point = key.public_key().public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)
Path("vapid_private.pem").write_bytes(private_pem)
public_key = urlsafe_b64encode(public_point).rstrip(b"=").decode("ascii")
print("VAPID_PUBLIC_KEY=" + public_key)
print("VAPID_PRIVATE_KEY=vapid_private.pem")
