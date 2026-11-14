/* Question × terminal UI state; a single FIFO feeds the session transport. */
window.TerminalWorkspace = class {
  constructor({api, container, addButton, onPending, onError, isExpired, onWindows = () => {}, onEvent = () => {}}) {
    Object.assign(this, {api, container, addButton, onPending, onError, isExpired, onWindows, onEvent});
    this.questions = {}; this.queue = []; this.processing = false; this.locked = false;
    addButton.onclick = () => this.add();
  }
  get pending() { return this.processing || this.queue.length > 0; }
  reset() { this.questions = {}; this.queue = []; this.processing = false; }
  show(question) {
    this.question = question;
    this.state = this.questions[question.n] ||= window.ExamLog.question(question);
    this.mount();
  }
  makeTerminal(n, host) {
    return window.ExamLog.terminal(n, host);
  }
  add() {
    if (this.locked || this.isExpired() || this.state.terminals.length === 2) return;
    const n = this.state.terminals[0].n === 1 ? 2 : 1;
    this.state.terminals.push(this.makeTerminal(n, this.question.host));
    this.state.terminals.sort((a, b) => a.n - b.n);
    this.onEvent('terminal-add', {n: this.question.n, terminal: n});
    this.state.active = n; this.mount(); this.focus();
  }
  close(t) {
    if (this.locked || this.isExpired() || t.phase !== 'idle' || this.state.terminals.length === 1) return;
    this.onEvent('terminal-close', {n: this.question.n, terminal: t.n});
    this.state.terminals = this.state.terminals.filter(item => item !== t);
    this.state.active = this.state.terminals[0].n; this.mount(); this.focus();
  }
  focus() { this.state.terminals.find(t => t.n === this.state.active)?.view.input.focus(); }
  switchTerminal() {
    if (this.state.terminals.length !== 2) return;
    this.state.active = this.state.terminals.find(t => t.n !== this.state.active).n; this.highlight(); this.focus();
  }
  highlight() {
    for (const t of this.state.terminals) t.view.panel.classList.toggle('active-terminal', t.n === this.state.active);
  }
  mount() {
    this.container.replaceChildren();
    this.container.classList.toggle('two-terminals', this.state.terminals.length === 2);
    this.container.style.setProperty('--top-height', `${this.state.ratio}%`);
    this.state.terminals.forEach((t, i) => {
      if (i) this.mountDivider();
      const panel = document.createElement('section'); panel.className = 'terminal-pane'; panel.setAttribute('aria-label', `Terminal ${t.n}`);
      panel.innerHTML = `<div class="terminal-head"><strong></strong><span class="terminal-context"></span><button type="button">× 닫기</button></div>
        <div class="terminal" role="log" tabindex="0"></div><div class="response-note"></div>
        <div class="terminal-status" role="status" aria-live="polite"></div>
        <form class="terminal-form"><label></label><textarea rows="2" spellcheck="false" autocomplete="off" placeholder="kubectl get pods -A"></textarea><button class="primary" type="submit">실행 ↵</button></form>`;
      const input = panel.querySelector('textarea'), form = panel.querySelector('form');
      t.view = {panel, input, title: panel.querySelector('strong'), context: panel.querySelector('.terminal-context'), close: panel.querySelector('.terminal-head button'), output: panel.querySelector('.terminal'), note: panel.querySelector('.response-note'), status: panel.querySelector('.terminal-status'), prompt: panel.querySelector('label'), run: form.querySelector('button')};
      input.id = `command-${t.n}`; t.view.prompt.htmlFor = input.id; input.value = t.draft;
      t.view.output.setAttribute('aria-label', `Terminal ${t.n} 기록`);
      input.setAttribute('aria-describedby', 'key-help');
      panel.addEventListener('focusin', () => { this.state.active = t.n; this.highlight(); });
      t.view.close.onclick = () => this.close(t);
      input.oninput = () => { t.draft = input.value; };
      input.onkeydown = event => this.keydown(event, t, form);
      form.onsubmit = event => { event.preventDefault(); this.enqueue(t); };
      this.container.append(panel); this.render(t);
    });
    this.highlight(); this.lock(this.locked); this.onWindows();
  }
  mountDivider() {
    const divider = document.createElement('div'); divider.className = 'terminal-divider'; divider.tabIndex = 0;
    divider.setAttribute('role', 'separator'); divider.setAttribute('aria-label', '터미널 높이 조절'); divider.setAttribute('aria-orientation', 'horizontal');
    divider.setAttribute('aria-valuemin', '30'); divider.setAttribute('aria-valuemax', '70');
    const apply = ratio => { this.state.ratio = Math.max(30, Math.min(70, ratio)); this.container.style.setProperty('--top-height', `${this.state.ratio}%`); divider.setAttribute('aria-valuenow', Math.round(this.state.ratio)); };
    apply(this.state.ratio);
    divider.onpointerdown = event => {
      const y = event.clientY, ratio = this.state.ratio; divider.setPointerCapture(event.pointerId);
      divider.onpointermove = e => apply(ratio + (e.clientY - y) / this.container.clientHeight * 100);
      divider.onpointerup = divider.onpointercancel = () => { divider.onpointermove = null; };
    };
    divider.onkeydown = event => { if (['ArrowUp', 'ArrowDown'].includes(event.key)) { event.preventDefault(); apply(this.state.ratio + (event.key === 'ArrowDown' ? 2 : -2)); } };
    this.container.append(divider);
  }
  lock(value) {
    this.locked = value;
    if (!this.state) return;
    this.addButton.disabled = value || this.isExpired() || this.state.terminals.length === 2;
    for (const t of this.state.terminals) {
      const disabled = value || this.isExpired() || t.phase !== 'idle';
      t.view.input.disabled = t.view.run.disabled = disabled;
      t.view.close.disabled = disabled || this.state.terminals.length === 1;
    }
  }
  keydown(event, t, form) {
    if (event.isComposing) return;
    // Tab completes like bash (Shift+Tab still moves focus)
    if (event.key === 'Tab' && !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey && window.Completion) {
      event.preventDefault(); this.tabComplete(t); return;
    }
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
    if (['ArrowUp', 'ArrowDown'].includes(event.key) && !event.shiftKey && !event.altKey && !t.view.input.value.includes('\n') && t.history.length) {
      event.preventDefault();
      if (t.historyIndex === t.history.length) t.savedDraft = t.view.input.value;
      t.historyIndex = Math.max(0, Math.min(t.history.length, t.historyIndex + (event.key === 'ArrowUp' ? -1 : 1)));
      t.draft = t.historyIndex === t.history.length ? t.savedDraft : t.history[t.historyIndex]; t.view.input.value = t.draft;
    }
  }
  // Paths and names come from the current problem state (/api/complete), fetched once per host until the next command.
  async tabComplete(t) {
    const input = t.view.input, host = t.host;
    if (!t.completion || t.completion.host !== host) {
      let data = {};
      try { data = this.api.complete ? await this.api.complete({host}) : {}; } catch { data = {}; }
      t.completion = {host, data};
    }
    const r = window.Completion.complete(input.value, input.selectionStart, t.completion.data);
    input.value = t.draft = r.text; input.setSelectionRange(r.cursor, r.cursor);
    t.view.note.textContent = r.candidates.join('   ');
  }
  splitResponse(markdown) {
    const blocks = [];
    const note = markdown.replace(/^(`{3,4})console[ \t]*\n([\s\S]*?)^\1[ \t]*(?:\n|$)/gm, (_, fence, body) => { blocks.push(body.trimEnd()); return ''; }).trim();
    return blocks.length ? {console: blocks.join('\n\n'), note, blocks} : {console: markdown, note: '', blocks};
  }
  applyResponse(t, response) {
    const headers = window.TerminalWorkspace.prototype.splitResponse(response).blocks.map(block => block.split('\n')[0].match(/^# \[SIM\] host=(\S+) ctx=(\S+)$/)).filter(Boolean);
    if (headers.length) { t.host = headers.at(-1)[1]; this.state.contexts[t.host] = headers.at(-1)[2]; }
  }
  // Show it like a real terminal: drop "# [SIM] host= ctx=" headers (kept in the response for host tracking) and the
  // "$ <typed command>" echo; any other "$ " line (multi-line input) becomes a prompt line.
  screenText(text, entry) {
    const typed = entry.text.split('\n').map(l => l.trim()), out = [];
    let echo = -1;
    for (const line of text.split('\n')) {
      if (/^# \[SIM\] host=\S+ ctx=\S+$/.test(line)) continue;
      if (echo === -1 && line.startsWith('$ ') && line.slice(2).trim() === typed[0]) { echo = 1; continue; }
      if (echo > 0 && echo < typed.length && line.replace(/^> /, '').trim() === typed[echo]) { echo++; continue; }
      if (echo > 0) echo = typed.length;
      out.push(line.startsWith('$ ') ? `root@${entry.host}:~# ${line.slice(2)}` : line);
    }
    return out.join('\n').trim();
  }
  contextFor(host) { return this.state.contexts[host] ?? this.state.defaultContext; }
  renderHeader(t) {
    const v = t.view;
    v.title.textContent = `Terminal - root@${t.host}: ~`; v.context.textContent = `T${t.n} · ctx=${this.contextFor(t.host)}`;
    v.prompt.textContent = `root@${t.host}:~#`;
  }
  renderStatus(t) {
    t.view.status.textContent = t.status; t.view.status.classList.toggle('busy', t.phase !== 'idle');
  }
  render(t) {
    const v = t.view, follow = v.output.scrollHeight - v.output.scrollTop - v.output.clientHeight < 70;
    this.renderHeader(t);
    v.output.replaceChildren();
    t.entries.forEach((entry, i) => {
      const command = document.createElement('pre'); command.className = 'input-line'; command.textContent = `root@${entry.host}:~# ${entry.text.split('\n').join('\n> ')}`;
      const response = this.splitResponse(entry.response), output = document.createElement('pre'); output.textContent = this.screenText(response.console, entry);
      v.output.append(command, output);
      if (response.note && i < t.entries.length - 1) { const note = document.createElement('div'); note.className = 'response-note'; note.textContent = response.note; v.output.append(note); }
    });
    v.note.textContent = t.entries.length ? this.splitResponse(t.entries.at(-1).response).note : '';
    this.renderStatus(t);
    if (follow) v.output.scrollTop = v.output.scrollHeight;
  }
  enqueue(t) {
    if (this.locked || this.isExpired() || t.phase !== 'idle') return;
    const text = t.view.input.value.trim(); if (!text) return;
    t.draft = t.view.input.value; t.phase = 'queued'; t.status = '대기 중 — 앞선 터미널 응답을 기다립니다.';
    this.queue.push({t, text}); this.renderStatus(t); this.lock(this.locked); this.onPending();
    return this.drain();
  }
  async drain() {
    if (this.processing) return;
    this.processing = true;
    try {
      while (this.queue.length) {
        const {t, text} = this.queue.shift();
        if (this.isExpired()) { t.phase = 'idle'; t.status = '시간 만료 — 대기 명령을 전송하지 않았습니다.'; this.renderStatus(t); continue; }
        t.phase = 'running'; t.status = 'Claude 응답 대기 중'; this.renderStatus(t);
        const started = Date.now();
        const interval = setInterval(() => { t.status = `Claude 응답 대기/수신 중 · ${Math.floor((Date.now() - started) / 1000)}초 경과`; this.renderStatus(t); }, 1000);
        t.completion = null; const entry = {text, host: t.host, response: ''}; t.entries.push(entry); t.history.push(text); t.historyIndex = t.history.length; this.render(t);
        try {
          for await (const delta of this.api.cmd({text, terminal: t.n, host: t.host})) { entry.response += delta; this.render(t); }
          this.applyResponse(t, entry.response); this.onWindows();
          t.draft = ''; t.view.input.value = ''; t.status = '명령을 입력하세요.';
        } catch (error) { entry.response += `\nError: ${error.message}`; t.status = '오류 — 입력을 보존했습니다. 다시 실행하세요.'; this.applyResponse(t, entry.response); this.onWindows(); this.onError(error.message); this.render(t); }
        finally { this.onEvent('cmd', {n: this.question.n, terminal: t.n, host: entry.host, text, response: entry.response}); clearInterval(interval); t.phase = 'idle'; this.state.terminals.forEach(item => { this.renderHeader(item); this.renderStatus(item); }); this.lock(this.locked); }
      }
    } finally { this.processing = false; this.onPending(); }
  }
};
