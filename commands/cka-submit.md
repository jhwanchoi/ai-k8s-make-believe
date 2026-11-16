---
description: 답안 제출. 같이 준 명령이나 YAML 을 먼저 가상 적용하고, 가상 상태 변화를 검토한 뒤 루브릭으로 채점한다
argument-hint: "[명령 또는 YAML]"
---

1. 이 대화에서 아직 안 불렀으면 Skill 도구로 `ai-k8s-make-believe:cka-rules` 를 부른다. `.cka/current` 가 없으면 `/ai-k8s-make-believe:cka-load` 를 안내하고 끝낸다.
2. 인자가 있으면 규칙의 "명령 처리" 절차로 먼저 적용하고 가상 출력을 보여준다.
3. `state.json` 의 `meta.mode` 가 `exam` 이 아니면 규칙의 "reviewer 호출" 형식으로 `mode=sim-review` 를 호출한다.
   - `이상 없음` 이면 4 로 간다.
   - 이상이 있으면 반환값을 보여주고 AskUserQuestion 으로 묻는다. 선택지는 "상태 수정 후 채점" (검토가 맞다고 볼 때), "무시" (검토가 틀렸다고 볼 때, 상태를 그대로 두고 채점).
   - 수정을 고르면 `json review-fixes` 블록대로 state.json 을 Edit 하고, 규칙의 history append 템플릿으로 `$ (review-fix)` 와 `변경: <path> = <값> (검토 #<n>)` 줄을 남긴다. 이때 `meta.cmd_count` 는 올리지 않고 지금 값을 `<n>` 으로 쓴다.
   - 어느 쪽이든 채점 뒤에 "시뮬레이션이 실제와 다르다고 제보하려면 '이슈 초안' 이라고 말해 주세요" 한 줄을 덧붙인다. 요청하면 저장소의 sim-mismatch 이슈 양식(입력한 명령, 가상 출력이나 채점 결과, 실제 결과와 근거 링크, Kubernetes 버전, 플러그인 버전과 모델)에 맞춘 본문 초안만 보여준다. 직접 올리지 않고, 문제 원문 전체나 kubeconfig 는 넣지 않는다.
4. "grader 호출" 형식으로 `mode=grade` 를 호출한다.
5. 반환값을 그대로 보여준다.

$ARGUMENTS
