"""STT local (faster-whisper). O navegador/WebView2 só captura áudio; a transcrição roda aqui, no PC, sem nuvem."""
import importlib.util, threading

_models, _lock = {}, threading.Lock()


def available():
    return importlib.util.find_spec("faster_whisper") is not None


def _model(name):
    if name not in _models:
        from faster_whisper import WhisperModel
        _models[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _models[name]


def loaded(name):
    return name in _models


def transcribe(pcm16, lang="pt", model="small"):
    """pcm16: bytes int16 mono 16 kHz."""
    import numpy as np
    audio = np.frombuffer(pcm16, np.int16).astype(np.float32) / 32768.0
    with _lock:
        segs, _ = _model(model).transcribe(audio, language=lang, vad_filter=True, beam_size=1, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segs).strip()
