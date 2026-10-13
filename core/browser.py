"""Navegador dentro do JARVIS.

v1: cada aba é uma janela nativa WebView2 (via pywebview) controlada pelo backend — back/forward/reload,
leitura do texto da página e cliques por texto. Sem pywebview (shell Edge), cai para o navegador padrão.
O próximo passo (avaliar após validar o WebView2 na sua máquina) é embutir o controle WebView2 como painel
da própria janela do JARVIS; a interface deste módulo (open/command/state) não muda.
"""
import json, re, threading, webbrowser
from urllib.parse import quote_plus

SEARCH = "https://duckduckgo.com/?q="


def normalize(target):
    t = target.strip()
    if re.match(r"^https?://", t, re.I):
        return t
    if re.match(r"^[\w-]+(\.[\w-]+)+(/.*)?$", t) and " " not in t:
        return "https://" + t
    return SEARCH + quote_plus(t)


class Browser:
    def __init__(self):
        self.wv, self.tabs, self.seq, self.active, self.lock = None, {}, 0, None, threading.Lock()

    @property
    def native(self):
        return self.wv is not None

    def attach(self, webview_module):
        self.wv = webview_module

    # ---- abas ----
    def open(self, target):
        url = normalize(target)
        if not self.native:
            webbrowser.open(url)
            return {"ok": f"aberto no navegador padrão: {url}", "native": False}
        with self.lock:
            self.seq += 1
            tid = self.seq
            w = self.wv.create_window(f"JARVIS · aba {tid}", url, width=1100, height=760, background_color="#ffffff")
            self.tabs[tid] = w
            self.active = tid
            w.events.closed += lambda tid=tid: self._closed(tid)
        return {"ok": f"aba {tid} aberta: {url}", "tab": tid, "native": True}

    def _closed(self, tid):
        self.tabs.pop(tid, None)
        if self.active == tid:
            self.active = next(iter(self.tabs), None)

    def _w(self, tid):
        tid = tid or self.active
        return tid, self.tabs.get(tid)

    def command(self, action, tab=None, url=None, text=None):
        if action == "open":
            return self.open(url or "")
        if not self.native:
            return {"error": "O navegador embutido só funciona com JARVIS_SHELL=webview (usei o navegador padrão)."}
        tid, w = self._w(tab)
        if not w:
            return {"error": "Nenhuma aba aberta."}
        try:
            if action == "back":
                w.evaluate_js("history.back()")
            elif action == "forward":
                w.evaluate_js("history.forward()")
            elif action == "reload":
                w.evaluate_js("location.reload()")
            elif action == "goto":
                w.load_url(normalize(url or ""))
            elif action == "close":
                w.destroy()
            elif action == "focus":
                self.active = tid
            elif action == "read":
                return {"url": w.get_current_url(), "text": (w.evaluate_js("document.body.innerText") or "")[:5000]}
            elif action == "click":  # clica no link/botão visível cujo texto contém `text`
                js = ("(()=>{const t=%s.toLowerCase();const e=[...document.querySelectorAll('a,button,[role=button],input[type=submit]')]"
                      ".find(x=>(x.innerText||x.value||'').toLowerCase().includes(t));if(e){e.click();return true}return false})()"
                      % json.dumps(text or ""))
                return {"ok": "cliquei"} if w.evaluate_js(js) else {"error": "elemento não encontrado na página"}
            else:
                return {"error": "ação desconhecida"}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
        return {"ok": action, "tab": tid}

    def state(self):
        out = []
        for tid, w in list(self.tabs.items()):
            try:
                url = w.get_current_url()
            except Exception:
                url = ""
            out.append({"id": tid, "url": url, "active": tid == self.active})
        return {"native": self.native, "tabs": out}


browser = Browser()
