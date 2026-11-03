---
description: 현재 문제의 다음 단계 힌트 (1 방향, 2 위치, 3 정답 공개). 모의고사 중에는 안 된다
---

1. 이 대화에서 아직 안 불렀으면 Skill 도구로 `ai-k8s-make-believe:cka-rules` 를 부른다. `.cka/current` 가 없으면 `/ai-k8s-make-believe:cka-load` 를 안내하고 끝낸다.
2. 규칙의 "grader 호출" 형식으로 `mode=hint` 를 호출한다.
3. 반환값을 그대로 보여준다.
