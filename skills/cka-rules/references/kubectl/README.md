# kubectl 명령 색인

가상 터미널이 kubectl 명령을 시뮬레이션할 때 그 명령의 파일 하나만 읽어서, 없는 하위 명령이나 플래그를 실제 kubectl 처럼 거부하는 데 쓴다.

- `VERSION`: 시뮬레이션할 Kubernetes 버전(마이너까지). CKA 시험 환경 버전을 따른다.
  - 근거: https://docs.linuxfoundation.org/tc-docs/certification/tips-cka-and-ckad ("The CKA environment is currently running Kubernetes v1.37"), https://github.com/cncf/curriculum (`CKA_Curriculum_v1.37.pdf`). 2026-11-09 확인.
- `kubectl*.md`: [kubernetes/website](https://github.com/kubernetes/website) 의 `content/en/docs/reference/kubectl/generated/` 를 `scripts/build_kubectl_index.py` 가 코드로 변환한 것. 명령, 설명 첫 문단, 사용법, 그 명령의 플래그, 하위 명령만 남긴다. 전역 플래그는 `kubectl.md` 에만 있다. 각 파일 첫 줄에 원본 커밋과 경로가 있다.
- 파일 이름: 명령 경로를 `_` 로 이음 (`kubectl create deployment` → `kubectl_create_deployment.md`).
- 라이선스: Kubernetes Documentation, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 원본은 Kubernetes 소스에서 자동 생성된 레퍼런스다.

## 다시 만들기

시험 버전이 바뀌면 `VERSION` 을 고치고 실행한다. 최신 릴리스 문서는 `main`, 이전 버전은 `release-1.xx` 브랜치에서 가져오고, 실행 시점의 커밋으로 고정한다.

```bash
python3 scripts/build_kubectl_index.py              # VERSION 기준으로 브랜치 자동 선택
python3 scripts/build_kubectl_index.py --ref <sha>  # 특정 커밋
python3 scripts/build_kubectl_index.py --selftest   # 네트워크 없이 변환기만 검사 (CI)
```

생성 파일은 손으로 고치지 않는다. 틀린 곳은 변환기를 고치고 다시 만든다.
