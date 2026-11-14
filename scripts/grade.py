#!/usr/bin/env python3
"""ai-k8s-make-believe deterministic grader: .cka/<id>/state.json vs the ```json rubric block in answer-key.md.

Usage: grade.py <problem_dir> | --check-init <problem_dir> | --selftest
Prints one line per rubric item (PASS / FAIL / MANUAL) and a SCORE line. FAIL lines end with
the actual value at the path (never the expected one). MANUAL items (op=llm) are judged by the grader agent.
--check-init lints the rubric against state.init.json and exits 1 if it is already solved or its paths
don't fit the state.
"""
import json
import re
import sys
from pathlib import Path

MISSING = object()
ROOTS = {"clusters", "hosts", "meta"}


def get(obj, path):
    for key in path:
        if isinstance(obj, dict) and key in obj:
            obj = obj[key]
        elif isinstance(obj, list) and isinstance(key, int) and -len(obj) <= key < len(obj):
            obj = obj[key]
        else:
            return MISSING
    return obj


def match(actual, expected):
    """Recursive partial match: dict = subset, list = every expected item matched by some actual item."""
    if isinstance(actual, dict) and isinstance(expected, dict):
        return all(k in actual and match(actual[k], v) for k, v in expected.items())
    if isinstance(actual, list) and isinstance(expected, list):
        return all(any(match(a, e) for a in actual) for e in expected)
    return actual == expected


def contains(actual, value):
    """str: substring. list: some element matches value. dict / list-vs-list: partial match."""
    if isinstance(actual, str):
        return isinstance(value, str) and value in actual
    if isinstance(actual, list) and not isinstance(value, list):
        return any(match(a, value) for a in actual)
    return match(actual, value)


def check(item, state):
    op = item["op"]
    if op == "llm":
        return "MANUAL"
    actual = get(state, item.get("path", []))
    if op == "absent":
        ok = actual is MISSING
    elif actual is MISSING:
        ok = False
    elif op == "exists":
        ok = True
    elif op == "eq":
        ok = actual == item["value"]
    elif op == "contains":
        ok = contains(actual, item["value"])
    elif op == "regex":
        ok = isinstance(actual, str) and re.search(item["value"], actual, re.M) is not None
    else:
        raise ValueError(f"unknown op {op!r} in rubric item {item.get('id')!r}")
    return "PASS" if ok else "FAIL"


def show(value, limit=120):
    if value is MISSING:
        return "<missing>"
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "..."


def lint_init(rubric, init):
    """Problems that mean the rubric is wrong before the user types anything."""
    problems = []
    for item in rubric:
        if item["op"] == "llm":
            continue
        path = item.get("path", [])
        if not path or path[0] not in ROOTS:
            problems.append(f"{item['id']}: path 는 {sorted(ROOTS)} 중 하나로 시작해야 합니다: {path}")
        elif len(path) > 1 and get(init, path[:2]) is MISSING:
            problems.append(f"{item['id']}: 초기 상태에 {path[:2]} 가 없습니다")
    auto = [item for item in rubric if item["op"] != "llm"]
    if auto and all(check(item, init) == "PASS" for item in auto):
        problems.append("초기 상태에서 자동 채점 항목이 이미 모두 PASS 입니다")
    return problems


def load_rubric(text):
    m = re.search(r"```json rubric\s*\n(.*?)\n```", text, re.S)
    if not m:
        sys.exit("answer-key.md: ```json rubric 블록이 없습니다")
    return json.loads(m.group(1))


def main(problem_dir):
    d = Path(problem_dir)
    state = json.loads((d / "state.json").read_text())
    rubric = load_rubric((d / "answer-key.md").read_text())
    got = auto = manual = 0
    for item in rubric:
        result, pts = check(item, state), item.get("points", 1)
        if result == "MANUAL":
            manual += pts
        else:
            auto += pts
            got += pts if result == "PASS" else 0
        actual = f" [actual: {show(get(state, item.get('path', [])))}]" if result == "FAIL" else ""
        print(f"{result:<6} {item['id']} ({pts}pt): {item.get('desc', '')}{actual}")
    print(f"SCORE auto {got}/{auto}, manual {manual}pt pending")


def check_init(problem_dir):
    d = Path(problem_dir)
    init = json.loads((d / "state.init.json").read_text())
    problems = lint_init(load_rubric((d / "answer-key.md").read_text()), init)
    for p in problems:
        print(f"PROBLEM {p}")
    print("CHECK-INIT ok" if not problems else f"CHECK-INIT failed ({len(problems)})")
    return 1 if problems else 0


def _selftest():
    state = {
        "clusters": {"c1": {"objects": {
            "prod/service/web": {"spec": {"selector": {"app": "web", "tier": "fe"},
                                          "ports": [{"port": 80, "targetPort": 8080, "protocol": "TCP"}]}},
            "_/clusterrole/r": {"rules": [{"resources": ["pods"], "verbs": ["get", "list", "watch"]}]},
        }}},
        "hosts": {"cp": {"files": {"/opt/x.db": "<binary: etcd snapshot>", "/etc/m.yaml": "kind: Pod\nimage: nginx:1.27\n"}}},
    }
    svc = ["clusters", "c1", "objects", "prod/service/web", "spec"]
    verbs = ["clusters", "c1", "objects", "_/clusterrole/r", "rules", 0, "verbs"]
    m_yaml = ["hosts", "cp", "files", "/etc/m.yaml"]

    def ok(op, path, value=None):
        return check({"id": "t", "op": op, "path": path, "value": value}, state) == "PASS"

    assert ok("exists", ["hosts", "cp", "files", "/opt/x.db"])
    assert ok("absent", ["hosts", "cp", "files", "/nope"])
    assert not ok("exists", svc + ["type"])
    assert not ok("eq", svc + ["type"], None)  # missing != null
    assert ok("eq", svc + ["selector"], {"app": "web", "tier": "fe"})
    assert not ok("eq", svc + ["selector"], {"app": "web"})
    assert ok("contains", svc + ["selector"], {"app": "web"})
    assert not ok("contains", svc + ["selector"], {"app": "we"})  # no substring inside dicts
    assert ok("contains", svc + ["ports"], {"port": 80, "targetPort": 8080})  # partial list element
    assert ok("contains", verbs, ["get", "list"])  # list subset
    assert not ok("contains", verbs, ["delete"])
    assert ok("contains", m_yaml, "nginx:1.27")
    assert ok("regex", m_yaml, r"^image: nginx:1\.\d+$")
    assert check({"id": "t", "op": "llm"}, state) == "MANUAL"
    assert load_rubric('x\n```json rubric\n[{"id": "a", "op": "llm"}]\n```\n') == [{"id": "a", "op": "llm"}]
    assert show(MISSING) == "<missing>" and show({"a": 1}) == '{"a": 1}'
    assert show("x" * 300).endswith("...") and len(show("x" * 300)) == 123

    exists_x = {"id": "x", "op": "exists", "path": ["hosts", "cp", "files", "/opt/x.db"]}
    new_svc = {"id": "n", "op": "exists", "path": ["clusters", "c1", "objects", "prod/service/new"]}
    llm = {"id": "l", "op": "llm"}
    assert lint_init([new_svc, llm], state) == []
    assert any("이미 모두 PASS" in p for p in lint_init([exists_x], state))
    assert lint_init([llm], state) == []  # nothing automatic to lint
    assert any("초기 상태에" in p for p in lint_init([dict(new_svc, path=["clusters", "c9", "objects"])], state))
    assert any("시작해야" in p for p in lint_init([dict(new_svc, path=["objects", "prod/service/new"])], state))
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    elif len(sys.argv) == 3 and sys.argv[1] == "--check-init":
        sys.exit(check_init(sys.argv[2]))
    elif len(sys.argv) == 2:
        main(sys.argv[1])
    else:
        sys.exit(__doc__)
