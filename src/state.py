import json
from pathlib import Path
from typing import Dict, Any
from src.config import BASE_DIR

WORKSPACE_DIR = BASE_DIR / "workspace"

def init_project(slug: str, topic: str) -> Path:
    """Crea la cartella del progetto e inizializza project.json."""
    project_dir = WORKSPACE_DIR / slug
    (project_dir / "images").mkdir(parents=True, exist_ok=True)
    (project_dir / "output").mkdir(parents=True, exist_ok=True)
    
    json_path = project_dir / "project.json"
    if not json_path.exists():
        initial_data = {
            "slug": slug,
            "topic": topic,
            "language": "en",
            "status": "initialized",
            "segments": []
        }
        save_project(slug, initial_data)
        print(f"[✓] Progetto inizializzato in: {project_dir}")
    else:
        print(f"[i] Progetto '{slug}' già esistente.")
        
    return project_dir

def load_project(slug: str) -> Dict[str, Any]:
    """Carica il file project.json."""
    json_path = WORKSPACE_DIR / slug / "project.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Progetto '{slug}' non trovato. Esegui prima col comando --step init")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_project(slug: str, data: Dict[str, Any]) -> None:
    """Salva i dati aggiornati in project.json."""
    json_path = WORKSPACE_DIR / slug / "project.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)