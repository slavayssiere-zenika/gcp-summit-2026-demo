import shared.auth.jwt as shared_jwt
import os
print("TEST_HISTORY SECRET_KEY:", os.environ.get("SECRET_KEY", "testsecret_must_be_32_characters_long_for_sha256"))
print("SHARED_JWT SECRET_KEY:", getattr(shared_jwt, 'SECRET_KEY', 'NOT_FOUND'))
