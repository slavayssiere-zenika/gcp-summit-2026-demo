from jose import jwt
SECRET_KEY = b"testsecret"
ALGORITHM = "HS256"

payload = {"sub": "user_1", "role": "admin"}
token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
print("Token:", token)

try:
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    print("Decoded:", decoded)
except Exception as e:
    import traceback
    traceback.print_exc()
    print("Exception", e)
