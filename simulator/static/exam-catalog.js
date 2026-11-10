/* Path selection and catalog assembly are pure; only load() reads allowed files. */
(function () {
  'use strict';
  const basename = path => path.split(/[\\/]/).pop();
  function select(files) {
    const entries = Array.from(files, file => ({file, path: file.webkitRelativePath || file.name}));
    const safe = entries.filter(({path}) => !path.split('/').includes('.cka'));
    const exams = safe.filter(({path}) => {
      const parts = path.split('/');
      return (parts.length === 1 || parts.at(-2) === 'exams') &&
        /\.md$/.test(path) && !/\.(answers|setup)\.md$/.test(path);
    });
    return {exams: exams.map(entry => ({...entry, solution: safe.find(other => other.path === entry.path.replace(/\.md$/, '.answers.md'))?.file || null})),
      history: entries.find(({path}) => /^(?:[^/]+\/)?\.cka\/exam-attempts\.jsonl$/.test(path))?.file || null};
  }
  function assemble(entries, groups, parseFile) {
    return entries.map(entry => {
      let count = null, error = '';
      try { count = parseFile(entry.text).problems.length; } catch { error = 'format error'; }
      const attempts = groups.filter(group => group.exam !== 'auto' && basename(group.exam) === entry.file.name)
        .flatMap(group => group.attempts).sort((a, b) => a.attempt - b.attempt);
      return {...entry, count, error, attempts};
    });
  }
  async function load(files, parseFile, parseAttempts) {
    const selected = select(files);
    const read = async file => { if (file.size > 1024 * 1024) throw Error('1MiB 이하의 파일을 선택하세요.'); return file.text(); };
    const entries = await Promise.all(selected.exams.map(async entry => {
      try { return {...entry, text: await read(entry.file)}; } catch { return {...entry, text: ''}; }
    }));
    const history = selected.history ? parseAttempts(await read(selected.history)) : {groups: [], skipped: 0};
    return {exams: assemble(entries, history.groups, parseFile), skipped: history.skipped};
  }
  const catalog = {select, assemble, load};
  if (typeof module !== 'undefined') module.exports = catalog;
  if (typeof window !== 'undefined') window.ExamCatalog = catalog;
})();
