import asyncio
import requests
import edge_tts
from pathlib import Path
from pydub import AudioSegment

from src.state import load_project, save_project, WORKSPACE_DIR

# Voci consigliate per documentari:
# "en-US-ChristopherNeural" (Narratore americano profondo, stile SunnyV2)
# "en-US-EricNeural"        (Narratore americano incalzante)
# "en-GB-RyanNeural"        (Narratore britannico stile BBC/Lemmino)
VOICE = "en-US-ChristopherNeural"
VOICE_RATE = "+5%"  # Leggermente più veloce per tenere alto il ritmo su YouTube

async def _generate_tts_file(text: str, out_path: Path) -> None:
    """Genera il file audio MP3 di una singola frase usando Microsoft Edge Neural TTS."""
    communicate = edge_tts.Communicate(text, VOICE, rate=VOICE_RATE)
    await communicate.save(str(out_path))

def generate_ai_voiceover(segments: list, project_dir: Path, output_wav: Path) -> list:
    """Genera la voce IA segmento per segmento e calcola i timestamp perfetti al millisecondo."""
    print(f"[*] Generazione Voce IA ({VOICE}) per {len(segments)} segmenti...")
    tts_dir = project_dir / "tts_chunks"
    tts_dir.mkdir(parents=True, exist_ok=True)

    combined_audio = AudioSegment.empty()
    pause_between_segments = AudioSegment.silent(duration=250)  # 250ms di respiro tra due frasi
    current_time = 0.0

    for seg in segments:
        seg_id = seg["id"]
        chunk_mp3 = tts_dir / f"tts_{seg_id:03d}.mp3"

        # Genera l'audio della frase con edge-tts
        asyncio.run(_generate_tts_file(seg["text"], chunk_mp3))

        # Carica l'audio generato e aggiunge la micro-pausa finale
        audio_chunk = AudioSegment.from_file(str(chunk_mp3)) + pause_between_segments
        duration_sec = round(len(audio_chunk) / 1000.0, 2)

        seg["start_time"] = round(current_time, 2)
        seg["end_time"] = round(current_time + duration_sec, 2)
        current_time = seg["end_time"]

        combined_audio += audio_chunk
        print(f"    -> [{seg_id:02d}] Audio IA generato ({duration_sec}s): {seg['start_time']}s -> {seg['end_time']}s")

    combined_audio.export(str(output_wav), format="wav")
    print(f"[✓] Traccia vocale completa salvata ({current_time:.2f}s): {output_wav.name}")
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
            "gsrnamespace": 6,
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
    """Fallback gratuito senza API key usando Openverse."""
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
    """Esegue la pipeline del Modulo 2: Voce IA + Timestamp esatti + Immagini."""
    project_data = load_project(slug)
    project_dir = WORKSPACE_DIR / slug
    images_dir = project_dir / "images"
    segments = project_data["segments"]
    clean_wav = project_dir / "audio_clean.wav"

    # 1. Generazione Voce IA e Timestamp al millisecondo
    segments = generate_ai_voiceover(segments, project_dir, clean_wav)

    # 2. Download Immagini (salta quelle già scaricate così non perdi tempo!)
    print(f"[*] Controllo e download delle {len(segments)} immagini...")
    for seg in segments:
        seg_id = seg["id"]
        query = seg["visual_query"]
        img_filename = f"seg_{seg_id:03d}.jpg"
        img_path = images_dir / img_filename

        if img_path.exists():
            seg["image_path"] = str(img_path.relative_to(WORKSPACE_DIR.parent))
            print(f"    -> [{seg_id:02d}] Già presente: {img_filename}")
            continue

        print(f"    -> [{seg_id:02d}] Cerco: '{query}'...")
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
    print(f"[✓] Modulo 2 completato con Voce IA!")