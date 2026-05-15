"""auth.py — analytics_mcp

Délègue la validation JWT à shared.auth.jwt.
Ce fichier est conservé pour la compatibilité des imports locaux (from auth import verify_jwt).
"""
from shared.auth.jwt import security, verify_jwt  # noqa: F401
