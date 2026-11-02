---
description: CKA 문제 로딩. 가상 환경과 정답 루브릭을 만든다 (텍스트, 파일 경로, 주제, 비우면 자동 출제, "오답"이면 오답 노트에서 재출제)
argument-hint: "[문제 텍스트 | 파일 경로 | 주제 | 오답]"
---

1. 이 대화에서 아직 안 불렀으면 Skill 도구로 `ai-k8s-make-believe:cka-rules` 를 부른다.
2. `.cka/current` 가 있으면 진행 중인 문제가 있다고 알리고, 이어서 풀지(`/cka`) 아니면 `/cka-giveup` 뒤 새로 시작할지 묻고 끝낸다.
3. 규칙의 "grader 호출" 형식으로 `mode=load` 를 호출한다. input 은 아래 인자.
4. 반환값을 그대로 보여준다.

인자:
$ARGUMENTS
