"""Notícias: RSS -> itens limpos -> ranking. A UI mostra UM card por vez; este módulo só entrega itens prontos."""
import hashlib, html, re, time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from memory import store
from tools.web import _get

# (fonte, categoria, url). Feeds que não respondem são ignorados e aparecem em HEALTH (/api/news/health).
_G1, _CNN, _FSP, _ABR, _UOL = "https://g1.globo.com/rss/g1/", "https://www.cnnbrasil.com.br/", "https://feeds.folha.uol.com.br/", \
    "https://agenciabrasil.ebc.com.br/rss/", "https://rss.uol.com.br/feed/"
FEEDS = [
    ("G1", "brasil", _G1), ("G1", "mundo", _G1 + "mundo/"), ("G1", "política", _G1 + "politica/"), ("G1", "economia", _G1 + "economia/"),
    ("G1", "tecnologia", _G1 + "tecnologia/"), ("G1", "ciência", _G1 + "ciencia-e-saude/"), ("G1", "entretenimento", _G1 + "pop-arte/"),
    ("GE", "esportes", "https://ge.globo.com/rss/ge/"), ("GE", "futebol", "https://ge.globo.com/rss/ge/futebol/"),
    ("BBC News Brasil", "mundo", "https://feeds.bbci.co.uk/portuguese/rss.xml"),
    ("CNN Brasil", "mundo", _CNN + "internacional/feed/"), ("CNN Brasil", "política", _CNN + "politica/feed/"),
    ("CNN Brasil", "economia", _CNN + "economia/feed/"), ("CNN Brasil", "esportes", _CNN + "esportes/feed/"),
    ("CNN Brasil", "tecnologia", _CNN + "tecnologia/feed/"), ("CNN Brasil", "entretenimento", _CNN + "entretenimento/feed/"),
    ("Folha", "brasil", _FSP + "emcimadahora/rss091.xml"), ("Folha", "mundo", _FSP + "mundo/rss091.xml"),
    ("Folha", "política", _FSP + "poder/rss091.xml"), ("Folha", "economia", _FSP + "mercado/rss091.xml"),
    ("Folha", "esportes", _FSP + "esporte/rss091.xml"), ("Folha", "tecnologia", _FSP + "tec/rss091.xml"),
    ("Folha", "ciência", _FSP + "ciencia/rss091.xml"), ("Folha", "cultura", _FSP + "ilustrada/rss091.xml"),
    ("Agência Brasil", "brasil", _ABR + "ultimasnoticias/feed.xml"), ("Agência Brasil", "política", _ABR + "politica/feed.xml"),
    ("Agência Brasil", "economia", _ABR + "economia/feed.xml"), ("Agência Brasil", "esportes", _ABR + "esportes/feed.xml"),
    ("Agência Brasil", "cultura", _ABR + "cultura/feed.xml"),
    ("UOL", "brasil", _UOL + "noticias.xml"), ("UOL", "tecnologia", _UOL + "tecnologia.xml"),
    ("UOL", "entretenimento", _UOL + "entretenimento.xml"), ("UOL", "esportes", _UOL + "esporte.xml"), ("UOL", "games", _UOL + "jogos.xml"),
    ("IGN Brasil", "games", "https://br.ign.com/feed.xml"), ("Jovem Nerd", "games", "https://jovemnerd.com.br/feed/"),
    ("Jovem Nerd", "cultura", "https://jovemnerd.com.br/feed/"),
    ("Canaltech", "tecnologia", "https://canaltech.com.br/rss/"), ("Olhar Digital", "tecnologia", "https://olhardigital.com.br/feed/"),
    # --- novos ---
    ("DW Brasil", "mundo", "https://rss.dw.com/xml/rss-br-all"),
    ("Poder360", "política", "https://www.poder360.com.br/feed/"), ("Metrópoles", "política", "https://www.metropoles.com/feed"),
    ("Metrópoles", "brasil", "https://www.metropoles.com/brasil/feed"), ("Agência Câmara", "política", "https://www.camara.leg.br/noticias/rss/dinamico/ULTIMAS-NOTICIAS"),
    ("O Globo", "brasil", "https://oglobo.globo.com/rss.xml"), ("R7", "brasil", "https://noticias.r7.com/feed.xml"),
    ("Veja", "brasil", "https://veja.abril.com.br/feed/"),
    ("Exame", "economia", "https://exame.com/feed/"), ("InfoMoney", "economia", "https://www.infomoney.com.br/feed/"),
    ("ESPN Brasil", "esportes", "https://www.espn.com.br/espn/rss/news"), ("ESPN Brasil", "futebol", "https://www.espn.com.br/espn/rss/futebol/news"),
    ("Trivela", "futebol", "https://trivela.com.br/feed/"),
    ("Tecnoblog", "tecnologia", "https://tecnoblog.net/feed/"), ("TecMundo", "tecnologia", "https://rss.tecmundo.com.br/feed"),
    ("Jornal da USP", "ciência", "https://jornal.usp.br/feed/"),
    ("Omelete", "entretenimento", "https://www.omelete.com.br/rss"), ("Omelete", "games", "https://www.omelete.com.br/games/rss"),
    ("Nintendo Blast", "games", "https://www.nintendoblast.com.br/feeds/posts/default?alt=rss"),
]
HEALTH = {}   # url -> {"source","category","ok","n","err"}

# ---------- limpeza de texto bruto ----------
_KW = r"(?:foto|fotos|imagem|imagens|crédito|créditos|credito|reprodução|reproducao|divulgação|divulgacao|ilustração|arte|vídeo|video)"
_CREDIT_PAREN = re.compile(r"(?i)\(\s*" + _KW + r"\s*[:/|-][^)]{0,90}\)")             # (Foto: Fulano/Agência)
_CREDIT_LINE = re.compile(r"(?i)^\s*" + _KW + r"\s*[:/|-].{0,90}$")                      # linha inteira "Foto: Fulano"
_CREDIT_TAIL = re.compile(r"(?i)\s*\b" + _KW + r"\s*[:/|-]\s*[^.!?]{0,60}$")               # "... frase. Crédito: Getty Images"
_AGENCY = re.compile(r"(?i)\b(getty images|afp|reuters|ap photo|epa|efe)\b\s*[/|-]?\s*(?=$|\n)")
_JUNK_LINE = re.compile(r"(?i)^(leia (mais|também)|veja (também|mais|o vídeo)|assista|continua depois|publicidade|"
                        r"compartilh|siga|assine|newsletter|clique|saiba mais|read more|menu|ver tudo|·|\|)")
_TAIL = re.compile(r"(?i)\s*(\[\s*(…|\.\.\.)\s*\]|…|\.\.\.|leia mais|read more|continue lendo).{0,20}$")


def clean(text, title=""):
    """HTML/RSS bruto -> texto limpo e curto, sem créditos, menus, lixo de feed e sem frase cortada."""
    t = re.sub(r"(?is)<(script|style|figure|figcaption|noscript).*?</\1>", " ", text or "")
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = _CREDIT_PAREN.sub(" ", t)
    lines = []
    for ln in (re.sub(r"[ \t\u00a0]+", " ", l).strip() for l in t.split("\n")):
        ln = _CREDIT_TAIL.sub("", ln).strip()
        if not ln or _CREDIT_LINE.match(ln) or _JUNK_LINE.match(ln) or _AGENCY.fullmatch(ln):
            continue
        if len(ln) < 25 and not re.search(r"[.!?]$", ln):       # menus/rótulos curtos
            continue
        lines.append(ln)
    t = " ".join(lines)
    t = _AGENCY.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = _TAIL.sub("", t).strip()
    if t and t[-1] not in ".!?\"”":                             # texto truncado: corta na última frase completa
        cut = max(t.rfind(". "), t.rfind("! "), t.rfind("? "))
        t = t[:cut + 1] if cut > 40 else t.rstrip(" ,;:-") + "…"
    nt = store.norm(title).strip()
    if len(nt) >= 15 and store.norm(t).startswith(nt):          # resumo que começa repetindo o título
        rest = t[len(title):].lstrip(" .:-–—")
        if len(rest) > 40 and not rest[:1].islower():           # resto começa uma frase nova; senão mantém o texto todo
            t = rest
        elif len(t) <= len(title) + 40:
            t = ""
    return t[:320]


def short(summary, n=200):
    """Primeira(s) frase(s) completas até n caracteres — usado para narrar."""
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", summary or ""):
        if len(out) + len(s) > n and out:
            break
        out = (out + " " + s).strip()
    return out[:n + 60]


def _img(it, raw):
    for el in it.iter():
        if el.tag.split("}")[-1] in ("content", "thumbnail", "enclosure") and el.get("url") \
                and (el.get("type") or "image").startswith("image"):
            return el.get("url")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', raw)
    return m.group(1) if m else None


def _feed(source, cat, url):
    out = []
    for it in ET.fromstring(_get(url)).iter("item"):
        raw = (it.findtext("description") or "") + (it.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or "")
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate")).timestamp()
        except Exception:
            ts = 0
        summ = clean(it.findtext("description") or "", title)
        out.append({"id": hashlib.sha1(link.encode()).hexdigest()[:12], "title": title, "source": source, "category": cat,
                    "summary": summ, "spoken": f"{title}. {short(summ)}".strip(), "url": link, "image": _img(it, raw),
                    "ts": ts, "published": time.strftime("%d/%m %H:%M", time.localtime(ts)) if ts else ""})
    return out


def og(url):
    """Completa imagem/descrição pela página (og:image / og:description) quando o RSS veio pobre."""
    try:
        page = _get(url, 6)[:200000].decode("utf-8", "ignore")
    except Exception:
        return {}
    def meta(*names):
        for n in names:
            m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*content=["\']([^"\']+)' % n, page, re.I) or \
                re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']%s["\']' % n, page, re.I)
            if m:
                return html.unescape(m.group(1))
    return {"image": meta("og:image", "twitter:image"), "summary": clean(meta("og:description", "description") or "")}


def enrich(item):
    if not item.get("image") or len(item.get("summary", "")) < 40:
        d = og(item["url"])
        item["image"] = item.get("image") or d.get("image")
        if len(item.get("summary", "")) < 40 and d.get("summary"):
            item["summary"] = d["summary"]
            item["spoken"] = f"{item['title']}. {short(item['summary'])}"
    return item


# ---------- ranking ----------
# Futuro (não implementado): perfil de interesses a partir de store.news_events().
EVENT_WEIGHT = {"open": 2, "more": 3, "save": 2, "repeat": 1, "skip": -1, "close": -1, "shown": 0}


def _importance(item, all_items):
    """Importância geral: recência + quantas fontes distintas cobrem o mesmo assunto."""
    age_h = max(0, (time.time() - item["ts"]) / 3600) if item["ts"] else 48
    words = {w for w in store.norm(item["title"]).split() if len(w) > 4}
    cover = {o["source"] for o in all_items if o["source"] != item["source"] and words & {w for w in store.norm(o["title"]).split() if len(w) > 4} and len(words & {w for w in store.norm(o["title"]).split() if len(w) > 4}) >= 2}
    return 1.0 / (1 + age_h / 6) + 0.5 * len(cover)


def _interest(item, profile):
    """Interesse pessoal (0 até existir perfil). Aqui entrará: pesos por categoria/fonte/palavras-chave."""
    return 0.0


def rank(items, profile=None, w_interest=0.4):
    for i in items:
        i["_score"] = (1 - w_interest) * _importance(i, items) + w_interest * _interest(i, profile)
    return sorted(items, key=lambda i: -i["_score"])


# ---------- deduplicação ----------
_STOPW = {"para", "como", "sobre", "entre", "depois", "contra", "após", "esta", "este", "mais", "pelo", "pela", "diz", "faz"}


def _link_key(u):
    return re.sub(r"[?#].*$", "", (u or "").lower()).rstrip("/").replace("://www.", "://")


def _tw(title):
    return {w for w in re.split(r"[^a-z0-9]+", store.norm(title)) if len(w) > 3 and w not in _STOPW}


def dedupe(items):
    """Mesmo link, mesmo título ou mesmo assunto (alta sobreposição de palavras) viram UMA entrada; as demais fontes ficam em `also`."""
    out, links, titles = [], {}, {}
    for it in items:
        lk, nt, tw = _link_key(it["url"]), store.norm(it["title"]).strip(), _tw(it["title"])
        dup = links.get(lk) or titles.get(nt)
        if not dup and tw:
            for o in out:
                ow = o["_tw"]
                inter = len(tw & ow)
                if inter >= 3 and inter / len(tw | ow) >= 0.5 or inter >= 5 and inter / min(len(tw), len(ow)) >= 0.8:
                    dup = o
                    break
        if dup:
            if it["source"] != dup["source"] and it["source"] not in dup.setdefault("also", []):
                dup["also"].append(it["source"])
            if not dup.get("image") and it.get("image"):
                dup["image"] = it["image"]
            continue
        it["_tw"] = tw
        out.append(it); links[lk] = it; titles[nt] = it
    for o in out:
        o.pop("_tw", None)
    return out


def _spread(items, limit):
    """Variedade: revezamento entre categorias (e evita a mesma fonte seguida), mantendo o ranking dentro de cada categoria."""
    buckets = {}
    for i in items:
        buckets.setdefault(i["category"], []).append(i)
    out, last = [], None
    while len(out) < limit and any(buckets.values()):
        for c in list(buckets):
            b = buckets[c]
            if not b:
                continue
            pick = next((i for i in b if i["source"] != last), b[0])
            b.remove(pick); out.append(pick); last = pick["source"]
            if len(out) >= limit:
                break
    return out


# ---------- API ----------
def _load_feed(f):
    s, c, u = f
    try:
        its = _feed(s, c, u)[:12]
        HEALTH[u + "#" + c] = {"source": s, "category": c, "ok": True, "n": len(its)}
        return its
    except Exception as e:
        HEALTH[u + "#" + c] = {"source": s, "category": c, "ok": False, "n": 0, "err": f"{type(e).__name__}"}
        return []


def fetch(prefs_news, topic=None, limit=10, all_categories=False):
    src, cats = prefs_news.get("sources", {}), prefs_news.get("categories", {})
    if topic:
        from ddgs import DDGS
        items = []
        for x in DDGS().news(topic, region="br-pt", max_results=limit):
            summ = clean(x.get("body") or "", x.get("title") or "")
            ts = 0
            try: ts = time.mktime(time.strptime(x["date"][:19], "%Y-%m-%dT%H:%M:%S"))
            except Exception: pass
            items.append({"id": hashlib.sha1((x.get("url") or "").encode()).hexdigest()[:12], "title": x.get("title"),
                          "source": x.get("source"), "category": "busca", "summary": summ,
                          "spoken": f"{x.get('title')}. {short(summ)}", "url": x.get("url"), "image": x.get("image"),
                          "ts": ts, "published": time.strftime("%d/%m %H:%M", time.localtime(ts)) if ts else ""})
        return items[:limit]
    feeds = [f for f in FEEDS if src.get(f[0], True) and (all_categories or cats.get(f[1], False))]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as ex:
        items = [i for lst in ex.map(_load_feed, feeds) for i in lst]
    items = dedupe(rank(items))
    return _spread(items, limit)


def health():
    ok = [h for h in HEALTH.values() if h["ok"]]
    return {"ok": len(ok), "total": len(HEALTH), "items": sorted(HEALTH.values(), key=lambda h: (h["ok"], h["source"]))}
