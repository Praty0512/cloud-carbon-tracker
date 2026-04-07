import os
from cryptography.fernet import Fernet

key=os.getenv("ENCRYPTION_KEY")

if not key:
 raise ValueError("ENCRYPTION_KEY not set")

cipher=Fernet(key.encode())

def enc(d):
 if d is None:
  return None
 return cipher.encrypt(d.encode()).decode()

def dec(d):
 if d is None:
  return None
 return cipher.decrypt(d.encode()).decode()