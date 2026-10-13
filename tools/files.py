import os, shutil, subprocess, time
from pathlib import Path
from config import settings
from memory import store
from tools import NeedConfirm

TEXT = [".txt", ".md", ".csv", ".json", ".py", ".html", ".log", ".ini", ".xml"]


def _path(p):
    p = Path(os.path.expandvars(os.path.expanduser(str(p))))
    if not p.is_absolute():
        for r in [settings.HOME] + settings.ROOTS:
            if (r / p).exists():
                return (r / p).resolve()
        p = settings.HOME / p
    return p.resolve()


def _inside(p):
    return any(p == r or r in p.parents for r in settings.ROOTS)


def _guard(p, approved):
    if p.name.lower() == ".env":
        raise PermissionError("Arquivo protegido.")
    if not approved and not _inside(p):
        raise NeedConfirm(f"Isso está fora das pastas autorizadas: {p}.")


def _fmt(r):
    return {"path": r[0], "modified": time.strftime("%d/%m/%Y %H:%M", time.localtime(r[1])),
            "size_mb": round(r[2] / 1048576, 2), "type": "pasta" if r[3] else "arquivo"}


def find_files(a, approved, state):
    if not store.ready:
        return {"note": "O índice de arquivos ainda está sendo construído; tente novamente em instantes."}
    toks = store.norm(a.get("query", "")).split()
    kw = dict(ext=a.get("ext"), within=a.get("modified_within_days"), before=a.get("modified_before_days"),
              min_mb=a.get("min_mb"), kind=a.get("type"), folder=a.get("folder"))
    limit = min(int(a.get("limit", 15)), 40)
    content = a.get("content")
    if content:
        needle, hits = store.norm(content), []
        for r in store.search(toks, limit=400, exts=TEXT, **{k: v for k, v in kw.items() if k != "ext"}):
            try:
                if r[2] < 2_000_000 and needle in store.norm(Path(r[0]).read_text(errors="ignore")):
                    hits.append(r)
            except OSError:
                pass
            if len(hits) >= limit:
                break
        return {"results": [_fmt(r) for r in hits]}
    return {"results": [_fmt(r) for r in store.search(toks, limit=limit, **kw)]}


def list_folder(a, approved, state):
    p = _path(a.get("path", "~"))
    _guard(p, approved)
    items = []
    for e in sorted(p.iterdir(), key=lambda x: x.name.lower())[:200]:
        try:
            st = e.stat()
            items.append({"name": e.name, "type": "pasta" if e.is_dir() else "arquivo",
                          "size_mb": round(st.st_size / 1048576, 2),
                          "modified": time.strftime("%d/%m/%Y", time.localtime(st.st_mtime))})
        except OSError:
            pass
    return {"path": str(p), "items": items}


def _bulk(state):
    state["ops"] = state.get("ops", 0) + 1
    if state["ops"] > 10 and not state.get("bulk_ok"):
        raise NeedConfirm("Vou alterar muitos arquivos de uma vez.")


def file_action(a, approved, state):
    act = a["action"]
    p = _path(a["path"])
    _guard(p, approved)
    if not p.exists() and act not in ("mkdir", "write"):
        return {"error": f"Não existe: {p}"}
    if act == "open":
        os.startfile(p); return {"ok": f"aberto {p.name}"}
    if act == "reveal":
        subprocess.Popen(["explorer", "/select,", str(p)]); return {"ok": "mostrado no Explorer"}
    if act == "mkdir":
        p.mkdir(parents=True, exist_ok=True); return {"ok": f"pasta {p}"}
    if act == "write":
        if p.exists() and not approved:
            raise NeedConfirm(f"Substituir o arquivo {p.name}.")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a.get("content", ""), encoding="utf-8"); return {"ok": f"criado {p}"}
    if act == "trash":
        if not approved:
            raise NeedConfirm(f"Enviar {p.name} para a lixeira.")
        from send2trash import send2trash
        send2trash(str(p)); return {"ok": "enviado para a lixeira"}
    if act == "rename":
        dest = p.with_name(a["dest"])
        if dest.exists() and not approved:
            raise NeedConfirm(f"Já existe {dest.name}; substituir.")
        p.rename(dest); return {"ok": f"renomeado para {dest.name}"}
    if act in ("move", "copy"):
        dest = _path(a["dest"])
        _guard(dest, approved)
        if dest.is_dir() or (not dest.suffix and not dest.exists()):
            dest.mkdir(parents=True, exist_ok=True)
            dest = dest / p.name
        if dest.exists() and not approved:
            raise NeedConfirm(f"Já existe {dest.name} no destino; substituir.")
        _bulk(state)
        if act == "move":
            shutil.move(str(p), str(dest))
        elif p.is_dir():
            shutil.copytree(p, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(p, dest)
        return {"ok": f"{act} -> {dest}"}
    return {"error": "ação desconhecida"}
