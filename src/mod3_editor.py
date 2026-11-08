import subprocess
from pathlib import Path
from src.config import BASE_DIR
from src.state import load_project, save_project, WORKSPACE_DIR

def render_segment_clip(image_path: Path, duration: float, out_clip: Path, fps: int = 30) -> None:
    """Converte una singola immagine in una clip MP4 1080p con effetto Zoom fluido (senza vibrazioni)."""
    frames = max(1, int(duration * fps))
    
    # 1. Portiamo l'immagine in un box 1920x1080 pulito
    # 2. L'ingrandiamo a 8000px (così zoompan lavora con precisione sub-pixel e non trema!)
    # 3. Applichiamo uno zoom lineare dall'1.0x all'1.12x lungo tutta la durata della clip
    vf_filter = (
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,"
        f"scale=8000:-1,"
        f"zoompan=z='1.0+0.12*(on/{frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps},"
        f"format=yuv420p"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", vf_filter,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        str(out_clip)
    ]
    
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def generate_davinci_xml(slug: str, project_data: dict, audio_path: Path, out_xml: Path) -> None:
    """Genera un file FCPXML importabile direttamente in DaVinci Resolve."""
    fps = 30
    segments = project_data["segments"]
    total_duration = segments[-1]["end_time"] if segments else 0
    total_frames = int(total_duration * fps)

    resources_xml = []
    spine_xml = []

    for seg in segments:
        seg_id = seg["id"]
        img_full_path = (BASE_DIR / seg["image_path"]).resolve()
        start_frames = int(seg["start_time"] * fps)
        dur_frames = max(1, int((seg["end_time"] - seg["start_time"]) * fps))

        res_id = f"r{seg_id}"
        resources_xml.append(
            f'        <asset id="{res_id}" name="seg_{seg_id:03d}" src="file://{img_full_path}" start="0s" duration="0s" hasVideo="1"/>'
        )
        spine_xml.append(
            f'                        <video name="seg_{seg_id:03d}" offset="{start_frames}/{fps}s" ref="{res_id}" duration="{dur_frames}/{fps}s" start="0s"/>'
        )

    audio_res_xml = ""
    audio_clip_xml = ""
    if audio_path.exists():
        audio_full = audio_path.resolve()
        resources_xml.append(
            f'        <asset id="r_audio" name="voiceover" src="file://{audio_full}" start="0s" duration="{total_frames}/{fps}s" hasAudio="1"/>'
        )
        audio_clip_xml = f'                        <asset-clip name="Voiceover" lane="-1" offset="0s" ref="r_audio" duration="{total_frames}/{fps}s" audioRole="dialogue"/>'

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.8">
    <resources>
        <format id="r0" name="FFVideoFormat1080p30" frameDuration="1/{fps}s" width="1920" height="1080"/>
{chr(10).join(resources_xml)}
    </resources>
    <library>
        <event name="{slug}">
            <project name="{project_data.get('title', slug)}">
                <sequence format="r0" duration="{total_frames}/{fps}s" tcStart="0s" tcFormat="NDF">
                    <spine>
{chr(10).join(spine_xml)}
{audio_clip_xml}
                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>
"""
    with open(out_xml, "w", encoding="utf-8") as f:
        f.write(xml_content)
    print(f"[✓] Timeline DaVinci Resolve generata: {out_xml}")

def run_editor(slug: str) -> None:
    """Monta il video finale .mp4 con FFmpeg ed esporta la timeline XML."""
    project_data = load_project(slug)
    project_dir = WORKSPACE_DIR / slug
    output_dir = project_dir / "output"
    temp_dir = output_dir / "temp_clips"
    temp_dir.mkdir(parents=True, exist_ok=True)

    segments = project_data["segments"]
    audio_clean = project_dir / "audio_clean.wav"

    # 1. Generiamo subito il file XML per DaVinci Resolve
    xml_path = output_dir / f"{slug}_timeline.fcpxml"
    generate_davinci_xml(slug, project_data, audio_clean, xml_path)

    # 2. Renderizziamo le singole clip con effetto Zoom
    print(f"[*] Rendering di {len(segments)} clip video (1080p con effetto Ken Burns)...")
    clip_files = []
    for seg in segments:
        seg_id = seg["id"]
        img_rel = seg.get("image_path", "")
        if not img_rel:
            print(f"    [!] Segmento {seg_id} non ha immagine, salto.")
            continue
            
        img_path = BASE_DIR / img_rel
        duration = round(seg["end_time"] - seg["start_time"], 2)
        clip_out = temp_dir / f"clip_{seg_id:03d}.mp4"
        
        print(f"    -> [{seg_id:02d}] Rendering clip ({duration}s) da {img_path.name}...")
        render_segment_clip(img_path, duration, clip_out)
        clip_files.append(clip_out)

    # 3. Creiamo il file di lista per concatenare le clip
    concat_list_path = temp_dir / "concat_list.txt"
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for clip in clip_files:
            f.write(f"file '{clip.resolve()}'\n")

    # 4. Uniamo tutte le clip + la tua voce in un unico file .mp4
    final_mp4 = output_dir / f"{slug}_final.mp4"
    print(f"[*] Unione delle clip e sincronizzazione con la tua voce...")

    if audio_clean.exists():
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list_path),
            "-i", str(audio_clean),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(final_mp4)
        ]
    else:
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list_path),
            "-c:v", "copy",
            str(final_mp4)
        ]

    subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    project_data["status"] = "rendered"
    save_project(slug, project_data)
    print(f"\n[🎉] VIDEO PRONTO! Trovi il tuo documentario finito qui:")
    print(f"    -> Video MP4: {final_mp4}")
    print(f"    -> DaVinci XML: {xml_path}")