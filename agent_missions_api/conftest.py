import os
import pytest

# Injecter les variables d'environnement de test AVANT tout import des modules applicatifs
os.environ.setdefault("SECRET_KEY", "test-secret-key-missions")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/12")
os.environ.setdefault("MISSIONS_MCP_URL", "http://localhost:9010")
os.environ.setdefault("CV_MCP_URL", "http://localhost:9004")
os.environ.setdefault("USERS_MCP_URL", "http://localhost:9001")
os.environ.setdefault("COMPETENCIES_MCP_URL", "http://localhost:9003")
os.environ.setdefault("PROMPTS_API_URL", "http://localhost:9099")
os.environ.setdefault("ANALYTICS_MCP_URL", "http://localhost:9008")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.0-flash")
os.environ.setdefault("APP_VERSION", "test")
