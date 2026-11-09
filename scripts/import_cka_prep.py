#!/usr/bin/env python3
"""CKA-PREP 형식 저장소(Question-<n> <주제>/Questions.bash, SolutionNotes.bash, LabSetUp.bash)를 받아
시뮬레이터 문제 파일(<name>.md), 풀이 파일(<name>.answers.md), 환경 파일(<name>.setup.md)을 로컬에 만든다.
환경 파일은 grader 가 가상 초기 상태를 만들 때만 읽는다. 고장 원인이 드러나므로 시험 화면에 보이지 않는다.

문제 원문은 레포에 커밋하지 않는다. 각자 자기 연습 폴더에 받아 쓴다.
Usage: import_cka_prep.py <GitHub 링크 | owner/repo> <out_dir> [--ref <commit|branch>] [--name <file name>] [--tar <받아 둔 tar.gz>] [--force]
       import_cka_prep.py --check <problems.md> [<answers.md>]   # 형식 검사(직접 쓴 파일도)
       import_cka_prep.py --selftest
표준 라이브러리만 사용한다.
"""
import io
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ARCH = "Cluster Architecture, Installation & Configuration"
# 폴더 주제 낱말 → CKA 도메인. 앞에서부터 처음 맞는 것을 쓴다.
DOMAIN_RULES = [
    (r"etcd|fix|troubleshoot|broken|debug", "Troubleshooting"),
    (r"gateway|ingress|network|nodeport|service|dns|tls|cni", "Services & Networking"),
    (r"storage|persistent|pvc|\bpv\b|volume", "Storage"),
    (r"helm|argo|crd|cri|kubeadm|rbac|kustomize|install|upgrade", ARCH),
    (r"taint|toleration|sidecar|hpa|resource|priority|deploy|schedul|affinity|pod", "Workloads & Scheduling"),
]
FOLDER = re.compile(r"(?:^|/)Question-(\d+) ?([^/]*)/(Questions|SolutionNotes|LabSetUp)\.bash$")


def classify(topic):
    for pattern, domain in DOMAIN_RULES:
        if re.search(pattern, topic, re.I):
            return domain
    return ARCH


def weights(count):
    """합이 100 인 정수 배점. 나머지는 앞 문항부터 1씩."""
    base, extra = divmod(100, count)
    return [base + (1 if i < extra else 0) for i in range(count)]


def question_text(bash):
    lines = []
    for line in bash.splitlines():
        if re.match(r"\s*#\s*Video\s*link", line, re.I):
            continue  # 풀이 영상은 정답 공개라 뺀다
        lines.append(re.sub(r"^#\s?", "", line.rstrip()))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines).strip())


def read_questions(tar_bytes):
    """tar.gz 안의 Question 폴더를 {n: {topic, Questions, SolutionNotes, LabSetUp}} 로. 디스크에 풀지 않는다."""
    found = {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            m = FOLDER.search(member.name)
            if not (m and member.isfile()):
                continue
            n, topic, kind = int(m.group(1)), m.group(2).strip(), m.group(3)
            entry = found.setdefault(n, {"topic": topic})
            entry[kind] = tar.extractfile(member).read().decode("utf-8", "replace")
    return dict(sorted(found.items()))


def render(repo, ref, questions):
    nums = list(questions)
    if nums != list(range(1, len(nums) + 1)):
        raise ValueError(f"문항 번호가 1부터 연속이 아닙니다: {nums}")
    url = f"https://github.com/{repo}"
    head = (f"출처: [{url}]({url}) (`{ref}`), 문항 n = 원본 `Question-n` 폴더. "
            "이 파일은 import_cka_prep.py 가 로컬에 만든 것이다. 원작자 권리는 원작자에게 있으니 공개 저장소에 올리지 않는다.")
    problems = [f"# {repo.split('/')[-1]} ({len(nums)}문항)\n", head,
                "배점은 균등, domain 은 폴더 주제 낱말로 붙인 추정이다(실제 시험 비중과 다르다).\n"]
    answers = [f"# {repo.split('/')[-1]} 풀이 ({len(nums)}문항)\n", head,
               "시험 중에는 보지 않는다. 시뮬레이터는 시험이 끝난 뒤 리포트에서만 연다.\n"]
    setups = [f"# {repo.split('/')[-1]} 환경 ({len(nums)}문항)\n", head,
              "원본 LabSetUp.bash. grader 가 가상 초기 상태(state.json)를 만들 때만 읽는다. 고장 원인이 드러나므로 응시자는 보지 않는다.\n"]
    for (n, q), weight in zip(questions.items(), weights(len(nums))):
        if "Questions" not in q:
            raise ValueError(f"Question-{n} 에 Questions.bash 가 없습니다")
        problems.append(f"## Q{n}\ndomain: {classify(q['topic'])}\nweight: {weight}\n\n{question_text(q['Questions'])}\n")
        solution = q.get("SolutionNotes", "(원본에 SolutionNotes.bash 없음)").strip().replace("```", "` ` `")
        answers.append(f"## Q{n}\n\n```bash\n{solution}\n```\n\n(원본: [Question-{n}]({url}/tree/{ref}))\n")
        setup = q.get("LabSetUp", "# (원본에 LabSetUp.bash 없음)").strip().replace("```", "` ` `")
        setups.append(f"## Q{n}\n\n```bash\n{setup}\n```\n")
    return "\n".join(problems), "\n".join(answers), "\n".join(setups)


def parse_source(source):
    """`owner/repo`, `https://github.com/owner/repo(.git)`, `.../tree/<ref>(/...)` → (repo, ref 또는 None)."""
    m = re.fullmatch(r"(?:https?://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/tree/([^/?#]+).*)?/?", source.strip())
    if not m:
        raise ValueError(f"GitHub 저장소 링크가 아닙니다: {source}")
    return f"{m.group(1)}/{m.group(2)}", m.group(3)


def _sections(text):
    sections, fence = [], None
    for line in text.split("\n"):
        marker = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        heading = re.fullmatch(r"## Q([1-9]\d*)[ \t]*", line) if fence is None else None
        if heading:
            sections.append((int(heading[1]), []))
        elif sections:
            sections[-1][1].append(line)
    return [(n, "\n".join(lines)) for n, lines in sections]


def check_pair(problems_md, answers_md=None):
    """UI parseFile/parseAnswers와 같은 문항·배점·bash·원본 링크 규칙."""
    def read(path):
        return Path(path).read_text().removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    text = read(problems_md)
    if not re.search(r"^#[ \t]+(\S[^\n]*)$", text, re.M):
        raise ValueError("# 제목이 없습니다")
    blocks = _sections(text)
    nums = [n for n, _ in blocks]
    if not nums or nums != list(range(1, len(nums) + 1)):
        raise ValueError("## Q 번호가 1부터 연속이 아닙니다")
    total = 0
    for n, body in blocks:
        match = re.fullmatch(r"\s*[ \t]*domain:[ \t]*([^\n]+)\n[ \t]*weight:[ \t]*([1-9]\d*)[ \t]*\n[ \t]*\n([\s\S]+)", body)
        if not match or not match[3].strip() or int(match[2]) > 9007199254740991:
            raise ValueError(f"Q{n}: domain, 양의 정수 weight, 빈 줄, 원문이 필요합니다")
        total += int(match[2])
    if total != 100:
        raise ValueError(f"배점 합이 100 이 아닙니다: {total}")
    if answers_md:
        answers = read(answers_md)
        if not re.search(r"^# +\S", answers, re.M):
            raise ValueError("풀이 파일에 # 제목이 없습니다")
        answer_blocks = _sections(answers)
        seen = set()
        if not answer_blocks:
            raise ValueError("풀이 문항이 없습니다")
        for n, body in answer_blocks:
            if n in seen:
                raise ValueError(f"풀이 Q{n} 번호가 중복되었습니다")
            seen.add(n)
            match = re.fullmatch(r"\s*\n```bash[ \t]*\n([\s\S]*?)\n```[ \t]*\n\s*\n\(원본: \[([^\]\n]+)\]\(([^\n]+)\)\)[ \t]*\s*", body)
            if not match:
                raise ValueError(f"풀이 Q{n} 에 bash 블록과 원본 링크가 필요합니다")
            url = urllib.parse.urlsplit(match[3].strip())
            if url.scheme.lower() not in ("http", "https") or not url.hostname:
                raise ValueError(f"풀이 Q{n} 원본 링크는 http/https 주소여야 합니다")
    return len(nums)


def main(argv):
    args, opts = [], {"--ref": None, "--name": None, "--tar": None}
    force = "--force" in argv
    it = iter(a for a in argv if a != "--force")
    for a in it:
        if a in opts:
            opts[a] = next(it)
        else:
            args.append(a)
    if args[:1] == ["--check"] and len(args) in (2, 3):
        print(f"형식 OK: {check_pair(*args[1:])}문항")
        return
    if len(args) != 2:
        sys.exit(__doc__)
    repo, link_ref = parse_source(args[0])
    out_dir = args[1]
    ref = opts["--ref"] or link_ref or "HEAD"
    url = f"https://codeload.github.com/{repo}/tar.gz/{ref}"
    if opts["--tar"]:
        tar_bytes = Path(opts["--tar"]).expanduser().read_bytes()
    else:
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                tar_bytes = r.read()
        except OSError as e:  # 사내 프록시 인증서 등. 검증을 끄지 않고 curl 로 받게 한다
            sys.exit(f"내려받기 실패({e}). `curl -fsSL {url} -o /tmp/src.tar.gz` 로 받은 뒤 --tar /tmp/src.tar.gz 로 다시 실행하세요.")
    questions = read_questions(tar_bytes)
    if not questions:
        sys.exit(f"NOT_CKA_PREP: {repo} 에서 Question-<n> 폴더를 찾지 못했습니다. 이 형식이 아니면 SKILL 의 '다른 형식' 절차를 따른다.")
    problems, answers, setups = render(repo, ref, questions)
    name = opts["--name"] or repo.split("/")[-1].lower()
    out = Path(out_dir).expanduser()
    targets = [out / f"{name}{suffix}" for suffix in (".md", ".answers.md", ".setup.md")]
    existing = [str(t) for t in targets if t.exists()]
    if existing and not force:  # 손으로 고친 메모 · 정오표를 덮지 않게
        sys.exit(f"이미 있는 파일: {', '.join(existing)}. 덮어쓰려면 --force 를 붙이세요.")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.md").write_text(problems)
    (out / f"{name}.answers.md").write_text(answers)
    (out / f"{name}.setup.md").write_text(setups)
    print(f"{len(questions)}문항: {out / (name + '.md')}, {out / (name + '.answers.md')}, {out / (name + '.setup.md')}")


def _selftest():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, text in {
            "r-abc/Question-1 Etcd-Fix/Questions.bash": "# Question:\n# Fix it\n\n# Video Link - https://youtu.be/x\n",
            "r-abc/Question-1 Etcd-Fix/SolutionNotes.bash": "kubectl get po\n",
            "r-abc/Question-1 Etcd-Fix/LabSetUp.bash": "sed -i s/2379/2380/ /etc/kubernetes/manifests/kube-apiserver.yaml\n",
            "r-abc/Question-2 Gateway-API/Questions.bash": "# Task\n# make a route\n",
            "r-abc/scripts/run.sh": "echo hi\n",
        }.items():
            data = text.encode()
            info = tarfile.TarInfo(path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    qs = read_questions(buf.getvalue())
    assert list(qs) == [1, 2] and qs[1]["topic"] == "Etcd-Fix"
    problems, answers, setups = render("o/r", "abc", qs)
    assert "## Q1\ndomain: Troubleshooting\nweight: 50\n\nQuestion:\nFix it\n" in problems
    assert "youtu" not in problems and "kubectl get po" not in problems  # 풀이 · 영상은 문제 파일에 없다
    assert "domain: Services & Networking" in problems
    assert "```bash\nkubectl get po\n```" in answers and "SolutionNotes.bash 없음" in answers
    assert "2380" in setups and "2380" not in problems and "2380" not in answers  # 환경은 환경 파일에만
    assert "LabSetUp.bash 없음" in setups
    assert weights(17) == [6] * 15 + [5] * 2 and sum(weights(3)) == 100
    try:
        render("o/r", "abc", {2: qs[2]})
        raise AssertionError("gap should fail")
    except ValueError:
        pass
    assert parse_source("https://github.com/owner/cka-practice") == ("owner/cka-practice", None)
    assert parse_source("https://github.com/o/r.git") == ("o/r", None)
    assert parse_source("https://github.com/o/r/tree/04ea3b6/Question-1") == ("o/r", "04ea3b6")
    assert parse_source("o/r") == ("o/r", None)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p, a = Path(d, "x.md"), Path(d, "x.answers.md")
        p.write_text(problems)
        a.write_text(answers)
        assert check_pair(p, a) == 2
        p.write_text(problems.replace("weight: 50", "weight: 40", 1))
        try:
            check_pair(p)
            raise AssertionError("sum != 100 should fail")
        except ValueError:
            pass
        for invalid in (problems.replace("weight: 50", "weight: 0", 1).replace("weight: 50", "weight: 100", 1),):
            p.write_text(invalid)
            try:
                check_pair(p)
                raise AssertionError("weight 0 should fail")
            except ValueError:
                pass
        p.write_text(problems)
        a.write_text(re.sub(r"\(원본:.*\)", "", answers))
        try:
            check_pair(p, a)
            raise AssertionError("missing source link should fail")
        except ValueError:
            pass
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    else:
        main(sys.argv[1:])
