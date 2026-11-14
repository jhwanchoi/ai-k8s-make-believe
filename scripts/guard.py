#!/usr/bin/env python3
"""PreToolUse(Bash) guard: block real k8s/node commands while a ai-k8s-make-believe problem is active.

Active = <project>/.cka/ exists (a practice directory), between problems too. Exit 2 blocks the call and stderr goes back to Claude.
Usage: hook stdin JSON | --selftest
"""
import json
import os
import re
import sys
from pathlib import Path

TOOLS = r"kubectl|k|etcdctl|etcdutl|kubeadm|kubelet|systemctl|journalctl|crictl|ctr|helm|kustomize|ssh|scp"
# ponytail: regex on command position, not a shell parser. Catches accidental runs
# (sudo/env/wrappers, sh -c, $(...), pipes), not deliberate obfuscation.
WRAPPERS = r"sudo|doas|env|command|builtin|exec|eval|nice|ionice|stdbuf|nohup|time|watch|xargs|timeout"
# A wrapper may take any options/values before the tool (lazy, so `nice -n 10 kubectl` and
# `timeout -s KILL 5 kubectl` match). Errs toward blocking: only active in practice dirs.
PREFIX = r"(?:(?:" + WRAPPERS + r")(?:\s+\S+)*?\s+|\w+=\S*\s+)*"
CMD = re.compile(
    r"(?:^|[;&|({`]|\$\(|-c\s+['\"])\s*" + PREFIX
    + r"[\\'\"]?(?:\S*/)?(?P<tool>" + TOOLS + r")(?=\s|$|[;&|)`'\"])",
    re.M,
)
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)(\w+)\1")
# A line that runs a shell (`bash <<X`, `cat <<X | sh`): its heredoc body is code, not data.
SHELL = re.compile(
    r"(?:^|[;&|({`]|\$\()\s*" + PREFIX + r"(?:\S*/)?(?:bash|sh|zsh|dash|ksh)(?=\s|$|[;&|)`'\"<])"
)


def strip_heredocs(cmd):
    """Drop quoted heredoc bodies fed to a non-shell: they are data (history logs, notes).

    Unquoted bodies stay: the shell expands $(...) and backticks inside them.
    """
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        if SHELL.search(line):
            continue
        for m in HEREDOC.finditer(line):
            if not m.group(1):
                continue
            end = next((j for j in range(i, len(lines)) if lines[j].strip() == m.group(2)), None)
            if end is None:  # no terminator (e.g. $((1<<2))): not a heredoc, keep scanning
                continue
            i = end + 1
    return "\n".join(out)


def blocked(cmd):
    m = CMD.search(strip_heredocs(cmd))
    return m.group("tool") if m else None


def main():
    if sys.argv[1:] == ["--selftest"]:
        return _selftest()
    data = json.load(sys.stdin)
    roots = {os.environ.get("CLAUDE_PROJECT_DIR"), data.get("cwd")} - {None, ""}
    if not any((Path(r) / ".cka").is_dir() for r in roots):
        return 0
    tool = blocked(data.get("tool_input", {}).get("command", ""))
    if not tool:
        return 0
    print(
        f"ai-k8s-make-believe: CKA 연습 디렉터리(.cka/ 있음)라 실제 '{tool}' 실행을 막았습니다. "
        "사용자 명령은 로컬에서 실행하지 말고 state.json 기준으로 시뮬레이션만 하세요. "
        "실제 클러스터 작업은 .cka/ 가 없는 다른 디렉터리에서 하라고 사용자에게 안내하세요.",
        file=sys.stderr,
    )
    return 2


def _selftest():
    must_block = [
        "kubectl get po",
        "sudo -E kubectl drain node01 --ignore-daemonsets",
        "ETCDCTL_API=3 etcdctl snapshot save /opt/x.db",
        "ls && kubeadm upgrade plan",
        "bash -c 'systemctl restart kubelet'",
        "echo $(kubectl get ns)",
        "/usr/local/bin/helm install x y",
        "k get no",
        "cat x | xargs kubectl apply -f",
        "kubectl apply -f - <<EOF\nkind: Pod\nEOF",
        "cat <<'X'\ndata\nX\nkubeadm reset -f",
        "env -i kubectl get po",
        "nice -n 10 kubectl drain node01",
        "timeout -s KILL 5 kubectl get po",
        "command kubectl get po",
        "\\kubectl get po",
        "'kubectl' get po",
        "echo $((1<<2))\nkubectl delete ns prod",
        "cat <<EOF\nno terminator\nkubectl delete ns prod",
        "cat <<EOF\n$(kubectl get pods)\nEOF",
        "bash <<EOF\nkubectl get pods\nEOF",
        "sh <<'X'\nkubectl get pods\nX",
        "cat <<EOF | bash\nkubectl get po\nEOF",
        "cat <<'EOF' | sudo sh\nkubectl get po\nEOF",
    ]
    must_allow = [
        "python3 grade.py .cka/q03-kubeadm-upgrade",
        "echo kubectl",
        "kubeconform pod.yaml",
        "kill 1",
        "grep -r kubectl-neat .",
        "cat <<'EOF'\n$(kubectl get pods)\nEOF",
        "ssh-keygen -l <<'X'\nkubectl get po\nX",
        "date '+### #3  %F %H:%M' >> .cka/q1/history.md; "
        "cat >> .cka/q1/history.md <<'CKA_HISTORY_EOF'\n"
        "$ kubectl drain node01\nkubectl delete ns prod\nsystemctl stop kubelet\nCKA_HISTORY_EOF",
    ]
    for c in must_block:
        assert blocked(c), f"should block: {c!r}"
    for c in must_allow:
        assert not blocked(c), f"should allow: {c!r} (matched {blocked(c)})"
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
