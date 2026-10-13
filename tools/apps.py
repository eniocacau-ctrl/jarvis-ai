"""Descoberta e resolução de aplicativos instalados (sem lista fixa de apps).

Fontes: Get-StartApps (Win32 + UWP, com AppID lançável), atalhos do Menu Iniciar (.lnk) e App Paths do registro.
A resolução casa a fala do usuário ("vs code", "vscode", "editor do código") com nome amigável, executável
e iniciais, por tokens — nada de if por aplicativo.
"""
import difflib, json, os, re, subprocess, sys, threading, time
from pathlib import Path
from memory import store

_apps, _lock, _ts = None, threading.Lock(), 0
TTL = 6 * 3600
_CNW = 0x08000000  # CREATE_NO_WINDOW


# ---------- descoberta ----------
def _from_startapps():
    ps = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=40,
                       creationflags=_CNW)
    data = json.loads(r.stdout.decode("utf-8", "ignore") or "[]")
    if isinstance(data, dict):
        data = [data]
    out = []
    for d in data:
        appid = d.get("AppID") or ""
        exe = Path(appid).stem if appid.lower().endswith(".exe") else ""
        out.append({"name": d.get("Name") or "", "exe": exe, "launch": f"shell:AppsFolder\\{appid}", "src": "startapps"})
    return out


def _from_lnk():
    dirs = [Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"]
    return [{"name": p.stem, "exe": "", "launch": str(p), "src": "lnk"} for d in dirs if d.exists() for p in d.rglob("*.lnk")]


def _from_app_paths():
    out = []
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                k = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths")
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(k)[0]):
                n = winreg.EnumKey(k, i)
                try:
                    path = winreg.QueryValueEx(winreg.OpenKey(k, n), "")[0]
                except OSError:
                    continue
                out.append({"name": Path(n).stem, "exe": Path(n).stem, "launch": path.strip('"'), "src": "apppaths"})
    except ImportError:
        pass
    return out


def installed(force=False):
    """Lista (em cache) de apps instalados. Dedup por nome normalizado; startapps tem prioridade."""
    global _apps, _ts
    with _lock:
        if _apps is None or force or time.time() - _ts > TTL:
            items = []
            for f in (_from_startapps, _from_lnk, _from_app_paths):
                try:
                    items += f()
                except Exception:
                    pass
            seen, res = {}, []
            for a in items:
                key = store.norm(a["name"])
                if not key or key in seen:
                    # aproveita o executável de uma fonte para outra entrada com o mesmo nome
                    if key in seen and a["exe"] and not seen[key]["exe"]:
                        seen[key]["exe"] = a["exe"]
                    continue
                seen[key] = a
                res.append(a)
            _apps, _ts = res, time.time()
        return _apps


# ---------- casamento ----------
def toks(s):
    return [t for t in re.split(r"[^a-z0-9]+", store.norm(s)) if t]


def _match_token(q, c, used):
    """q casa com algum token livre de c (prefixo) ou com as iniciais de tokens seguidos ("vs" = visual studio).
    Devolve os índices consumidos ou None."""
    for i, t in enumerate(c):
        if i not in used and t.startswith(q):
            return {i}
    for k in range(2, len(c) + 1):                       # iniciais de k tokens consecutivos
        for s in range(0, len(c) - k + 1):
            span = set(range(s, s + k))
            if not span & used and "".join(t[0] for t in c[s:s + k]) == q:
                return span
    for k in range(1, len(c)):                           # "vscode" = iniciais("visual studio") + "code"
        ini = "".join(t[0] for t in c[:k])
        if q.startswith(ini) and len(q) > len(ini):
            rest = q[len(ini):]
            for j in range(k, len(c)):
                if j not in used and c[j].startswith(rest):
                    return set(range(k)) | {j}
    return None


def score(query, app):
    q = toks(query)
    if not q:
        return 0.0
    name, exe = store.norm(app["name"]).strip(), store.norm(app["exe"]).strip()
    qj = "".join(q)
    if name == " ".join(q) or name == qj:
        return 2.0
    best = 0.0
    for label in filter(None, (app["name"], app["exe"])):
        c = toks(label)
        if not c:
            continue
        used, hit = set(), 0
        for t in q:
            m = _match_token(t, c, used)
            if m is not None:
                used |= m
                hit += 1
        if hit == len(q):
            s = 1.0 + 0.1 * len(used) / len(c) - 0.03 * (len(c) - len(used))   # prefere nomes sem tokens sobrando
            if label == app["exe"]:
                s -= 0.05
            best = max(best, s)
        else:
            best = max(best, 0.55 * hit / len(q) * 0.5)
    r = difflib.SequenceMatcher(None, qj, "".join(toks(app["name"]))).ratio()
    if r >= 0.8:
        best = max(best, 0.9 * r)
    return best


def resolve(query, limit=5, apps=None):
    apps = installed() if apps is None else apps
    ranked = sorted(((score(query, a), a) for a in apps), key=lambda x: (-x[0], len(x[1]["name"])))
    return [(s, a) for s, a in ranked if s >= 0.6][:limit]


def launch_entry(a):
    if a["launch"].startswith("shell:"):
        subprocess.Popen(["explorer.exe", a["launch"]])
    else:
        os.startfile(a["launch"])


def open_app(query):
    """Abre o melhor candidato; se houver ambiguidade real devolve candidatos para o LLM decidir pelo contexto."""
    cands = resolve(query)
    if not cands:
        return {"error": f"Não encontrei nenhum aplicativo instalado parecido com '{query}'."}
    (s1, a1), rest = cands[0], cands[1:]
    close = [a["name"] for s, a in rest if s >= s1 - 0.12]
    if (close or s1 < 0.75) and s1 < 2.0:
        return {"ambiguous": True, "candidates": [a1["name"]] + close,
                "note": "Escolha pelo contexto e chame de novo com o nome EXATO do candidato (ou pergunte se não souber)."}
    launch_entry(a1)
    return {"ok": f"abri '{a1['name']}'", "app": a1["name"]}


_STOP = {"de", "do", "da", "o", "a", "um", "uma", "app", "aplicativo", "programa", "meu", "minha"}


def list_apps(query=""):
    """Nomes dos apps instalados, opcionalmente filtrados por palavras (ajuda em pedidos vagos como 'editor')."""
    qs = [t for t in toks(query) if t not in _STOP]
    names = [a["name"] for a in installed()]
    if qs:
        names = [n for n in names if any(q in store.norm(n) for q in qs)]
    return sorted(set(names), key=str.lower)[:60]
