import pytest

def test_debug():
    import os
    print("os.environ SECRET_KEY:", os.environ.get("SECRET_KEY"))
    from agent_commons import jwt_middleware
    print("jwt_middleware SECRET_KEY:", jwt_middleware.SECRET_KEY)
    import test_main
    print("test_main SECRET_KEY:", test_main.SECRET_KEY)

