"""`python main.py`: sobe o backend local e abre a janela do JARVIS.

JARVIS_SHELL=edge     (padrão) Edge em modo app — reconhecimento de voz do navegador funciona.
JARVIS_SHELL=webview  janela nativa WebView2 (pywebview) + navegador embutido por abas nativas.
                      Atenção: o WebView2 pode não oferecer SpeechRecognition; se o microfone falhar, use edge ou STT local.
"""
import os, shutil, socket, subprocess, sys, threading, time, webbrowser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uvicorn
from config import settings


def edge():
    for c in (shutil.which("msedge"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", shutil.which("chrome")):
        if c and os.path.exists(c):
            return c


def wait_server():
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", settings.PORT), 0.2).close(); return
        except OSError:
            time.sleep(0.1)


def run_webview(url):
    import webview
    from core.browser import browser
    browser.attach(webview)
    webview.create_window("J.A.R.V.I.S.", url, width=1320, height=840, min_size=(980, 640), background_color="#05090f")
    webview.start(private_mode=False, storage_path=str(settings.DATA / "webview"))


def run_edge(url):
    exe = edge()
    if exe:  # perfil próprio: lembra a permissão do microfone; flag permite falar sem clique prévio
        subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={settings.DATA / 'profile'}", "--window-size=1280,820",
                          "--autoplay-policy=no-user-gesture-required"]).wait()
    else:
        webbrowser.open(url)
        while True:
            time.sleep(3600)


def main():
    from tools import screen
    screen._dpi_aware()
    srv = uvicorn.Server(uvicorn.Config("interface.server:app", host="127.0.0.1", port=settings.PORT, log_level="warning"))
    threading.Thread(target=srv.run, daemon=True).start()
    wait_server()
    url = f"http://127.0.0.1:{settings.PORT}"
    if os.getenv("JARVIS_SHELL", "edge").lower() == "webview":
        try:
            return run_webview(url)
        except ImportError:
            print("pywebview não instalado (pip install pywebview); usando Edge.")
    run_edge(url)


if __name__ == "__main__":
    main()
