import asyncio, json, os, sys, threading, time
from pathlib import Path
import psutil
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from config import prefs, settings
from core import stt
from core.agent import Agent
from core.browser import browser
from memory import store
from tools import NeedConfirm, files, news, screen

WEB = os.path.join(os.path.dirname(__file__), "web")
app = FastAPI()
app.mount("/static", StaticFiles(directory=WEB), name="static")
NEWS = {}  # id -> item (cache da última busca; alimenta eventos e enriquecimento)


@app.on_event("startup")
def _startup():
    store.init()
    threading.Thread(target=store.reindex_loop, daemon=True).start()


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"), headers={"Cache-Control": "no-store"})


# ---------------- configurações ----------------
class Patch(BaseModel):
    patch: dict


def _autostart(enabled):
    d = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
    f = d / "JARVIS.vbs"
    if enabled and d.exists():
        py = Path(sys.executable).with_name("pythonw.exe")
        py = py if py.exists() else Path(sys.executable)
        f.write_text(f'CreateObject("Wscript.Shell").Run """{py}"" ""{settings.BASE / "main.py"}""", 0, False\n', encoding="utf-8")
    elif f.exists():
        f.unlink()


@app.get("/api/prefs")
def get_prefs():
    return prefs.get()


@app.put("/api/prefs")
def put_prefs(p: Patch):
    old = prefs.get()["general"]["autostart"]
    cur = prefs.update(p.patch)
    if cur["general"]["autostart"] != old:
        try:
            _autostart(cur["general"]["autostart"])
        except OSError:
            pass
    return cur


@app.get("/api/history")
def history():
    return store.recent_chat(30) if prefs.get()["privacy"]["history"] else []


@app.delete("/api/history")
def clear_history():
    store.clear_chat()
    return {"ok": True}


# ---------------- sistema ----------------
@app.get("/api/system")
def system():
    vm = psutil.virtual_memory()
    disks = []
    for d in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(d.mountpoint)
            disks.append({"drive": d.mountpoint, "percent": u.percent, "free_gb": round(u.free / 1e9), "total_gb": round(u.total / 1e9)})
        except OSError:
            pass
    top = []
    for p in sorted(psutil.process_iter(["name", "memory_info"]), key=lambda p: p.info["memory_info"].rss if p.info["memory_info"] else 0, reverse=True)[:10]:
        top.append({"name": p.info["name"], "ram_mb": round(p.info["memory_info"].rss / 1048576)})
    return {"cpu": psutil.cpu_percent(), "ram": vm.percent, "ram_used_gb": round(vm.used / 1e9, 1),
            "ram_total_gb": round(vm.total / 1e9, 1), "disks": disks, "top": top}


# ---------------- arquivos (somente leitura/abrir; ações destrutivas só via agente com confirmação) ----------------
@app.get("/api/files/roots")
def roots():
    return [str(r) for r in settings.ROOTS]


@app.get("/api/files/list")
def flist(path: str):
    try:
        return files.list_folder({"path": path}, False, {})
    except NeedConfirm:
        raise HTTPException(403, "Fora das pastas autorizadas.")
    except (PermissionError, OSError) as e:
        raise HTTPException(400, str(e))


@app.get("/api/files/search")
def fsearch(q: str, ext: str = "", content: str = ""):
    return files.find_files({"query": q, "ext": ext or None, "content": content or None, "limit": 30}, False, {})


class FileOp(BaseModel):
    path: str
    reveal: bool = False


@app.post("/api/files/open")
def fopen(o: FileOp):
    try:
        return files.file_action({"action": "reveal" if o.reveal else "open", "path": o.path}, False, {})
    except NeedConfirm:
        raise HTTPException(403, "Fora das pastas autorizadas.")


# ---------------- notícias ----------------
def _fetch_news(limit=10):
    items = news.fetch(prefs.get()["news"], None, limit)
    if items:
        news.enrich(items[0])
    NEWS.clear()
    NEWS.update({i["id"]: i for i in items})
    return items


@app.get("/api/news")
def get_news(limit: int = 40):
    """Aba NEWS: todas as categorias (as fontes desligadas continuam respeitadas)."""
    items = news.fetch(prefs.get()["news"], None, min(limit, 60), all_categories=True)
    if items:
        news.enrich(items[0])
    NEWS.clear()
    NEWS.update({i["id"]: i for i in items})
    return items


@app.get("/api/news/health")
def news_health():
    return news.health()


@app.get("/api/news/enrich")
def enrich_news(id: str):
    it = NEWS.get(id)
    if not it:
        raise HTTPException(404)
    return news.enrich(it)


class NewsEvent(BaseModel):
    id: str
    action: str


@app.post("/api/news/event")
def news_event(e: NewsEvent):
    it = NEWS.get(e.id) or {}
    store.news_event(e.id, it.get("source", ""), it.get("category", ""), it.get("title", ""), e.action)
    return {"ok": True}


# ---------------- tela ----------------
@app.get("/api/screen")
def screen_info():
    return {"monitors": screen.monitors(), "selected": prefs.get()["screen"]["monitor"], "enabled": prefs.get()["privacy"]["screen"]}


# ---------------- STT local ----------------
@app.get("/api/stt/status")
def stt_status():
    m = prefs.get()["voice"]["stt_model"]
    return {"local": stt.available(), "model": m, "loaded": stt.loaded(m)}


@app.websocket("/ws/stt")
async def ws_stt(sock: WebSocket):
    """Cliente envia PCM int16 16 kHz (binário) e {"type":"end"}; recebe loading/interim/final/error."""
    await sock.accept()
    v = prefs.get()["voice"]
    lang, model = v["lang"].split("-")[0], v["stt_model"]
    buf, state = bytearray(), {"busy": False, "last": 0.0}
    MAX = 16000 * 2 * 30

    async def run(final):
        try:
            if not stt.loaded(model):
                await sock.send_json({"type": "loading"})
            text = await asyncio.to_thread(stt.transcribe, bytes(buf), lang, model)
            await sock.send_json({"type": "final" if final else "interim", "text": text})
        except Exception as e:
            await sock.send_json({"type": "error", "code": "stt-failed", "detail": f"{type(e).__name__}: {e}"})
        finally:
            state["busy"] = False

    try:
        if not stt.available():
            await sock.send_json({"type": "error", "code": "stt-missing", "detail": "pip install faster-whisper"})
            return
        while True:
            m = await sock.receive()
            if m.get("type") == "websocket.disconnect":
                break
            if m.get("bytes"):
                if len(buf) < MAX:
                    buf += m["bytes"]
                now = time.time()
                if not state["busy"] and len(buf) > 16000 * 2 and now - state["last"] > 1.5:
                    state.update(busy=True, last=now)
                    asyncio.create_task(run(False))
            elif m.get("text") and '"end"' in m["text"]:
                while state["busy"]:
                    await asyncio.sleep(0.05)
                await run(True)
                break
    except WebSocketDisconnect:
        pass


# ---------------- navegador ----------------
class BrowserCmd(BaseModel):
    action: str
    url: str = ""
    text: str = ""
    tab: int | None = None


@app.get("/api/browser")
def browser_state():
    return browser.state()


@app.post("/api/browser")
def browser_cmd(c: BrowserCmd):
    out = browser.command(c.action, c.tab, c.url, c.text)
    return {**out, "state": browser.state()}


# ---------------- tempo real ----------------
@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()

    async def emit(m):
        try:
            await sock.send_json(m)
        except Exception:
            pass

    agent = Agent(emit)

    async def news_start():
        try:
            items = await asyncio.to_thread(_fetch_news)
            if not items:
                return
            agent.history.append({"role": "assistant", "content": "[Notícias no card; a primeira está sendo lida] " + json.dumps(
                [{k: i[k] for k in ("title", "source", "summary", "url")} for i in items], ensure_ascii=False)})
            await emit({"type": "news_session", "items": items, "narrate": prefs.get()["news"]["narrate"], "intro": True})
        except Exception:
            pass

    async def stats():
        while True:
            await emit({"type": "stats", "cpu": psutil.cpu_percent(), "ram": psutil.virtual_memory().percent,
                        "disk": psutil.disk_usage(os.path.abspath(os.sep)).percent})
            await asyncio.sleep(3)

    st = asyncio.create_task(stats())
    try:
        while True:
            m = await sock.receive_json()
            t = m.get("type")
            if t == "user" and m.get("text"):
                agent.start(m["text"])
            elif t == "confirm":
                agent.resolve(m.get("ok"))
            elif t == "cancel":
                agent.cancel()
            elif t == "hello" and prefs.get()["news"]["on_start"]:
                asyncio.create_task(news_start())
    except WebSocketDisconnect:
        pass
    finally:
        st.cancel()
        agent.cancel()
