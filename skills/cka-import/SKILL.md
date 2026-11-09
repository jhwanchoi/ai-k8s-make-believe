---
name: cka-import
description: ai-k8s-make-believe 모의고사 문제 가져오기. 사용자가 CKA 연습문제 GitHub 저장소 링크(예 https://github.com/vj2201/CKA-PREP-2025-v2)를 주며 "이 문제로 풀자", "문제 받아 줘", "문제/답 md 만들어 줘" 라고 하면 부른다. 연습 폴더에 시뮬레이터 문제 파일(<name>.md)과 풀이 파일(<name>.answers.md)을 만든다. 문제 원문은 저장소에 커밋하지 않는다.
---

# 문제 가져오기 (링크 → 문제 · 풀이 md)

링크 하나를 받아 연습 폴더에 두 파일을 만든다.

| 파일 | 담는 것 | 누가 보나 |
|---|---|---|
| `<name>.md` | 문제 원문, 문항마다 `domain` · `weight` | 시험 중 화면 · grader |
| `<name>.answers.md` | 문항마다 원본 풀이 ```` ```bash ```` 블록 | 시험이 끝난 뒤에만 |

## 규칙

- **저장소에 올리지 않는다.** 원본 대부분은 라이선스가 없거나 원작자 권리가 있다. 파일은 사용자 연습 폴더에만 둔다(기본 `./exams/`). 플러그인 저장소 안이면 멈추고 다른 폴더를 묻는다.
- **덤프 경고.** 원본에 실제 시험을 옮긴 흔적("In the exam ...", "real exam question" 등)이 보이면 한 줄로 알린다: 실제 시험 유출 문제는 CNCF 응시 약관 위반이라 자격이 취소될 수 있다. 진행 여부는 사용자가 정한다.
- 문제 파일에는 풀이 · 풀이 영상 링크를 넣지 않는다.
- 사용자 명령을 실행하지 않는 `cka-rules` 규칙은 그대로다. 여기서 Bash 는 `curl`, `python3 <plugin_root>/scripts/import_cka_prep.py` 에만 쓴다.

## 절차

1. 출력 폴더를 정한다. 사용자가 말하지 않았으면 현재 작업 디렉터리의 `exams/`.
2. CKA-PREP 형식(`Question-<n> <주제>/Questions.bash`, `SolutionNotes.bash`)이면 스크립트로 만든다.
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/import_cka_prep.py <링크> exams
   ```
   - 링크에 `/tree/<커밋>` 이 있으면 그 커밋을 쓴다. 없으면 기본 브랜치 최신이다. 같은 문제를 다시 받으려면 커밋을 고정하라고 알려 준다.
   - "내려받기 실패" 가 나오면(사내 프록시 인증서 등) 안내대로 `curl -fsSL <codeload 주소> -o <tmp>.tar.gz` 로 받고 `--tar <tmp>.tar.gz` 를 붙여 다시 실행한다. 인증서 검증을 끄지 않는다.
3. `NOT_CKA_PREP` 이 나오면 다른 형식이다. 직접 만든다.
   - 저장소의 README 와 문제 · 풀이 파일을 읽는다(`curl` 로 raw 파일, 또는 `gh api`).
   - 문제 파일 양식: 첫 줄 `# 제목`, 머리말(출처 링크 · 커밋 · "원작자 권리는 원작자에게 있다"), 그 뒤 문항마다
     ```
     ## Q<n>
     domain: <CKA 도메인>
     weight: <정수>

     <문제 원문>
     ```
     번호는 1부터 연속, 배점 합은 100(원본에 배점이 없으면 균등). domain 은 Troubleshooting · Cluster Architecture, Installation & Configuration · Services & Networking · Workloads & Scheduling · Storage 중 하나.
   - 풀이 파일 양식: `# 제목`, 머리말, 문항마다 `## Q<n>`, 빈 줄, ```` ```bash ```` 블록(원본 풀이 그대로). 풀이가 없는 문항은 블록 안에 `# (원본에 풀이 없음)`.
   - 원본 문장은 바꾸지 않는다. 주석 기호 · 영상 링크만 뺀다.
4. 형식을 검사한다. 통과할 때까지 고친다.
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/import_cka_prep.py --check exams/<name>.md exams/<name>.answers.md
   ```
5. 알린다: 두 파일 경로, 문항 수, 도메인별 문항 수, 덤프 경고(해당하면), 시작 방법 한 줄 — 시뮬레이터 화면에서 두 파일을 고르거나 `/ai-k8s-make-believe:cka-exam start exams/<name>.md`. 풀이 내용은 대화에 옮기지 않는다.
