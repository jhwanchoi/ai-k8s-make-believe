/* Transport boundary: replace this file with fetch/SSE; keep the methods below.
 * file: {name, text} (browser upload contents); timestamps: epoch seconds.
 * cmd({text, terminal, host}) is an async iterable of markdown deltas, not rendered HTML.
 */
window.MockAPI = (() => {
  const example = `# 작은 운영 클러스터 연습

직접 창작한 UI 체험용 모의고사입니다. 실제 시험 문제나 덤프가 아닙니다.

## Q1
 domain: Troubleshooting
 weight: 40

컨텍스트: k8s-c1 · 시작 호스트: controlplane

team-a 네임스페이스의 ledger Deployment가 정상 응답하지 않습니다.
현재 Pod 상태와 이벤트를 조사하고 애플리케이션을 복구하세요.

- Deployment 이름과 replica 수를 유지하세요.
- 모든 replica가 Ready인지 확인하세요.
- 조사한 내용을 문항 메모에 남겨도 됩니다.

## Q2
 domain: Services & Networking
 weight: 35

컨텍스트: k8s-c1 · 시작 호스트: controlplane

team-b 네임스페이스의 atlas Deployment를 클러스터 내부에서 접근할 수 있게 하세요.

- Service 이름은 atlas-internal입니다.
- Service 포트는 80, 애플리케이션 수신 포트는 8080입니다.
- 기존 Pod의 label을 변경하지 마세요.
- Service의 대상이 연결되는지 확인하세요.

## Q3
 domain: Storage
 weight: 25

컨텍스트: k8s-c1 · 시작 호스트: controlplane

archive 네임스페이스에 데이터를 보관할 PVC와 Pod를 만드세요.

- PVC 이름은 records, 요청 용량은 1Gi, 접근 모드는 ReadWriteOnce입니다.
- 기존 StorageClass standard를 사용하세요.
- Pod 이름은 reader, 이미지는 busybox:1.36입니다.
- 볼륨을 /records에 마운트하고 Pod가 실행 상태를 유지하게 하세요.
- PVC가 Bound인지 확인하세요.
`;
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const delay = () => wait(1000 + Math.random() * 2000);
  let exam = null;
  let answerBook = null; // Private: never attach to the in-progress exam summary.
  let active = false;
  let clock = null;
  const copy = value => JSON.parse(JSON.stringify(value));
  function questionSections(text) {
    const sections = []; let section = null, fence = null;
    for (const line of text.split('\n')) {
      const marker = line.match(/^[ \t]{0,3}(`{3,}|~{3,})(.*)$/);
      if (marker) {
        if (!fence) fence = marker[1];
        else if (marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = null;
      }
      const heading = !fence && line.match(/^## Q([1-9]\d*)[ \t]*$/);
      if (heading) { section = {n: Number(heading[1]), lines: []}; sections.push(section); }
      else if (section) section.lines.push(line);
    }
    return sections;
  }
  function parseFile(text) {
    const normalized = text.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
    const title = normalized.match(/^#[ \t]+(\S[^\n]*)$/m);
    if (!title) throw Error('# 제목이 필요합니다.');
    const sections = questionSections(normalized);
    if (!sections.length) throw Error('## Q1 형식의 문항이 필요합니다.');
    const problems = sections.map(({n, lines}, i) => {
      const match = lines.join('\n').match(/^\s*[ \t]*domain:[ \t]*([^\n]+)\n[ \t]*weight:[ \t]*([1-9]\d*)[ \t]*\n[ \t]*\n([\s\S]+)$/);
      if (!match || n !== i + 1) throw Error('Q 번호는 1부터 연속이어야 하며 domain, 양의 정수 weight, 빈 줄, 원문 순서여야 합니다.');
      const weight = Number(match[2]);
      if (!Number.isSafeInteger(weight) || !match[3].trim()) throw Error('양의 정수 배점과 문제 원문이 필요합니다.');
      return {n, domain: match[1].trim(), weight, text: match[3].trim(), id: `mock-q${n}`, host: 'controlplane', context: 'k8s-c1', contexts: {controlplane: 'k8s-c1'}};
    });
    if (problems.reduce((sum, p) => sum + p.weight, 0) !== 100) throw Error('문항 배점의 합은 100이어야 합니다.');
    return {title: title[1], problems};
  }
  function parseAnswers(text) {
    const normalized = text.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
    if (!/^# +\S/m.test(normalized)) throw Error('풀이 파일에 # 제목이 필요합니다.');
    const sections = questionSections(normalized);
    if (!sections.length) throw Error('풀이 파일에 ## Q1 형식의 문항이 필요합니다.');
    const seen = new Set();
    return sections.map(({n, lines}) => {
      if (seen.has(n)) throw Error(`풀이 파일의 Q${n} 번호가 중복되었습니다.`);
      seen.add(n);
      const match = lines.join('\n').match(/^\s*\n```bash[ \t]*\n([\s\S]*?)\n```[ \t]*\n\s*\n\(원본: \[([^\]\n]+)\]\(([^\n]+)\)\)[ \t]*\s*$/);
      if (!match) throw Error(`Q${n} 풀이에 bash 블록과 원본 링크가 필요합니다.`);
      let url;
      try { url = new URL(match[3]); } catch { throw Error(`Q${n} 원본 링크 주소가 올바르지 않습니다.`); }
      if (!['https:', 'http:'].includes(url.protocol)) throw Error(`Q${n} 원본 링크는 http/https 주소여야 합니다.`);
      return {n, bash: match[1], source: {label: match[2], url: url.href}};
    });
  }
  async function exclusive(fn) {
    if (active) throw Error('다른 요청을 처리 중입니다.');
    active = true;
    try { await delay(); return fn(); } finally { active = false; }
  }
  function summary() {
    if (exam && clock) exam.ends_at = Date.now() / 1000 + clock.remaining();
    return exam ? copy(exam) : null;
  }
  function running() {
    if (!exam || exam.ended) throw Error('진행 중인 시험이 없습니다.');
  }
  const api = {
    // Local parsing utilities do not issue API requests.
    parseFile,
    parseAnswers,
    exampleFile: () => ({name: 'mock-01.md', text: example}),
    // Local clock bridge; real server owns pause/resume accounting.
    bindLog: log => { clock = log; },
    // POST /api/exam/resume {log, answers?}; replay stored output, never execute cmd.
    resumeExam: ({log, answers = null}) => exclusive(() => {
      const restored = window.ExamLog.replay(log);
      if (restored.exam.ended) throw Error('종료한 시험은 이어 풀 수 없습니다.');
      exam = copy(restored.exam); answerBook = answers ? parseAnswers(answers.text) : null; clock = null;
      return copy(restored);
    }),
    // GET /api/exam
    getExam: () => exclusive(() => summary()),
    // POST /api/exam/start {file, answers?, minutes}: answers stay private until endExam.
    startExam: ({file, answers = null, minutes}) => exclusive(() => {
      if (!Number.isInteger(minutes) || minutes < 1 || minutes > 360) throw Error('시험 시간은 1~360분 정수로 입력하세요.');
      const parsed = parseFile(file.text);
      const parsedAnswers = answers ? parseAnswers(answers.text) : null;
      answerBook = parsedAnswers; clock = null;
      const started_at = Math.floor(Date.now() / 1000);
      parsed.problems.forEach(p => { p.visited = p.n === 1; p.meta = {submitted: false}; });
      exam = {...parsed, started_at, ends_at: started_at + minutes * 60, current: 1, ended: false};
      return summary();
    }),
    // POST /api/exam/goto {n}
    gotoExam: ({n}) => exclusive(() => {
      running();
      if ((clock ? clock.remaining() <= 0 : Date.now() / 1000 >= exam.ends_at)) throw Error('시험 시간이 만료되었습니다.');
      if (!Number.isInteger(n) || n < 1 || n > exam.problems.length) throw Error('문항 번호가 범위를 벗어났습니다.');
      exam.current = n;
      exam.problems[n - 1].visited = true;
      return summary();
    }),
    // POST /api/submit: exam-mode grading never reveals scores or correctness.
    submit: () => exclusive(() => {
      running();
      if ((clock ? clock.remaining() <= 0 : Date.now() / 1000 >= exam.ends_at)) throw Error('시험 시간이 만료되었습니다.');
      exam.problems[exam.current - 1].meta.submitted = true;
      return {message: '제출 기록됨', exam: summary()};
    }),
    // POST /api/cmd {text} -> streaming markdown deltas (SSE adapter contract)
    async *cmd({text, terminal, host}) {
      if (active) throw Error('다른 요청을 처리 중입니다.');
      active = true;
      try {
        running();
        if ((clock ? clock.remaining() <= 0 : Date.now() / 1000 >= exam.ends_at)) throw Error('시험 시간이 만료되었습니다.');
        await delay();
        if (text.trim() === 'demo-error') throw Error('목업 연결이 끊겼습니다. 입력은 보존되었습니다. 다시 실행하세요.');
        const p = exam.problems[exam.current - 1];
        if (![1, 2].includes(terminal) || !/^[\w.-]+$/.test(host || '')) throw Error('터미널 번호와 host가 필요합니다.');
        let outputHost = host;
        const contextFor = target => Object.hasOwn(p.contexts, target) ? p.contexts[target] : p.context;
        if (!Object.hasOwn(p.contexts, host)) Object.defineProperty(p.contexts, host, {value: p.context, writable: true, enumerable: true, configurable: true});
        // Real-format answers from an empty cluster (mock-shell.js); nothing is computed or remembered.
        let output = window.MockShell ? window.MockShell.respond(text, host) : '';
        if (/^kubectl config current-context$/.test(text.trim())) output = contextFor(host);
        else if (/^ssh\s+[\w.-]+$/.test(text.trim())) { outputHost = text.trim().split(/\s+/)[1]; output = ''; }
        else if (text.trim() === 'exit') { output = host === p.host ? 'logout' : `logout\nConnection to ${host} closed.`; outputHost = p.host; }
        else if (/^kubectl config use-context\s+\S+$/.test(text.trim())) { p.contexts[host] = text.trim().split(/\s+/).at(-1); output = `Switched to context "${p.contexts[host]}".`; }
        if (!Object.hasOwn(p.contexts, outputHost)) Object.defineProperty(p.contexts, outputHost, {value: p.context, writable: true, enumerable: true, configurable: true});
        let markdown = `\`\`\`\`console\n# [SIM] host=${outputHost} ctx=${contextFor(outputHost)}\n$ ${text}\n${output}\n\`\`\`\``;
        if (text.trim() === 'demo-plain') markdown = 'Simulation notice: this response contains no console block.';
        if (text.trim() === 'demo-mixed') markdown += `\n추가 안내입니다.\n\`\`\`\`console\n# [SIM] host=${outputHost} ctx=${contextFor(outputHost)}\nMock stream complete.\n\`\`\`\``;
        for (let i = 0; i < markdown.length; i += 28) { await wait(45); yield markdown.slice(i, i + 28); }
      } finally { active = false; }
    },
    // POST /api/exam/end -> report path + report data
    endExam: () => exclusive(() => {
      running(); exam.ended = true;
      const ratios = [.5, 1, .6];
      const problems = exam.problems.map((p, i) => ({...p, score: +(p.weight * ratios[i % 3]).toFixed(2), answer: answerBook?.find(a => a.n === p.n) || null}));
      const total = +problems.reduce((s, p) => s + p.score, 0).toFixed(2);
      return {path: 'mock/exam-report.md', hasAnswers: answerBook !== null, mock: true, total, passed: total >= 66, problems};
    })
  };
  return api;
})();
