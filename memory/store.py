"""SQLite: memória persistente + índice de arquivos (cache de busca)."""
import os, sqlite3, time, unicodedata
import threading
from config import settings

ready = False
_lock = threading.Lock()
SKIP = {"node_modules", "appdata", "__pycache__", "$recycle.bin", "venv", "site-packages"}


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s).lower()) if unicodedata.category(c) != "Mn")


def _run(sql, params=(), many=False, fetch=False):
    with _lock:
        c = sqlite3.connect(settings.DB, timeout=30)
        try:
            cur = c.executemany(sql, params) if many else c.execute(sql, params)
            res = cur.fetchall() if fetch else None
            c.commit()
            return res
        finally:
            c.close()


def init():
    global ready
    with _lock:
        c = sqlite3.connect(settings.DB)
        c.executescript(
            "create table if not exists memory(id integer primary key, text text, ts real);"
            "create table if not exists files(path text primary key, name text, norm text, npath text,"
            " ext text, mtime real, size integer, isdir integer);"
            "create index if not exists ix_norm on files(norm);"
            "create table if not exists kv(k text primary key, v text);"
            "create table if not exists chat(id integer primary key, role text, text text, ts real);"
            # eventos de notícias: base do futuro perfil de interesses (ver tools/news_rank.py)
            "create table if not exists news_events(id integer primary key, item_id text, source text,"
            " category text, title text, action text, ts real);"
            "create index if not exists ix_news_ev on news_events(item_id);"
        )
        ready = c.execute("select count(*) from files").fetchone()[0] > 0
        c.commit(); c.close()


def index_files():
    global ready
    rows = []
    for root in settings.ROOTS:
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if not x.startswith(".") and x.lower() not in SKIP]
            for n, isd in [(x, 1) for x in dirs] + [(x, 0) for x in files]:
                if n.startswith(".") or n.lower() == ".env":
                    continue
                p = os.path.join(d, n)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                rows.append((p, n, norm(n), norm(p), os.path.splitext(n)[1].lower(), st.st_mtime, st.st_size, isd))
    _run("delete from files")
    _run("insert or replace into files values(?,?,?,?,?,?,?,?)", rows, many=True)
    ready = True


def reindex_loop(every=900):
    from config import prefs
    while True:
        try:
            if prefs.get()["privacy"]["indexing"]:
                index_files()
        except Exception:
            pass
        time.sleep(every)


def search(tokens, ext=None, within=None, before=None, min_mb=None, kind=None, folder=None, limit=15, exts=None):
    q, p = "select path,mtime,size,isdir from files where 1=1", []
    for t in tokens:
        q += " and norm like ?"; p.append(f"%{t}%")
    for t in norm(folder or "").split():
        q += " and npath like ?"; p.append(f"%{t}%")
    if ext:
        q += " and ext=?"; p.append("." + ext.lower().lstrip("."))
    if exts:
        q += f" and ext in ({','.join('?' * len(exts))})"; p += list(exts)
    if within is not None:
        q += " and mtime>=?"; p.append(time.time() - float(within) * 86400)
    if before is not None:
        q += " and mtime<=?"; p.append(time.time() - float(before) * 86400)
    if min_mb:
        q += " and size>=?"; p.append(float(min_mb) * 1048576)
    if kind == "folder":
        q += " and isdir=1"
    elif kind == "file":
        q += " and isdir=0"
    q += " order by mtime desc limit ?"; p.append(int(limit))
    return _run(q, p, fetch=True)


def remember(text):
    _run("insert into memory(text,ts) values(?,?)", (text, time.time()))


def recall(query, limit=10):
    toks = norm(query).split()
    rows = _run("select text from memory order by ts desc limit 500", fetch=True)
    hits = [r[0] for r in rows if not toks or any(t in norm(r[0]) for t in toks)]
    return hits[:limit]


# ---- configurações persistentes (JSON em kv) ----
def kv_get(key, default=None):
    import json
    r = _run("select v from kv where k=?", (key,), fetch=True)
    try:
        return json.loads(r[0][0]) if r else default
    except Exception:
        return default


def kv_set(key, value):
    import json
    _run("insert or replace into kv values(?,?)", (key, json.dumps(value, ensure_ascii=False)))


# ---- histórico de conversa (só grava se Privacidade > histórico estiver ligado) ----
def add_chat(role, text):
    _run("insert into chat(role,text,ts) values(?,?,?)", (role, text, time.time()))


def recent_chat(limit=20):
    rows = _run("select role,text from chat order by id desc limit ?", (limit,), fetch=True)
    return [{"role": r[0], "text": r[1]} for r in reversed(rows)]


def clear_chat():
    _run("delete from chat")


# ---- eventos de notícia ----
def news_event(item_id, source, category, title, action):
    _run("insert into news_events(item_id,source,category,title,action,ts) values(?,?,?,?,?,?)",
         (item_id, source, category, title, action, time.time()))


def news_events(limit=2000):
    return _run("select item_id,source,category,action,ts from news_events order by id desc limit ?",
                (limit,), fetch=True)
