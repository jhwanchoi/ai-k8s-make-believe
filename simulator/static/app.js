/* All transport is in mock-api.js. DOM content is always written as text. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const api = window.MockAPI;
  let exam, selectedFile, selectedAnswers = null, answerCount = 0, readingAnswers = false, busy = false, expired = false, timer;
  let preferences = {}, storageKey = '';
  let elapsedInterval, waitStarted;
  const notice = text => { $('notice').textContent = text; };
  function screen(id) {
    for (const name of ['start', 'exam', 'report']) $(name).hidden = name !== id;
    $('exam-menus').hidden = id !== 'exam';
    document.querySelectorAll('.menu').forEach(menu => { menu.open = false; });
  }
  const current = () => exam.problems[exam.current - 1];
  const terminals = new window.TerminalWorkspace({
    api, container: $('terminal-workspace'), addButton: $('add-terminal'),
    onPending: () => { setBusy(busy); tick(); if (expired) $('confirm-end').disabled = busy || terminals.pending; },
    onContext: context => { current().context = context; }, onError: notice,
    isExpired: () => expired
  });
  const desktop = new window.DesktopUI({terminals});
  terminals.onWindows = () => desktop.syncTerminals();
  const occupied = () => busy || terminals.pending;
  function setBusy(value, message = '') {
    busy = value;
    for (const id of ['prev', 'next', 'jump', 'end', 'submit-question']) $(id).disabled = occupied() || expired;
    $('prev').disabled ||= exam?.current === 1;
    $('next').disabled ||= exam?.current === exam?.problems.length;
    terminals.lock(busy);
    if (terminals.state) desktop.syncTerminals();
    $('command-status').textContent = message || (expired ? '시간 만료' : terminals.pending ? '명령 처리 중' : '가상 환경');
    clearInterval(elapsedInterval);
    if (value) {
      waitStarted = Date.now();
      elapsedInterval = setInterval(() => { $('command-status').textContent = `${message} · ${Math.floor((Date.now() - waitStarted) / 1000)}초 경과`; }, 1000);
    }
  }
  function savePreferences() {
    preferences[exam.current] = {note: $('notes').value, flag: $('flag').checked};
    try { localStorage.setItem(storageKey, JSON.stringify(preferences)); }
    catch { notice('브라우저 저장소를 사용할 수 없어 메모와 플래그는 현재 화면에서만 유지됩니다.'); }
    updateFlags();
  }
  function updateFlags() {
    for (const p of exam.problems) {
      const flag = preferences[p.n]?.flag;
      const status = p.meta.submitted ? '제출함' : p.visited ? '풀이 중' : '미방문';
      $('jump').options[p.n - 1].textContent = `Q${p.n} · ${status}${flag ? ' · 🚩 나중에 보기' : ''}`;
    }
  }
  function renderQuestion() {
    const p = current();
    $('submit-status').textContent = p.meta.submitted ? '제출 기록됨' : '';
    $('question-heading').textContent = `Question ${p.n}`;
    $('metadata').textContent = `${p.domain} · 배점 ${p.weight}%`;
    $('problem').textContent = p.text;
    $('jump').value = p.n;
    $('notes').value = preferences[p.n]?.note || '';
    $('flag').checked = !!preferences[p.n]?.flag;
    terminals.show(p); updateFlags(); setBusy(false);
  }
  async function start(file, answers = null) {
    if (answers && readingAnswers) return;
    if (!$('minutes').reportValidity()) return;
    $('start-file').disabled = $('start-example').disabled = $('file').disabled = $('answers-file').disabled = true;
    $('report-rows').replaceChildren();
    notice('가상 시험 환경을 준비하고 있습니다. 약 1~3초 걸립니다.');
    try {
      exam = await api.startExam({file, answers, minutes: Number($('minutes').value)});
      terminals.reset(); desktop.closeFirefox(); expired = false; preferences = {};
      storageKey = `k12s-notes:${file.text}`;
      try { const data = JSON.parse(localStorage.getItem(storageKey) || '{}'); if (data && typeof data === 'object') preferences = data; }
      catch { notice('저장된 메모를 불러올 수 없습니다.'); }
      $('jump').replaceChildren(...exam.problems.map(p => new Option(`Q${p.n}`, p.n)));
      screen('exam'); renderQuestion(); tick(); timer = setInterval(tick, 250);
      notice('목업 모드 · 응답과 점수는 고정 예시입니다. 실제 명령을 실행하지 않습니다.');
      terminals.focus();
    } catch (error) { notice(error.message); }
    finally { $('start-file').disabled = !selectedFile; $('start-example').disabled = $('file').disabled = $('answers-file').disabled = false; }
  }
  function tick() {
    if (!exam || exam.ended) return;
    const seconds = Math.max(0, Math.ceil(exam.ends_at - Date.now() / 1000));
    const ratio = Math.max(0, Math.min(100, seconds / (exam.ends_at - exam.started_at) * 100));
    $('time-fill').style.width = `${ratio}%`;
    $('time-progress').setAttribute('aria-valuenow', Math.round(ratio));
    $('timer').textContent = `${Math.ceil(seconds / 60)} minutes · ${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    $('time-progress').className = 'time-progress ' + (seconds <= 300 ? 'critical' : seconds <= 600 ? 'warn' : '');
    if (!seconds && !expired) {
      expired = true; clearInterval(timer); setBusy(busy, occupied() ? '진행 중 응답을 마무리하고 있습니다.' : '');
      showEnd(true);
    }
  }
  async function goto(n) {
    if (occupied() || expired || n < 1 || n > exam.problems.length || n === exam.current) return;
    setBusy(true, '문항을 불러오고 있습니다');
    try { exam = await api.gotoExam({n}); renderQuestion(); $('question-heading').tabIndex = -1; $('question-heading').focus(); }
    catch (error) { notice(error.message); $('jump').value = exam.current; }
    finally { setBusy(false); tick(); if (expired) $('confirm-end').disabled = false; }
  }
  function showEnd(timedOut = false) {
    $('end-title').textContent = timedOut ? '시험 시간이 만료되었습니다' : '시험을 종료할까요?';
    const flags = Object.values(preferences).filter(p => p?.flag).length;
    $('end-description').textContent = timedOut ? '입력이 잠겼습니다. 진행 중 응답이 끝나면 리포트를 확인하세요.' : `나중에 보기 ${flags}문항이 있습니다. 종료 후 풀이로 돌아갈 수 없습니다.`;
    $('cancel-end').hidden = timedOut; $('confirm-end').disabled = occupied();
    $('end-status').textContent = '';
    if (!$('end-dialog').open) $('end-dialog').showModal();
  }
  async function end() {
    if (occupied()) return;
    setBusy(true, '목업 리포트를 준비하고 있습니다');
    $('confirm-end').disabled = $('cancel-end').disabled = true;
    $('end-status').textContent = '채점 중… 약 1~3초 걸립니다.';
    try {
      const result = await api.endExam(); exam.ended = true; clearInterval(timer);
      $('score').textContent = `${result.total}%`;
      $('result').textContent = result.passed ? '합격 (목업)' : '불합격 (목업)';
      $('report-rows').replaceChildren();
      const domains = new Map();
      for (const p of result.problems) {
        const row = document.createElement('tr');
        for (const value of [`Q${p.n}`, p.domain, `${p.score} / ${p.weight}`]) { const cell = document.createElement('td'); cell.textContent = value; row.append(cell); }
        appendAnswer(row, p, result.hasAnswers);
        $('report-rows').append(row);
        const d = domains.get(p.domain) || {score: 0, weight: 0}; d.score += p.score; d.weight += p.weight; domains.set(p.domain, d);
      }
      $('weaknesses').replaceChildren();
      for (const [name, d] of domains) {
        const line = document.createElement('p'); const ratio = Math.round(d.score / d.weight * 100);
        line.textContent = `${name} · ${ratio}% — ${ratio < 66 ? '추가 연습이 필요한 도메인입니다.' : '예시 기준으로 안정적인 도메인입니다.'}`;
        $('weaknesses').append(line);
      }
      $('end-dialog').close(); screen('report'); notice('목업 데이터 · 실제 채점 결과가 아닙니다.');
      $('report').tabIndex = -1; $('report').focus();
    } catch (error) { $('end-status').textContent = `${error.message} 다시 시도하세요.`; }
    finally { setBusy(false); $('confirm-end').disabled = $('cancel-end').disabled = false; }
  }
  function appendAnswer(row, problem, hasAnswers) {
    const cell = document.createElement('td'); row.append(cell);
    if (!problem.answer) {
      const note = document.createElement('span'); note.className = 'answer-unavailable';
      note.textContent = hasAnswers ? '이 문항의 풀이가 없습니다' : '풀이 파일을 고르지 않았습니다'; cell.append(note); return;
    }
    const button = document.createElement('button'); button.textContent = '풀이 보기';
    button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-controls', `answer-q${problem.n}`);
    cell.append(button);
    let detail;
    button.onclick = () => {
      if (!detail) {
        detail = document.createElement('tr'); detail.id = `answer-q${problem.n}`; detail.className = 'answer-row';
        const content = document.createElement('td'); content.colSpan = 4;
        const pre = document.createElement('pre'), code = document.createElement('code'); code.textContent = problem.answer.bash; pre.append(code);
        const source = document.createElement('a'); source.textContent = `원본: ${problem.answer.source.label}`;
        source.href = problem.answer.source.url; source.target = '_blank'; source.rel = 'noopener noreferrer';
        content.append(pre, source); detail.append(content); row.after(detail);
      } else detail.hidden = !detail.hidden;
      button.setAttribute('aria-expanded', !detail.hidden); button.textContent = detail.hidden ? '풀이 보기' : '풀이 닫기';
    };
  }
  function previewAnswers() {
    if (!selectedAnswers) return;
    let count;
    if (selectedFile) count = api.parseFile(selectedFile.text).problems.length;
    $('answers-preview').textContent = `풀이 ${answerCount}문항 · 내용은 시험 종료 후에만 공개됩니다.` +
      (count !== undefined && count !== answerCount ? ` 경고: 문제 ${count}문항과 풀이 개수가 다릅니다. 시작은 가능합니다.` : '');
    $('answers-preview').classList.toggle('warning', count !== undefined && count !== answerCount);
  }
  $('answers-file').onchange = async () => {
    const file = $('answers-file').files[0]; selectedAnswers = null; answerCount = 0;
    $('answers-preview').classList.remove('warning');
    if (!file) { $('answers-preview').textContent = '선택하지 않아도 시작할 수 있습니다. 풀이는 종료 후에만 표시됩니다.'; return; }
    readingAnswers = true; $('answers-preview').textContent = '풀이 파일 형식을 확인하고 있습니다…';
    try {
      if (file.size > 1024 * 1024) throw Error('풀이 파일은 1MiB 이하로 선택하세요.');
      const text = await file.text();
      if ($('answers-file').files[0] !== file) return;
      answerCount = api.parseAnswers(text).length; selectedAnswers = {name: file.name, text}; previewAnswers();
    } catch (error) { $('answers-preview').textContent = `${error.message} 풀이 없이 시작할 수 있습니다.`; }
    finally { readingAnswers = false; }
  };
  async function submitQuestion() {
    tick();
    if (occupied() || expired) return;
    setBusy(true, '문항 제출을 기록하고 있습니다');
    $('submit-status').textContent = '제출 기록 중…';
    try {
      const result = await api.submit();
      exam = result.exam;
      $('submit-status').textContent = result.message;
      notice(result.message); updateFlags();
    } catch (error) { $('submit-status').textContent = error.message; }
    finally {
      setBusy(false); tick();
      if (expired) $('confirm-end').disabled = false;
    }
  }
  $('submit-question').onclick = () => { $('controls-menu').open = false; return submitQuestion(); };
  $('file').onchange = async () => {
    const file = $('file').files[0]; selectedFile = null; $('start-file').disabled = true;
    if (!file) { previewAnswers(); return; }
    try {
      if (file.size > 1024 * 1024) throw Error('문제 파일은 1MiB 이하로 선택하세요.');
      const text = await file.text(); const parsed = api.parseFile(text);
      selectedFile = {name: file.name, text};
      $('preview').textContent = `${parsed.title}\n${parsed.problems.length}문항 · 총 배점 100%\n` + parsed.problems.map(p => `Q${p.n} · ${p.domain} · ${p.weight}%`).join('\n');
      $('start-file').disabled = false; notice('문제 파일을 확인했습니다.'); previewAnswers();
    } catch (error) { $('preview').textContent = error.message; notice(error.message); previewAnswers(); }
  };
  $('start-file').onclick = () => { if (readingAnswers) { notice('풀이 파일 확인이 끝난 뒤 시작하세요.'); return; } return start(selectedFile, selectedAnswers); };
  $('start-example').onclick = () => start(api.exampleFile());
  $('notes').oninput = $('flag').onchange = savePreferences;
  $('prev').onclick = () => goto(exam.current - 1); $('next').onclick = () => goto(exam.current + 1);
  $('jump').onchange = () => goto(Number($('jump').value));
  document.addEventListener('keydown', e => {
    if (e.altKey && e.shiftKey && e.code === 'KeyT' && !$('exam').hidden && !$('end-dialog').open) { e.preventDefault(); terminals.switchTerminal(); return; }
    if (!e.altKey || !['ArrowLeft', 'ArrowRight'].includes(e.key) || $('exam').hidden || $('end-dialog').open) return;
    e.preventDefault(); goto(exam.current + (e.key === 'ArrowRight' ? 1 : -1));
  });
  $('end').onclick = () => { $('controls-menu').open = false; showEnd(); }; $('cancel-end').onclick = () => { $('end-dialog').close(); $('end').focus(); };
  $('confirm-end').onclick = end;
  $('end-dialog').addEventListener('cancel', e => { if (expired || occupied()) e.preventDefault(); });
  $('restart').onclick = () => { screen('start'); exam = null; $('report-rows').replaceChildren(); notice(''); $('start-example').focus(); };
  function resize(id, property, initial, min, max, sign) {
    let value = initial;
    function apply(next) { value = Math.max(min, Math.min(max, next)); $('workspace').style.setProperty(property, `${value}%`); $(id).setAttribute('aria-valuenow', Math.round(value)); }
    $(id).onpointerdown = e => {
      const x = e.clientX, origin = value; $(id).setPointerCapture(e.pointerId);
      $(id).onpointermove = event => apply(origin + sign * (event.clientX - x) / $('workspace').clientWidth * 100);
      $(id).onpointerup = $(id).onpointercancel = () => { $(id).onpointermove = null; };
    };
    $(id).onkeydown = e => { if (['ArrowLeft', 'ArrowRight'].includes(e.key)) { e.preventDefault(); apply(value + sign * (e.key === 'ArrowRight' ? 2 : -2)); } };
  }
  resize('split-one', '--q', 28, 18, 50, 1);
  window.addEventListener('beforeunload', e => { if (exam && !exam.ended) { e.preventDefault(); e.returnValue = ''; } });
})();
