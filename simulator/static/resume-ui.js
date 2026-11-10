/* Storage discovery and resume cards contain metadata only, never solutions. */
window.ResumeUI = class {
  constructor({container, onResume, onError}) { Object.assign(this, {container, onResume, onError}); }
  refresh(problemText = null) {
    this.container.replaceChildren();
    for (const saved of window.ExamLog.saved(this.onError)) {
      if (problemText !== null && saved.key !== window.ExamLog.findKey(problemText)) continue;
      try {
        if (!window.ExamLog.timing(saved.events).paused) {
          const recovered = new window.ExamLog({log: saved.log, onError: this.onError});
          recovered.append('pause', {at: saved.events.at(-1).t}, false); saved.log = recovered.text; saved.events = recovered.events;
        }
        const state = window.ExamLog.replay(saved.log), first = saved.events[0];
        const card = document.createElement('section'); card.className = 'resume-card';
        const title = document.createElement('h3'); title.textContent = `이어서 풀기 · ${first.title}`;
        const text = document.createElement('p');
        text.textContent = `현재 Q${state.exam.current} · 남은 시간 ${Math.ceil(state.timing.remaining / 60)}분 · 마지막 활동 ${new Date(saved.events.at(-1).t).toLocaleString('ko-KR')}`;
        const resume = document.createElement('button'); resume.textContent = '이어서 풀기'; resume.className = 'primary';
        resume.onclick = () => this.onResume(saved);
        const discard = document.createElement('button'); discard.textContent = '버리고 새로 시작';
        discard.onclick = () => { try { localStorage.removeItem(saved.key); this.refresh(problemText); } catch { this.onError('시험 로그를 삭제하지 못했습니다.'); } };
        const help = document.createElement('p'); help.textContent = '풀이를 보려면 시작 화면에서 풀이 파일을 다시 고른 뒤 이어 푸세요';
        card.append(title, text, help, resume, discard); this.container.append(card);
      } catch {
        const card = document.createElement('section'); card.className = 'resume-card';
        const title = document.createElement('h3'); title.textContent = '복원할 수 없는 기록';
        const text = document.createElement('p'); text.textContent = `복원할 수 없는 기록 · ${saved.events?.[0].title || saved.key}`;
        const download = document.createElement('button'); download.textContent = '로그 내려받기';
        download.onclick = () => {
          const url = URL.createObjectURL(new Blob([localStorage.getItem(saved.key) ?? saved.log], {type: 'application/x-ndjson'}));
          const a = document.createElement('a'); a.href = url; a.download = `${saved.key.replace(':', '-')}.jsonl`; a.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        };
        const discard = document.createElement('button'); discard.textContent = '버리기';
        discard.onclick = () => { try { localStorage.removeItem(saved.key); this.refresh(problemText); } catch { this.onError('시험 로그를 삭제하지 못했습니다.'); } };
        card.append(title, text, download, discard); this.container.append(card);
      }
    }
  }
};
