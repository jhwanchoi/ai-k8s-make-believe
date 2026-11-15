/* Question × terminal UI state; a single FIFO feeds the session transport. */
window.TerminalWorkspace = class {
  constructor({api, container, addButton, onPending, onError, isExpired, onWindows = () => {}, onEvent = () => {}}) {
    Object.assign(this, {api, container, addButton, onPending, onError, isExpired, onWindows, onEvent});
    this.questions = {}; this.queue = []; this.processing = false; this.locked = false;
    addButton.onclick = () => this.add();
  }
  // 편집기가 열린 동안도 문항 이동 · 제출을 잠근다 (창이 다시 그려지면 편집 내용이 사라진다)
  get pending() { return this.processing || this.queue.length > 0 || !!this.state?.terminals.some(t => t.phase === 'editing'); }
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
        <div class="terminal-scroll"><div class="terminal" role="log" tabindex="0"></div><div class="response-note"></div>
        <div class="terminal-status" role="status" aria-live="polite"></div>
        <form class="terminal-form"><label></label><textarea rows="1" spellcheck="false" autocomplete="off" autocapitalize="off"></textarea><button class="sr-only" type="submit">실행</button></form></div>`;
      const input = panel.querySelector('textarea'), form = panel.querySelector('form');
      t.view = {panel, input, title: panel.querySelector('strong'), context: panel.querySelector('.terminal-context'), close: panel.querySelector('.terminal-head button'), output: panel.querySelector('.terminal'), note: panel.querySelector('.response-note'), status: panel.querySelector('.terminal-status'), prompt: panel.querySelector('label'), run: form.querySelector('button'), scroll: panel.querySelector('.terminal-scroll')};
      // 실제 터미널처럼 화면 아무 곳이나 누르면 프롬프트로 (글자를 고르는 중이면 그대로)
      t.view.scroll.addEventListener('mouseup', () => { if (!String(window.getSelection())) input.focus(); });
      input.id = `command-${t.n}`; t.view.prompt.htmlFor = input.id; input.value = t.draft;
      t.view.output.setAttribute('aria-label', `Terminal ${t.n} 기록`);
      input.setAttribute('aria-describedby', 'key-help');
      panel.addEventListener('focusin', () => { this.state.active = t.n; this.highlight(); });
      t.view.close.onclick = () => this.close(t);
      input.oninput = () => { t.draft = input.value; this.fit(t); };
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
  // 입력 줄 높이를 내용에 맞춘다 (heredoc 처럼 여러 줄이면 늘어난다)
  fit(t) { const i = t.view.input; i.style.height = 'auto'; i.style.height = `${i.scrollHeight}px`; }
  setInput(t, value, cursor = value.length) {
    const i = t.view.input; i.value = t.draft = value; i.setSelectionRange(cursor, cursor); this.fit(t);
  }
  // bash 처럼 아직 끝나지 않은 입력: 닫히지 않은 heredoc, 끝의 \, 닫히지 않은 따옴표 → Enter 는 줄바꿈
  needsMore(text) {
    if (/\\$/.test(text)) return true;
    let quote = null;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quote) { if (c === quote) quote = null; else if (c === '\\' && quote === '"') i++; }
      else if (c === "'" || c === '"') quote = c; else if (c === '\\') i++;
    }
    if (quote) return true;
    const lines = text.split('\n');
    for (let n = 0; n < lines.length; n++) {
      for (const m of lines[n].matchAll(/<<(-?)\s*(['"]?)([\w.-]+)\2/g)) {
        if (!lines.slice(n + 1).some(l => (m[1] ? l.trim() : l) === m[3])) return true;
      }
    }
    return false;
  }
  // 실제처럼 실행하지 않고 화면에만 남기는 줄 (^C, clear)
  local(t, text) {
    t.entries.push({text, host: t.host, response: '', local: true}); this.setInput(t, ''); this.render(t);
  }
  // 실제 시험 터미널(Linux, bash)의 단축키. 복사 · 붙여넣기는 공식 안내대로 Ctrl+Shift+C / Ctrl+Shift+V
  shortcut(event, t) {
    const i = t.view.input, v = i.value, s = i.selectionStart, e = i.selectionEnd;
    const lineStart = v.lastIndexOf('\n', s - 1) + 1, lineEnd = v.indexOf('\n', s) < 0 ? v.length : v.indexOf('\n', s);
    const key = event.key.toLowerCase();
    if (event.shiftKey && key === 'c') { navigator.clipboard?.writeText(String(window.getSelection()) || v.slice(s, e)); return true; }
    if (event.shiftKey && key === 'v') { navigator.clipboard?.readText().then(text => this.setInput(t, v.slice(0, s) + text + v.slice(e), s + text.length)).catch(() => {}); return true; }
    if (event.shiftKey) return false;
    switch (key) {
      case 'c': this.local(t, `${v}^C`); return true;
      case 'l': t.clearedAt = t.entries.length; this.render(t); return true;
      case 'u': this.setInput(t, v.slice(0, lineStart) + v.slice(s), lineStart); return true;
      case 'k': this.setInput(t, v.slice(0, s) + v.slice(lineEnd), s); return true;
      case 'w': { const from = v.slice(lineStart, s).replace(/\S+\s*$/, '').length + lineStart; this.setInput(t, v.slice(0, from) + v.slice(s), from); return true; }
      case 'a': i.setSelectionRange(lineStart, lineStart); return true;
      case 'e': i.setSelectionRange(lineEnd, lineEnd); return true;
      case 'd': if (!v) { this.setInput(t, 'exit'); t.view.run.form.requestSubmit(); } else this.setInput(t, v.slice(0, s) + v.slice(s + 1), s); return true;
      default: return false;
    }
  }
  keydown(event, t, form) {
    if (event.isComposing) return;
    if (event.ctrlKey && !event.metaKey && !event.altKey && this.shortcut(event, t)) { event.preventDefault(); return; }
    // Tab completes like bash (Shift+Tab still moves focus)
    if (event.key === 'Tab' && !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey && window.Completion) {
      event.preventDefault(); this.tabComplete(t); return;
    }
    if (event.key === 'Enter' && !event.shiftKey && !this.needsMore(t.view.input.value)) { event.preventDefault(); form.requestSubmit(); }
    if (['ArrowUp', 'ArrowDown'].includes(event.key) && !event.shiftKey && !event.altKey && !t.view.input.value.includes('\n') && t.history.length) {
      event.preventDefault();
      if (t.historyIndex === t.history.length) t.savedDraft = t.view.input.value;
      t.historyIndex = Math.max(0, Math.min(t.history.length, t.historyIndex + (event.key === 'ArrowUp' ? -1 : 1)));
      this.setInput(t, t.historyIndex === t.history.length ? t.savedDraft : t.history[t.historyIndex]);
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
    t.view.panel.classList.toggle('running', t.phase !== 'idle'); // 실행 중에는 실제처럼 프롬프트가 없다
  }
  render(t) {
    const v = t.view, follow = v.scroll.scrollHeight - v.scroll.scrollTop - v.scroll.clientHeight < 70;
    this.renderHeader(t);
    v.output.replaceChildren();
    t.entries.forEach((entry, i) => {
      if (i < (t.clearedAt || 0)) return; // Ctrl+L, clear
      const command = document.createElement('pre'), prompt = document.createElement('span'); command.className = 'input-line';
      prompt.className = 'prompt'; prompt.textContent = `root@${entry.host}:~# `; command.append(prompt, entry.text.split('\n').join('\n> '));
      const response = this.splitResponse(entry.response), output = document.createElement('pre'); output.textContent = this.screenText(response.console, entry);
      v.output.append(command); if (output.textContent) v.output.append(output);
      if (response.note && i < t.entries.length - 1) { const note = document.createElement('div'); note.className = 'response-note'; note.textContent = response.note; v.output.append(note); }
    });
    v.note.textContent = t.entries.length ? this.splitResponse(t.entries.at(-1).response).note : '';
    this.renderStatus(t);
    if (follow) v.scroll.scrollTop = v.scroll.scrollHeight;
  }
  enqueue(t) {
    if (this.locked || this.isExpired() || t.phase !== 'idle') return;
    const text = t.view.input.value.trim();
    if (!text) { this.local(t, ''); return; } // 빈 Enter 는 새 프롬프트만
    const edit = text.match(/^(?:sudo\s+)?(vim|vi|nano)\s+(\S+)$/);
    if (edit && window.TermEditor && window.CM && this.api.readFile) { this.edit(t, text, edit[1], edit[2]); return; }
    if (text === 'clear') { t.history.push(text); t.historyIndex = t.history.length; t.clearedAt = t.entries.length; this.setInput(t, ''); this.render(t); return; }
    t.draft = t.view.input.value; t.phase = 'queued'; t.status = '대기 중 — 앞선 터미널 응답을 기다립니다.';
    this.queue.push({t, text}); this.renderStatus(t); this.lock(this.locked); this.onPending();
    return this.drain();
  }
  // vim · nano 는 Claude 대신 터미널 창 안 편집기로 연다. 저장은 편집기가 서버에 바로 쓴다
  edit(t, text, mode, path) {
    t.history.push(text); t.historyIndex = t.history.length;
    const entry = {text, host: t.host, response: '', local: true};
    t.entries.push(entry); this.setInput(t, '');
    t.phase = 'editing'; t.status = ''; t.view.panel.classList.add('editing');
    this.render(t); this.lock(this.locked); this.onPending();
    window.TermEditor.open({pane: t.view.panel, host: t.host, path, mode: mode === 'nano' ? 'nano' : 'vim', api: this.api,
      onClose: ({error} = {}) => {
        if (error) entry.response = error;
        t.phase = 'idle'; t.view.panel.classList.remove('editing');
        this.render(t); this.lock(this.locked); this.onPending(); t.view.input.focus();
      }});
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
          this.setInput(t, ''); t.status = '';
        } catch (error) { entry.response += `\nError: ${error.message}`; t.status = '오류 — 입력을 보존했습니다. 다시 실행하세요.'; this.applyResponse(t, entry.response); this.onWindows(); this.onError(error.message); this.render(t); }
        finally { this.onEvent('cmd', {n: this.question.n, terminal: t.n, host: entry.host, text, response: entry.response}); clearInterval(interval); t.phase = 'idle'; this.state.terminals.forEach(item => { this.renderHeader(item); this.renderStatus(item); }); this.lock(this.locked); }
      }
    } finally { this.processing = false; this.onPending(); }
  }
};
