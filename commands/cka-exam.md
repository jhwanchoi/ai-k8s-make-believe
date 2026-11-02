---
description: 모의고사 모드 (2시간, 힌트 없음, 끝나고 일괄 채점). start [문제 파일 | 문항 수], next, prev, goto N, status, end
argument-hint: "start [파일|문항수] | next | prev | goto N | status | end"
---

이 대화에서 아직 안 불렀으면 Skill 도구로 `ai-k8s-make-believe:cka-rules` 를 부른다. grader 는 규칙의 "grader 호출" 형식으로 부르고, 반환값은 그대로 보여준다.

인자: $ARGUMENTS

- `start ...`: `.cka/exam.json` 이나 `.cka/current` 가 있으면 먼저 정리하라고(`/cka-exam end` 또는 `/cka-giveup`) 안내하고 끝낸다. 없으면 `mode=exam-start`, input 은 start 뒤 나머지.
- `next`, `prev`, `goto N`: `.cka/exam.json` 의 `current` 로 목표 번호를 정한다. 범위를 벗어나면 안내하고 끝낸다. 그 문제의 `id` 폴더가 이미 있으면 `.cka/current` 와 exam.json 의 `current` 만 바꾸고 `problem.md` 를 보여준다. 없으면 `mode=exam-goto`, input 은 번호.
- `status`: exam.json 을 읽어 남은 시간(`date +%s` 기준)과 문제별 상태(미방문, 진행, 제출)를 표로 보여준다. 제출 여부는 각 `state.json` 의 `meta.submitted`.
- `end`: `mode=exam-end`.
