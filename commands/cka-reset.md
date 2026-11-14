---
description: 현재 문제의 가상 환경을 처음 상태로 되돌린다 (시도, 힌트 횟수는 유지)
---

1. 이 대화에서 아직 안 불렀으면 Skill 도구로 `ai-k8s-make-believe:cka-rules` 를 부른다. `.cka/current` 로 id 를 찾고, 없으면 안내하고 끝낸다.
2. `.cka/<id>/state.json` 에서 `meta.attempts`, `meta.hint_level`, `meta.cmd_count`, `meta.reviewed_cmd`(있으면) 를 읽어 둔다.
3. `.cka/<id>/state.init.json` 내용에 2의 값을 넣어 `state.json` 을 Write 한다. 시도, 힌트 횟수를 유지해야 리셋으로 힌트 단계를 되돌리는 일이 없다.
4. 규칙의 history append 템플릿으로 `$ (reset)` / `변경: state.init.json 으로 복원` 항목을 남긴다.
5. 시작 위치(host, ctx)와 함께 초기화됐다고 알린다.
