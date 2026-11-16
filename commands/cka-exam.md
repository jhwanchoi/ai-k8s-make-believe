---
description: 모의고사 모드 (2시간, 힌트 없음, 끝나고 일괄 채점). start [문제 파일 | 문항 수], next, prev, goto N, status, end
argument-hint: "start [파일|문항수] | next | prev | goto N | status | end"
---

이 대화에서 아직 안 불렀으면 Skill 도구로 `ai-k8s-make-believe:cka-rules` 를 부른다. grader 는 규칙의 "grader 호출", reviewer 는 "reviewer 호출" 형식으로 부르고, 반환값은 그대로 보여준다.

인자: $ARGUMENTS

- `start ...`: `.cka/exam.json` 이나 `.cka/current` 가 있으면 먼저 정리하라고(`/ai-k8s-make-believe:cka-exam end` 또는 `/ai-k8s-make-believe:cka-giveup`) 안내하고 끝낸다. 없으면 `mode=exam-start`, input 은 start 뒤 나머지. 그 뒤 새 `.cka/current` 로 reviewer `mode=init-review` 를 호출하고 그 한 줄을 덧붙인다.
- `next`, `prev`, `goto N`: `.cka/exam.json` 의 `current` 로 목표 번호를 정한다. 범위를 벗어나면 안내하고 끝낸다. 그 문제의 `id` 폴더가 이미 있으면 `.cka/current` 와 exam.json 의 `current` 만 바꾸고 `problem.md` 를 보여준다. 없으면 `mode=exam-goto`, input 은 번호. 그 뒤 새 `.cka/current` 로 reviewer `mode=init-review` 를 호출하고 그 한 줄을 덧붙인다.
- `status`: exam.json 을 읽어 남은 시간(`date +%s` 기준)과 문제별 상태(미방문, 진행, 제출)를 표로 보여준다. 제출 여부는 각 `state.json` 의 `meta.submitted`.
- `end`:
  1. exam.json 의 `problems` 중 `id` 폴더가 있는 문제마다 reviewer `mode=sim-review` 를 호출한다 (id 는 그 문제의 id).
  2. 이상이 하나라도 있으면 문제별 검토 결과를 한꺼번에 보여주고, AskUserQuestion 으로 한 번만 묻는다. 선택지는 "상태 수정 후 채점" (모든 수정 적용), "무시". 문제별로 다르게 하고 싶으면 사용자가 직접 적게 둔다.
  3. 수정할 문제마다 `/ai-k8s-make-believe:cka-submit` 의 3단계와 같은 방식으로 state.json 을 고치고 history 에 `$ (review-fix)` 를 남긴다.
  4. `mode=exam-end` 를 호출한다. 이슈 초안 안내 한 줄도 `/ai-k8s-make-believe:cka-submit` 과 같게 덧붙인다.
