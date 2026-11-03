---
description: 답안 제출. 같이 준 명령이나 YAML 을 먼저 가상 적용한 뒤, 현재 가상 상태를 루브릭으로 채점한다
argument-hint: "[명령 또는 YAML]"
---

1. 이 대화에서 아직 안 불렀으면 Skill 도구로 `ai-k8s-make-believe:cka-rules` 를 부른다. `.cka/current` 가 없으면 `/ai-k8s-make-believe:cka-load` 를 안내하고 끝낸다.
2. 인자가 있으면 규칙의 "명령 처리" 절차로 먼저 적용하고 가상 출력을 보여준다.
3. "grader 호출" 형식으로 `mode=grade` 를 호출한다.
4. 반환값을 그대로 보여준다.

$ARGUMENTS
