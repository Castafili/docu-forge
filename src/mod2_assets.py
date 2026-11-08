import requests
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import split_on_silence

from src.state import load_project, save_project, WORKSPACE_DIR

def remove_silences(input_audio: Path, output_audio: Path) -> float:
    """Taglia i silenzi più lunghi di 0.5s dall'audio registrato e restituisce la durata esatta in secondi."""
    print(f"[*] Pulizia silenzi da: {input_audio.name}...")
    sound = AudioSegment.from_file(str(input_audio))
    
    chunks = split_on_silence(
        sound,
        min_silence_len=500,        # Silenzi > 500ms vengono tagliati
        silence_thresh=sound.dBFS - 16,
        keep_silence=200            # Lascia 200ms di respiro naturale tra le frasi
    )
    
    combined = AudioSegment.empty()
    for chunk in chunks:
        combined += chunk
        
    combined.export(str(output_audio), format="wav")
    duration_sec = round(len(combined) / 1000.0, 2)
    print(f"[✓] Audio pulito salvato ({duration_sec}s): {output_audio.name}")
    return duration_sec

def align_segments_to_duration(total_duration: float, segments: list) -> list:
    """Sincronizza i segmenti proporzionalmente alla durata reale del tuo audio pulito."""
    print(f"[*] Sincronizzazione dei {len(segments)} segmenti su {total_duration}s di audio reale...")
    
    total_chars = sum(len(s["text"]) for s in segments)
    current_time = 0.0
    
    for seg in segments:
        ratio = len(seg["text"]) / total_chars
        seg_duration = round(total_duration * ratio, 2)
        seg["start_time"] = round(current_time, 2)
        seg["end_time"] = round(current_time + seg_duration, 2)
        current_time = seg["end_time"]
        
    segments[-1]["end_time"] = round(total_duration, 2)
    print(f"[✓] Timestamp calcolati con successo (0.0s -> {total_duration}s)!")
    return segments

def estimate_timestamps(segments: list) -> list:
    """Calcola timestamp stimati se non hai ancora registrato l'audio."""
    print("[i] Nessun file audio_raw trovato: calcolo timestamp stimati sul testo...")
    current_time = 0.0
    for seg in segments:
        words = len(seg["text"].split())
        duration = max(3.5, round(words / 2.5, 2))
        seg["start_time"] = round(current_time, 2)
        seg["end_time"] = round(current_time + duration, 2)
        current_time += duration
    print(f"[✓] Durata totale stimata dello script: {current_time:.1f} secondi.")
    return segments

def download_image_wikimedia(query: str, dest_path: Path) -> bool:
    """Cerca e scarica una foto da Wikimedia Commons (Gratis, Zero API Key)."""
    url = "https://commons.wikimedia.org/w/api.php"
    headers = {"User-Agent": "DocuForge/1.0 (https://github.com/castafili/docu-forge)"}
    
    words = query.split()
    search_attempts = [query]
    if len(words) > 2:
        search_attempts.append(" ".join(words[:2]))
        search_attempts.append(" ".join(words[-2:]))

    for attempt_query in search_attempts:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {attempt_query}",
            "gsrnamespace": 6,          # Cerca nel namespace File/Immagini
            "gsrlimit": 5,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 1920,
            "format": "json"
        }
        try:
            r = requests.get(url, params=params, headers=headers, timeout=10)
            data = r.json()
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                img_info = page.get("imageinfo", [{}])[0]
                img_url = img_info.get("thumburl") or img_info.get("url")
                if img_url and not img_url.lower().endswith((".svg", ".pdf", ".tif", ".gif")):
                    img_data = requests.get(img_url, headers=headers, timeout=15).content
                    with open(dest_path, "wb") as f:
                        f.write(img_data)
                    return True
        except Exception as e:
            print(f"    [!] Errore Wikimedia per '{attempt_query}': {e}")
            
    return False

def download_image_openverse(query: str, dest_path: Path) -> bool:
    """Fallback gratuito senza API key usando Openverse (archivio Creative Commons)."""
    url = "https://api.openverse.org/v1/images/"
    headers = {"User-Agent": "DocuForge/1.0"}
    params = {"q": query, "page_size": 3}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        results = r.json().get("results", [])
        for item in results:
            img_url = item.get("url")
            if img_url and img_url.lower().endswith((".jpg", ".jpeg", ".png")):
                img_r = requests.get(img_url, headers=headers, timeout=15)
                if img_r.status_code == 200:
                    with open(dest_path, "wb") as f:
                        f.write(img_r.content)
                    return True
    except Exception:
        pass
    return False

def run_assets(slug: str) -> None:
    """Esegue l'intera pipeline del Modulo 2: Audio + Timestamp + Immagini."""
    project_data = load_project(slug)
    project_dir = WORKSPACE_DIR / slug
    images_dir = project_dir / "images"
    segments = project_data["segments"]

    # 1. Gestione Audio
    raw_wav = project_dir / "audio_raw.wav"
    raw_mp3 = project_dir / "audio_raw.mp3"
    clean_wav = project_dir / "audio_clean.wav"

    raw_audio = raw_wav if raw_wav.exists() else (raw_mp3 if raw_mp3.exists() else None)

    if raw_audio:
        duration_sec = remove_silences(raw_audio, clean_wav)
        segments = align_segments_to_duration(duration_sec, segments)
    else:
        segments = estimate_timestamps(segments)

    # 2. Download Immagini per ogni segmento
    print(f"[*] Ricerca e download di {len(segments)} immagini...")
    for seg in segments:
        seg_id = seg["id"]
        query = seg["visual_query"]
        img_filename = f"seg_{seg_id:03d}.jpg"
        img_path = images_dir / img_filename

        print(f"    -> [{seg_id:02d}] ({seg['start_time']}s - {seg['end_time']}s) Cerco: '{query}'...")
        success = download_image_wikimedia(query, img_path)
        if not success:
            success = download_image_openverse(query, img_path)

        if success:
            seg["image_path"] = str(img_path.relative_to(WORKSPACE_DIR.parent))
            print(f"       [✓] Salvata: {img_filename}")
        else:
            print(f"       [!] Nessuna immagine trovata per '{query}'")

    project_data["segments"] = segments
    project_data["status"] = "assets_ready"
    save_project(slug, project_data)
    print(f"[✓] Modulo 2 completato! Controlla la cartella: workspace/{slug}/images/")