import os, re, shutil, subprocess, time
from pathlib import Path
import psutil
from memory import store
from tools import NeedConfirm, apps

def launch(a, approved, state):
    """Abre site (no navegador do JARVIS), caminho ou aplicativo (resolvido entre os instalados)."""
    t = a["target"].strip()
    if re.match(r"(https?://|www\.)", t):
        from core.browser import browser
        out = browser.open(t if t.startswith("http") else "https://" + t)
        out["_ui"] = {"type": "browser", "state": browser.state()}
        return out
    p = Path(os.path.expandvars(os.path.expanduser(t)))
    if p.is_absolute() and p.exists():
        os.startfile(p); return {"ok": f"aberto {p.name}"}
    res = apps.open_app(t)
    if "error" in res and shutil.which(t):          # comandos do PATH (calc, notepad, cmd...)
        os.startfile(shutil.which(t)); return {"ok": f"aberto {t}"}
    return res


def find_app(a, approved, state):
    return {"apps": apps.list_apps(a.get("query", ""))}


def close_app(a, approved, state):
    n = store.norm(a["name"])
    procs = [p for p in psutil.process_iter(["name"]) if n in store.norm(p.info["name"] or "")]
    if not procs:
        return {"error": "Nenhum processo com esse nome."}
    if not approved:
        raise NeedConfirm(f"Fechar {a['name']} ({len(procs)} processo(s)).")
    for p in procs:
        try: p.terminate()
        except Exception: pass
    return {"ok": f"{len(procs)} processo(s) encerrado(s)"}


def _size(path, deadline):
    tot = 0
    for d, _, fs in os.walk(path):
        for f in fs:
            try: tot += os.path.getsize(os.path.join(d, f))
            except OSError: pass
        if time.time() > deadline:
            break
    return tot


def system_info(a, approved, state):
    k = a.get("kind", "overview")
    if k == "processes":
        ps = sorted(psutil.process_iter(["name", "memory_info"]), key=lambda p: p.info["memory_info"].rss if p.info["memory_info"] else 0, reverse=True)[:10]
        return {"top": [{"name": p.info["name"], "ram_mb": round(p.info["memory_info"].rss / 1048576)} for p in ps]}
    if k == "space":
        root = Path(os.path.expanduser(a.get("path") or "~"))
        deadline, out = time.time() + 25, []
        for e in root.iterdir():
            try:
                s = _size(e, deadline) if e.is_dir() else e.stat().st_size
                out.append({"name": e.name, "gb": round(s / 1e9, 2)})
            except OSError:
                pass
        return {"path": str(root), "largest": sorted(out, key=lambda x: -x["gb"])[:10]}
    vm = psutil.virtual_memory()
    disks = []
    for d in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(d.mountpoint)
            disks.append({"drive": d.mountpoint, "free_gb": round(u.free / 1e9), "total_gb": round(u.total / 1e9)})
        except OSError:
            pass
    return {"cpu_percent": psutil.cpu_percent(0.3), "ram_percent": vm.percent, "disks": disks}
