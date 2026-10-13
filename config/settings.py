import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
REASONING = os.getenv("GROQ_REASONING", "low")
PORT = int(os.getenv("JARVIS_PORT", "8765"))
NEWS_ON_START = os.getenv("NEWS_ON_START", "true").lower() == "true"
TITLE = os.getenv("JARVIS_TITLE", "Senhor")
HOME = Path.home()
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
DB = DATA / "jarvis.db"


def _roots():
    env = os.getenv("JARVIS_ROOTS")
    if env:
        r = [Path(p) for p in env.split(";") if p.strip()]
    else:
        r = [HOME / n for n in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")]
        r += list(HOME.glob("OneDrive*"))
    return [p.resolve() for p in r if p.exists()]


ROOTS = _roots()
