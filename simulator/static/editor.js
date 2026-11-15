/* 웹 터미널의 vim · vi · nano 화면 편집기. Claude 를 부르지 않는다.
 * open({pane, host, path, mode: 'vim'|'nano', api, onClose}) — 터미널 창 안을 편집기로 바꾸고, 닫히면 onClose({error}).
 * 파일은 api.readFile 로 읽고 api.writeFile 로 저장한다(서버 모드: state.json, 목업: 메모리).
 * 실제 시험처럼 INSERT 키는 막고(i 로 입력 모드), ~/.vimrc 의 expandtab · tabstop · shiftwidth · number 를 따른다.
 * 편집기 코드는 vendor/codemirror-vim.js (window.CM).
 */
window.TermEditor = (() => {
  let active = null; // 지금 열린 편집기 (vim ex 명령은 전역이라 여기로 보낸다)

  function vimrcOptions(text) {
    let expand = false, tabSize = 8, shift = 0, number = false;
    for (const line of (text || '').split('\n')) {
      const m = line.trim().match(/^(?:set|se)\s+(.+)$/);
      if (!m) continue;
      for (const opt of m[1].split(/\s+/)) {
        if (/^(expandtab|et)$/.test(opt)) expand = true;
        else if (/^(noexpandtab|noet)$/.test(opt)) expand = false;
        else if (/^(number|nu)$/.test(opt)) number = true;
        else if (/^(nonumber|nonu)$/.test(opt)) number = false;
        const ts = opt.match(/^(?:tabstop|ts)=(\d+)$/), sw = opt.match(/^(?:shiftwidth|sw)=(\d+)$/);
        if (ts) tabSize = Math.max(1, Math.min(16, +ts[1]));
        if (sw) shift = Math.max(1, Math.min(16, +sw[1]));
      }
    }
    return {tabSize, unit: expand ? ' '.repeat(shift || tabSize) : '\t', number};
  }

  let defined = false;
  function defineVimCommands(Vim) {
    if (defined) return;
    defined = true;
    const force = params => /!\s*$/.test(params.input || '') || (params.argString || '').trim() === '!';
    Vim.defineEx('write', 'w', () => active && active.save());
    Vim.defineEx('wq', 'wq', () => active && active.save().then(ok => ok && active && active.close()));
    Vim.defineEx('xit', 'x', () => active && (active.dirty() ? active.save().then(ok => ok && active && active.close()) : active.close()));
    Vim.defineEx('quit', 'q', (cm, params) => {
      if (!active) return;
      if (active.dirty() && !force(params)) active.message('E37: No write since last change (add ! to override)');
      else active.close();
    });
  }

  function open({pane, host, path, mode, api, onClose}) {
    const CM = window.CM, nano = mode === 'nano';
    const box = document.createElement('div');
    box.className = `term-editor${nano ? ' nano' : ''}`;
    box.setAttribute('role', 'region'); box.setAttribute('aria-label', `${nano ? 'nano' : 'vim'} ${path}`);
    const title = document.createElement('div'), body = document.createElement('div'), msg = document.createElement('div'), help = document.createElement('div');
    title.className = 'term-editor-title'; body.className = 'term-editor-body'; msg.className = 'term-editor-msg'; help.className = 'term-editor-help';
    if (nano) {
      title.innerHTML = '<span>GNU nano 7.2</span><span class="name"></span><span class="mod"></span>';
      title.querySelector('.name').textContent = path;
      help.innerHTML = '<span><b>^O</b> Write Out</span><span><b>^X</b> Exit</span>';
      box.append(title, body, msg, help);
    } else box.append(body);
    pane.append(box);

    let view = null, saved = '', file = null, asking = false, closed = false;
    const finish = (result = {}) => {
      if (closed) return;
      closed = true;
      if (view) view.destroy();
      box.remove();
      if (active === editor) active = null;
      onClose(result);
    };
    const message = text => {
      if (nano || !view) { msg.textContent = text; return; }
      const span = document.createElement('span'); span.textContent = text;
      CM.getCM(view).openNotification(span, {bottom: true, duration: 5000});
    };
    const stats = text => `${text ? text.split('\n').length - (text.endsWith('\n') ? 1 : 0) : 0}L, ${new TextEncoder().encode(text).length}B`;
    const editor = {
      dirty: () => !!view && view.state.doc.toString() !== saved,
      message,
      close: () => finish(),
      save: () => {
        const text = view.state.doc.toString();
        return api.writeFile({host, path: file.path, text, editor: nano ? 'nano' : mode})
          .then(() => {
            saved = text; updateTitle();
            message(nano ? `[ Wrote ${text.split('\n').length - (text.endsWith('\n') ? 1 : 0)} lines ]` : `"${path}" ${stats(text)} written`);
            return true;
          })
          .catch(error => { message(`E212: Can't open file for writing (${error.message})`); return false; });
      },
    };
    const updateTitle = () => { if (nano) title.querySelector('.mod').textContent = editor.dirty() ? 'Modified' : ''; };
    const nanoExit = () => {
      if (!editor.dirty()) { finish(); return; }
      asking = true; msg.textContent = 'Save modified buffer?  Y Yes  N No  ^C Cancel';
    };

    // 실제 시험 원격 데스크톱처럼 INSERT 키는 막는다 (i 로 입력 모드). 편집 중 키가 시험 화면 단축키로 새지 않게 한다
    box.addEventListener('keydown', event => {
      if (event.key === 'Insert') { event.preventDefault(); event.stopPropagation(); return; }
      if (asking) {
        event.preventDefault(); event.stopPropagation();
        const key = event.key.toLowerCase();
        if (key === 'y') { asking = false; editor.save().then(ok => ok && finish()); }
        else if (key === 'n') { asking = false; finish(); }
        else if (key === 'escape' || (event.ctrlKey && key === 'c')) { asking = false; msg.textContent = ''; }
      }
    }, true);
    box.addEventListener('keydown', event => event.stopPropagation());

    api.readFile({host, path}).then(got => {
      if (closed) return;
      file = got; saved = got.text || '';
      const opts = vimrcOptions(got.vimrc);
      if (!nano) defineVimCommands(CM.Vim);
      const extensions = [
        ...(nano ? [CM.keymap.of([
          {key: 'Ctrl-o', run: () => { editor.save(); return true; }},
          {key: 'Ctrl-x', run: () => { nanoExit(); return true; }},
        ])] : [CM.vim({status: true})]),
        // 터미널처럼 검은 배경 (oneDark 보다 앞에 둬야 이긴다)
        CM.EditorView.theme({'&': {height: '100%', backgroundColor: '#050505'}, '.cm-gutters': {backgroundColor: '#050505', border: 'none'}}, {dark: true}),
        CM.setup, ...(opts.number ? [CM.lineNumbers()] : []), CM.oneDark,
        CM.indentUnit.of(opts.unit), CM.EditorState.tabSize.of(opts.tabSize),
        ...(/\.ya?ml$/i.test(got.path) ? [CM.yaml()] : []),
        CM.EditorView.updateListener.of(update => { if (update.docChanged) updateTitle(); }),
      ];
      view = new CM.EditorView({state: CM.EditorState.create({doc: saved, extensions}), parent: body});
      active = editor;
      message(nano ? (got.exists ? `[ Read ${stats(saved).split('L')[0]} lines ]` : '[ New File ]') : `"${path}" ${got.exists ? stats(saved) : '[New]'}`);
      view.focus();
    }).catch(error => finish({error: `${nano ? 'nano' : mode}: ${path}: ${error.message}`}));
    return editor;
  }

  return {open, vimrcOptions};
})();
