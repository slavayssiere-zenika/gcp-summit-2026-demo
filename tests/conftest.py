"""
conftest.py — Configuration globale pour la suite de tests du workspace.

Définit le rootdir et les fixtures partagées entre tous les modules de tests.
Permet de lancer pytest depuis n'importe quel sous-répertoire sans erreur de
résolution de chemin relatif.
"""
import sys
import os

# S'assure que le rootdir du workspace est dans sys.path
# pour que les imports relatifs dans les tests fonctionnent
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
