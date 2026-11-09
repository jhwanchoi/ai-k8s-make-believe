/* One browser window inside the mock desktop; never an automatic document picker. */
window.DesktopUI = class {
  constructor({terminals}) {
    this.terminals = terminals;
    this.$ = id => document.getElementById(id);
    this.url = 'https://kubernetes.io/docs'; this.externalWindow = null; this.browserRatio = 50;
    this.$('application-terminal').onclick = () => { terminals.add(); this.$('applications-menu').open = false; };
    this.$('application-firefox').onclick = this.$('firefox-task').onclick = () => this.openFirefox();
    this.$('close-firefox').onclick = () => this.closeFirefox();
    this.$('open-browser').onclick = () => this.openExternal();
    this.$('browser-form').onsubmit = event => { event.preventDefault(); this.navigate(this.$('browser-address').value); };
    this.$('browser-back').onclick = () => this.history('back');
    this.$('browser-forward').onclick = () => this.history('forward');
    this.$('browser-reload').onclick = () => this.reload();
    this.$('browser-frame').onload = () => { this.status('문서 로드 이벤트 수신 · 내부 링크 이동은 주소창에 반영되지 않습니다. 표시되지 않으면 새 창으로 여세요.'); };
    this.resizeBrowser();
    const clock = () => { const now = new Date(); this.$('desktop-clock').textContent = now.toLocaleTimeString('ko-KR', {hour: '2-digit', minute: '2-digit', hour12: false}); this.$('desktop-clock').dateTime = now.toISOString(); };
    clock(); setInterval(clock, 1000);
    // Native details keep menus keyboard accessible; Escape/outside click close them.
    document.addEventListener('keydown', event => { if (event.key === 'Escape') document.querySelectorAll('.menu').forEach(menu => { if (menu.open) { menu.open = false; menu.querySelector('summary').focus(); } }); });
    document.addEventListener('click', event => { document.querySelectorAll('.menu').forEach(menu => { if (!menu.contains(event.target)) menu.open = false; }); });
  }
  status(text) { this.$('browser-status').textContent = text; }
  syncTerminals() {
    const container = this.$('window-buttons'); container.replaceChildren();
    for (const t of this.terminals.state.terminals) {
      const button = document.createElement('button'); button.textContent = `Terminal ${t.n} — ${t.host}`;
      button.onclick = () => { this.terminals.state.active = t.n; this.terminals.highlight(); this.terminals.focus(); };
      container.append(button);
    }
    this.$('application-terminal').disabled = this.terminals.addButton.disabled;
  }
  openFirefox() {
    this.$('firefox-window').hidden = false;
    this.$('desktop-windows').classList.remove('firefox-closed');
    this.$('firefox-task').setAttribute('aria-pressed', 'true');
    this.$('applications-menu').open = false;
    if (!this.$('browser-frame').getAttribute('src')) this.navigate(this.url);
    this.$('browser-address').focus();
  }
  closeFirefox() {
    this.$('firefox-window').hidden = true;
    this.$('desktop-windows').classList.add('firefox-closed');
    this.$('firefox-task').setAttribute('aria-pressed', 'false');
  }
  navigate(value) {
    try {
      const url = new URL(value);
      if (!['https:', 'http:'].includes(url.protocol)) throw Error('unsupported protocol');
      this.url = url.href; this.$('browser-address').value = this.url;
      this.$('browser-frame').src = this.url;
      this.$('browser-fallback-link').href = this.url;
      this.$('firefox-title').textContent = `Firefox — ${url.hostname}`;
      this.status('문서 로딩 중… 내부 링크의 현재 주소는 읽을 수 없습니다.');
    } catch { this.status('http:// 또는 https://로 시작하는 올바른 주소를 입력하세요.'); }
  }
  history(direction) {
    try { this.$('browser-frame').contentWindow.history[direction](); }
    catch { this.status('교차 출처 보안으로 이 문서의 뒤로/앞으로 이동이 제한됩니다. 새 창에서 이용하세요.'); }
  }
  reload() {
    try { this.$('browser-frame').contentWindow.location.reload(); }
    catch { this.$('browser-frame').src = this.url; this.status('교차 출처 제한으로 주소창에 입력한 주소를 다시 불러옵니다.'); }
  }
  openExternal() {
    try {
      if (!this.externalWindow || this.externalWindow.closed || this.externalUrl !== this.url) {
        this.externalWindow = window.open(this.url, 'cka-docs'); this.externalUrl = this.url;
      }
      const blocked = !this.externalWindow || this.externalWindow.closed;
      this.$('browser-fallback').hidden = !blocked;
      if (!blocked) this.externalWindow.focus();
    } catch { this.$('browser-fallback').hidden = false; }
  }
  resizeBrowser() {
    const divider = this.$('split-browser'), area = this.$('desktop-windows');
    const apply = next => { this.browserRatio = Math.max(25, Math.min(70, next)); area.style.setProperty('--terminal-width', `${this.browserRatio}%`); divider.setAttribute('aria-valuenow', Math.round(this.browserRatio)); };
    divider.onpointerdown = event => {
      const x = event.clientX, initial = this.browserRatio; divider.setPointerCapture(event.pointerId);
      divider.onpointermove = e => apply(initial + (e.clientX - x) / area.clientWidth * 100);
      divider.onpointerup = divider.onpointercancel = () => { divider.onpointermove = null; };
    };
    divider.onkeydown = event => { if (['ArrowLeft', 'ArrowRight'].includes(event.key)) { event.preventDefault(); apply(this.browserRatio + (event.key === 'ArrowRight' ? 2 : -2)); } };
  }
};
