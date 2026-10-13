import asyncio, json, time
from groq import AsyncGroq
from config import settings
from config import prefs
from memory import store
from tools import registry, NeedConfirm

SYSTEM = """Você é J.A.R.V.I.S., agente pessoal de computador do usuário (Windows). Trate-o por "{title}".
Suas respostas aparecem na tela (markdown) e são FALADAS: abra sempre com 1-2 frases curtas e naturais, sem emojis.
Use markdown (listas, negrito, código) só quando ajudar de verdade (resultados, comparações, passos); a fala usa apenas o começo.
Aja em vez de perguntar: se o pedido for claro, use as ferramentas (quantas precisar, em sequência), observe cada resultado e decida o próximo passo; só então responda.
Se vários arquivos servirem, escolha o mais provável (geralmente o mais recente) e diga qual escolheu; pergunte só se realmente ambíguo.
Aplicativos: o usuário fala de forma natural ("vs code", "editor", "o navegador"). Use open_app_or_url com o que ele disse; se voltar 'ambiguous',
escolha pelo contexto da conversa e chame de novo com o nome exato; para pedidos vagos use find_app. Diga qual aplicativo abriu.
Sites e pesquisas: abra pela ferramenta browser/open_app_or_url (abre no navegador do JARVIS); use 'read' para ler a página quando precisar.
Tela: você consegue VER a tela do usuário (ele tem até dois monitores). Para "o que tem na tela", "leia isso", "tem erro aqui?", "o que é esse programa?" use screen_analyze
com uma pergunta específica (monitor 'all' para ambos, ou o número citado; sem número vale o monitor selecionado). Nunca olhe a tela sem necessidade. Diga de qual monitor veio a informação.
Ações destrutivas: chame a ferramenta normalmente; o sistema pede a confirmação ao usuário.
Notícias: nunca invente. A ferramenta news mostra UM card e o app lê só a primeira; depois responda no máximo com uma frase curta e não leia as demais.
Pedidos como "próxima", "repete", "abre essa matéria", "fecha" usam news_control. "Fale mais" sobre a notícia atual: leia a matéria (web, url) e resuma.
Nunca revele chaves de API, tokens, senhas, .env ou segredos do ambiente.
Use a memória (remember) quando o usuário disser algo útil para o futuro.
Pastas autorizadas: {roots}. Agora: {now}."""


class Agent:
    def __init__(self, emit):
        self.emit, self.history, self.task, self.fut = emit, [], None, None
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None

    # --- controle ---
    def start(self, text):
        self.cancel()
        self.task = asyncio.create_task(self._run(text))

    def cancel(self):
        if self.fut and not self.fut.done():
            self.fut.set_result(False)
        if self.task and not self.task.done():
            self.task.cancel()

    def resolve(self, ok):
        if self.fut and not self.fut.done():
            self.fut.set_result(bool(ok))

    async def _ask(self, text):
        self.fut = asyncio.get_running_loop().create_future()
        await self.emit({"type": "confirm", "text": text})
        return await self.fut

    # --- loop do agente ---
    async def _llm(self):
        p = prefs.get()
        sys_msg = SYSTEM.format(title=p["general"]["name"], roots="; ".join(map(str, settings.ROOTS)),
                                now=time.strftime("%A, %d/%m/%Y %H:%M"))
        ai = p["ai"]
        kw = dict(model=ai["model"], messages=[{"role": "system", "content": sys_msg}] + self.history,
                  tools=registry.SCHEMAS, tool_choice="auto", temperature=float(ai["temperature"]),
                  max_tokens=int(ai["max_tokens"]))
        if ai["reasoning"] and ai["reasoning"] != "off":
            kw["reasoning_effort"] = ai["reasoning"]
        return await self.client.chat.completions.create(**kw)

    async def _run(self, text):
        start = len(self.history)
        state = {}
        try:
            if not self.client:
                await self.emit({"type": "say", "text": "Falta configurar a chave do Groq no arquivo .env."})
                return
            self.history.append({"role": "user", "content": text})
            hist = prefs.get()["privacy"]["history"]
            if hist:
                store.add_chat("user", text)
            await self.emit({"type": "state", "v": "thinking"})
            for _ in range(max(1, int(prefs.get()["ai"]["max_steps"]))):
                m = (await self._llm()).choices[0].message
                entry = {"role": "assistant", "content": m.content or ""}
                if m.tool_calls:
                    entry["tool_calls"] = [{"id": t.id, "type": "function", "function": {
                        "name": t.function.name, "arguments": t.function.arguments}} for t in m.tool_calls]
                self.history.append(entry)
                if m.content:
                    await self.emit({"type": "say", "text": m.content})
                    if hist:
                        store.add_chat("assistant", m.content)
                if not m.tool_calls:
                    break
                await self.emit({"type": "state", "v": "executing"})
                for t in m.tool_calls:
                    self.history.append({"role": "tool", "tool_call_id": t.id, "content": (await self._call(t, state))[:6000]})
                await self.emit({"type": "state", "v": "thinking"})
            else:
                await self.emit({"type": "say", "text": "Atingi o limite de passos antes de concluir. Posso continuar se você quiser."})
            self._trim()
            await self.emit({"type": "state", "v": "idle"})
        except asyncio.CancelledError:
            del self.history[start:]
            await self.emit({"type": "state", "v": "idle"})
        except Exception as e:
            del self.history[start:]
            await self.emit({"type": "state", "v": "error"})
            await self.emit({"type": "say", "text": f"Tive um problema: {str(e)[:120]}"})

    async def _call(self, t, state):
        name = t.function.name
        try:
            args = json.loads(t.function.arguments or "{}")
        except Exception:
            return json.dumps({"error": "argumentos inválidos"})
        label = registry.describe(name, args)
        phase = {"screen_capture": "capturing", "screen_analyze": "analyzing"}.get(name)
        if phase:
            await self.emit({"type": "state", "v": phase})
            await self.emit({"type": "screen", "status": phase})
        await self.emit({"type": "step", "id": t.id, "text": label, "status": "running"})
        approved = False
        for _ in range(2):
            try:
                out = await asyncio.to_thread(registry.run, name, args, approved, state)
                break
            except NeedConfirm as e:
                if not await self._ask(f"{e} Posso prosseguir?"):
                    await self.emit({"type": "step", "id": t.id, "text": label, "status": "error"})
                    return json.dumps({"error": "O usuário negou a ação."})
                approved, state["bulk_ok"] = True, True
            except Exception as e:
                await self.emit({"type": "step", "id": t.id, "text": label, "status": "error"})
                return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
        else:
            return json.dumps({"error": "não executado"})
        bad = isinstance(out, dict) and ("error" in out)
        if phase:
            await self.emit({"type": "screen", "status": "error" if bad else "ready"})
        await self.emit({"type": "step", "id": t.id, "text": label, "status": "error" if bad else "done"})
        if isinstance(out, dict) and "_ui" in out:
            await self.emit(out.pop("_ui"))
        return json.dumps(out, ensure_ascii=False, default=str)

    def _trim(self, keep=6):
        idx = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        if len(idx) > keep:
            self.history = self.history[idx[-keep]:]
