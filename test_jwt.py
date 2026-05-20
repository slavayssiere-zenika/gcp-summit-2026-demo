import sys
import os
os.environ["SECRET_KEY"] = "testsecret"

# Assure que la racine du monorepo est dans sys.path pour résoudre `shared/`
_MONOREPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _MONOREPO_ROOT not in sys.path:
    sys.path.insert(0, _MONOREPO_ROOT)
