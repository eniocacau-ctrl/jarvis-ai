/* J.A.R.V.I.S. — interface. Módulos: util · prefs · TTS · STT · Dock (voz/texto) · News · Browser · Files · System · Settings · WS */
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const api=(u,o)=>fetch(u,o).then(r=>r.ok?r.json():Promise.reject(r));
const post=(u,b,m='POST')=>api(u,{method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
const norm=s=>s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
const base=p=>p.split(/[\\/]/).filter(Boolean).pop()||p;

/* ---------- markdown seguro (sem libs) ---------- */
function md(src){const code=[];
 const t=esc(src).replace(/```[\w-]*\n?([\s\S]*?)```/g,(_,c)=>{code.push(c.replace(/\n$/,''));return `\u0000${code.length-1}\u0000`});
 const inl=s=>s.replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
  .replace(/(^|[\s(])\*([^*\s][^*]*)\*/g,'$1<em>$2</em>').replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,'<a href="$2" data-ext>$1</a>')
  .replace(/(^|\s)(https?:\/\/[^\s<)]+)/g,'$1<a href="$2" data-ext>$2</a>');
 let out='',list=null;const close=()=>{if(list){out+=`</${list}>`;list=null}};
 for(const ln of t.split('\n')){let m;
  if(/^\u0000\d+\u0000$/.test(ln.trim())){close();out+=ln.trim()}
  else if(m=ln.match(/^\s*[-*•]\s+(.*)/)){if(list!=='ul'){close();out+='<ul>';list='ul'}out+=`<li>${inl(m[1])}</li>`}
  else if(m=ln.match(/^\s*\d+[.)]\s+(.*)/)){if(list!=='ol'){close();out+='<ol>';list='ol'}out+=`<li>${inl(m[1])}</li>`}
  else if(m=ln.match(/^#{1,4}\s+(.*)/)){close();out+=`<h4>${inl(m[1])}</h4>`}
  else if(!ln.trim())close();else{close();out+=`<p>${inl(ln)}</p>`}}
 close();return out.replace(/\u0000(\d+)\u0000/g,(_,i)=>`<pre><code>${code[+i]}</code></pre>`)}
function speakable(s){const t=s.replace(/```[\s\S]*?```/g,' ').replace(/`[^`]*`/g,' ').replace(/\[([^\]]+)\]\([^)]*\)/g,'$1').replace(/https?:\/\/\S+/g,'')
 .replace(/[*_#>|~]/g,'').replace(/^\s*[-•]\s+/gm,'').replace(/\s+/g,' ').trim();let o='';
 for(const x of t.match(/[^.!?]+[.!?]+|[^.!?]+$/g)||[t]){if((o+x).length>260&&o)break;o+=x}return o.trim()}

/* ---------- estado global e preferências (persistentes no backend) ---------- */
const S={srv:'idle',speaking:false,hearing:false,proc:false,pend:false,last:''};let P=null,ws=null,Caps={local:false};
const LB={idle:'PARADO',listening:'OUVINDO',processing:'PROCESSANDO',thinking:'PENSANDO',executing:'EXECUTANDO',capturing:'CAPTURANDO',analyzing:'ANALISANDO',speaking:'FALANDO',error:'ERRO'};
function render(){const s=S.speaking?'speaking':S.proc?'processing':S.hearing?'listening':S.srv;document.body.dataset.s=s;$('#lbl').textContent=LB[s]||s.toUpperCase()}
function applyPrefs(){const r=document.documentElement;r.dataset.theme=P.general.theme;r.classList.toggle('noanim',!P.general.animations);
 r.classList.toggle('compact',P.ui.density==='compact');r.style.setProperty('--glow',P.ui.glow);r.style.setProperty('--fs',P.ui.font_size+'px');Always.sync()}
let saveT,pend={};
function setPref(path,val){const ks=path.split('.');let o=P,p=pend;for(const k of ks.slice(0,-1)){o=o[k];p=(p[k]??={})}
 o[ks.at(-1)]=val;p[ks.at(-1)]=val;clearTimeout(saveT);saveT=setTimeout(()=>{const b=pend;pend={};post('/api/prefs',{patch:b},'PUT').catch(()=>{})},300);applyPrefs()}

/* ---------- conversa ---------- */
function addMsg(kind,html){const d=document.createElement('div');d.className='msg '+kind;d.innerHTML=html;const st=$('#stream');st.append(d);
 while(st.children.length>80)st.firstChild.remove();st.scrollTop=st.scrollHeight;return d}
const note=(t,warn)=>addMsg('note'+(warn?' warn':''),esc(t));
function typing(on){let e=$('.typing');if(on&&!e){e=document.createElement('div');e.className='typing';e.textContent='···';$('#stream').append(e);$('#stream').scrollTop=1e9}else if(!on&&e)e.remove()}
$('#stream').addEventListener('click',e=>{const a=e.target.closest('a[data-ext]');if(a){e.preventDefault();openUrl(a.href)}});
function openUrl(u){Browser.cmd('open',{url:u})}
function send(text,silent){if(silent)note(silent);else addMsg('me',esc(text));ws.send(JSON.stringify({type:'user',text}));typing(true);
 $('#steplist').prepend(Object.assign(document.createElement('div'),{className:'step sep',textContent:new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}))}
function interrupt(){TTS.stop();Dock.cancel();ws.send(JSON.stringify({type:'cancel'}))}
function answer(ok){S.pend=false;$('#cf').style.display='none';TTS.stop();ws.send(JSON.stringify({type:'confirm',ok}))}
$('#y').onclick=()=>answer(true);$('#n').onclick=()=>answer(false);
function notify(t){if(!P.general.notifications||!document.hidden||!window.Notification)return;
 if(Notification.permission==='granted')new Notification('J.A.R.V.I.S.',{body:t});else if(Notification.permission==='default')Notification.requestPermission()}

/* ---------- voz de saída (TTS) ---------- */
const TTS={q:[],paused:false,gen:0,busy:false,
 voices:()=>speechSynthesis.getVoices(),
 pick(){const all=this.voices();let v=all.find(x=>x.name===P?.voice.voice);if(v)return v;
  const pt=all.filter(x=>/^pt[-_]BR/i.test(x.lang));return pt.find(x=>/natural|online/i.test(x.name))||pt[0]||all.find(x=>/^pt/i.test(x.lang))||null},
 say(text,{flush=false}={}){if(!text)return;if(flush)this.stop();(text.match(/[^.!?\n]+[.!?]*/g)||[]).forEach(s=>s.trim()&&this.q.push(s.trim()));if(!this.busy)this.next()},
 next(){const s=this.q.shift();if(!s){this.busy=false;S.speaking=false;render();return}this.busy=true;S.speaking=true;render();const my=this.gen;
  if(!this.voices().length&&(this.tries=(this.tries||0)+1)<8){this.q.unshift(s);setTimeout(()=>my===this.gen&&this.next(),250);return}   // vozes carregam de forma assíncrona
  this.tries=0;const u=new SpeechSynthesisUtterance(s),v=this.pick();u.lang=P.voice.lang;if(v)u.voice=v;
  u.rate=+P.voice.rate;u.pitch=+P.voice.pitch;u.volume=+P.voice.volume;u.onend=()=>{if(my===this.gen)this.next()};u.onerror=e=>{if(!['interrupted','canceled'].includes(e.error)&&!this.warned){this.warned=1;note('Falha ao falar ('+e.error+'). Teste a voz em Configurações › Voz.',1)}if(my===this.gen)this.next()};speechSynthesis.speak(u)},
 pause(){if(this.paused){speechSynthesis.resume();this.paused=false}else if(this.busy){speechSynthesis.pause();this.paused=true}$('#tpause').textContent=this.paused?'▶':'⏸';render()},
 stop(){this.gen++;this.q=[];speechSynthesis.cancel();this.paused=false;this.busy=false;S.speaking=false;$('#tpause').textContent='⏸';render()},
 test(){this.say(`Olá, ${P.general.name}. Esta é a minha voz atual. Posso trocá-la quando quiser.`,{flush:true})}};
speechSynthesis.onvoiceschanged=()=>Settings.open==='voice'&&Settings.render();
$('#trepeat').onclick=()=>S.last?TTS.say(S.last,{flush:true}):note('Ainda não há resposta para repetir.');$('#tpause').onclick=()=>TTS.pause();$('#tstop').onclick=()=>TTS.stop();

/* ---------- voz de entrada (STT) — provedores intercambiáveis ----------
   Contrato: new Provider(handlers).start()/stop()/cancel(); handlers: onStart,onInterim(t),onSpeechEnd,onFinal(t),onError(code),onEnd.
   Para STT local: registre STT.providers.local (capta áudio, envia por WebSocket ao faster-whisper e emite os mesmos eventos). */
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
class BrowserSTT{static supported=!!SR;
 constructor(h,continuous=false){this.h=h;this.c=continuous}
 start(){const r=this.r=new SR(),h=this.h;r.lang=P.voice.lang;r.interimResults=!this.c;r.continuous=this.c;r.maxAlternatives=1;
  r.onstart=()=>h.onPending?.();r.onaudiostart=()=>h.onStart?.();r.onspeechend=()=>h.onSpeechEnd?.();r.onerror=e=>h.onError?.(e.error);r.onend=()=>h.onEnd?.();
  r.onresult=e=>{let it='',fin='';for(let i=e.resultIndex;i<e.results.length;i++){const x=e.results[i];(x.isFinal?(fin+=x[0].transcript):(it+=x[0].transcript))}
   if(it)h.onInterim?.(it.trim());if(fin)h.onFinal?.(fin.trim())};
  try{r.start()}catch(e){h.onError?.('start-failed')}}
 stop(){try{this.r.stop()}catch(e){}}cancel(){if(this.r){this.r.onend=null;this.r.onresult=null;try{this.r.abort()}catch(e){}}}}
const WORKLET="class P extends AudioWorkletProcessor{process(i){const c=i[0][0];if(c)this.port.postMessage(c.slice(0));return true}}registerProcessor('pcm',P)";
const toI16=(f,rate)=>{const r=rate/16000,n=Math.floor(f.length/r),o=new Int16Array(n);for(let i=0;i<n;i++){let a=0,c=0;for(let j=Math.floor(i*r);j<Math.floor((i+1)*r)&&j<f.length;j++){a+=f[j];c++}o[i]=Math.max(-1,Math.min(1,a/(c||1)))*32767}return o};
/* STT local: o navegador só captura o microfone (funciona em Edge e WebView2); a transcrição roda no backend (faster-whisper). */
class LocalSTT{static supported=!!(navigator.mediaDevices?.getUserMedia&&window.AudioWorklet);
 constructor(h){this.h=h;this.dead=false;this.ended=false}
 async start(){const h=this.h;let stream;
  try{stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,channelCount:1}})}catch(e){return h.onError?.(e.name==='NotFoundError'?'audio-capture':'not-allowed')}
  if(this.dead){stream.getTracks().forEach(t=>t.stop());return}this.stream=stream;
  const ws=this.ws=new WebSocket(`ws://${location.host}/ws/stt`);ws.binaryType='arraybuffer';
  try{await new Promise((ok,no)=>{ws.onopen=ok;ws.onerror=no})}catch(e){this.cleanup();return h.onError?.('stt-failed')}
  ws.onerror=()=>{if(!this.dead){this.cleanup();h.onError?.('stt-failed')}};ws.onclose=()=>{if(!this.dead&&!this.ended){this.cleanup();h.onError?.('stt-failed')}};
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.type==='interim'&&!this.dead)h.onInterim?.(m.text);else if(m.type==='loading')h.onLoading?.();
   else if(m.type==='final'){this.cleanup();m.text?h.onFinal?.(m.text):h.onError?.('no-speech')}else if(m.type==='error'){this.cleanup();h.onError?.(m.code)}};
  try{const ctx=this.ctx=new AudioContext({sampleRate:16000});await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET],{type:'text/javascript'})));
   if(this.dead)return;const node=new AudioWorkletNode(ctx,'pcm');ctx.createMediaStreamSource(stream).connect(node);
   const rate=ctx.sampleRate;let pend=[],pn=0,floor=0,total=0,speech=false,quiet=0;
   node.port.onmessage=e=>{if(this.dead||this.ended)return;const f=e.data;let sum=0;for(let i=0;i<f.length;i++)sum+=f[i]*f[i];const rms=Math.sqrt(sum/f.length),dur=f.length/rate;total+=dur;
    document.documentElement.style.setProperty('--lvl',Math.min(1,rms*8).toFixed(2));if(total<.4)floor=Math.max(floor,rms);
    const th=Math.max(.012,floor*2.5);if(rms>th){speech=true;quiet=0}else if(speech)quiet+=dur;
    const q=toI16(f,rate);pend.push(q);pn+=q.length;if(pn>=2048){this.send(pend);pend=[];pn=0}
    if(speech&&quiet>1.1||total>30)this.finish(pend);else if(!speech&&total>7){this.cleanup();h.onError?.('no-speech')}};
   h.onStart?.()}catch(e){this.cleanup();h.onError?.('start-failed')}}
 send(ch){const n=ch.reduce((a,c)=>a+c.length,0),o=new Int16Array(n);let k=0;for(const c of ch){o.set(c,k);k+=c.length}if(this.ws?.readyState===1)this.ws.send(o.buffer)}
 finish(pend){if(this.ended||this.dead)return;this.ended=true;this.send(pend);this.mic();this.h.onSpeechEnd?.();this.ws?.send(JSON.stringify({type:'end'}))}
 mic(){this.stream?.getTracks().forEach(t=>t.stop());this.ctx?.close().catch(()=>{});document.documentElement.style.setProperty('--lvl',0)}
 cleanup(){this.dead=true;this.mic();try{this.ws?.close()}catch(e){}}
 stop(){this.ended?0:this.finish([])}cancel(){this.cleanup()}}
const STT={providers:{browser:BrowserSTT,local:LocalSTT},get:()=>STT.pick()||BrowserSTT,
 pick(force){const r=P.voice.recognition;if(force||r==='local'||(r==='auto'&&Caps.local))return LocalSTT.supported&&Caps.local?LocalSTT:null;return BrowserSTT.supported?BrowserSTT:null}};
const ERR={'no-speech':'Não ouvi nada. Tente de novo.','audio-capture':'Nenhum microfone encontrado.','not-allowed':'Permissão do microfone negada.',
 'service-not-allowed':'O reconhecimento de voz está bloqueado neste ambiente.','network':'Sem acesso ao serviço de voz do navegador.','language-not-supported':'Idioma de reconhecimento não suportado.','start-failed':'Não consegui iniciar o microfone.','start-timeout':'O microfone não iniciou. Verifique permissão/dispositivo.','stt-missing':'STT local não instalado (pip install faster-whisper).','stt-failed':'Falha no STT local.'};
const ERR_HINT={network:1,'service-not-allowed':1};

/* ---------- dock: ouvir → mostrar texto ao vivo → editar → enviar ---------- */
const Dock={mode:'idle',stt:null,timer:null,wd:null,final:'',forceLocal:false,
 set(mode,msg){this.mode=mode;const m={idle:'PRONTO',starting:'INICIANDO MICROFONE…',listening:'OUVINDO…',processing:msg||'PROCESSANDO…',review:P.voice.auto_send?'REVISE — ENVIO AUTOMÁTICO':'REVISE E ENVIE',error:msg||'ERRO'}[mode];
  $('#dst').textContent=m;$('#t').classList.toggle('live',mode==='listening'||mode==='processing');S.hearing=mode==='listening';S.proc=mode==='processing'||mode==='starting';
  $('#cancel').hidden=!['starting','listening','processing','review'].includes(mode);$('#retry').hidden=!['error','review'].includes(mode);$('#mic').classList.toggle('on',mode==='listening');render()},
 listen(){if(Always.on)return note('Modo "sempre ouvindo" ativo: diga "JARVIS, …".');if(!P.privacy.mic)return note('Microfone desativado em Configurações › Privacidade.',1);
  const Impl=STT.pick(this.forceLocal);if(!Impl){note(Caps.local?'Este ambiente não permite capturar áudio.':'Sem reconhecimento de voz neste ambiente: o WebView2 não oferece o do navegador. Instale o STT local (pip install faster-whisper) e reinicie, ou use JARVIS_SHELL=edge.',1);return this.set('error','RECONHECIMENTO INDISPONÍVEL')}
  if(S.srv!=='idle'||TTS.busy)interrupt();this.cancel(true);this.final='';$('#t').value='';this.set('starting');
  const d=this;this.wd=setTimeout(()=>d.mode==='starting'&&d.fail('start-timeout'),9000);
  this.stt=new Impl({onStart:()=>{clearTimeout(d.wd);d.set('listening')},onInterim:t=>{$('#t').value=t},onLoading:()=>d.set('processing','CARREGANDO MODELO DE VOZ…'),
   onSpeechEnd:()=>d.mode==='listening'&&d.set('processing'),onFinal:t=>d.gotFinal(t),onError:c=>d.fail(c),onEnd:()=>{if(d.mode==='listening'||d.mode==='processing')d.fail('no-speech')}});this.stt.start()},
 gotFinal(t){clearTimeout(this.wd);this.final=t;$('#t').value=t;if(S.pend){const n=norm(t);if(/\b(sim|pode|confirmo|autorizo|claro|vai)\b/.test(n))return this.reset(),answer(true);
   if(/\b(nao|negativo|cancela|para)\b/.test(n))return this.reset(),answer(false)}
  this.set('review');if(P.voice.auto_send&&t)this.countdown()},
 fail(code){if(code==='aborted')return;clearTimeout(this.wd);this.cancelTimer();this.stt?.cancel();this.stt=null;
  if(ERR_HINT[code]&&Caps.local&&!this.forceLocal){this.forceLocal=true;note('A voz do navegador não está disponível aqui; usando o STT local.');return this.listen()}
  this.set('error',(ERR[code]||'ERRO: '+code).toUpperCase());if(ERR_HINT[code])note('O reconhecimento do navegador não funciona neste shell. Instale o STT local (pip install faster-whisper) ou use JARVIS_SHELL=edge.',1)},
 countdown(){this.cancelTimer();const cd=$('#cd');cd.style.setProperty('--d',P.voice.send_delay+'s');cd.className='';void cd.offsetWidth;cd.className='run';
  this.timer=setTimeout(()=>this.submit(),P.voice.send_delay*1000)},
 cancelTimer(){clearTimeout(this.timer);this.timer=null;$('#cd').className=''},
 cancel(silent){clearTimeout(this.wd);this.cancelTimer();if(this.stt){this.stt.cancel();this.stt=null}if(!silent&&this.mode!=='idle')$('#t').value='';if(this.mode!=='idle')this.set('idle')},
 reset(){this.cancel();$('#t').value=''},
 retry(){this.listen()},
 submit(){this.cancelTimer();const v=$('#t').value.trim();if(!v)return;this.stt?.cancel();this.stt=null;$('#t').value='';this.set('idle');
  if(S.pend)answer(/^s/i.test(norm(v)));else send(v)}};
$('#t').addEventListener('input',()=>{if(Dock.timer){Dock.cancelTimer();Dock.set('review')}});
$('#t').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();Dock.submit()}});
$('#send').onclick=()=>Dock.submit();$('#cancel').onclick=()=>Dock.reset();$('#retry').onclick=()=>Dock.retry();
$('#mic').onclick=()=>Dock.mode==='listening'?Dock.reset():Dock.listen();
$('#orb').onclick=()=>(S.speaking||S.srv!=='idle')?interrupt():Dock.mode==='listening'?Dock.reset():Dock.listen();
addEventListener('keydown',e=>{if(e.key==='Escape')interrupt();
 if(e.code==='Space'&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)&&$('#v-jarvis').classList.contains('on')){e.preventDefault();Dock.listen()}});

/* ---------- "sempre ouvindo" (wake word, opt-in) ---------- */
const WAKE=/\b(j[aá]r?v[ií][sz]e?|jarbas)\b[\s,.:!-]*/i;
const Always={on:false,stt:null,follow:0,
 sync(){const want=P.voice.wake_word&&P.privacy.mic&&BrowserSTT.supported&&P.voice.recognition!=='local';if(want&&!this.on){this.on=true;this.loop()}else if(!want&&this.on){this.on=false;this.stt?.cancel();this.stt=null;$('#dact').textContent=''}},
 loop(){if(!this.on)return;$('#dact').textContent='ESCUTA ATIVA · "JARVIS, …"';const a=this;
  this.stt=new BrowserSTT({onFinal:t=>a.heard(t),onEnd:()=>a.on&&setTimeout(()=>a.loop(),300),onError:()=>{}},true);this.stt.start()},
 heard(t){if(!t)return;const n=norm(t);if(S.pend){if(/\b(sim|pode|confirmo|autorizo|claro|vai)\b/.test(n))return answer(true);if(/\b(nao|negativo|cancela|para)\b/.test(n))return answer(false)}
  const m=t.match(WAKE);if(S.speaking){if(!m)return;TTS.stop()}if(!m&&Date.now()>this.follow)return;
  const cmd=m?t.slice(m.index+m[0].length).trim():t;if(!cmd){TTS.say(`Pois não, ${P.general.name}.`);this.follow=Date.now()+8000;return}send(cmd)}};

/* ---------- notícia: card flutuante e arrastável (componente independente, nunca vira mensagem no chat) ---------- */
const ev=(id,action)=>post('/api/news/event',{id,action}).catch(()=>{});
const News={items:[],i:0,t0:0,st:JSON.parse(localStorage.getItem('jarvis.nc')||'{}'),
 cur(){return this.items[this.i]},
 start(items,narrate=true,intro=false){this.items=items;this.i=0;this.show(narrate,intro)},
 show(speak=true,intro=false){const n=this.cur();if(!n)return;this.t0=Date.now();this.openCard();this.draw();ev(n.id,'shown');
  if(speak&&P.voice.autospeak)TTS.say((intro?`${P.general.name}, esta é a principal notícia agora. `:'')+n.spoken,{flush:true});
  if(!n.image||(n.summary||'').length<40)api('/api/news/enrich?id='+n.id).then(d=>{Object.assign(n,d);if(this.cur()===n)this.draw()}).catch(()=>{})},
 openCard(){const el=$('#nc');el.classList.remove('closing');el.classList.add('on');el.classList.toggle('min',!!this.st.min);el.classList.toggle('max',!!this.st.max);
  this.st.x==null?this.move(innerWidth-el.offsetWidth-28,innerHeight-el.offsetHeight-110):this.move(this.st.x,this.st.y)},
 move(x,y){const el=$('#nc');x=Math.max(0,Math.min(x,innerWidth-Math.min(el.offsetWidth,innerWidth)));y=Math.max(0,Math.min(y,innerHeight-44));el.style.left=x+'px';el.style.top=y+'px';this.st.x=x;this.st.y=y},
 save(){try{localStorage.setItem('jarvis.nc',JSON.stringify(this.st))}catch(e){}},
 draw(){const n=this.cur(),el=$('#nc');if(!n)return;$('#nc .ntitle').textContent=n.title;$('#ncn').textContent=`${this.i+1}/${this.items.length}`;
  $('#nc .nmeta').textContent=[n.source,n.published,n.category].filter(Boolean).join(' • ').toUpperCase()+((n.also||[]).length?` (+${n.also.length} fontes)`:'');
  $('#nc .nsum').textContent=n.summary||'';this.tag();const d=$('#nc .nimg');d.style.backgroundImage='';d.style.display=n.image?'':'none';
  if(n.image){const im=new Image();im.onload=()=>this.cur()===n&&(d.style.backgroundImage=`url("${n.image}")`);im.onerror=()=>{d.style.display='none'};im.src=n.image}},
 tag(){const n=this.cur();$('#nc .ntag').textContent=this.st.min&&n?n.title.slice(0,46)+(n.title.length>46?'…':''):'[ J.A.R.V.I.S. — NOTÍCIA ]'},
 nav(a){if(!this.items.length&&a!=='close')return;const n=this.cur();
  if(a==='min'||a==='max'){this.st[a]=!this.st[a];if(a==='max')this.st.min=false;$('#nc').classList.toggle('min',!!this.st.min);$('#nc').classList.toggle('max',!!this.st.max);this.tag();this.save();setTimeout(()=>this.move(this.st.x,this.st.y),320);return}
  if(a==='next'){ev(n.id,Date.now()-this.t0<5000?'skip':'next');if(this.i+1>=this.items.length){this.close(false);note('Essas foram as notícias por agora.');return}this.i++;this.show()}
  else if(a==='previous'){if(this.i>0){this.i--;this.show()}}
  else if(a==='repeat'){ev(n.id,'repeat');TTS.say(n.spoken,{flush:true})}
  else if(a==='open'){ev(n.id,'open');openUrl(n.url)}
  else if(a==='more'){ev(n.id,'more');send(`Fale mais sobre esta notícia: "${n.title}" (${n.url}). Leia a matéria e resuma em poucas frases.`,'Aprofundando a notícia…')}
  else if(a==='close')this.close(true)},
 close(log){if(log&&this.cur())ev(this.cur().id,'close');const el=$('#nc');el.classList.add('closing');setTimeout(()=>el.classList.remove('on','closing'),200);TTS.stop()}};
$('#nc').addEventListener('click',e=>{const b=e.target.closest('button[data-n]');b&&News.nav(b.dataset.n)});
$('#nc .nhead').addEventListener('pointerdown',e=>{if(e.target.closest('button'))return;const h=e.currentTarget,r=$('#nc').getBoundingClientRect(),dx=e.clientX-r.left,dy=e.clientY-r.top;h.setPointerCapture(e.pointerId);
 const mv=ev=>News.move(ev.clientX-dx,ev.clientY-dy),up=()=>{h.removeEventListener('pointermove',mv);News.save()};h.addEventListener('pointermove',mv);h.addEventListener('pointerup',up,{once:true})});
addEventListener('resize',()=>News.st.x!=null&&$('#nc').classList.contains('on')&&News.move(News.st.x,News.st.y));

/* ---------- navegador ---------- */
const Browser={st:{native:false,tabs:[]},
 async refresh(){try{this.st=await api('/api/browser');this.draw()}catch(e){}},
 async cmd(action,extra={}){try{const r=await post('/api/browser',{action,...extra});this.st=r.state;this.draw();if(r.error)note(r.error,1);return r}catch(e){note('Falha no navegador.',1)}},
 draw(){const t=this.st.tabs;$('#tabsb').innerHTML=t.length?t.map(x=>`<div class="item" data-tab="${x.id}"><span>${x.active?'◉':'○'}</span><b>Aba ${x.id}</b><span style="color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(x.url)}</span><small><button data-focus="${x.id}">focar</button> <button data-close="${x.id}">✕</button></small></div>`).join(''):'<div class="hint">Nenhuma aba aberta.</div>';
  $('#bnote').textContent=this.st.native?'Cada aba é uma janela nativa WebView2 (com abas ligadas ao JARVIS). Peça "abre o site X", "volta", "recarrega", "lê a página" por voz.':'Navegador embutido indisponível neste modo (Edge): as páginas abrem no navegador padrão. Inicie com JARVIS_SHELL=webview para abas nativas.'}};
$('#tabsb').addEventListener('click',e=>{const f=e.target.closest('[data-focus]'),c=e.target.closest('[data-close]');f&&Browser.cmd('focus',{tab:+f.dataset.focus});c&&Browser.cmd('close',{tab:+c.dataset.close})});
$$('[data-b]').forEach(b=>b.onclick=()=>Browser.cmd(b.dataset.b));
const go=()=>{const v=$('#addr').value.trim();if(v){Browser.cmd(Browser.st.tabs.length?'goto':'open',{url:v});$('#addr').value=''}};
$('#go').onclick=go;$('#addr').onkeydown=e=>e.key==='Enter'&&go();$('#newtab').onclick=()=>{Browser.cmd('open',{url:$('#addr').value.trim()||'https://duckduckgo.com'});$('#addr').value=''};

/* ---------- arquivos ---------- */
const fmtSize=mb=>mb>=1024?(mb/1024).toFixed(1)+' GB':mb>=1?mb.toFixed(1)+' MB':Math.max(1,Math.round(mb*1024))+' KB';
const Files={ready:false,
 async init(){if(this.ready)return;this.ready=true;const r=await api('/api/files/roots').catch(()=>[]);
  $('#froots').innerHTML=r.map(p=>`<span class="chip" data-p="${esc(p)}">📁 ${esc(base(p))}</span>`).join('');},
 draw(rows,title){$('#fpath').textContent=title;$('#flist').innerHTML=rows.length?rows.map(r=>`<div class="item" data-p="${esc(r.path)}" data-d="${r.dir?1:0}"><span>${r.dir?'📁':'📄'}</span><b>${esc(base(r.path))}</b><small>${esc(r.info)}</small><button data-reveal="${esc(r.path)}" title="Mostrar no Explorer">📍</button></div>`).join(''):'<div class="hint">Nada encontrado.</div>'},
 async browse(p){try{const d=await api('/api/files/list?path='+encodeURIComponent(p));this.draw(d.items.map(i=>({path:d.path+'\\'+i.name,dir:i.type==='pasta',info:i.type==='pasta'?i.modified:fmtSize(i.size_mb)+' · '+i.modified})),d.path)}catch(e){note('Pasta fora das autorizadas ou inacessível.',1)}},
 async search(q){if(!q)return;const d=await api('/api/files/search?q='+encodeURIComponent(q)).catch(()=>({results:[]}));
  this.draw((d.results||[]).map(i=>({path:i.path,dir:i.type==='pasta',info:i.modified+(i.type==='pasta'?'':' · '+fmtSize(i.size_mb))})),'RESULTADOS PARA "'+q+'"')}};
$('#froots').onclick=e=>{const c=e.target.closest('[data-p]');c&&Files.browse(c.dataset.p)};
$('#flist').onclick=e=>{const rv=e.target.closest('[data-reveal]');if(rv)return post('/api/files/open',{path:rv.dataset.reveal,reveal:true}).catch(()=>{});
 const it=e.target.closest('[data-p]');if(!it)return;it.dataset.d==='1'?Files.browse(it.dataset.p):post('/api/files/open',{path:it.dataset.p}).catch(()=>note('Não consegui abrir.',1))};
$('#fgo').onclick=()=>Files.search($('#fq').value.trim());$('#fq').onkeydown=e=>e.key==='Enter'&&Files.search(e.target.value.trim());

/* ---------- aba de notícias ---------- */
let NL=[],NCAT='todas';const cap=t=>t.charAt(0).toUpperCase()+t.slice(1);
function drawNews(){const cats=[...new Set(NL.map(n=>n.category))].sort(),vis=NL.filter(n=>NCAT==='todas'||n.category===NCAT);
 $('#ncats').innerHTML=['todas',...cats].map(c=>`<span class="chip ${c===NCAT?'on':''}" data-c="${esc(c)}">${esc(cap(c))} ${c==='todas'?NL.length:NL.filter(n=>n.category===c).length}</span>`).join('');
 $('#ncount').textContent=`· ${vis.length}`;
 $('#nlist').innerHTML=vis.map((n,i)=>`<div class="nrow" data-i="${i}"><div class="th" ${n.image?`style="background-image:url('${esc(n.image)}')"`:''}></div><div><div class="tt">${esc(n.title)}</div><div class="mm"><span class="tag">${esc(n.category)}</span>${esc(n.source)} · ${esc(n.published||'')}${(n.also||[]).length?` · +${n.also.length} fontes`:''}</div></div></div>`).join('')||'<div class="hint">Nada nesta categoria.</div>'}
async function loadNewsTab(){$('#nlist').innerHTML='<div class="hint">Buscando em várias fontes…</div>';NL=await api('/api/news?limit=40').catch(()=>[]);drawNews();
 api('/api/news/health').then(h=>$('#nhealth').textContent=`${h.ok}/${h.total} feeds responderam`).catch(()=>{})}
$('#ncats').onclick=e=>{const c=e.target.closest('[data-c]');if(c){NCAT=c.dataset.c;drawNews()}};
$('#nlist').onclick=e=>{const r=e.target.closest('[data-i]');if(!r)return;News.items=NL.filter(n=>NCAT==='todas'||n.category===NCAT);News.i=+r.dataset.i;News.show(true)};
$('#nrefresh').onclick=loadNewsTab;

/* ---------- tela (👁 SCREEN): o agente decide quando olhar; aqui só escolha de monitor e status ---------- */
const Screen={mons:[],
 async init(){try{this.mons=(await api('/api/screen')).monitors}catch(e){}this.draw()},
 draw(){const el=$('#scrmons'),m=this.mons,sel=String(P.screen.monitor);
  if(!m.length)el.innerHTML='<span class="one">Nenhum monitor detectado</span>';
  else if(m.length===1)el.innerHTML=`<span class="one">Monitor 1 — ${m[0].width}×${m[0].height}</span>`;
  else el.innerHTML=m.map(x=>`<button data-m="${x.id}" class="${sel==x.id?'on':''}">Monitor ${x.id} — ${x.width}×${x.height}${x.primary?' ★':''}</button>`).join('')+`<button data-m="all" class="${sel==='all'?'on':''}">Ambos</button>`;
  $('#scrboth').hidden=m.length<2},
 status(st){const e=$('#scrst');e.className=st;e.lastElementChild.textContent={ready:'Ready',capturing:'Capturing…',analyzing:'Analyzing…',error:'Error'}[st]||st},
 ask(w){send(`Veja a tela ${w==='all'?'dos dois monitores':'do monitor '+w} e descreva o que está acontecendo, incluindo erros e textos importantes.`,'Analisando a tela…')}};
$('#scrmons').onclick=e=>{const b=e.target.closest('[data-m]');if(b){setPref('screen.monitor',b.dataset.m);Screen.draw()}};
$('#scrsee').onclick=()=>Screen.ask(String(P.screen.monitor));$('#scrboth').onclick=()=>Screen.ask('all');

/* ---------- sistema ---------- */
let sysT=null;
async function drawSystem(){const d=await api('/api/system').catch(()=>null);if(!d)return;
 const bar=(n,v,x='')=>`<div class="bar"><span>${n} <em>${Math.round(v)}%${x}</em></span><i><b style="width:${v}%"></b></i></div>`;
 $('#sysbars').innerHTML=bar('CPU',d.cpu)+bar('RAM',d.ram,` · ${d.ram_used_gb}/${d.ram_total_gb} GB`);
 $('#sysdisks').innerHTML=d.disks.map(x=>bar(x.drive,x.percent,` · ${x.free_gb} GB livres de ${x.total_gb}`)).join('');
 $('#systop').innerHTML=d.top.map(p=>`<tr><td>${esc(p.name)}</td><td>${p.ram_mb} MB</td></tr>`).join('')}

async function diagnose(){const L=[];L.push('SpeechRecognition do navegador: '+(SR?'presente':'AUSENTE (comum no WebView2)'));
 L.push('STT local (faster-whisper): '+(Caps.local?`instalado (modelo ${Caps.model}${Caps.loaded?', carregado':', carrega no 1º uso'})`:'não instalado'));
 try{const st=await navigator.mediaDevices.getUserMedia({audio:true});st.getTracks().forEach(t=>t.stop());L.push('Acesso ao microfone: OK')}catch(e){L.push('Acesso ao microfone: FALHOU ('+e.name+')')}
 try{L.push('Microfones encontrados: '+(await navigator.mediaDevices.enumerateDevices()).filter(x=>x.kind==='audioinput').length)}catch(e){}
 const v=TTS.voices();L.push(`Vozes TTS: ${v.length} (pt-BR: ${v.filter(x=>/^pt[-_]BR/i.test(x.lang)).length}); em uso: ${TTS.pick()?.name||'nenhuma'}`);
 const p=STT.pick();L.push('Reconhecimento que será usado: '+(p===LocalSTT?'local':p===BrowserSTT?'navegador':'NENHUM'));
 addMsg('ai','<strong>Diagnóstico de voz</strong><ul>'+L.map(x=>`<li>${esc(x)}</li>`).join('')+'</ul>')}

/* ---------- configurações (geradas de um esquema; tudo persistente) ---------- */
const MODELS=['openai/gpt-oss-120b','openai/gpt-oss-20b','llama-3.3-70b-versatile','llama-3.1-8b-instant','qwen/qwen3.8-27b','qwen/qwen3.6-27b'];
const SCHEMA={
 general:{t:'Geral',f:[['name','text','Como devo te chamar'],['language','select','Idioma da interface',[['pt-BR','Português (Brasil)'],['en-US','English']]],['autostart','bool','Iniciar com o Windows'],
  ['theme','select','Tema',[['cyan','Ciano'],['ice','Gelo'],['emerald','Esmeralda'],['amber','Âmbar']]],['animations','bool','Animações'],['notifications','bool','Notificações (tarefa concluída em segundo plano)']]},
 voice:{t:'Voz',f:[['voice','voice','Voz'],['lang','select','Idioma da voz e do reconhecimento',[['pt-BR','Português (Brasil)'],['pt-PT','Português (Portugal)'],['en-US','English (US)']]],['rate','range','Velocidade',[.6,1.6,.05]],['pitch','range','Tom (pitch)',[.5,1.5,.05]],['volume','range','Volume',[0,1,.05]],
  ['autospeak','bool','Falar respostas automaticamente'],['recognition','select','Reconhecimento de voz',[['auto','Automático (local se instalado)'],['local','Local — faster-whisper (offline)'],['browser','Navegador (Web Speech)']]],['stt_model','select','Modelo do STT local',[['tiny','tiny (mais rápido)'],['base','base'],['small','small (recomendado)'],['medium','medium (mais preciso)']]],['auto_send','bool','Enviar transcrição automaticamente (após revisão)'],['send_delay','range','Tempo para revisar antes de enviar (s)',[.5,5,.1]],
  ['wake_word','bool','Sempre ouvindo (diga "JARVIS, …") — envia áudio ao serviço de voz do navegador enquanto ativo'],['_test','btn','Testar voz'],['_diag','btn','Diagnóstico de voz (microfone, STT, vozes)']]},
 ai:{t:'IA',f:[['model','model','Modelo (Groq)'],['temperature','range','Temperatura',[0,1.2,.05]],['max_tokens','range','Máximo de tokens por resposta',[300,4000,100]],['reasoning','select','Raciocínio',[['off','Desligado'],['low','Baixo'],['medium','Médio'],['high','Alto']]],['max_steps','range','Limite de passos do agente',[2,25,1]],['vision_model','model','Modelo de visão (análise de tela)']]},
 privacy:{t:'Privacidade',f:[['mic','bool','Permitir microfone'],['history','bool','Guardar histórico de conversa'],['memory','bool','Permitir memória de longo prazo'],['indexing','bool','Indexar arquivos (busca rápida)'],['screen','bool','Permitir visão de tela (captura só quando pedida; nada é salvo)'],['_clear','btn','Apagar histórico']]},
 news:{t:'Notícias',f:[['on_start','bool','Mostrar uma notícia ao iniciar'],['narrate','bool','Narrar a notícia'],['sources','map','Fontes'],['categories','map','Categorias']]},
 screen:{t:'Tela',f:[['monitor','monitor','Monitor analisado']]},
 ui:{t:'Interface',f:[['glow','range','Brilho',[0,1.6,.1]],['density','select','Densidade',[['comfortable','Confortável'],['compact','Compacta']]],['font_size','range','Tamanho do texto',[12,18,1]]]}};
const Settings={open:'general',
 render(){$('#setnav').innerHTML=Object.entries(SCHEMA).map(([k,v])=>`<button data-s="${k}" class="${k===this.open?'on':''}">${v.t}</button>`).join('');
  const sec=SCHEMA[this.open];$('#setform').innerHTML=`<h4>${sec.t.toUpperCase()}</h4>`+sec.f.map(([k,type,label,opt])=>this.field(k,type,label,opt)).join('')},
 field(k,type,label,opt){const path=this.open+'.'+k,v=P[this.open][k];let c='';
  if(type==='text')c=`<input data-k="${path}" value="${esc(v)}">`;
  else if(type==='bool')c=`<input type="checkbox" class="sw" data-k="${path}" ${v?'checked':''}>`;
  else if(type==='select')c=`<select data-k="${path}">${opt.map(([a,b])=>`<option value="${a}" ${a==v?'selected':''}>${b}</option>`).join('')}</select>`;
  else if(type==='range')c=`<input type="range" data-k="${path}" data-num="1" min="${opt[0]}" max="${opt[1]}" step="${opt[2]}" value="${v}"><span class="v">${v}</span>`;
  else if(type==='model')c=`<input data-k="${path}" list="models" value="${esc(v)}"><datalist id="models">${MODELS.map(m=>`<option value="${m}">`).join('')}</datalist>`;
  else if(type==='voice'){const vs=TTS.voices().slice().sort((a,b)=>(/^pt[-_]BR/i.test(b.lang)-/^pt[-_]BR/i.test(a.lang))||a.name.localeCompare(b.name));
   c=`<select data-k="${path}"><option value="">Automática (melhor pt-BR)</option>${vs.map(x=>`<option value="${esc(x.name)}" ${x.name===v?'selected':''}>${esc(x.name)} — ${x.lang}</option>`).join('')}</select>`}
  else if(type==='map')c=`<div style="display:flex;flex-wrap:wrap;gap:10px 18px">${Object.entries(v).map(([n,on])=>`<label style="width:auto;display:flex;gap:6px;align-items:center"><input type="checkbox" data-k="${path}.${n}" ${on?'checked':''}> ${esc(n)}</label>`).join('')}</div>`;
  else if(type==='monitor'){const m=Screen.mons;if(m.length<2)return `<div class="fld"><label>${label}</label><span class="hint">${m.length?`Apenas um monitor detectado (${m[0].width}×${m[0].height}).`:'Nenhum monitor detectado.'}</span></div>`;
   c=`<select data-k="${path}">${m.map(x=>`<option value="${x.id}" ${String(v)===String(x.id)?'selected':''}>Monitor ${x.id} — ${x.width}×${x.height}${x.primary?' (principal)':''}</option>`).join('')}<option value="all" ${v==='all'?'selected':''}>Ambos os monitores</option></select>`}
  else if(type==='btn')return `<div class="fld"><button data-act="${k}">${label}</button></div>`;
  return `<div class="fld"><label>${label}</label>${c}</div>`}};
$('#setnav').onclick=e=>{const b=e.target.closest('[data-s]');if(b){Settings.open=b.dataset.s;Settings.render()}};
$('#setform').addEventListener('input',e=>{const t=e.target,k=t.dataset.k;if(!k)return;
 const val=t.type==='checkbox'?t.checked:t.dataset.num?+t.value:t.value;setPref(k,val);if(k.startsWith('screen.'))Screen.draw();if(t.type==='range')t.nextElementSibling.textContent=t.value});
$('#setform').addEventListener('click',e=>{const b=e.target.closest('[data-act]');if(!b)return;
 if(b.dataset.act==='_test')TTS.test();if(b.dataset.act==='_diag')diagnose();if(b.dataset.act==='_clear')api('/api/history',{method:'DELETE'}).then(()=>note('Histórico apagado.'))});

/* ---------- abas ---------- */
function switchTab(name){$$('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.tab===name));$$('.view').forEach(v=>v.classList.toggle('on',v.id==='v-'+name));
 clearInterval(sysT);if(name==='system'){drawSystem();sysT=setInterval(drawSystem,2500)}
 if(name==='browser')Browser.refresh();if(name==='files')Files.init();if(name==='news')loadNewsTab();if(name==='settings')Settings.render()}
$('#tabs').onclick=e=>{const b=e.target.closest('button[data-tab]');b&&switchTab(b.dataset.tab)};

/* ---------- tempo real ---------- */
function connect(){ws=new WebSocket(`ws://${location.host}/ws`);ws.onopen=()=>ws.send(JSON.stringify({type:'hello'}));ws.onclose=()=>setTimeout(connect,2000);
 ws.onmessage=e=>{const m=JSON.parse(e.data);switch(m.type){
  case'state':S.srv=m.v;if(m.v==='idle'){typing(false);Always.follow=Date.now()+10000}else typing(true);render();break;
  case'say':typing(false);addMsg('ai',md(m.text));S.last=speakable(m.text);if(P.voice.autospeak)TTS.say(speakable(m.text));notify(speakable(m.text));break;
  case'step':{const l=$('#steplist');let d=$('#st-'+m.id);if(!d){d=document.createElement('div');d.id='st-'+m.id;l.prepend(d)}d.className='step '+m.status;d.innerHTML=`<u>${m.status==='done'?'✓':m.status==='error'?'✕':''}</u><span>${esc(m.text)}</span>`;while(l.children.length>30)l.lastChild.remove();break}
  case'news_session':News.start(m.items,m.narrate,m.intro);break;
  case'screen':Screen.status(m.status);break;
  case'news_nav':News.nav(m.action);break;
  case'browser':Browser.st=m.state;Browser.draw();break;
  case'stats':for(const[k,v]of[['c',m.cpu],['r',m.ram],['d',m.disk]]){$('#b'+k).style.width=v+'%';$('#v'+k).textContent=Math.round(v)+'%'}break;
  case'confirm':S.pend=true;$('#cft').textContent=m.text;$('#cf').style.display='flex';TTS.say(m.text,{flush:true});break}}}

(async function boot(){P=await api('/api/prefs');applyPrefs();Dock.set('idle');Caps=await api('/api/stt/status').catch(()=>({local:false}));Screen.init();
 const h=await api('/api/history').catch(()=>[]);if(h.length){h.forEach(x=>addMsg(x.role==='user'?'me':'ai',x.role==='user'?esc(x.text):md(x.text)));note('— histórico —')}
 connect()})();
