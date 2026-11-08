import os
from pathlib import Path
from dotenv import load_dotenv

# Carica le variabili dal file .env (se esiste)
load_dotenv()

# Percorso radice del progetto (calcolato in automatico)
BASE_DIR = Path(__file__).resolve().parent.parent

# Chiavi API (per ora possono anche essere vuote)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

def check_config():
    """Controlla e stampa lo stato della configurazione."""
    print(f"[i] Cartella progetto: {BASE_DIR}")
    print(f"[i] GOOGLE_API_KEY presente: {'Sì' if GOOGLE_API_KEY else 'No (da configurare)'}")
    print(f"[i] PEXELS_API_KEY presente: {'Sì' if PEXELS_API_KEY else 'No (da configurare)'}")