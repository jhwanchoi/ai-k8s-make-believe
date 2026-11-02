---
name: cka-rules
description: ai-k8s-make-believe(CKA 시뮬레이터) 공통 규칙. 프로젝트에 .cka/current 가 있는 상태에서 사용자가 kubectl, etcdctl, kubeadm, systemctl, journalctl, crictl, helm, kustomize, ssh 명령이나 Kubernetes YAML 을 "$ " 로 시작해 입력하거나 /cka, /cka-* 커맨드를 쓸 때 반드시 먼저 로드한다. 명령을 실제로 실행하지 않고 .cka/<id>/state.json 가상 상태로 시뮬레이션하는 방법을 정의한다.
---

# ai-k8s-make-believe 규칙

## 절대 규칙

1. **실행 금지.** 사용자 명령(kubectl, etcdctl, kubeadm, systemctl, journalctl, crictl, helm, kustomize, ssh, vim 등)은 로컬에서 절대 실행하지 않는다. Bash 는 `.cka/` 파일 관리, `date`, `grade.py` 에만 쓴다. guard 훅이 막아 주지만 훅에 기대지 않는다.
   - 권한 프롬프트를 줄이려고 파일 찾기는 Glob, 읽기는 Read, 새 파일은 Write, 수정은 Edit 로 한다. Bash 는 정해진 템플릿만 쓰고 파이프, `&&`, `$(...)`, `2>/dev/null` 을 붙이지 않는다.
2. **정답 격리.** 메인 대화는 `answer-key.md` 를 읽지 않고, 정답을 추측해서 말하지도 않는다. 출제, 채점, 힌트, 포기, 모의고사 채점은 `ai-k8s-make-believe:cka-grader` 서브에이전트가 맡는다. 메인 컨텍스트에 정답이 없으니 가상 출력에 정답이 샐 일도 없다.
3. **시뮬레이션 표시.** 가상 터미널 출력은 항상 아래 형식의 코드 블록으로 낸다. 흉내만 가능한 결과(Deployment 에서 Pod 까지 이어지는 컨트롤러 연쇄, 스케줄링, taint/toleration, rollout, NetworkPolicy 트래픽 차단, 복잡한 장애)는 블록 바로 아래에 `(추정)` 을 붙인다.

````
```console
# [SIM] host=controlplane ctx=k8s-c1
$ kubectl get pod -n prod
NAME   READY   STATUS    RESTARTS   AGE
web    1/1     Running   0          3m
```
````

4. **언어.** 설명, 힌트, 안내는 사용자가 쓰는 언어로 한다. 가상 터미널 출력은 실제 도구처럼 영어로 둔다.

## 파일 구조

```
.cka/
├── current             # 진행 중 문제 id 한 줄 (.cka/ 가 있으면 guard 훅이 켜진다)
├── exam.json           # 모의고사 중에만
├── wrong-notes.md      # 오답 노트 (문제별 3~5줄)
└── <id>/               # 예: q07-etcd-backup
    ├── problem.md      # 문제 원문, 요구사항, curriculum 표시
    ├── state.json      # 현재 가상 상태 (판정 기준)
    ├── state.init.json # /cka-reset 용 초기 상태
    ├── history.md      # 명령, 가상 출력, 변경 내역 (append-only)
    └── answer-key.md   # 정답, 루브릭, 숨은 원인 (grader 전용)
```

## 읽기 정책

| 시점 | 메인이 읽는 파일 | grader 가 읽는 파일 |
|---|---|---|
| 명령 실행 | `state.json` (`problem.md` 는 대화에 문제가 없을 때만) | 없음 |
| 채점, 힌트 | 없음 | `state.json`, `answer-key.md` |
| 정답 처리 후 피드백 | 없음 | 위 + `history.md` |
| 상태 꼬임 디버깅, 되돌리기 | `history.md` | 없음 |

**history.md 는 평소 append만 한다.** Read, Edit, Write 를 쓰지 않는다. Edit/Write 는 먼저 Read 해야 해서 매 턴 비용이 history 길이만큼 늘어난다. 아래 Bash 템플릿을 그대로 쓴다. `date`, `cat` 으로 시작하고 `$(...)` 치환이 없어야 `Bash(date:*)`, `Bash(cat:*)` 권한 규칙으로 허용된다. 종결자는 꼭 `CKA_HISTORY_EOF` 로 한다. 사용자 입력에 흔한 `EOF` 줄이 heredoc 을 일찍 끝내면 나머지 줄이 셸 명령으로 실행되기 때문이다.

```bash
date '+### #<n>  %F %H:%M' >> .cka/<id>/history.md; cat >> .cka/<id>/history.md <<'CKA_HISTORY_EOF'
$ kubectl label pod web app=frontend -n prod
> pod/web labeled
변경: objects["prod/pod/web"].metadata.labels += {app: frontend}
CKA_HISTORY_EOF
```

- 출력은 3줄 이내로 줄인다. 조회만 한 명령은 `변경: 없음`.
- `<n>` 은 갱신한 뒤의 `meta.cmd_count`.
- `meta.cmd_count` 가 30의 배수가 되면 그때만 history.md 를 Read 해서, 최근 10개를 뺀 나머지를 `- #1~#20: <한 줄 요약>` 식으로 합치고 Write 로 교체한다.

## state.json 스키마

```json
{
  "meta": {"id": "q07-etcd-backup", "mode": "practice", "attempts": 0, "hint_level": 0, "cmd_count": 0,
           "context": "k8s-c1", "host": "controlplane", "user": "root", "cwd": "/root"},
  "clusters": {
    "k8s-c1": {
      "version": "v1.34.1",
      "nodes": {
        "controlplane": {"ready": true, "roles": ["control-plane"], "version": "v1.34.1", "unschedulable": false,
                         "taints": ["node-role.kubernetes.io/control-plane:NoSchedule"]}
      },
      "objects": {
        "prod/pod/web": {"metadata": {"labels": {"app": "web"}},
                         "spec": {"containers": [{"name": "web", "image": "nginx:1.27"}]},
                         "status": {"phase": "Running"}},
        "_/clusterrole/pod-reader": {"rules": [{"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list"]}]}
      }
    }
  },
  "hosts": {
    "controlplane": {
      "files": {"/etc/kubernetes/manifests/etcd.yaml": "apiVersion: v1\nkind: Pod\n...",
                "/opt/etcd-backup.db": "<binary: etcd snapshot, endpoint=https://127.0.0.1:2379, revision=1284>"},
      "services": {"kubelet": "active"},
      "packages": {"kubeadm": "1.34.1-1.1"},
      "logs": {"kubelet": ["E1102 16:40:01 run.go:72] \"command failed\" err=\"failed to load kubelet config file\""]}
    }
  }
}
```

- 문제에 필요한 것만 모델링한다. 클러스터 전체를 재현하지 않는다.
- 객체 키는 `<namespace>/<kind>/<name>`, 클러스터 범위 객체는 `_/<kind>/<name>`. kind 는 소문자 단수 (`deployment`, `networkpolicy`).
- 객체 값은 `kubectl get -o json` 구조에서 apiVersion, kind, metadata.name, metadata.namespace 를 뺀 나머지 중 필요한 필드만 둔다 (`metadata.labels`, `spec`, `status`, RBAC 의 `rules`, `subjects`, `roleRef` 등). 필드 위치는 실제 API 와 똑같이 둔다. grader 의 루브릭 경로가 이 규칙을 전제로 한다.
- 숨은 고장은 **증상만** 넣는다 (깨진 파일 내용, 서비스 상태, logs 줄). 원인 설명은 answer-key 에만 있다. `journalctl`, `kubectl logs`, `crictl logs`, `systemctl status` 출력은 이 값으로 만든다.
- 바이너리 파일은 `<binary: ...>` 설명 문자열로 둔다.
- 처음 보여준 출력을 나중에 또 보여줄 일이 있으면 (예: `kubectl get ns` 목록) 그때 state 에 넣어 일관성을 지킨다.

## 명령 처리 (/cka, "$ ..." 입력)

1. `.cka/current` 로 id 를 찾는다. 없으면 `/cka-load` 를 안내하고 끝낸다.
2. `.cka/exam.json` 이 있으면 `date +%s` 를 `ends_at` 과 비교한다. 시간이 지났으면 명령을 받지 않고 `/cka-exam end` 를 안내한다.
3. `state.json` 을 Read 한다.
4. 여러 줄이면 한 줄씩 차례로, 실제 도구처럼 해석한다.
   - 문법, 플래그, 경로 오류: 실제 kubectl, etcdctl, kubeadm, systemctl, bash 와 같은 형식의 에러를 내고 상태는 바꾸지 않는다.
   - 조회 (`get`, `describe`, `logs`, `get events`, `cat`, `ls`, `systemctl status`, `journalctl`): state 기반으로 출력한다.
   - 변경: 결과를 계산해 state.json 을 Edit 한다. 틀린 답도 실제처럼 조용히 성공할 수 있다 (selector 오타도 `service/web-svc created`). 문제는 확인 명령에서 드러나게 둔다.
   - 파일 작성 (`cat <<EOF > x.yaml`, `... --dry-run=client -o yaml > x.yaml`, `vim x.yaml` 뒤 붙여넣은 내용): `hosts.<host>.files` 에 저장한다. `vim` 처럼 인터랙티브한 명령은 "저장할 내용을 붙여넣어 주세요" 라고 요청한다.
   - `kubectl apply/create -f`: YAML 문법, apiVersion/kind 조합, 필수 필드를 검사하고 통과하면 objects 에 반영한다.
   - static pod: `/etc/kubernetes/manifests/` 파일이 바뀌면 kubelet 이 반영한 것으로 보고 `kube-system/pod/<name>-<node>` 를 갱신한다.
   - 전환: `kubectl config use-context` 는 meta.context, `ssh <node>` 와 `exit` 는 meta.host, `sudo -i` 는 meta.user 를 바꾼다.
   - state 에 없는 리소스는 실제처럼 `NotFound`.
5. `meta.cmd_count` 를 1 올리고 (Edit) history 에 append 한다.
6. 가상 출력을 보여준다. 채점은 사용자가 `/cka-submit` 할 때만 한다. 맞았는지 틀렸는지 먼저 말하지 않는다.

## grader 호출

Agent 도구, `subagent_type: ai-k8s-make-believe:cka-grader`. 프롬프트는 항상 이 형식:

```
mode=<load|grade|hint|giveup|exam-start|exam-goto|exam-end>
plugin_root=${CLAUDE_PLUGIN_ROOT}
project=<현재 작업 디렉터리 절대 경로>
id=<.cka/current 값, 없으면 생략>
lang=<사용자가 쓰는 언어. 예: ko, en>
input:
<인자>
```

반환값은 사용자에게 그대로 보여준다. 요약하거나 해석을 덧붙이지 않는다.
