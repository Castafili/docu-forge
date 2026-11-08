import json
import wikipediaapi
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from src.config import GOOGLE_API_KEY
from src.state import load_project, save_project, WORKSPACE_DIR

# 1. Schema JSON strutturato per l'output dell'AI
class SegmentSchema(BaseModel):
    id: int = Field(description="Sequential segment number (starting from 1)")
    text: str = Field(description="Voiceover line in English (1-2 punchy sentences max, engaging and witty tone)")
    visual_query: str = Field(description="Search query in English (3-5 words) to find a historical photo or stock image matching this line")

class DocumentaryScript(BaseModel):
    title: str = Field(description="Catchy, high-CTR YouTube video title in English")
    segments: list[SegmentSchema]

def fetch_wikipedia_content(topic: str) -> str:
    """Scarica il testo dalla Wikipedia INGLESE (en.wikipedia.org)."""
    wiki = wikipediaapi.Wikipedia(
        user_agent="DocuForge/1.0 (https://github.com/castafili/docu-forge)",
        language="en"
    )
    page = wiki.page(topic)
    if not page.exists():
        print(f"[!] Exact Wikipedia page not found for '{topic}'. Relying on model knowledge.")
        return ""
    
    print(f"[✓] English Wikipedia source found: '{page.title}' ({len(page.text)} chars)")
    return page.text[:15000]

def run_research(slug: str) -> None:
    """Esegue la ricerca in inglese e genera project.json e script.md."""
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY mancante! Inseriscila nel file .env")

    project_data = load_project(slug)
    topic = project_data["topic"]
    
    print(f"[*] Searching English sources for: '{topic}'...")
    wiki_text = fetch_wikipedia_content(topic)
    
    print("[*] Generating English documentary script with Gemini...")
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    prompt = f"""
    You are the lead writer for a wildly popular English YouTube documentary channel covering bizarre history, absurd bureaucracy, epic engineering failures, and crazy cyber/gaming stories (in the style of Lemmino, Sam O'Nella, and SunnyV2).
    
    Write a fast-paced, witty, and engaging voiceover script about: "{topic}".
    
    Rules:
    - Write in clear, natural, punchy English (easy to read aloud with great pacing).
    - Break the script into 8-12 short segments (each segment should take about 5-10 seconds to read aloud).
    - Segment 1 MUST be a killer hook that grabs the viewer's attention in the first 5 seconds.
    - For each segment, provide a concrete 'visual_query' (3-5 keywords) to search for historical photos or stock footage.
    
    Use these verified facts as your primary source material:
    {wiki_text if wiki_text else "Use verified historical facts."}
    """

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DocumentaryScript,
            temperature=0.7,
        ),
    )

    result_json = json.loads(response.text)
    
    formatted_segments = []
    for seg in result_json["segments"]:
        formatted_segments.append({
            "id": seg["id"],
            "text": seg["text"],
            "visual_query": seg["visual_query"],
            "start_time": 0.0,
            "end_time": 0.0,
            "image_path": ""
        })

    project_data["title"] = result_json["title"]
    project_data["status"] = "script_generated"
    project_data["segments"] = formatted_segments
    save_project(slug, project_data)

    # Creiamo il file Markdown comodo da leggere
    md_path = WORKSPACE_DIR / slug / "script.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {result_json['title']}\n\n")
        for seg in formatted_segments:
            f.write(f"**[{seg['id']:02d}]** {seg['text']}\n")
            f.write(f"*Visual: `{seg['visual_query']}`*\n\n")

    print(f"[✓] English Script generated successfully!")
    print(f"    -> JSON Data: workspace/{slug}/project.json")
    print(f"    -> Readable Script: {md_path}")