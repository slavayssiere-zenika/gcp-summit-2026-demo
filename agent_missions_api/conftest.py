import os
import pytest

# Injecter les variables d'environnement de test AVANT tout import des modules applicatifs
os.environ["SECRET_KEY"] = "test-secret-key-missions"
os.environ["REDIS_URL"] = "redis://localhost:6379/12"
os.environ["MISSIONS_MCP_URL"] = "http://localhost:9010"
os.environ["CV_MCP_URL"] = "http://localhost:9004"
os.environ["USERS_MCP_URL"] = "http://localhost:9001"
os.environ["COMPETENCIES_MCP_URL"] = "http://localhost:9003"
os.environ["PROMPTS_API_URL"] = "http://localhost:9099"
os.environ["ANALYTICS_MCP_URL"] = "http://localhost:9008"
os.environ["GEMINI_MISSIONS_MODEL"] = "gemini-3.1-flash-lite-preview"
os.environ["GEMINI_MODEL"] = "gemini-3.1-flash-lite-preview"
os.environ.setdefault("APP_VERSION", "test")
