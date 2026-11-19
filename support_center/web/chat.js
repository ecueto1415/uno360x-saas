(() => {
  'use strict';
  if (document.getElementById('uno-support')) return;
  const root = document.createElement('section');
  root.id = 'uno-support';
  root.innerHTML = `<button class="us-launch" type="button" aria-controls="us-panel" aria-expanded="false">◌ <span>Soporte</span></button>
    <section id="us-panel" hidden role="dialog" aria-label="Soporte UNO360X">
      <header><div><strong>Jenifer · Soporte UNO360X</strong><small>Estamos para ayudarte</small></div><button type="button" class="us-close" aria-label="Cerrar soporte">×</button></header>
      <p class="us-privacy">Cuéntanos qué necesitas. No envíes contraseñas, códigos ni certificados. Este chat se comparte con el equipo de soporte.</p>
      <div class="us-tools"><small class="us-continuous">Tu conversación queda guardada en esta empresa.</small><button type="button" class="us-older" hidden>Ver mensajes anteriores</button></div>
      <div class="us-messages" role="log" aria-live="polite"></div><p class="us-status" role="status"></p>
      <form><label for="us-text">Tu mensaje</label><textarea id="us-text" rows="3" maxlength="3000" required placeholder="¿En qué te ayudamos?"></textarea>
      <div class="us-actions"><button type="button" class="us-human">Hablar con el equipo</button><button type="button" class="us-ai" hidden>Volver a Jenifer</button><button type="submit" class="us-send">Enviar</button></div></form>
    </section>`;
  document.body.append(root);
  const $ = q => root.querySelector(q), launch = $('.us-launch'), panel = $('#us-panel'), log = $('.us-messages'), status = $('.us-status');
  let data = null, selected = null, csrf = '', poll = null, loading = false, request = null, humanNew = false, generation = 0, older = [], hasOlder = false, historyLoading = false, historyLoaded = false;
  const en = document.documentElement.lang?.startsWith('en');
  if (en) {
    launch.querySelector('span').textContent = 'Support';
    $('header strong').textContent = 'Jenifer · UNO360X Support';
    $('header small').textContent = 'Here to help';
    $('.us-privacy').textContent = 'Tell us what you need. Do not send passwords, codes or certificates. This chat is shared with the support team.';
    $('.us-continuous').textContent = 'Your conversation is saved for this company.';
    $('.us-older').textContent = 'View earlier messages';
    $('label').textContent = 'Your message'; $('#us-text').placeholder = 'How can we help?';
    $('.us-human').textContent = 'Talk to the team'; $('.us-send').textContent = 'Send';
    $('.us-ai').textContent = 'Back to Jenifer';
  }
  async function api(body, id, before) {
    const query = new URLSearchParams();
    if (id) query.set('case_id',id);
    if (before) query.set('before',String(before));
    const response = await fetch('/__support' + (query.size ? '?' + query : ''), {
      credentials: 'same-origin', cache: 'no-store', ...(body ? {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify(body)} : {})
    });
    if (response.status === 401) throw new Error(en ? 'Sign in again to continue.' : 'Vuelve a iniciar sesión para continuar.');
    let result;
    try { result = await response.json(); } catch { throw new Error(en ? 'Support is temporarily unavailable.' : 'El soporte no está disponible en este momento.'); }
    if (!response.ok) throw new Error(response.status === 401 ? (en ? 'Sign in again to continue.' : 'Vuelve a iniciar sesión para continuar.') : result.error || 'No se pudo completar la solicitud.');
    return result;
  }
  function linkedText(node,text) {
    const pattern=/(https?:\/\/[^\s<>"']+|\/(?:uno360x(?:[-/][^\s<>"']*)?|odoo(?:\/[^\s<>"']*)?|__team(?:\?[^\s<>"']*)?))/g;
    let last=0;
    for(const match of String(text).matchAll(pattern)) {
      const raw=match[0].replace(/[.,;!?)]+$/,'');
      node.append(document.createTextNode(text.slice(last,match.index)));
      let url;
      try {url=new URL(raw,location.origin);} catch {}
      if(url && url.origin===location.origin && /^(?:\/uno360x[-/]|\/odoo(?:\/|$)|\/__team(?:$|\/))/.test(url.pathname)) {
        const a=document.createElement('a');a.href=url.pathname+url.search+url.hash;a.textContent=raw;node.append(a);
      } else node.append(document.createTextNode(raw));
      last=match.index+raw.length;
    }
    node.append(document.createTextNode(text.slice(last)));
  }
  function render(value) {
    const changed = selected !== (value.selected?.id || null);
    data = value; csrf = value.csrf_token; selected = value.selected?.id || null;
    if (changed || older.length && value.messages.length && value.messages[0].id > older[older.length-1].id) { older = []; historyLoaded = false; }
    // Keep already viewed history when polling advances the newest page.
    const combined = new Map([...older,...(selected ? value.messages : [])].map(m => [m.id,m]));
    const messages = [...combined.values()].sort((a,b) => a.id-b.id);
    older = messages;
    if (!historyLoaded) hasOlder = Boolean(value.has_older);
    $('.us-older').hidden = !hasOlder;
    const signature = JSON.stringify(messages.map(m => [m.id, m.state, m.body]));
    if (log.dataset.signature !== signature) {
      const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
      log.replaceChildren();
      if (!messages.length) {
        const p = document.createElement('p'); p.className = 'us-empty';
        p.textContent = en ? 'Hi, I am Jenifer. How can I help? We can continue here whenever you return.' : 'Hola, soy Jenifer. ¿En qué puedo ayudarte? Cuando vuelvas, seguimos aquí.'; log.append(p);
      }
      for (const m of messages) {
        const article = document.createElement('article'); article.className = 'us-message us-' + m.role;
        const name = document.createElement('strong'); name.textContent = m.role === 'user' ? (en ? 'You' : 'Tú') : m.role === 'team' ? (en ? 'UNO360X Team' : 'Equipo UNO360X') : 'Jenifer';
        const p = document.createElement('p'); linkedText(p,m.body); article.append(name, p); log.append(article);
      }
      log.dataset.signature = signature;
      if (nearBottom) log.scrollTop = log.scrollHeight;
    }
    const pending = messages.some(m => ['pending','working'].includes(m.state));
    const human = selected ? value.selected?.human : humanNew;
    $('.us-ai').hidden = !human || value.selected?.status === 'resolved';
    $('.us-human').hidden = Boolean(human) && value.selected?.status !== 'resolved';
    $('header strong').textContent = human && value.selected?.status !== 'resolved' ? (en ? 'UNO360X Support Team' : 'Equipo de soporte UNO360X') : (en ? 'Jenifer · UNO360X Support' : 'Jenifer · Soporte UNO360X');
    $('#us-text').placeholder = human && value.selected?.status !== 'resolved' ? (en ? 'Message for the team. Use Back to Jenifer for AI assistance.' : 'Mensaje para el equipo. Pulsa Volver a Jenifer para hablar con ella.') : (en ? 'How can we help?' : '¿En qué te ayudamos?');
    status.textContent = pending ? (en ? 'Jenifer is preparing a response…' : 'Jenifer está preparando una respuesta…') : value.selected?.status === 'resolved' && selected ? (en ? 'The team resolved your request. Jenifer is available; keep writing here.' : 'El equipo resolvió tu consulta. Jenifer está disponible; sigue escribiendo aquí.') : human ? (en ? 'Sent to the team. Your conversation is saved; you can close this window.' : 'Enviado al equipo. La conversación queda guardada; puedes cerrar esta ventana.') : '';
    $('.us-send').disabled = loading || pending;
    schedule();
  }
  function schedule() {
    clearTimeout(poll);
    if (panel.hidden || document.hidden || !selected) return;
    const pending = data?.messages.some(m => ['pending','working'].includes(m.state));
    poll = setTimeout(refresh, pending ? 4000 : 30000);
  }
  async function refresh() {
    const mine = ++generation;
    try { const result = await api(null, selected); if (mine === generation && !panel.hidden) render(result); }
    catch (error) { if (mine === generation) status.textContent = error.message; }
  }
  launch.onclick = () => {
    panel.hidden = !panel.hidden; launch.setAttribute('aria-expanded', String(!panel.hidden));
    if (panel.hidden) { generation++; clearTimeout(poll); } else { refresh(); $('#us-text').focus(); }
  };
  $('.us-close').onclick = () => { panel.hidden = true; launch.setAttribute('aria-expanded','false'); generation++; clearTimeout(poll); launch.focus(); };
  $('.us-older').onclick = async () => {
    if (historyLoading || !selected || !older.length) return;
    historyLoading = true; $('.us-older').disabled = true;
    const mine = generation, height = log.scrollHeight, top = log.scrollTop;
    try {
      const page = await api(null,selected,older[0].id);
      if (mine !== generation || page.selected?.id !== selected) return;
      older = [...page.messages,...older]; hasOlder = Boolean(page.has_older); historyLoaded = true;
      render(data); log.scrollTop = top + log.scrollHeight - height;
    } catch (error) { status.textContent = error.message; }
    finally { historyLoading = false; $('.us-older').disabled = false; }
  };
  $('#us-text').addEventListener('input', () => { request = null; });
  $('form').onsubmit = async event => {
    event.preventDefault();
    if (loading) return;
    const body = $('#us-text').value.trim(); if (!body) return;
    loading = true; generation++; clearTimeout(poll); $('.us-send').disabled = true;
    const payload = request || {case_id:selected,body,request_id:crypto.randomUUID(),human:humanNew}; request = payload;
    try { if (!csrf) csrf = (await api()).csrf_token; const result = await api(payload); request = null; humanNew = false; $('#us-text').value = ''; loading = false; render(result); log.scrollTop = log.scrollHeight; }
    catch (error) { status.textContent = error.message; }
    finally { loading = false; $('.us-send').disabled = data?.messages.some(m => ['pending','working'].includes(m.state)) || false; }
  };
  $('.us-human').onclick = async () => {
    if (loading) return;
    if (!selected) { humanNew = true; status.textContent = en ? 'Write your message to send it to the team.' : 'Escribe tu mensaje para enviarlo al equipo.'; $('#us-text').focus(); return; }
    loading = true; generation++; clearTimeout(poll);
    try { render(await api({case_id:selected,handoff:true})); } catch (error) { status.textContent = error.message; }
    finally { loading = false; $('.us-send').disabled = data?.messages.some(m => ['pending','working'].includes(m.state)) || false; }
  };
  $('.us-ai').onclick = async () => {
    if (loading || !selected) return;
    loading = true; generation++; clearTimeout(poll); $('.us-ai').disabled = true;
    try { render(await api({case_id:selected,resume:true})); } catch (error) { status.textContent = error.message; }
    finally { loading = false; $('.us-ai').disabled = false; $('.us-send').disabled = data?.messages.some(m => ['pending','working'].includes(m.state)) || false; }
  };
  root.addEventListener('keydown', event => { if (event.key === 'Escape' && !panel.hidden) $('.us-close').click(); });
  document.addEventListener('visibilitychange', schedule);
  document.addEventListener('click', event => {
    const a = event.target.closest('a[href="/uno360x-ayuda"]');
    if (a && !event.ctrlKey && !event.metaKey) { event.preventDefault(); event.stopImmediatePropagation(); if (panel.hidden) launch.click(); }
  }, true);
})();
