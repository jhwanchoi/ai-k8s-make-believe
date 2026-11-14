/* Server transport: when simulator/server.py serves the page (/config.js sets SIM_SERVER), replace the mock
 * methods with fetch/SSE calls of the same names. Local utilities (parseFile, parseAnswers, exampleFile, bindLog)
 * stay from mock-api.js. Static mode (no config.js) keeps the mock as it is.
 */
(() => {
  if (!window.SIM_SERVER) return;
  const local = window.MockAPI;
  async function call(method, path, body) {
    const res = await fetch(path, {method, headers: {'Content-Type': 'application/json', 'X-Sim': '1'}, body: body === undefined ? undefined : JSON.stringify(body)});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Error(data.error || `서버 오류 (${res.status})`);
    return data;
  }
  window.MockAPI = {
    parseFile: local.parseFile,
    parseAnswers: local.parseAnswers,
    exampleFile: local.exampleFile,
    bindLog: local.bindLog,
    getExam: () => call('GET', '/api/exam'),
    complete: ({host}) => call('GET', `/api/complete?host=${encodeURIComponent(host)}`),
    startExam: ({file, answers = null, minutes}) => call('POST', '/api/exam/start', {file, answers, minutes}),
    gotoExam: ({n}) => call('POST', '/api/exam/goto', {n}),
    submit: () => call('POST', '/api/submit', {}),
    endExam: () => call('POST', '/api/exam/end', {}),
    // Replay stays in the browser (commands are never re-run); the server must still hold the same exam.
    resumeExam: async ({log}) => {
      const restored = window.ExamLog.replay(log);
      if (restored.exam.ended) throw Error('종료한 시험은 이어 풀 수 없습니다.');
      const current = await call('GET', '/api/exam');
      if (!current || current.ended || current.title !== restored.exam.title) throw Error('서버에 이어 풀 시험이 없습니다. 새로 시작하세요.');
      return {...restored, exam: {...restored.exam, ...current}};
    },
    // POST /api/cmd -> SSE: "data: <json string>" deltas, then "event: done" or "event: error".
    async *cmd({text, terminal, host}) {
      // Obvious typos (unknown command, kubectl flag) get the real error without Claude; the server only records them.
      const localOutput = window.CommandCheck ? window.CommandCheck.check(text) : null;
      const payload = localOutput ? {text, terminal, host, local_output: localOutput} : {text, terminal, host};
      const res = await fetch('/api/cmd', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Sim': '1'}, body: JSON.stringify(payload)});
      if (!res.ok) { const data = await res.json().catch(() => ({})); throw Error(data.error || `서버 오류 (${res.status})`); }
      const reader = res.body.getReader(), decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const {value, done} = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
        let cut;
        while ((cut = buffer.indexOf('\n\n')) >= 0) {
          const block = buffer.slice(0, cut); buffer = buffer.slice(cut + 2);
          const event = (block.match(/^event: (.+)$/m) || [])[1] || 'message';
          const data = block.split('\n').filter(l => l.startsWith('data: ')).map(l => l.slice(6)).join('\n');
          if (!data) continue; // ": working" keepalive
          if (event === 'error') throw Error(JSON.parse(data).message);
          if (event === 'done') return;
          yield JSON.parse(data);
        }
        if (done) throw Error('응답이 중간에 끊겼습니다. 다시 실행하세요.');
      }
    },
  };
  document.addEventListener('DOMContentLoaded', () => {
    const badge = document.querySelector('.brand .badge'); if (badge) badge.textContent = 'Claude 시뮬레이션';
    const eyebrow = document.querySelector('#report .eyebrow'); if (eyebrow) eyebrow.textContent = 'EXAM REPORT';
    const desc = document.querySelector('#report > p:not(.eyebrow):not(#actual-time)'); if (desc) desc.textContent = '플러그인 grader 가 루브릭으로 채점한 결과입니다.';
    document.querySelectorAll('#report h2 small').forEach(el => el.remove());
    const note = [...document.querySelectorAll('#direct-files p')].find(el => el.textContent.includes('목업')); if (note) note.textContent = '명령과 채점은 Claude 가 시뮬레이션합니다. 실제 명령은 실행하지 않습니다.';
  });
})();
