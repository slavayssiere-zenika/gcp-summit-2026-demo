from jose import jwt
import time

secret = "secret"
payload = {"sub": "test", "exp": int(time.time()) - 100}
token = jwt.encode(payload, secret, algorithm="HS256")

try:
    print("Without leeway:")
    jwt.decode(token, secret, algorithms=["HS256"])
except Exception as e:
    print(e)

try:
    print("With leeway:")
    print(jwt.decode(token, secret, algorithms=["HS256"], options={"leeway": 300}))
except Exception as e:
    print(e)
