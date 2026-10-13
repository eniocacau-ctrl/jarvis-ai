# J.A.R.V.I.S. (Windows)

Agente pessoal de computador: Python + FastAPI + Groq, interface HUD local. Sem Docker/Electron/nuvem.

## Instalar e rodar
```
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env     (coloque sua GROQ_API_KEY)
python main.py
```
**Shell da janela** (`JARVIS_SHELL`):
- `edge` (padrão): Edge em modo app. O reconhecimento de voz do navegador funciona.
- `webview`: janela nativa WebView2 (`pip install pywebview`) + abas de navegador nativas controladas pelo JARVIS.
  O WebView2 pode não oferecer SpeechRecognition: se o microfone falhar, volte para `edge` ou use STT local (roadmap).

## Estrutura
```
main.py                 sobe backend e abre a janela
config/settings.py      .env, pastas autorizadas   |  config/prefs.py  preferências persistentes (SQLite kv)
core/agent.py           loop LLM -> ferramenta -> observação (passos, confirmações, limites vindos das prefs)
core/browser.py         navegador (abas nativas WebView2 via pywebview; fallback navegador padrão)
tools/registry.py       ÚNICA camada de capacidades (o modelo escolhe, o backend valida/executa)
tools/apps.py           descoberta + resolução de apps instalados (Start Menu/UWP/App Paths, sem lista fixa)
tools/news.py           RSS -> limpeza -> ranking (interesse pessoal x importância geral) -> cards
tools/files.py|system.py|web.py
memory/store.py         SQLite: memória, índice de arquivos, kv (prefs), chat, news_events
interface/server.py     REST (abas) + WebSocket (tempo real)   |  interface/web/{index.html,app.css,app.js}
```

## Protocolo WebSocket (servidor -> UI)
`state` · `say` · `step{id,text,status}` · `news_session{items}` · `news_nav{action}` · `browser{state}` · `confirm` · `stats`.
UI -> servidor: `hello` · `user{text}` · `confirm{ok}` · `cancel`.

## Voz (diagnóstico e STT)
Fluxo: microfone -> STT -> agente -> resposta -> TTS (voz do Windows via Web Speech). Em Configurações › Voz há **Diagnóstico de voz**
(permissão, microfones, SpeechRecognition, STT local, vozes pt-BR). Reconhecimento (`auto`): usa o **STT local** (faster-whisper, offline)
se instalado; senão o do navegador. O WebView2 normalmente NÃO tem SpeechRecognition: nesse caso instale `pip install faster-whisper`
(o navegador só capta o áudio; a transcrição roda no backend; modelo `small` baixa no 1º uso). A UI só mostra "OUVINDO" quando o áudio realmente começou.

## Tela (👁 SCREEN)
`tools/screen.py`: CAPTURE (Pillow/mss, monitores detectados via Windows API) -> imagem só em RAM -> modelo de visão (Groq, `ai.vision_model` = `qwen/qwen3.8-27b`, máx. 3 imagens) ->
interpretação em texto -> agente. Ferramentas `screen_capture` e `screen_analyze`; o monitor padrão (1, 2 ou ambos) fica em Configurações › Tela.
Só captura sob demanda; nada vai a disco; a imagem é descartada após a análise (ou 60 s). Desligável em Privacidade.

## Notícias
UM card por vez: imagem, título, fonte, data, resumo limpo (créditos/menus/texto truncado removidos), Ouvir, Fale mais, Abrir, Próxima, Fechar.
Cada interação vira linha em `news_events` (shown/next/skip/open/more/repeat/close). O perfil de interesses futuro
entra em `tools/news.py` (`_interest`, `EVENT_WEIGHT`, `rank(w_interest=...)`) sem mudar mais nada.

## Segurança
Operações só em pastas autorizadas (`JARVIS_ROOTS`). Lixeira, fechar apps, substituir arquivos, mover/copiar >10 itens e acesso
fora das pastas pedem confirmação (botão ou voz). O LLM nunca executa nada: só escolhe ferramentas; o backend valida. `.env` nunca é indexado.
A UI (aba FILES) só abre/mostra arquivos; ações destrutivas só passam pelo agente, com confirmação.

## Roadmap
1. (feito) núcleo, agente, arquivos, web, notícias, memória
2. (feito nesta versão) abas, configurações persistentes, voz configurável, transcrição com revisão, card de notícia, resolução de apps, navegador por abas nativas
3. Embutir o WebView2 como painel da própria janela (pythonnet) · STT local (faster-whisper) · perfil de interesses de notícias
4. Controle do Windows (teclado/mouse/janelas) · visão de tela · empacotamento .exe
