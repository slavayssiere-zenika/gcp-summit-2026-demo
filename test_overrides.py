from main import app
from src.prompts.router import verify_jwt
import src.prompts.auth as auth

print(id(verify_jwt))
print(id(auth.verify_jwt))
