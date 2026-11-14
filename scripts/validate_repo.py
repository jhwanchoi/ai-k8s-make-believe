#!/usr/bin/env python3
"""PR과 main push마다 CI에서 실행하는 저장소 검사.

1. plugin.json과 marketplace.json이 올바른 JSON이고, 플러그인 이름이 서로 맞고, 아이콘이 실제로 있는지
2. skill, agent, command 파일의 frontmatter에 필요한 필드가 있는지 (skill과 agent는 name이 폴더/파일 이름과 같은지)
3. scripts/grade.py, scripts/guard.py, scripts/import_cka_prep.py, scripts/diagram.py, scripts/build_kubectl_index.py, scripts/build_kubectl_flags_js.py, simulator/server.py의 selftest가 통과하는지
4. 추적 중인 파일에 연습 상태(.cka/), kubeconfig 비밀값, 개인 키, 이메일, 휴대전화 번호 형식이 없는지

표준 라이브러리만 사용한다.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []

BLOCKED_FILE = re.compile(r"(^|/)\.cka/|(^|/)kubeconfig$|\.kubeconfig$")
SECRET = re.compile(r"client-(?:key|certificate)-data:\s*\S|-----BEGIN [A-Z ]*PRIVATE KEY-----")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_EMAIL = re.compile(r"@users\.noreply\.github\.com$|^noreply@anthropic\.com$")
SSH_REMOTE = re.compile(r"git@[A-Za-z0-9.-]+:[^\s)]*")
PHONE = re.compile(r"\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b")


def frontmatter(md: Path) -> dict[str, str] | None:
    match = re.match(r"^---\n(.*?)\n---\n", md.read_text(encoding="utf-8"), re.S)
    if not match:
        errors.append(f"frontmatter가 없음: {md.relative_to(ROOT)}")
        return None
    return {k.strip(): v.strip() for k, v in
            (line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)}


def check_component(md: Path, expected_name: str | None) -> None:
    fields = frontmatter(md)
    if fields is None:
        return
    rel = md.relative_to(ROOT)
    if not fields.get("description"):
        errors.append(f"frontmatter에 description이 없음: {rel}")
    if expected_name is not None and fields.get("name") != expected_name:
        errors.append(f"name({fields.get('name')})이 이름({expected_name})과 다름: {rel}")


def check_manifests() -> None:
    try:
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"manifest를 읽을 수 없음: {e}")
        return
    if plugin.get("name") not in {p.get("name") for p in market.get("plugins", [])}:
        errors.append("marketplace.json에 plugin.json의 플러그인이 등록되지 않음")
    icon = plugin.get("icon")
    if icon and not (ROOT / icon).is_file():
        errors.append(f"plugin.json의 icon 파일이 없음: {icon}")

    for skill_md in sorted(ROOT.glob("skills/*/SKILL.md")):
        check_component(skill_md, skill_md.parent.name)
    for agent_md in sorted(ROOT.glob("agents/*.md")):
        check_component(agent_md, agent_md.stem)
    for command_md in sorted(ROOT.glob("commands/*.md")):
        check_component(command_md, None)


def check_selftests() -> None:
    scripts = [f"scripts/{name}" for name in ("grade.py", "guard.py", "import_cka_prep.py", "diagram.py",
                                              "build_kubectl_index.py", "build_kubectl_flags_js.py")]
    for script in scripts + ["simulator/server.py"]:
        result = subprocess.run([sys.executable, "-I", str(ROOT / script), "--selftest"],
                                capture_output=True, text=True)
        if result.returncode != 0:
            errors.append(f"{script} selftest 실패: {(result.stderr or result.stdout).strip()[-300:]}")


def check_private_data() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()

    for rel in tracked:
        if BLOCKED_FILE.search(rel):
            errors.append(f"연습 상태나 접속 정보로 보이는 파일이 저장소에 있음: {rel}")
            continue
        try:
            lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for no, line in enumerate(lines, 1):
            if SECRET.search(line):
                errors.append(f"{rel}:{no}: kubeconfig 비밀값이나 개인 키 형식 발견")
            for email in EMAIL.findall(SSH_REMOTE.sub("", line)):
                if not ALLOWED_EMAIL.search(email):
                    errors.append(f"{rel}:{no}: 이메일 형식 발견")
            if PHONE.search(line):
                errors.append(f"{rel}:{no}: 휴대전화 번호 형식 발견")


def main() -> int:
    check_manifests()
    check_selftests()
    check_private_data()
    if errors:
        print("검사 실패:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("검사 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
