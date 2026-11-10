/* JSONL is the only durable exam state. Explicit event fields exclude solutions/scores. */
window.ExamLog = class {
  static fields = {start: ['title', 'problemText', 'minutes', 'at'], goto: ['n'], cmd: ['n', 'terminal', 'host', 'text', 'response'], 'terminal-add': ['n', 'terminal'], 'terminal-close': ['n', 'terminal'], submit: ['n'], flag: ['n', 'value'], memo: ['n', 'text'], pause: ['at'], resume: ['at'], end: ['at']};
  static hash(text) {
    let hash = 0x811c9dc5;
    for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 0x01000193) >>> 0;
    return hash.toString(16).padStart(8, '0');
  }
  static findKey(problemText) {
    const base = `k12s-log:${this.hash(problemText)}`;
    for (let n = 1; ; n++) {
      const key = base + (n === 1 ? '' : `-${n}`), text = localStorage.getItem(key);
      if (text === null) return key;
      try { if (this.parse(text)[0].problemText === problemText) return key; }
      catch { return key; } // Keep unreadable records visible for download/discard.
    }
  }
  static parse(log) {
    const events = typeof log === 'string' ? log.trim().split('\n').filter(Boolean).map(line => JSON.parse(line)) : log;
    if (!Array.isArray(events) || events[0]?.type !== 'start') throw Error('시험 시작 로그가 없습니다.');
    return events.map((event, i) => {
      const fields = this.fields[event.type];
      if (!fields || event.seq !== i + 1 || !Number.isFinite(Date.parse(event.t))) throw Error('시험 로그 순서나 형식이 올바르지 않습니다.');
      const clean = {type: event.type, seq: event.seq, t: event.t};
      for (const field of fields) { if (!(field in event)) throw Error('시험 로그 필드가 누락되었습니다.'); clean[field] = event[field]; }
      return clean;
    });
  }
  static timing(events, now = Date.now()) {
    let spent = 0, since = null, ended = false;
    for (const e of events) {
      const at = Date.parse(e.at || e.t);
      if (e.type === 'start' || e.type === 'resume') { if (since === null && !ended) since = at; }
      if (e.type === 'pause' || e.type === 'end') {
        if (since !== null) spent += Math.max(0, at - since);
        since = null; if (e.type === 'end') ended = true;
      }
    }
    const elapsed = (spent + (since === null ? 0 : Math.max(0, now - since))) / 1000;
    return {elapsed, remaining: Math.max(0, events[0].minutes * 60 - elapsed), paused: since === null, ended};
  }
  static terminal(n, host) {
    return {n, host, entries: [], history: [], draft: '', historyIndex: 0, savedDraft: '', phase: 'idle', status: '명령을 입력하세요.'};
  }
  static question(p) {
    return {contexts: Object.assign(Object.create(null), p.contexts || {[p.host]: p.context}), defaultContext: p.context, active: 1, ratio: 50, terminals: [this.terminal(1, p.host)]};
  }
  static replay(log, now = Date.now()) {
    const events = this.parse(log), first = events[0], parsed = window.MockAPI.parseFile(first.problemText);
    const exam = {...parsed, started_at: Date.parse(first.at) / 1000, current: 1, ended: false};
    exam.problems.forEach(p => { p.visited = p.n === 1; p.meta = {submitted: false}; });
    const questions = {}, preferences = {};
    const ensure = n => {
      const p = exam.problems[n - 1]; if (!p) throw Error('로그 문항 번호가 올바르지 않습니다.');
      return questions[n] ||= this.question(p);
    };
    ensure(1);
    for (const e of events.slice(1)) {
      if (['goto', 'cmd', 'terminal-add', 'terminal-close', 'submit', 'memo', 'flag'].includes(e.type)) ensure(e.n);
      const q = questions[e.n], p = exam.problems[e.n - 1];
      if (e.type === 'goto') { exam.current = e.n; p.visited = true; }
      if (e.type === 'terminal-add') { if (!q.terminals.some(t => t.n === e.terminal)) q.terminals.push(this.terminal(e.terminal, p.host)); q.terminals.sort((a, b) => a.n - b.n); q.active = e.terminal; }
      if (e.type === 'terminal-close') { q.terminals = q.terminals.filter(t => t.n !== e.terminal); q.active = q.terminals[0]?.n; }
      if (e.type === 'cmd') {
        const t = q.terminals.find(t => t.n === e.terminal); if (!t) throw Error('로그 터미널이 없습니다.');
        t.entries.push({text: e.text, host: e.host, response: e.response}); t.history.push(e.text); t.historyIndex = t.history.length;
        window.TerminalWorkspace.prototype.applyResponse.call({state: q}, t, e.response);
        p.contexts = {...q.contexts};
      }
      if (e.type === 'submit') p.meta.submitted = true;
      if (e.type === 'memo' || e.type === 'flag') {
        const pref = preferences[e.n] ||= {note: '', flag: false};
        if (e.type === 'memo') pref.note = e.text; else pref.flag = e.value;
      }
      if (e.type === 'end') exam.ended = true;
    }
    const timing = this.timing(events, now);
    exam.ends_at = now / 1000 + timing.remaining;
    return {exam, questions, preferences, timing};
  }
  constructor({log = '', onError = () => {}, storageDisabled = false, key = null, expected = undefined, onConflict = () => {}} = {}) {
    this.storageKey = key; this.expected = expected; this.onConflict = onConflict; this.locked = false;
    this.events = log ? window.ExamLog.parse(log) : []; this.onError = onError; this.storageDisabled = storageDisabled; this.pendingMemos = new Map();
  }
  get text() { return this.events.map(e => JSON.stringify(e)).join('\n') + (this.events.length ? '\n' : ''); }
  get key() { return this.storageKey ||= window.ExamLog.findKey(this.events[0].problemText); }
  checkOwner() {
    if (this.locked) return false;
    if (this.storageDisabled || this.expected === undefined) return true;
    if (localStorage.getItem(this.key) === this.expected) return true;
    this.locked = true; clearTimeout(this.memoTimer); this.pendingMemos.clear(); this.onConflict(); return false;
  }
  remaining() { return window.ExamLog.timing(this.events).remaining; }
  persist() {
    try { if (this.storageDisabled) throw Error('memory only'); if (!this.checkOwner()) return; localStorage.setItem(this.key, this.text); this.expected = this.text; }
    catch { this.onError('시험 로그를 저장하지 못했습니다(저장 공간 부족 또는 접근 제한). [로그 내려받기]로 보관하세요.'); }
  }
  append(type, data = {}, persist = true) {
    if (this.locked) return;
    this.flushMemos();
    const fields = window.ExamLog.fields[type]; if (!fields) throw Error('알 수 없는 이벤트');
    const t = new Date().toISOString(), event = {type, seq: this.events.length + 1, t};
    for (const field of fields) event[field] = field === 'at' ? (data.at || t) : data[field];
    this.events.push(event); if (persist) this.persist(); return event;
  }
  memo(n, text) {
    this.pendingMemos.set(n, text); clearTimeout(this.memoTimer);
    this.memoTimer = setTimeout(() => this.flushMemos(), 400);
  }
  flushMemos() {
    clearTimeout(this.memoTimer);
    if (!this.pendingMemos.size) return;
    const pending = [...this.pendingMemos]; this.pendingMemos.clear();
    for (const [n, text] of pending) this.append('memo', {n, text});
  }
  pause() { if (!window.ExamLog.timing(this.events).paused) this.append('pause'); }
  resume() { const time = window.ExamLog.timing(this.events); if (time.paused && !time.ended) this.append('resume'); }
  download() {
    this.flushMemos();
    const url = URL.createObjectURL(new Blob([this.text], {type: 'application/x-ndjson'}));
    const a = document.createElement('a'); a.href = url; a.download = `${this.key.replace(':', '-')}.jsonl`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  static saved(onError = () => {}) {
    const result = [];
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i); if (!key.startsWith('k12s-log:') || key.split(':').length !== 2) continue;
        try {
          const log = localStorage.getItem(key), events = this.parse(log), timing = this.timing(events);
          let broken = false;
          try { this.replay(log); } catch { broken = true; }
          if (!timing.ended || broken) result.push({key, log, events});
        } catch { result.push({key, log: localStorage.getItem(key), events: null}); }
      }
    } catch { onError('저장된 시험 로그에 접근할 수 없습니다.'); }
    return result.sort((a, b) => (b.events?.at(-1).t || '').localeCompare(a.events?.at(-1).t || ''));
  }
  static archive(key) {
    const text = localStorage.getItem(key);
    if (text) {
      const events = this.parse(text);
      if (!this.timing(events).ended) throw Error('진행 중 시험은 먼저 이어 풀거나 버리세요.');
      localStorage.setItem(`${key}:${events[0].t}`, text);
      const archives = [];
      for (let i = 0; i < localStorage.length; i++) {
        const candidate = localStorage.key(i);
        if (candidate.startsWith(`${key}:`)) archives.push(candidate);
      }
      archives.sort();
      for (const oldest of archives.slice(0, -5)) localStorage.removeItem(oldest);
    }
  }
};
