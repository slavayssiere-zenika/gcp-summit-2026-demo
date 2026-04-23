import logging
import os
import sys

# Assure que le dossier des logs existe
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "fake_profiles")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "workflow.log")

def setup_logger(name="summit_workflow"):
    """
    Configure un logger qui écrit à la fois dans la console (stdout) et dans un fichier partagé.
    """
    logger = logging.getLogger(name)
    
    # Éviter de rajouter les handlers plusieurs fois si appelé répétitivement
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.INFO)

    # Format de log
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler pour le fichier
    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # Handler pour la console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Pour éviter la propagation au root logger et les doublons éventuels
    logger.propagate = False

    return logger

# Logger par défaut prêt à l'emploi
logger = setup_logger()
