"""Preferências do usuário (persistentes no SQLite, tabela kv). Uma única fonte de verdade para backend e UI."""
import copy
from config import settings
from memory import store

DEFAULTS = {
    "_v": 4,
    "general": {"name": settings.TITLE, "language": "pt-BR", "autostart": False, "theme": "cyan",
                "animations": True, "notifications": True},
    "voice": {"voice": "", "lang": "pt-BR", "rate": 1.05, "pitch": 1.0, "volume": 1.0, "autospeak": True,
              "recognition": "auto",          # auto | local (faster-whisper) | browser (Web Speech); stt_model: tiny/base/small/medium
              "stt_model": "small",
              "auto_send": True, "send_delay": 1.6, "wake_word": False},
    "ai": {"model": settings.GROQ_MODEL, "temperature": 0.3, "max_tokens": 1500,
           "reasoning": settings.REASONING or "low", "max_steps": 10,
           "vision_model": "qwen/qwen3.8-27b"},
    "privacy": {"mic": True, "history": True, "memory": True, "indexing": True, "screen": True},
    "screen": {"monitor": "1"},          # "1" | "2" | ... | "all"
    "news": {"on_start": settings.NEWS_ON_START, "narrate": True,
             "sources": {n: True for n in ("G1", "GE", "BBC News Brasil", "CNN Brasil", "Folha", "Agência Brasil", "UOL", "IGN Brasil", "Jovem Nerd",
                                           "Canaltech", "Olhar Digital", "DW Brasil", "Poder360", "Metrópoles", "R7", "Exame",
                                           "InfoMoney", "Veja", "O Globo", "ESPN Brasil", "Trivela", "Tecnoblog", "TecMundo",
                                           "Jornal da USP", "Omelete", "Nintendo Blast", "Agência Câmara")},
             "categories": {c: True for c in ("brasil", "mundo", "política", "tecnologia", "ciência", "esportes", "futebol",
                                              "economia", "entretenimento", "games", "cultura")}},
    "ui": {"glow": 1.0, "density": "comfortable", "font_size": 14},
}


def _merge(base, patch):
    for k, v in patch.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _merge(base[k], v)
        elif k in base and not isinstance(base[k], dict):   # ignora chaves desconhecidas
            base[k] = v
    return base


VERSION = 4


def _migrate(st):
    """Preferências salvas por versões anteriores: reconhecimento passa a 'auto'; fontes/categorias de notícia novas valem."""
    if st.get("_v", 2) < 3:
        st.get("voice", {}).pop("recognition", None)
        st.get("news", {}).pop("sources", None)
        st.get("news", {}).pop("categories", None)
    if st.get("_v", 2) < 4:                      # modelos de visão antigos (Llama 4) foram aposentados na Groq
        st.get("ai", {}).pop("vision_model", None)
    return st


def get():
    return _merge(copy.deepcopy(DEFAULTS), _migrate(store.kv_get("prefs", {}) or {}))


def update(patch):
    cur = _merge(get(), patch)
    cur["_v"] = VERSION
    store.kv_set("prefs", cur)
    return cur
