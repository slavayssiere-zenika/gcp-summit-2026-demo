import os
import sys

# Charger conftest logic
os.environ["SECRET_KEY"] = "test-secret-key-missions"

from main import app
from shared.auth.jwt import SECRET_KEY as shared_secret

SECRET_KEY = os.environ.get("SECRET_KEY", "fallback")

print("shared.auth.jwt.SECRET_KEY:", shared_secret)
print("test_history SECRET_KEY:", SECRET_KEY)
