import html, re, urllib.request

UA = {"User-Agent": "Mozilla/5.0 JARVIS/1.0"}

def _get(url, timeout=10):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def web(a, approved, state):
    if a.get("url"):
        raw = _get(a["url"]).decode("utf-8", "ignore")
        raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))
        return {"url": a["url"], "text": txt[:5000]}
    from ddgs import DDGS
    r = DDGS().text(a["query"], region="br-pt", max_results=6)
    return {"results": [{"title": x.get("title"), "url": x.get("href"), "snippet": x.get("body")} for x in r]}
