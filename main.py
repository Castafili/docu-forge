import argparse
from src.config import check_config
from src.state import init_project
from src.mod1_research import run_research
from src.mod2_assets import run_assets
from src.mod3_editor import run_editor

def main():
    parser = argparse.ArgumentParser(description="Docu-Forge: Pipeline per Documentari YouTube")
    parser.add_argument("--slug", help="Identificativo cartella (es. 01_emu_war)")
    parser.add_argument("--topic", help="Titolo pagina Wikipedia EN (es. 'Emu War')")
    parser.add_argument(
        "--step", 
        choices=["check", "init", "research", "assets", "render"], 
        default="check",
        help="Quale operazione eseguire"
    )
    
    args = parser.parse_args()
    
    if args.step == "check":
        check_config()
        
    elif args.step == "init":
        if not args.slug or not args.topic:
            print("[!] Errore: per 'init' servono sia --slug che --topic")
            return
        init_project(args.slug, args.topic)
        
    elif args.step == "research":
        if not args.slug:
            print("[!] Errore: specifica --slug")
            return
        run_research(args.slug)

    elif args.step == "assets":
        if not args.slug:
            print("[!] Errore: specifica --slug")
            return
        run_assets(args.slug)

    elif args.step == "render":
        if not args.slug:
            print("[!] Errore: specifica --slug")
            return
        run_editor(args.slug)

if __name__ == "__main__":
    main()