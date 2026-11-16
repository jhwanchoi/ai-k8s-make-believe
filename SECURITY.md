# 보안 정책

## 실행 차단 훅의 범위

이 플러그인의 PreToolUse 훅(`scripts/guard.py`)은 연습하는 동안 Claude가 사용자 명령을 **실수로** 실제 클러스터나 노드에서 실행하지 않게 막는 안전망입니다. 보안 경계는 아닙니다.

- `.cka/` 폴더가 있는 디렉터리에서만 동작합니다. 그 밖에서는 아무것도 하지 않습니다.
- 명령 위치에 오는 `kubectl`, `etcdctl`, `etcdutl`, `kubeadm`, `kubelet`, `systemctl`, `journalctl`, `crictl`, `ctr`, `helm`, `kustomize`, `ssh`, `scp`를 막습니다. `sudo`, `env`, `nice`, `timeout` 같은 래퍼 뒤에 와도 막습니다.
- python3 가 없으면 판단을 할 수 없으므로 연습 디렉터리에서는 Bash 를 모두 막습니다.
- 셸 파서가 아니라 정규식으로 찾기 때문에 일부러 꾸민 명령까지 막지는 못합니다.
- heredoc 본문은 종결자에 따옴표가 있고(`<<'EOF'`) 셸에 넘기지 않을 때만 데이터로 보고 검사에서 뺍니다. 따옴표 없는 heredoc(`$(...)` 가 실행됨)과 `bash <<EOF`, `cat <<EOF | sh` 처럼 셸로 넘기는 본문은 검사합니다.
- 파일에 스크립트를 써 둔 뒤 `bash x.sh` 로 실행하는 경우는 파일 내용을 보지 않으므로 막지 못합니다.
- `.cka/`가 아직 없는 새 디렉터리에서는 동작하지 않습니다. 실제 클러스터에 연결된 kubeconfig가 있다면 `mkdir -p .cka`로 연습 디렉터리를 먼저 만드세요.

## 취약점 제보

훅을 우회해 실제 명령이 실행되는 경우처럼 보안과 관련된 문제는 공개 이슈 대신 [비공개 취약점 제보](https://github.com/jhwanchoi/ai-k8s-make-believe/security/advisories/new)로 알려 주세요.
