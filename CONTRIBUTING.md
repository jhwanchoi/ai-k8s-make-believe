# 기여 안내

## 진행 방식

1. 저장소를 fork하거나 브랜치를 만들어 작업합니다. `main`에는 직접 push할 수 없습니다.
2. Pull Request를 열면 템플릿의 확인 항목을 채워 주세요.
3. `check` 워크플로가 통과하고 관리자가 확인하면 병합합니다. 병합은 squash merge로 합니다.

## 지침(skills/, agents/)을 바꿀 때

`skills/cka-rules`와 `agents/cka-grader.md`는 이 플러그인을 쓰는 모든 사람의 시뮬레이션과 채점을 바꿉니다.

- 가상 출력 형식을 바꾼다면 실제 출력 예시와 확인한 버전(Kubernetes, kubectl, etcdctl 등)을 PR에 적어 주세요.
- 출제 범위나 도메인 비중을 바꾼다면 [cncf/curriculum](https://github.com/cncf/curriculum) 근거 링크를 붙여 주세요.
- 루브릭 `op`나 `state.json` 스키마를 바꾼다면 `scripts/grade.py`와 그 selftest도 함께 고쳐 주세요.

## 문제와 예시

- 실제 시험 유출 문제를 저장소에 넣지 않습니다. 예시는 직접 만든 문제로 씁니다.
- 실제 kubeconfig, 토큰, 인증서, 회사 클러스터 이름과 주소를 넣지 않습니다.
- 연습하다 생긴 `.cka/` 폴더는 올리지 않습니다 (`.gitignore`에 들어 있습니다).

## 로컬에서 확인하기

```bash
python3 scripts/validate_repo.py
claude plugin validate .
claude --plugin-dir .
```
