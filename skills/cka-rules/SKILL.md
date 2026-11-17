---
name: cka-rules
description: ai-k8s-make-believe(CKA 시뮬레이터) 공통 규칙. 프로젝트에 .cka/current 가 있는 상태에서 사용자가 kubectl, etcdctl, kubeadm, systemctl, journalctl, crictl, helm, kustomize, ssh 명령이나 Kubernetes YAML 을 "$ " 로 시작해 입력하거나 /ai-k8s-make-believe:cka, /ai-k8s-make-believe:cka-* 커맨드를 쓸 때 반드시 먼저 로드한다. 명령을 실제로 실행하지 않고 .cka/<id>/state.json 가상 상태로 시뮬레이션하는 방법을 정의한다.
---

# ai-k8s-make-believe 규칙

## 절대 규칙

1. **실행 금지.** 사용자 명령(kubectl, etcdctl, kubeadm, systemctl, journalctl, crictl, helm, kustomize, ssh, vim 등)은 로컬에서 절대 실행하지 않는다. Bash 는 `.cka/` 파일 관리, `date`, `grade.py` 에만 쓴다. guard 훅이 막아 주지만 훅에 기대지 않는다.
   - 권한 프롬프트를 줄이려고 파일 찾기는 Glob, 읽기는 Read, 새 파일은 Write, 수정은 Edit 로 한다. Bash 는 정해진 템플릿만 쓰고 파이프, `&&`, `$(...)`, `2>/dev/null` 을 붙이지 않는다.
2. **정답 격리.** 메인 대화는 `answer-key.md` 와 연습 폴더의 풀이(`<name>.answers.md`) · 환경(`<name>.setup.md`) 파일을 읽지 않고, 정답을 추측해서 말하지도 않는다. 출제, 채점, 힌트, 포기, 모의고사 채점은 `ai-k8s-make-believe:cka-grader` 서브에이전트가 맡는다. 메인 컨텍스트에 정답을 두지 않아 가상 출력에 정답이 새는 일을 줄인다.
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
5. **Claude Code 입력과 겹치는 것.** 실제 터미널 습관대로 치면 Claude Code 가 먼저 가로채는 입력이 있다. 사용자에게 그 입력을 시키지 않는다.
   - `exit`, `quit`, `:q`, `:wq` 를 한 줄만 입력하면 Claude Code 가 끝난다. 셸에서 나오는 명령은 `$ exit` 처럼 `$` 를 붙이게 안내한다.
   - Ctrl+C 를 두 번, Ctrl+D 를 누르면 Claude Code 가 끝난다. 그래서 Ctrl+C 로 멈춰야 하는 명령은 사용자가 바로 Ctrl+C 를 누른 것으로 보고 끝낸다 (아래 "명령 처리").
   - `!` 로 시작하는 입력은 Claude Code 의 bash 모드라 이 시뮬레이터를 거치지 않고 사용자 컴퓨터에서 실제로 실행된다. 사용자가 `!` 로 시작하는 명령을 쓰려는 것 같으면 `$` 로 바꾸라고 안내한다.
   - 이 대화에서 처음으로 명령을 처리할 때 (입력 첫 줄이 `# terminal=` 이 아닐 때만) 출력 끝에 한 번만 사용자 언어로 짧게 알린다: "명령은 `$` 로 시작하세요. `exit`, `:wq` 를 `$` 없이 치거나 Ctrl+C 를 두 번 누르면 Claude Code 가 종료되고, `!` 로 시작하면 내 컴퓨터에서 실제로 실행됩니다."

## 파일 구조

```
.cka/
├── current             # 진행 중 문제 id 한 줄 (.cka/ 가 있으면 guard 훅이 켜진다)
├── exam.json           # 모의고사 중에만
├── wrong-notes.md      # 오답 노트 (문제별 3~5줄)
├── exam-attempts.jsonl # 모의고사 차시 기록 (끝날 때마다 한 줄, append-only)
├── exam-report-*.md    # 모의고사 리포트
├── archive/<id>/       # 끝난 문제 폴더 (grader 가 옮김, 메인은 읽지 않음)
└── <id>/               # 예: q07-etcd-backup
    ├── problem.md      # 문제 원문, 요구사항, curriculum 표시
    ├── state.json      # 현재 가상 상태 (판정 기준)
    ├── state.init.json # /ai-k8s-make-believe:cka-reset 용 초기 상태
    ├── history.md      # 명령, 가상 출력, 변경 내역 (append-only)
    ├── answer-key.md   # 정답, 루브릭, 숨은 원인 (grader 전용)
    └── diagram.md      # 초기, 최종 상태 그림 (문제 종료 때 diagram.py 가 만듦)
```

## 읽기 정책

| 시점 | 메인이 읽는 파일 | grader 가 읽는 파일 |
|---|---|---|
| 출제 (모의고사) | 없음 | 문제 파일, `exam.json` 의 `setup` 환경 파일(그 문항 절만 반영, 실행 안 함) |
| 명령 실행 | `state.json` (`problem.md` 는 대화에 문제가 없을 때만) | 없음 |
| 채점, 힌트 | 없음 | `state.json`, `answer-key.md` |
| 정답 처리 후 피드백 | 없음 | 위 + `history.md` |
| 상태 꼬임 디버깅, 되돌리기 | `history.md` | 없음 |

reviewer 는 출제 검증 때 `problem.md`, `state.init.json`, `answer-key.md` 를, 시뮬레이션 검토 때 `problem.md`, `state.init.json`, `state.json`, `history.md` 를 읽는다. 시뮬레이션 검토 때는 answer-key.md 를 읽지 않는다.

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
- 요약하거나 줄이지 않는다. 되돌리기와 채점 뒤 피드백이 전체 기록을 쓴다.

## state.json 스키마

```json
{
  "meta": {"id": "q07-etcd-backup", "mode": "practice", "attempts": 0, "hint_level": 0, "cmd_count": 0,
           "context": "k8s-c1", "host": "controlplane", "user": "root", "cwd": "/root"},
  "clusters": {
    "k8s-c1": {
      "version": "v1.37.0",
      "nodes": {
        "controlplane": {"ready": true, "roles": ["control-plane"], "version": "v1.37.0", "unschedulable": false,
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
      "packages": {"kubeadm": "1.37.0-1.1"},
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
- 파일 속성(`ls -l` 의 권한, 소유자, 수정 시각)은 처음 보여 줄 때 `hosts.<host>.file_attrs["<경로>"] = {mode, owner, group, mtime}` 에 넣고 이후 그대로 쓴다. 크기는 내용 길이로 계산한다.
- 처음 보여준 출력을 나중에 또 보여줄 일이 있으면 (예: `kubectl get ns` 목록) 그때 state 에 넣어 일관성을 지킨다.

## 명령 처리 (/ai-k8s-make-believe:cka, "$ ..." 입력)

1. `.cka/current` 로 id 를 찾는다. 없으면 `/ai-k8s-make-believe:cka-load` 를 안내하고 끝낸다.
2. `.cka/exam.json` 이 있으면 `date +%s` 를 `ends_at` 과 비교한다. 시간이 지났으면 명령을 받지 않고 `/ai-k8s-make-believe:cka-exam end` 를 안내한다.
3. `state.json` 을 Read 한다. 입력 첫 줄이 `# terminal=<n> host=<host>` 이면 (웹 시뮬레이터 서버가 붙인다) 그 줄은 명령이 아니다. `meta.host` 가 다르면 먼저 그 host 로 바꾸고, 나머지 줄을 명령으로 처리한다.
4. 여러 줄이면 한 줄씩 차례로, 실제 도구처럼 해석한다.
   - kubectl(`k` 포함) 명령은 시뮬레이션 전에 `${CLAUDE_PLUGIN_ROOT}/skills/cka-rules/references/kubectl/` 에서 그 명령의 파일 하나만 Read 한다. 명령 경로를 `_` 로 이은 이름이다 (`kubectl create deployment` → `kubectl_create_deployment.md`). 없으면 상위 명령 파일을 읽는다. 전역 플래그는 `kubectl.md` 에 있고 필요할 때만 읽는다. 이 대화에서 이미 읽은 파일은 다시 읽지 않는다.
   - 색인에 없는 하위 명령이나 플래그는 실제 kubectl 형식의 에러(`error: unknown flag: --foo`, `error: unknown command "foo" for "kubectl create"`)를 내고 상태는 바꾸지 않는다. 플래그 타입과 기본값도 색인을 따른다.
   - 문법, 플래그, 경로 오류: 실제 kubectl, etcdctl, kubeadm, systemctl, bash 와 같은 형식의 에러를 내고 상태는 바꾸지 않는다.
   - 조회 (`get`, `describe`, `logs`, `get events`, `cat`, `ls`, `systemctl status`, `journalctl`): state 기반으로 출력한다.
   - 변경: 결과를 계산해 state.json 을 Edit 한다. 틀린 답도 실제처럼 조용히 성공할 수 있다 (selector 오타도 `service/web-svc created`). 문제는 확인 명령에서 드러나게 둔다.
   - 파일 작성 (`cat <<EOF > x.yaml`, `... --dry-run=client -o yaml > x.yaml`, `vim x.yaml` 뒤 붙여넣은 내용): `hosts.<host>.files` 에 저장한다.
   - 화면 편집기 (`vim`, `vi`, `nano <파일>`, `kubectl edit <리소스>`): 터미널에서는 편집 화면을 띄울 수 없으니 이렇게 처리한다.
     - 지금 내용을 코드 블록으로 보여준다. 파일이면 `files` 값(없으면 빈 새 파일), `kubectl edit` 이면 그 객체를 `kubectl get -o yaml` 형태로 보여준다.
     - 이어서 안내 한 줄을 사용자 언어로 붙인다: "고친 전체 내용을 다음 메시지에 붙여넣으면 `:wq` 로 저장한 것으로 봅니다. `:wq` 나 `:q` 를 한 줄만 따로 입력하지 마세요. Claude Code 가 그 입력을 세션 종료로 받습니다. 저장하지 않고 나가려면 `$ :q!` 를 입력하세요."
     - 다음 메시지가 붙여넣은 내용이면 저장으로 본다. 마지막 줄이 `:wq`, `:x`, `:w` 이면 그 줄은 빼고 저장하고, `:q!` 이면 저장하지 않는다. `$ :wq`, `$ :x` 처럼 `$` 를 붙인 한 줄은 고치지 않고 저장, `$ :q!`, `$ :q` 는 저장하지 않고 닫는 것으로 본다. 그 뒤 메시지는 평소대로 명령으로 처리한다.
     - 파일은 `files` 에 저장한다. `kubectl edit` 은 `apply` 와 같은 검사를 하고 통과하면 객체에 반영해 `deployment.apps/web edited` 를, 바뀐 게 없으면 `Edit cancelled, no changes made.` 를 낸다. 검사에 걸리면 실제처럼 `error: deployments.apps "web" is invalid` 와 함께 `A copy of your changes has been stored to "/tmp/kubectl-edit-xxxx.yaml"` 를 내고 상태는 바꾸지 않는다.
     - history 에는 `$ vim x.yaml` (또는 `$ kubectl edit ...`) 한 항목으로 남기고 변경 줄을 붙인다. `meta.cmd_count` 도 한 번만 올린다.
   - `kubectl apply/create -f`: YAML 문법, apiVersion/kind 조합, 필수 필드를 검사하고 통과하면 objects 에 반영한다.
   - static pod: `/etc/kubernetes/manifests/` 파일이 바뀌면 kubelet 이 반영한 것으로 보고 `kube-system/pod/<name>-<node>` 를 갱신한다.
   - 전환: `kubectl config use-context` 는 meta.context, `ssh <node>` 와 `exit` 는 meta.host, `sudo -i` 는 meta.user 를 바꾼다. `exit` 는 `logout` 과 (ssh 였으면) `Connection to <node> closed.` 를 낸다.
   - 셸 안으로 들어가는 명령 (`ssh`, `sudo -i`, `kubectl exec -it ... -- sh`, `kubectl run -it ... -- sh`, `kubectl debug -it`): 이 대화에서 처음이면 출력 뒤에 "나올 때는 `$ exit` 로 입력하세요. `$` 없이 `exit` 만 치면 Claude Code 가 종료됩니다." 를 붙인다. `exec -it`, `run -it`, `debug -it` 는 `meta.shell = {"kind": "container", "target": "<ns>/<pod>/<container>"}` 를 두고, `$ exit` 전까지 오는 명령은 그 컨테이너 안에서 실행한 것으로 시뮬레이션한다 (`kubectl` 이 없으면 `sh: kubectl: not found`). `$ exit` 에서 `meta.shell` 을 지운다.
   - 끝나지 않고 계속 도는 명령 (`kubectl get -w`, `--watch`, `kubectl logs -f`, `kubectl events -w`, `journalctl -f`, `tail -f`, `watch ...`, `top`, `kubectl port-forward`, `kubectl proxy`, `etcdctl watch`, `crictl logs -f`): 지금 상태 한 번만 출력하고 (port-forward 는 `Forwarding from 127.0.0.1:<p> -> <p>`, proxy 는 `Starting to serve on 127.0.0.1:8001`) 마지막 줄에 `^C` 를 둔다. 사용자가 Ctrl+C 를 누를 필요가 없다는 것을 처음 한 번만 알린다.
   - 화면을 넘기는 명령 (`less`, `more`, `man`, `kubectl explain` 의 긴 출력): 페이저 없이 전부 출력한다. `q` 를 누르라고 하지 않는다.
   - state 에 없는 리소스는 실제처럼 `NotFound`.
5. `meta.cmd_count` 를 1 올리고 (Edit) history 에 append 한다.
6. 가상 출력을 보여준다. 채점은 사용자가 `/ai-k8s-make-believe:cka-submit` 할 때만 한다. 맞았는지 틀렸는지 먼저 말하지 않는다.

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

## reviewer 호출

Agent 도구, `subagent_type: ai-k8s-make-believe:cka-reviewer`. 프롬프트는 grader 와 같은 형식이고 `mode` 만 `init-review` (출제 직후) 또는 `sim-review` (연습은 제출 직전, 모의고사는 exam end 때) 다. 언제 부르고 결과를 어떻게 처리하는지는 `/ai-k8s-make-believe:cka-load`, `/ai-k8s-make-believe:cka-submit`, `/ai-k8s-make-believe:cka-exam` 커맨드에 있다. `meta.reviewed_cmd` 는 reviewer 가 관리하므로 메인은 고치지 않는다.
