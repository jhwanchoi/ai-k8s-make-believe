/* Read-only exam history; no storage or exam API calls. */
(function () {
  'use strict';
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const integer = value => Number.isSafeInteger(value) && value >= 0;
  function valid(record) {
    return record && typeof record.exam === 'string' && record.exam.trim() !== '' &&
      integer(record.attempt) && record.attempt > 0 &&
      finite(record.started_at) && record.started_at >= 0 &&
      finite(record.ended_at) && record.ended_at >= record.started_at &&
      !Number.isNaN(new Date(record.ended_at * 1000).getTime()) &&
      finite(record.total) && record.total >= 0 && record.total <= 100 &&
      typeof record.passed === 'boolean' && Array.isArray(record.problems) &&
      record.problems.length > 0 && record.problems.every(problem => problem &&
        integer(problem.n) && problem.n > 0 && typeof problem.domain === 'string' &&
        finite(problem.weight) && problem.weight > 0 && problem.weight <= 100 &&
        finite(problem.score) && problem.score >= 0 && problem.score <= problem.weight &&
        integer(problem.cmd_count)) &&
      new Set(record.problems.map(problem => problem.n)).size === record.problems.length;
  }
  function parseAttempts(text) {
    const groups = new Map();
    let skipped = 0;
    for (const line of text.replace(/^\uFEFF/, '').split(/\r?\n/)) {
      if (!line.trim()) continue;
      try {
        const record = JSON.parse(line);
        if (!valid(record)) throw new Error('Invalid record');
        if (!groups.has(record.exam)) groups.set(record.exam, []);
        groups.get(record.exam).push(record);
      } catch { skipped++; }
    }
    return {groups: Array.from(groups, ([exam, attempts]) => ({exam,
      attempts: attempts.sort((a, b) => a.attempt - b.attempt)})), skipped};
  }
  function scoreTrend(score, previous) {
    return previous == null || score === previous ? '' : score > previous ? ' ▲' : ' ▼';
  }
  function renderAttempts(container, parsed) {
    const node = (tag, text) => {
      const element = document.createElement(tag);
      if (text !== undefined) element.textContent = text;
      return element;
    };
    const summary = (record, trend = '') => `${record.total}%${trend} · ${record.passed ? '합격' : '불합격'}\n${new Date(record.ended_at * 1000).toLocaleString('ko-KR')}\n${Math.round((record.ended_at - record.started_at) / 60 * 10) / 10}분`;
    container.replaceChildren();
    if (parsed.skipped) container.append(node('p', `${parsed.skipped}줄을 읽지 못했습니다`));
    if (!parsed.groups.length) container.append(node('p', '표시할 차시 기록이 없습니다.'));
    for (const {exam, attempts} of parsed.groups) {
      const section = node('section'); section.className = 'attempt-group';
      section.append(node('h3', `${exam === 'auto' ? '자동 출제' : exam.split(/[\\/]/).pop()} · ${attempts.length}차시 기록`));
      section.append(node('p', exam));
      if (exam === 'auto') {
        section.append(node('p', '자동 출제는 차시마다 문제가 달라 총점만 표시합니다.'));
        const list = node('ul');
        attempts.forEach(record => list.append(node('li', `${record.attempt}차시 · ${summary(record)}`)));
        section.append(list);
      } else {
        const scroll = node('div'); scroll.className = 'attempt-table'; scroll.tabIndex = 0;
        const table = node('table');
        table.append(node('caption', '문항별 점수 / 배점 · ▲ 상승 · ▼ 하락 (직전 차시 대비)'));
        const head = node('thead'), heading = node('tr'), first = node('th', '문항'); first.scope = 'col';
        heading.append(first);
        attempts.forEach(record => { const th = node('th', `${record.attempt}차시`); th.scope = 'col'; heading.append(th); });
        head.append(heading); table.append(head);
        const body = node('tbody');
        const numbers = [...new Set(attempts.flatMap(record => record.problems.map(problem => problem.n)))].sort((a, b) => a - b);
        for (const number of numbers) {
          const row = node('tr'), last = attempts.at(-1).problems.find(problem => problem.n === number);
          const label = node('th', `Q${number}${last && last.score < last.weight ? ' · 다시 볼 문항' : ''}`); label.scope = 'row'; row.append(label);
          attempts.forEach((record, index) => {
            const problem = record.problems.find(item => item.n === number);
            const previous = attempts[index - 1]?.problems.find(item => item.n === number);
            const cell = node('td', problem ? `${problem.score} / ${problem.weight}${scoreTrend(problem.score, previous?.score)}` : '—');
            if (problem) cell.append(node('small', `명령 ${problem.cmd_count}회`));
            row.append(cell);
          });
          body.append(row);
        }
        table.append(body);
        const foot = node('tfoot'), total = node('tr'), label = node('th', '총점 · 결과 · 종료 일시 · 소요 시간'); label.scope = 'row'; total.append(label);
        attempts.forEach((record, index) => total.append(node('td', summary(record, scoreTrend(record.total, attempts[index - 1]?.total)))));
        foot.append(total); table.append(foot); scroll.append(table); section.append(scroll);
      }
      container.append(section);
    }
  }
  if (typeof window !== 'undefined') window.AttemptsUI = {parseAttempts, renderAttempts};
  if (typeof module !== 'undefined' && module.exports) module.exports = {parseAttempts, scoreTrend, renderAttempts};
  if (typeof document !== 'undefined') {
    const input = document.getElementById('attempts-file');
    const results = document.getElementById('attempts-results');
    let selection = 0;
    document.getElementById('open-attempts').addEventListener('click', () => input.click());
    input.addEventListener('change', async () => {
      const current = ++selection, file = input.files[0];
      if (!file) return;
      results.textContent = '차시 기록을 읽는 중입니다.';
      if (/\.setup\.md$/.test(file.name) || ((file.webkitRelativePath || '').split('/').includes('.cka') && file.name !== 'exam-attempts.jsonl')) { results.textContent = '환경 및 내부 파일은 읽지 않습니다.'; return; }
      if (file.size > 1024 * 1024) { results.textContent = '1MiB 이하의 파일을 선택하세요.'; return; }
      try {
        const text = await file.text();
        if (current === selection) renderAttempts(results, parseAttempts(text));
      } catch { if (current === selection) results.textContent = '차시 기록 파일을 읽지 못했습니다.'; }
    });
  }
})();
