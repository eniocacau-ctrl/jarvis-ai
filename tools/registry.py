"""Camada única de capacidades. O modelo escolhe; o usuário nunca precisa saber os nomes."""
from memory import store
from config import prefs
from core.browser import browser
from tools import NeedConfirm, files, news, screen, system, web  # noqa


def _t(name, desc, props, req=()):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": list(req)}}}


S, N = {"type": "string"}, {"type": "number"}
SCHEMAS = [
    _t("find_files", "Busca arquivos/pastas no índice local (rápido). Tolera acentos. Resultados ordenados do mais recente.",
       {"query": {**S, "description": "palavras do nome"}, "folder": {**S, "description": "palavras do caminho"},
        "ext": S, "type": {"type": "string", "enum": ["file", "folder"]},
        "modified_within_days": N, "modified_before_days": N, "min_mb": N, "content": {**S, "description": "texto dentro de arquivos de texto"},
        "limit": N}),
    _t("list_folder", "Lista o conteúdo de uma pasta.", {"path": S}, ["path"]),
    _t("file_action", "Opera em arquivos: open, reveal, copy, move, rename (dest=novo nome), mkdir, write, trash.",
       {"action": {"type": "string", "enum": ["open", "reveal", "copy", "move", "rename", "mkdir", "write", "trash"]},
        "path": S, "dest": S, "content": S}, ["action", "path"]),
    _t("open_app_or_url", "Abre um aplicativo instalado (nome falado, ex.: 'vs code', 'chrome'), site (URL; abre no navegador do JARVIS) ou caminho. "
       "Se devolver 'ambiguous', escolha entre os candidatos pelo contexto e chame de novo com o nome exato.", {"target": S}, ["target"]),
    _t("find_app", "Lista aplicativos instalados cujo nome contém as palavras (use para pedidos vagos como 'editor', 'player').", {"query": S}),
    _t("browser", "Navegador do JARVIS. open (url ou termo de busca), goto, back, forward, reload, close, read (texto da página), click (texto do link/botão).",
       {"action": {"type": "string", "enum": ["open", "goto", "back", "forward", "reload", "close", "read", "click"]},
        "url": {**S, "description": "URL ou termo de busca"}, "text": {**S, "description": "texto do elemento a clicar"}, "tab": N}, ["action"]),
    _t("close_app", "Fecha um aplicativo pelo nome.", {"name": S}, ["name"]),
    _t("system_info", "overview (CPU/RAM/discos), processes (top RAM) ou space (maiores itens de uma pasta).",
       {"kind": {"type": "string", "enum": ["overview", "processes", "space"]}, "path": S}),
    _t("web", "Pesquisa na internet (query) ou lê uma página (url).", {"query": S, "url": S}),
    _t("news", "Busca notícias e MOSTRA um card (uma notícia por vez, com 'próxima'). Sem topic = principais do dia. "
       "O app lê só a primeira notícia em voz alta: não liste nem leia as outras.", {"topic": S, "limit": N}),
    _t("screen_capture", "Captura a tela (somente em memória, nunca em disco) do monitor pedido. Omita 'monitor' para usar o selecionado nas configurações. Normalmente use screen_analyze direto.",
       {"monitor": {**S, "description": "'1', '2'... ou 'all'"}, "all_monitors": {"type": "boolean"}}),
    _t("screen_analyze", "OLHA a tela: captura (se preciso) e analisa com o modelo de visão, devolvendo a interpretação em texto. Use para 'o que tem na tela', "
       "'leia isso', 'tem erro aqui?', 'que programa é esse?'. A pergunta guia a análise; monitor opcional ('1','2','all').",
       {"question": S, "monitor": S}, ["question"]),
    _t("news_control", "Controla o card de notícia aberto: next, previous, repeat (ouvir de novo), open (abrir a matéria no navegador), close, more (aprofundar a atual).",
       {"action": {"type": "string", "enum": ["next", "previous", "repeat", "open", "close", "more"]}}, ["action"]),
    _t("memory", "Guarda (remember) ou busca (recall) informações úteis sobre o usuário.",
       {"action": {"type": "string", "enum": ["remember", "recall"]}, "text": S}, ["action", "text"]),
]


def _news(a, approved, state):
    items = news.fetch(prefs.get()["news"], a.get("topic"), min(int(a.get("limit", 10)), 15))
    if not items:
        return {"error": "Não consegui obter notícias agora."}
    news.enrich(items[0])
    llm = [{k: i[k] for k in ("title", "source", "summary", "url", "published")} for i in items]
    return {"items": llm, "note": "A interface mostra o primeiro card e lê só ele. Responda com no máximo uma frase curta.",
            "_ui": {"type": "news_session", "items": items, "narrate": prefs.get()["news"]["narrate"]}}


def _news_control(a, approved, state):
    return {"ok": a["action"], "_ui": {"type": "news_nav", "action": a["action"]}}


def _browser(a, approved, state):
    out = browser.command(a["action"], a.get("tab"), a.get("url"), a.get("text"))
    out["_ui"] = {"type": "browser", "state": browser.state()}
    return out


_vc = {}


def _screen_gate():
    if not prefs.get()["privacy"]["screen"]:
        raise PermissionError("A visão de tela está desativada em Configurações › Privacidade.")


def _which(a):
    return "all" if a.get("all_monitors") else (a.get("monitor") or prefs.get()["screen"]["monitor"])


def _screen_capture(a, approved, state):
    _screen_gate()
    return {**screen.capture(_which(a)), "note": "Imagem só em memória; chame screen_analyze para interpretá-la."}


def _screen_analyze(a, approved, state):
    _screen_gate()
    from groq import Groq
    from config import settings
    if "c" not in _vc:
        _vc["c"] = Groq(api_key=settings.GROQ_API_KEY)
    ai = prefs.get()["ai"]
    return screen.analyze(a.get("question", ""), _vc["c"], ai["vision_model"], which=_which(a))


def _memory(a, approved, state):
    if not prefs.get()["privacy"]["memory"]:
        return {"error": "A memória está desativada nas configurações de privacidade."}
    if a["action"] == "remember":
        store.remember(a["text"]); return {"ok": "memorizado"}
    return {"memories": store.recall(a["text"])}


HANDLERS = {"find_files": files.find_files, "list_folder": files.list_folder, "file_action": files.file_action,
            "open_app_or_url": system.launch, "find_app": system.find_app, "close_app": system.close_app,
            "system_info": system.system_info, "web": web.web, "news": _news, "news_control": _news_control,
            "browser": _browser, "memory": _memory, "screen_capture": _screen_capture, "screen_analyze": _screen_analyze}

LABELS = {"find_files": "Procurando arquivos", "list_folder": "Lendo pasta", "file_action": "Operando arquivo",
          "open_app_or_url": "Abrindo", "find_app": "Procurando aplicativos", "browser": "Navegador",
          "news_control": "Controlando notícias", "screen_capture": "Capturando a tela", "screen_analyze": "Analisando a tela", "close_app": "Fechando aplicativo", "system_info": "Consultando o sistema",
          "web": "Pesquisando na web", "news": "Buscando notícias", "memory": "Acessando memória"}


def describe(name, args):
    d = args.get("query") or args.get("target") or args.get("path") or args.get("name") or args.get("topic") or args.get("action") or ""
    return f"{LABELS.get(name, name)}: {str(d)[:60]}".strip(": ")


def run(name, args, approved=False, state=None):
    h = HANDLERS.get(name)
    if not h:
        return {"error": "ferramenta desconhecida"}
    return h(args, approved, state if state is not None else {})
