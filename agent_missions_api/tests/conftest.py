import os
import sys

_MONOREPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MONOREPO_ROOT not in sys.path:
    sys.path.insert(0, _MONOREPO_ROOT)

# Fix test execution by strictly defining the SECRET_KEY before ANY import of main.py
# and preventing os.environ.pop from clearing it if we need to reuse it across tests.
# Wait, main.py pops it, so we need to either redefine it or ensure tests use the same value.
os.environ["SECRET_KEY"] = "testsecret_must_be_32_characters_long_for_sha256"
