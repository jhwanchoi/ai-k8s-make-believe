#!/usr/bin/env python3
"""시뮬레이터 웹 화면의 실서버: simulator/static 을 열고, UIUX.md 의 API 를 백그라운드 Claude Code 세션으로 처리한다.

명령(/api/cmd)은 `claude -p` 단발 호출(도구 없음, cmd-prompt.md)로 출력과 상태 변경을 받고, 서버가 state.json 에 적용한다.
출제·이동·제출·종료는 연습 폴더를 cwd 로 `claude -p --plugin-dir <repo> --resume` 플러그인 세션(시험 하나에 하나)으로 보낸다.
요청은 한 번에 하나만 처리한다. 127.0.0.1 에만 연다. 사용자 전역 설정은 읽지 않는다(--setting-sources project,local).
풀이(<name>.answers.md)와 환경(<name>.setup.md), answer-key 는 시험이 끝나기 전에 브라우저로 보내지 않는다.

Usage: server.py [--practice ~/cka-practice] [--port 8765] [--model sonnet] [--browser-url http://127.0.0.1:5800/] | --selftest
표준 라이브러리만 사용한다.
"""
import argparse
import json
import os
import posixpath
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "simulator" / "static"
sys.path.insert(0, str(REPO / "scripts"))
from import_cka_prep import _sections  # noqa: E402  문항 나누기는 UI parseFile 과 같은 규칙

PLUGIN = "/ai-k8s-make-believe:"
# E2E 에서 확인한 범위. 파일 쓰기는 --permission-mode acceptEdits 로 연습 폴더 안에서만 된다.
ALLOWED_TOOLS = ["Bash(date:*)", "Bash(cat >> .cka/:*)", "Bash(python3:*)", "Bash(mkdir -p .cka/archive)",
                 "Bash(mv .cka/:*)", "Bash(rm .cka/current)", "Bash(rm .cka/exam.json)", "Read", "Glob",
                 # 힌트 1단계(공식 문서 검색어)를 실제로 찾아보고 확인할 때. 시험에서 열 수 있는 문서 도메인만 연다.
                 "WebSearch", "WebFetch(domain:kubernetes.io)", "WebFetch(domain:helm.sh)",
                 "WebFetch(domain:gateway-api.sigs.k8s.io)"]
HEADLESS = ("이 세션은 ai-k8s-make-believe 웹 시뮬레이터 서버가 headless 로 실행한다. 사용자에게 질문할 수 없으니 "
            "AskUserQuestion 을 쓰지 않는다. 검토(reviewer)에서 이상이 나오면 '무시'를 고른 것으로 진행하고, "
            "검토 결과는 반환값(모의고사면 리포트)에 남긴다.")
EXAM_NAME = re.compile(r"[\w.-]+\.md")
CMD_PROMPT = REPO / "simulator" / "cmd-prompt.md"
RETRO_PROMPT = REPO / "simulator" / "retro-prompt.md"
KUBECTL_REFS = REPO / "skills" / "cka-rules" / "references" / "kubectl"
CHANGE_ROOTS = ("clusters", "hosts", "meta")
TIMEOUT = {"cmd": 600, "start": 1200, "goto": 900, "submit": 600, "end": 1800, "retro": 600}


# ---------- 파일 형식 ----------

def _norm(text):
    return text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def parse_problems(text):
    """UI parseFile 과 같은 형식: # 제목, ## Q<n>, domain:, weight:, 빈 줄, 원문."""
    text = _norm(text)
    title = re.search(r"^#[ \t]+(\S[^\n]*)$", text, re.M)
    if not title:
        raise ValueError("# 제목이 필요합니다.")
    problems = []
    for i, (n, body) in enumerate(_sections(text)):
        m = re.fullmatch(r"\s*[ \t]*domain:[ \t]*([^\n]+)\n[ \t]*weight:[ \t]*([1-9]\d*)[ \t]*\n[ \t]*\n([\s\S]+)", body)
        if not m or n != i + 1 or not m[3].strip():
            raise ValueError("Q 번호는 1부터 연속이어야 하며 domain, 양의 정수 weight, 빈 줄, 원문 순서여야 합니다.")
        problems.append({"n": n, "domain": m[1].strip(), "weight": int(m[2]), "text": m[3].strip()})
    if not problems:
        raise ValueError("## Q1 형식의 문항이 필요합니다.")
    if sum(p["weight"] for p in problems) != 100:
        raise ValueError("문항 배점의 합은 100이어야 합니다.")
    return {"title": title[1], "problems": problems}


def parse_answers(text):
    out = []
    for n, body in _sections(_norm(text)):
        m = re.fullmatch(r"\s*\n```bash[ \t]*\n([\s\S]*?)\n```[ \t]*\n\s*\n\(원본: \[([^\]\n]+)\]\(([^\n]+)\)\)[ \t]*\s*", body)
        if m:
            out.append({"n": n, "bash": m[1], "source": {"label": m[2], "url": m[3].strip()}})
    return out


def exam_file(practice, name):
    """업로드 이름을 연습 폴더 exams/ 안의 파일로만 바꾼다. 경로, 숨김 파일, 풀이·환경 파일은 거부한다."""
    if not isinstance(name, str) or not EXAM_NAME.fullmatch(name) or name.startswith(".") \
            or name.endswith((".answers.md", ".setup.md")):
        raise ValueError("문제 파일 이름은 exams/ 안의 <이름>.md 여야 합니다.")
    exams = (Path(practice) / "exams").resolve()
    path = (exams / name).resolve()
    if path.parent != exams:
        raise ValueError("문제 파일 이름은 exams/ 안의 <이름>.md 여야 합니다.")
    return path


# ---------- Claude 세션 ----------

def parse_stream(lines):
    """claude --output-format stream-json 줄들 -> (session_id, result dict | None). 깨진 줄은 건너뛴다."""
    session, result = None, None
    for line in lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        session = event.get("session_id") or session
        if event.get("type") == "result":
            result = event
    return session, result


# ---------- 웹 명령: 입력 한 번, 출력 한 번 ----------

class OutputStream:
    """모델 텍스트 조각에서 <output> … </output> 안쪽만 흘려보낸다. 태그가 조각 사이에서 잘려도 된다."""
    OPEN, CLOSE = "<output>", "</output>"

    def __init__(self):
        self.buf, self.state, self.started = "", "before", False

    def feed(self, chunk):
        self.buf += chunk
        out = ""
        if self.state == "before":
            i = self.buf.find(self.OPEN)
            if i < 0:
                self.buf = self.buf[-(len(self.OPEN) - 1):]
                return ""
            self.buf, self.state = self.buf[i + len(self.OPEN):], "in"
        if self.state == "in":
            i = self.buf.find(self.CLOSE)
            if i >= 0:
                out, self.buf, self.state = self.buf[:i], "", "after"
            else:  # 닫는 태그의 앞부분일 수 있는 꼬리는 남겨 둔다
                keep = next((k for k in range(min(len(self.CLOSE) - 1, len(self.buf)), 0, -1)
                             if self.CLOSE.startswith(self.buf[-k:])), 0)
                out, self.buf = self.buf[:len(self.buf) - keep], self.buf[len(self.buf) - keep:]
        if not self.started and out:
            out = out.lstrip("\n")  # <output> 바로 뒤 줄바꿈
            self.started = bool(out)
        return out


def parse_reply(text):
    """최종 응답 -> (출력, changes 리스트 | None, 문제 설명). changes 가 없거나 깨지면 None."""
    m = re.search(r"<output>\n?(.*?)</output>", text, re.S)
    output = m[1].rstrip("\n") if m else re.sub(r"<changes>.*?</changes>", "", text, flags=re.S).strip()
    c = re.search(r"<changes>(.*?)</changes>", text, re.S)
    if not c:
        return output, None, "changes 태그 없음"
    try:
        changes = json.loads(c[1].strip() or "[]")
    except json.JSONDecodeError as e:
        return output, None, f"changes JSON 오류: {e.msg}"
    return output, changes, ""


def fmt_path(path):
    out = ""
    for k in path:
        out += f"[{k}]" if isinstance(k, int) else (f'["{k}"]' if "/" in k or "." in k else ("." if out else "") + k)
    return out


def apply_changes(state, changes):
    """changes 를 검증해 새 state 와 history 의 '변경:' 줄을 돌려준다. 하나라도 잘못되면 ValueError (아무것도 적용 안 함)."""
    if not isinstance(changes, list):
        raise ValueError("changes 는 배열이어야 합니다")
    new, lines = json.loads(json.dumps(state)), []
    for c in changes:
        op, path = (c.get("op"), c.get("path")) if isinstance(c, dict) else (None, None)
        if op not in ("set", "delete") or not isinstance(path, list) or not path or path[0] not in CHANGE_ROOTS \
                or any(isinstance(k, bool) or not isinstance(k, (str, int)) for k in path):
            raise ValueError(f"잘못된 변경: {json.dumps(c, ensure_ascii=False)[:120]}")
        if path == ["meta", "cmd_count"]:
            continue  # 서버가 센다
        if op == "set" and "value" not in c:
            raise ValueError(f"set 에 value 가 없습니다: {fmt_path(path)}")
        cur = new
        for k in path[:-1]:
            if isinstance(cur, dict) and isinstance(k, str):
                if k not in cur or not isinstance(cur[k], (dict, list)):
                    if op == "delete":
                        cur = None
                        break
                    cur[k] = {}
                cur = cur[k]
            elif isinstance(cur, list) and isinstance(k, int) and -len(cur) <= k < len(cur):
                cur = cur[k]
            elif op == "delete":
                cur = None
                break
            else:
                raise ValueError(f"경로를 따라갈 수 없습니다: {fmt_path(path)}")
        last = path[-1]
        if op == "set":
            if isinstance(cur, dict) and isinstance(last, str):
                cur[last] = c["value"]
            elif isinstance(cur, list) and isinstance(last, int) and -len(cur) <= last <= len(cur):
                cur[last:last + 1 if last < len(cur) else last] = [c["value"]]
            else:
                raise ValueError(f"경로에 값을 넣을 수 없습니다: {fmt_path(path)}")
            lines.append(f"변경: {fmt_path(path)} = {json.dumps(c['value'], ensure_ascii=False)[:100]}")
        else:
            if isinstance(cur, dict) and isinstance(last, str):
                cur.pop(last, None)
            elif isinstance(cur, list) and isinstance(last, int) and -len(cur) <= last < len(cur):
                del cur[last]
            lines.append(f"변경: {fmt_path(path)} 삭제")
    return new, lines


def kubectl_refs(text):
    """명령에 나온 kubectl 마다 레퍼런스 파일 하나(없으면 상위 명령). 이름 -> 내용."""
    refs = {}
    for line in text.split("\n")[:1]:
        words = re.findall(r"[^\s|;&]+|[|;&]+", line)
        for i, w in enumerate(words):
            if w not in ("kubectl", "k"):
                continue
            path, best, skip = [], "kubectl.md", False
            for a in words[i + 1:]:
                if re.fullmatch(r"[|;&]+", a):
                    break
                if skip or a.startswith("-"):  # 플래그와, 값을 받는 전역 플래그의 값(kubectl -n dev get)
                    skip = not skip and a in ("-n", "--namespace", "--context", "--kubeconfig", "--cluster", "--user")
                    continue
                name = "kubectl_" + "_".join(path + [a]) + ".md"
                if not (KUBECTL_REFS / name).exists():
                    break
                path.append(a)
                best = name
            if best:
                refs[best] = (KUBECTL_REFS / best).read_text()
    return refs


def recent_history(path, n=15):
    try:
        text = path.read_text()
    except OSError:
        return ""
    entries = [e for e in re.split(r"(?m)^(?=### #)", text) if e.startswith("### #")]
    return "".join(entries[-n:]).strip()


def build_cmd_input(cka, pid, state, terminal, host, text):
    """한 번 호출에 넣을 사용자 메시지. answer-key, 풀이, 환경 파일은 읽지 않는다."""
    d = cka / pid
    parts = [f"## 문제\n{(d / 'problem.md').read_text()}",
             f"## 현재 state.json\n{json.dumps(state, ensure_ascii=False)}",
             f"## 최근 명령 기록\n{recent_history(d / 'history.md') or '(없음)'}"]
    for name, body in kubectl_refs(text).items():
        parts.append(f"## kubectl 레퍼런스 {name}\n{body}")
    sizes = [f"{h} {path}: {len(body.encode())}" for h, hv in state.get("hosts", {}).items()
             for path, body in hv.get("files", {}).items() if isinstance(body, str) and not body.startswith("<")]
    parts.append("## 파일 크기 (바이트)\n" + ("\n".join(sizes) or "(없음)"))
    started = time.gmtime((d / "state.init.json").stat().st_mtime) if (d / "state.init.json").exists() else time.gmtime()
    parts.append(f"## 시각\n현재 시각: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
                 f"문제 시작 시각: {time.strftime('%Y-%m-%dT%H:%M:%SZ', started)}")
    parts.append(f"## 실행할 명령\n# terminal={terminal} host={host}\n{text}")
    return "\n\n".join(parts)


def history_entry(n, text, output, change_lines):
    shown = [line for line in output.split("\n") if line.strip()][:3]
    body = "\n".join(f"> {line}" for line in shown) or "> (출력 없음)"
    return (f"### #{n}  {time.strftime('%Y-%m-%d %H:%M')}\n$ {text}\n{body}\n"
            + ("\n".join(change_lines) if change_lines else "변경: 없음") + "\n")


def home_of(state):
    user = state.get("meta", {}).get("user") or "root"
    return "/root" if user == "root" else f"/home/{user}"


def file_path(state, raw):
    """편집기에 연 경로를 절대 경로로: ~ 은 홈, 상대 경로는 meta.cwd 기준, normpath. 이상하면 ValueError."""
    if not isinstance(raw, str) or not raw or len(raw) > 512 or "\x00" in raw:
        raise ValueError("파일 경로가 잘못됐습니다.")
    home = home_of(state)
    if raw == "~" or raw.startswith("~/"):
        raw = home + raw[1:]
    elif not raw.startswith("/"):
        raw = (state.get("meta", {}).get("cwd") or home).rstrip("/") + "/" + raw
    path = posixpath.normpath(raw)
    if not path.startswith("/") or path in ("/", "//") or path.endswith("/"):
        raise ValueError("파일 경로가 잘못됐습니다.")
    return path


def save_file(state, host, path, text):
    """편집기 저장: hosts.<host>.files[path] 와 file_attrs[path].mtime 을 바꾼 새 state 와 history '변경:' 줄."""
    new = json.loads(json.dumps(state))
    h = new.setdefault("hosts", {}).setdefault(host, {})
    h.setdefault("files", {})[path] = text
    attrs = h.setdefault("file_attrs", {}).setdefault(path, {})
    for key, default in (("mode", "-rw-r--r--"), ("owner", "root"), ("group", "root")):
        attrs.setdefault(key, default)
    attrs["mtime"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    attrs.pop("size", None)  # 크기는 내용 길이로 계산한다
    return new, f'변경: hosts.{host}.files["{path}"] 저장 ({len(text.encode())} bytes)'


class Claude:
    def __init__(self, practice, model):
        self.practice, self.model = Path(practice), model
        self.lock = threading.Lock()
        self.session_file = self.practice / ".cka" / "server-session.json"

    def session(self):
        try:
            return json.loads(self.session_file.read_text())["session_id"]
        except (OSError, ValueError, KeyError):
            return None

    def ask(self, prompt, on_text, system=CMD_PROMPT, kind="cmd"):
        """단발 호출(웹 명령, 행동 회고): 도구 없음, 세션 저장 없음, 기본 시스템 프롬프트 대신 system 파일.
        모델 텍스트 조각마다 on_text 를 부르고 (최종 텍스트, 비용, 초) 를 돌려준다."""
        args = ["claude", "-p", "--model", self.model, "--setting-sources", "project,local", "--no-session-persistence",
                "--tools", "", "--system-prompt", system.read_text(),
                "--output-format", "stream-json", "--verbose", "--include-partial-messages"]
        started = time.time()
        errors = tempfile.TemporaryFile(mode="w+")
        proc = subprocess.Popen(args, cwd=self.practice, env={**os.environ, "KUBECONFIG": "/dev/null"},
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True)
        timer = threading.Timer(TIMEOUT[kind], proc.kill)
        timer.start()
        result = None
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                delta = (event.get("event") or {}).get("delta") or {} if event.get("type") == "stream_event" else {}
                if delta.get("type") == "text_delta":
                    on_text(delta.get("text", ""))
                elif event.get("type") == "result":
                    result = event
            proc.wait()
        finally:
            timer.cancel()
        seconds = round(time.time() - started, 1)
        if not result or result.get("is_error") or proc.returncode:
            errors.seek(0)
            detail = (result or {}).get("result") or errors.read()[-300:] or "응답이 없습니다"
            raise RuntimeError(f"Claude 실행 실패 ({kind}): {detail.strip()}")
        return result.get("result") or "", result.get("total_cost_usd"), seconds

    def forget(self):
        self.session_file.unlink(missing_ok=True)

    def run(self, kind, prompt, on_line=None):
        """프롬프트 하나를 보내고 마지막 결과 텍스트를 돌려준다. on_line 은 줄이 올 때마다 불린다(SSE keepalive 용)."""
        args = ["claude", "-p", "--plugin-dir", str(REPO), "--add-dir", str(REPO), "--permission-mode", "acceptEdits",
                "--output-format", "stream-json", "--verbose", "--include-partial-messages", "--model", self.model,
                "--append-system-prompt", HEADLESS, "--allowedTools", *ALLOWED_TOOLS,
                # 사용자 전역 설정(~/.claude/settings.json 의 훅·플러그인·MCP)을 읽지 않는다. 한 번에 30초 넘게 걸리던 원인.
                # 이 플러그인 훅(guard)은 --plugin-dir 로 들어오므로 그대로 동작한다.
                "--setting-sources", "project,local"]
        sid = self.session()
        if sid:
            args += ["--resume", sid]
        env = {**os.environ, "KUBECONFIG": "/dev/null"}
        started = time.time()
        errors = tempfile.TemporaryFile(mode="w+")  # stderr 를 파이프로 두면 많이 쌓일 때 멈출 수 있다
        proc = subprocess.Popen(args, cwd=self.practice, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=errors, text=True)
        timer = threading.Timer(TIMEOUT[kind], proc.kill)
        timer.start()
        lines = []
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
            for line in proc.stdout:
                lines.append(line)
                if on_line:
                    on_line()
            proc.wait()
        finally:
            timer.cancel()
        session, result = parse_stream(lines)
        if session:
            self.session_file.parent.mkdir(exist_ok=True)
            self.session_file.write_text(json.dumps({"session_id": session}))
        info = {"at": int(started), "kind": kind, "seconds": round(time.time() - started, 1),
                "session_cost_usd": (result or {}).get("total_cost_usd"), "session_id": session, "exit": proc.returncode}
        with open(self.practice / ".cka" / "server-log.jsonl", "a") as log:
            log.write(json.dumps(info) + "\n")
        print(f"[claude] {kind} {info['seconds']}s session ${info['session_cost_usd']}", file=sys.stderr)
        if not result or result.get("is_error") or proc.returncode:
            errors.seek(0)
            detail = (result or {}).get("result") or errors.read()[-300:] or "응답이 없습니다"
            raise RuntimeError(f"Claude 실행 실패 ({kind}): {detail.strip()}")
        return result.get("result") or ""


# ---------- 시험 상태 (파일에서 읽기) ----------

class Exams:
    def __init__(self, practice):
        self.practice = Path(practice)
        self.cka = self.practice / ".cka"
        self.meta_file = self.cka / "server-exam.json"

    def _json(self, path, default=None):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return default

    def meta(self):
        return self._json(self.meta_file)

    def plugin_exam(self):
        return self._json(self.cka / "exam.json")

    def summary(self):
        """UI 가 쓰는 시험 요약. 문제 원문만 담고 풀이·환경·answer-key 는 담지 않는다."""
        meta = self.meta()
        if not meta:
            return None
        parsed = parse_problems(exam_file(self.practice, meta["file"]).read_text())
        plugin = self.plugin_exam() or {}
        ids = {p.get("n"): p.get("id") for p in plugin.get("problems", [])}
        problems = []
        for p in parsed["problems"]:
            pid = ids.get(p["n"])
            state = self._json(self.cka / pid / "state.json", {}) if pid else {}
            m = state.get("meta", {})
            host, ctx = m.get("host", "controlplane"), m.get("context", "k8s-c1")
            problems.append({**p, "id": pid or f"q{p['n']}", "host": host, "context": ctx, "contexts": {host: ctx},
                             "visited": bool(pid), "meta": {"submitted": bool(m.get("submitted"))}})
        return {"title": parsed["title"], "problems": problems, "started_at": meta["started_at"],
                "ends_at": meta["ends_at"], "current": plugin.get("current", meta.get("current", 1)),
                "ended": bool(meta.get("ended"))}

    def list(self):
        attempts = self.attempt_lines()
        out = []
        for path in sorted((self.practice / "exams").glob("*.md")):
            if path.name.endswith((".answers.md", ".setup.md")):
                continue
            try:
                count, error = len(parse_problems(path.read_text())["problems"]), ""
            except ValueError:
                count, error = None, "format error"
            out.append({"name": path.name, "count": count, "error": error,
                        "solution": path.with_name(path.name[:-3] + ".answers.md").exists(),
                        "attempts": sum(1 for a in attempts if Path(a.get("exam", "")).name == path.name)})
        return out

    def attempt_lines(self):
        try:
            text = (self.cka / "exam-attempts.jsonl").read_text()
        except OSError:
            return []
        out = []
        for line in text.splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out

    def completion(self, host):
        """Tab 자동완성용: 현재 문제의 가상 파일 경로, 객체 이름, 노드. ls · get 으로 보이는 것만 담고 answer-key 는 읽지 않는다."""
        try:
            pid = (self.cka / "current").read_text().strip()
        except OSError:
            return {"files": [], "objects": [], "nodes": []}
        state = self._json(self.cka / pid / "state.json", {}) if pid and "/" not in pid else {}
        cluster = state.get("clusters", {}).get(state.get("meta", {}).get("context", ""), {})
        return {"files": sorted(state.get("hosts", {}).get(host, {}).get("files", {})),
                "objects": sorted(cluster.get("objects", {})), "nodes": sorted(cluster.get("nodes", {}))}

    def report(self):
        """종료 뒤에만 부른다. 마지막 차시 기록 + 풀이 파일(있으면)."""
        meta = self.meta()
        rel = f"exams/{meta['file']}"
        attempt = next((a for a in reversed(self.attempt_lines()) if a.get("exam") == rel), None)
        if not attempt:
            raise RuntimeError("차시 기록(.cka/exam-attempts.jsonl)을 찾지 못했습니다.")
        answers_path = exam_file(self.practice, meta["file"]).with_name(meta["file"][:-3] + ".answers.md")
        answers = parse_answers(answers_path.read_text()) if answers_path.exists() else []
        reports = sorted(self.cka.glob("exam-report-*.md"))
        parsed = parse_problems(exam_file(self.practice, meta["file"]).read_text())["problems"]
        scores = {p.get("n"): p for p in attempt.get("problems", [])}
        problems = [{**p, "score": scores.get(p["n"], {}).get("score", 0),
                     "answer": next((a for a in answers if a["n"] == p["n"]), None)} for p in parsed]
        return {"path": str(reports[-1].relative_to(self.practice)) if reports else None, "hasAnswers": bool(answers),
                "mock": False, "total": attempt.get("total"), "passed": attempt.get("passed"), "problems": problems}


# ---------- 문서 이용 기록 ----------
# 기준: LF CKA 허용 리소스(번역판 포함), 그 외는 위반. 같은 규칙을 두 번 넘게 어기면 시험 종료(핸드북)

BROWSER_CONTAINER = "cka-firefox"  # README 의 docker run 이름
DOC_LANG = r"(?:/[a-z]{2}(?:-[a-z]{2,4})?)?"  # /ko, /zh-cn 같은 번역판 접두사


def doc_allowed(url):
    """허용 문서면 True, 위반이면 False. http(s) 가 아니면(about:blank 등) None — 판정하지 않는다."""
    u = urlsplit(url)
    if u.scheme not in ("http", "https"):
        return None
    host, path = (u.hostname or "").lower(), u.path or "/"
    if host == "kubernetes.io":
        return bool(re.match(DOC_LANG + r"/(docs|blog|search)(/|$)", path))
    if host == "helm.sh":
        return bool(re.match(DOC_LANG + r"/docs(/|$)", path))
    return host == "gateway-api.sigs.k8s.io"


def doc_visits(since, until, container=BROWSER_CONTAINER):
    """컨테이너 Firefox 의 방문 기록(places.sqlite) 중 시험 시간 안의 것. 차단 · 로드 실패한 주소는 남지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("places.sqlite", "places.sqlite-wal"):
            r = subprocess.run(["docker", "cp", f"{container}:/config/profile/{name}", tmp],
                               capture_output=True, text=True, timeout=30)
            if r.returncode and name == "places.sqlite":
                raise RuntimeError(r.stderr.strip() or "docker cp 실패")
        con = sqlite3.connect(str(Path(tmp) / "places.sqlite"))
        try:
            rows = con.execute("SELECT v.visit_date, v.visit_type, p.url FROM moz_historyvisits v "
                               "JOIN moz_places p ON p.id = v.place_id WHERE v.visit_date BETWEEN ? AND ? "
                               "ORDER BY v.visit_date", (int(since * 1e6), int(until * 1e6))).fetchall()
        finally:
            con.close()
    return [{"at": int(t / 1e6), "url": url, "reload": vtype == 9} for t, vtype, url in rows]


def doc_report(visits):
    """방문마다 허용 여부를 붙이고 위반 횟수(새로고침 제외)로 판정한다."""
    judged = [{**v, "allowed": doc_allowed(v["url"])} for v in visits]
    judged = [v for v in judged if v["allowed"] is not None]
    violations = sum(1 for v in judged if not v["allowed"] and not v["reload"])
    verdict = "문제 없음" if not violations else "경고" if violations <= 2 else "실제 시험이면 종료(탈락)"
    return {"visits": judged, "violations": violations, "verdict": verdict}


def doc_markdown(docs):
    """리포트 md 끝에 붙일 절."""
    lines = ["", "## 문서 이용 기록", ""]
    if docs.get("error"):
        return "\n".join(lines + [docs["error"], ""])
    lines += [f"판정: **{docs['verdict']}** (허용 밖 방문 {docs['violations']}회, 새로고침 제외). "
              "기준: LF CKA 허용 리소스(kubernetes.io/docs · blog · search, helm.sh/docs, gateway-api.sigs.k8s.io, 번역판 포함), "
              "1~2회 경고, 3회 이상 시험 종료.", ""]
    if docs["visits"]:
        lines += ["| 시각 | 주소 | 판정 |", "|---|---|---|"]
        lines += [f"| {time.strftime('%H:%M:%S', time.localtime(v['at']))} | {v['url'].replace('|', '%7C')} | "
                  f"{'허용' if v['allowed'] else '위반'}{' (새로고침)' if v['reload'] else ''} |" for v in docs["visits"]]
    else:
        lines.append("연 문서가 없습니다.")
    return "\n".join(lines + [""])


# ---------- 행동 회고 ----------
# 점수와 별개로 어떻게 풀었는지 돌아본다. 기준과 응답 형식은 retro-prompt.md

RETRO_AXES = ("스스로 풀기", "문서 찾기", "디테일", "검증")
HISTORY_TIME = re.compile(r"^### #\d+\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", re.M)


def history_span(history):
    """history.md 의 (명령 수, 처음~마지막 명령 사이 분). 기록 시각이 분 단위라 +1 로 센다."""
    times = [time.mktime(time.strptime(t, "%Y-%m-%d %H:%M")) for t in HISTORY_TIME.findall(history)]
    return len(times), (int((max(times) - min(times)) // 60) + 1 if times else 0)


def build_retro_input(cka, meta, attempt):
    """회고에 넘길 자료: 손댄 문항의 문제 · 요구사항 · 명령 기록, 시험 중 문서 방문. 정답 · 루브릭은 넣지 않는다."""
    scores = {p.get("n"): p for p in (attempt or {}).get("problems", [])}
    parts, stats = [], {}
    for n, pid in sorted(((int(k), v) for k, v in (meta.get("problem_ids") or {}).items())):
        folder = next((d for d in (cka / "archive" / pid, cka / pid) if (d / "history.md").exists()), None)
        if not folder or "/" in pid:
            continue
        history = (folder / "history.md").read_text()[-30000:]
        count, minutes = history_span(history)
        stats[n] = {"minutes": minutes, "commands": count}
        problem = (folder / "problem.md").read_text() if (folder / "problem.md").exists() else ""
        score = scores.get(n, {})
        parts.append(f"## Q{n} ({pid}) · 명령 {count}개 · 처음~마지막 명령 {minutes}분 · 점수 {score.get('score', '?')}/{score.get('weight', '?')}\n\n"
                     f"### 문제\n{problem}\n\n### 명령 기록\n{history}")
    docs = meta.get("docs") or {}
    if docs.get("visits") is not None:
        lines = [f"- {time.strftime('%H:%M:%S', time.localtime(v['at']))} {'허용' if v['allowed'] else '위반'} {v['url']}"
                 for v in docs["visits"]]
        doc_text = "\n".join(lines) or "(연 문서 없음)"
    else:
        doc_text = docs.get("error") or "(문서 브라우저 기록 없음: Firefox 컨테이너 없이 실행)"
    started = time.strftime("%Y-%m-%d %H:%M", time.localtime(meta["started_at"]))
    ended = time.strftime("%H:%M", time.localtime(meta.get("ended_at") or time.time()))
    return (f"# 시험 {meta.get('file')} · {started} ~ {ended}\n\n" + "\n\n".join(parts)
            + f"\n\n## 시험 중 문서 방문 (시각순)\n{doc_text}\n"), stats


def parse_retro(text, stats):
    """Claude 응답에서 JSON 을 꺼내 형식을 확인하고 문항별 시간 · 명령 수(코드로 센 값)를 붙인다."""
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if start >= 0 else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("problems"), list) or not isinstance(data.get("habits"), list):
        raise RuntimeError("회고 응답 형식이 올바르지 않습니다. 다시 시도하세요.")
    for p in data["problems"]:
        if not isinstance(p, dict) or not isinstance(p.get("axes"), list):
            raise RuntimeError("회고 응답 형식이 올바르지 않습니다. 다시 시도하세요.")
        p.update(stats.get(p.get("n"), {}))
    return data


def retro_markdown(retro):
    """리포트 md 끝에 붙일 절."""
    lines = ["", "## 행동 회고", "", "점수와 별개로 어떻게 풀었는지 돌아본 것. 근거의 #번호는 명령 기록 번호다.", ""]
    for p in retro["problems"]:
        lines += [f"### Q{p.get('n')} {p.get('title', '')} (명령 {p.get('commands', '?')}개, {p.get('minutes', '?')}분)", "",
                  "| 기준 | 평가 | 근거 |", "|---|---|---|"]
        lines += [f"| {a.get('axis', '')} | {a.get('grade', '')} | {str(a.get('evidence', '')).replace('|', '/')} |" for a in p["axes"]]
        lines.append("")
    if not retro["problems"]:
        lines += ["손댄 문항이 없습니다.", ""]
    lines += ["### 다음 시험에서", ""] + [f"{i}. {h}" for i, h in enumerate(retro["habits"], 1)]
    return "\n".join(lines + [""])


# ---------- HTTP ----------

def current_problem(cka):
    """진행 중인 문제의 (id, state.json 경로, state). 없으면 ValueError."""
    pid = (cka / "current").read_text().strip() if (cka / "current").exists() else ""
    if not pid or "/" in pid or not (cka / pid / "state.json").exists():
        raise ValueError("진행 중인 문제가 없습니다.")
    path = cka / pid / "state.json"
    return pid, path, json.loads(path.read_text())


def make_handler(practice, claude, exams, port, browser_url=None):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(STATIC), **kw)

        def log_message(self, fmt, *args):
            if not self.path.startswith("/api/"):
                return
            super().log_message(fmt, *args)

        def _json(self, code, body):
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _guard(self):
            # 다른 사이트가 브라우저를 통해 로컬 서버를 부르지 못하게: Host 확인 + 사용자 정의 헤더(사전 요청 강제)
            if self.headers.get("Host") not in hosts or (self.command == "POST" and self.headers.get("X-Sim") != "1"):
                self._json(403, {"error": "forbidden"})
                return False
            return True

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}") if length <= 2 * 1024 * 1024 else {}

        def do_GET(self):
            if self.path == "/config.js":
                shown = str(practice).replace(str(Path.home()), "~", 1)
                data = f"window.SIM_SERVER = true;\nwindow.SIM_PRACTICE = {json.dumps(shown)};\n"
                if browser_url:  # 화면 안 Firefox 창에 띄울 진짜 Firefox(컨테이너 웹 VNC) 주소
                    data += f"window.SIM_BROWSER = {json.dumps(browser_url)};\n"
                data = data.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if not self.path.startswith("/api/"):
                return super().do_GET()
            if not self._guard():
                return
            if self.path == "/api/exam":
                return self._json(200, exams.summary())
            if self.path == "/api/exams":
                return self._json(200, exams.list())
            if self.path == "/api/attempts":
                return self._json(200, {"lines": exams.attempt_lines()})
            if self.path.startswith("/api/exam-file"):
                # 문제 파일 원문만 (exam_file 이 경로 이탈 · 풀이 · 환경 파일을 거부한다)
                try:
                    path = exam_file(practice, parse_qs(urlsplit(self.path).query).get("name", [""])[0])
                    return self._json(200, {"name": path.name, "text": path.read_text()})
                except (ValueError, OSError):
                    return self._json(404, {"error": "문제 파일을 찾지 못했습니다."})
            if self.path.startswith("/api/file"):
                # 편집기 열기: 현재 문제 state 의 가상 파일만 (answer-key 는 읽지 않는다)
                q = parse_qs(urlsplit(self.path).query)
                host = q.get("host", [""])[0]
                try:
                    if not re.fullmatch(r"[\w.-]+", host):
                        raise ValueError("host 가 잘못됐습니다.")
                    _, _, state = current_problem(practice / ".cka")
                    path = file_path(state, q.get("path", [""])[0])
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
                files = state.get("hosts", {}).get(host, {}).get("files", {})
                vimrc = files.get(home_of(state) + "/.vimrc")
                return self._json(200, {"path": path, "exists": path in files, "text": files.get(path) or "",
                                        "vimrc": vimrc if isinstance(vimrc, str) else ""})
            if self.path.startswith("/api/complete"):
                host = parse_qs(urlsplit(self.path).query).get("host", [""])[0]
                return self._json(200, exams.completion(host))
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._guard():
                return
            routes = {"/api/exam/start": self.start, "/api/exam/goto": self.goto, "/api/submit": self.submit,
                      "/api/exam/end": self.end, "/api/cmd": self.cmd, "/api/file": self.save,
                      "/api/attempts/reset": self.reset_attempts, "/api/exam/abort": self.abort, "/api/exam/retro": self.retro}
            route = routes.get(self.path)
            if not route:
                return self._json(404, {"error": "not found"})
            if not claude.lock.acquire(blocking=False):
                return self._json(409, {"error": "다른 요청을 처리 중입니다."})
            try:
                route(self._body())
            except (ValueError, RuntimeError) as e:
                self._json(400, {"error": str(e)})
            finally:
                claude.lock.release()

        def _running(self):
            meta = exams.meta()
            if not meta or meta.get("ended") or not exams.plugin_exam():
                raise ValueError("진행 중인 시험이 없습니다.")
            return meta

        def start(self, body):
            minutes = body.get("minutes")
            if not isinstance(minutes, int) or not 1 <= minutes <= 360:
                raise ValueError("시험 시간은 1~360분 정수로 입력하세요.")
            if exams.plugin_exam() or (practice / ".cka" / "current").exists():
                raise ValueError("연습 폴더에 진행 중인 문제나 시험이 있습니다. 먼저 끝내거나 정리하세요.")
            file = body.get("file") or {}
            path = exam_file(practice, file.get("name"))
            text = file.get("text") or ""
            parse_problems(text)
            if path.exists() and _norm(path.read_text()) != _norm(text):
                raise ValueError(f"exams/{path.name} 이 이미 있고 내용이 다릅니다. 이름을 바꿔 올리세요.")
            path.parent.mkdir(exist_ok=True)
            if not path.exists():
                path.write_text(text)
            answers = body.get("answers")
            answers_path = path.with_name(path.name[:-3] + ".answers.md")
            if answers and answers.get("text") and not answers_path.exists():
                answers_path.write_text(answers["text"])
            (practice / ".cka").mkdir(exist_ok=True)
            claude.forget()  # 시험마다 새 세션
            claude.run("start", f"{PLUGIN}cka-exam start exams/{path.name}")
            plugin = exams.plugin_exam()
            if not plugin:
                raise RuntimeError("시험을 시작하지 못했습니다(.cka/exam.json 없음).")
            started = int(plugin.get("started_at") or time.time())
            plugin["ends_at"] = started + minutes * 60  # UI 에서 고른 시간으로 맞춘다
            (practice / ".cka" / "exam.json").write_text(json.dumps(plugin, ensure_ascii=False, indent=1))
            exams.meta_file.write_text(json.dumps({"file": path.name, "minutes": minutes, "started_at": started,
                                                   "ends_at": started + minutes * 60, "ended": False}))
            self._json(200, exams.summary())

        def goto(self, body):
            self._running()
            n = body.get("n")
            if not isinstance(n, int) or not 1 <= n <= len(exams.summary()["problems"]):
                raise ValueError("문항 번호가 범위를 벗어났습니다.")
            claude.run("goto", f"{PLUGIN}cka-exam goto {n}")
            self._json(200, exams.summary())

        def abort(self, body):
            """진행 중인 시험을 채점 없이 버린다. 문제 폴더 · exam.json · 세션은 .cka/backup/aborted-<시각>/ 으로 옮긴다."""
            cka = practice / ".cka"
            plugin = exams.plugin_exam() or {}
            names = {p.get("id") for p in plugin.get("problems", []) if p.get("id")}
            try:
                names.add((cka / "current").read_text().strip())
            except OSError:
                pass
            names = {n for n in names if n and "/" not in n and n not in (".", "..")}
            moving = [cka / n for n in sorted(names)] + [cka / f for f in
                      ("exam.json", "current", "server-exam.json", "server-session.json")]
            moving = [m for m in moving if m.exists()]
            if not moving:
                raise ValueError("진행 중인 시험이 없습니다.")
            backup = cka / "backup" / f"aborted-{time.strftime('%Y%m%d-%H%M%S')}"
            backup.mkdir(parents=True)
            for m in moving:
                m.rename(backup / m.name)
            self._json(200, {"moved": [m.name for m in moving], "backup": str(backup.relative_to(practice))})

        def reset_attempts(self, body):
            """한 시험의 차시 기록을 지워 다음 시작을 1차시로. 지운 줄은 .cka/backup/ 에 옮겨 되돌릴 수 있게 둔다."""
            name = exam_file(practice, body.get("exam")).name
            path = practice / ".cka" / "exam-attempts.jsonl"
            try:
                lines = path.read_text().splitlines()
            except OSError:
                lines = []
            def mine(line):
                try:
                    return Path(json.loads(line).get("exam", "")).name == name
                except ValueError:
                    return False
            removed = [line for line in lines if mine(line)]
            if removed:
                backup = practice / ".cka" / "backup" / f"exam-attempts-{name[:-3]}-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
                backup.parent.mkdir(exist_ok=True)
                backup.write_text("\n".join(removed) + "\n")
                kept = [line for line in lines if not mine(line)]
                path.write_text("\n".join(kept) + ("\n" if kept else ""))
            self._json(200, {"removed": len(removed)})

        def submit(self, body):
            self._running()
            claude.run("submit", f"{PLUGIN}cka-submit")
            self._json(200, {"message": "제출 기록됨", "exam": exams.summary()})

        def end(self, body):
            meta = self._running()
            # 종료하면 exam.json 이 지워지므로 회고에 쓸 문항 id 를 먼저 남긴다
            meta["problem_ids"] = {str(p["n"]): p["id"] for p in exams.plugin_exam().get("problems", []) if p.get("id")}
            claude.run("end", f"{PLUGIN}cka-exam end")
            meta["ended"], meta["ended_at"] = True, int(time.time())
            exams.meta_file.write_text(json.dumps(meta))
            report = exams.report()
            if browser_url:  # 진짜 Firefox(컨테이너)를 쓸 때만 방문 기록이 있다
                try:
                    report["docs"] = doc_report(doc_visits(meta["started_at"], time.time()))
                except (OSError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as e:
                    report["docs"] = {"error": f"문서 이용 기록을 읽지 못했습니다: {e}"}
                if report["path"]:
                    with open(practice / report["path"], "a") as md:
                        md.write(doc_markdown(report["docs"]))
                meta["docs"] = report["docs"]
                exams.meta_file.write_text(json.dumps(meta))
            self._json(200, report)

        def retro(self, body):
            """종료한 시험의 행동 회고. 한 번 만들면 server-exam.json 에 두고 다시 부르면 그대로 돌려준다."""
            meta = exams.meta()
            if not meta or not meta.get("ended"):
                raise ValueError("종료한 시험이 없습니다.")
            if meta.get("retro"):
                return self._json(200, meta["retro"])
            rel = f"exams/{meta['file']}"
            attempt = next((a for a in reversed(exams.attempt_lines()) if a.get("exam") == rel), None)
            prompt, stats = build_retro_input(practice / ".cka", meta, attempt)
            if not stats:
                retro = {"problems": [], "habits": []}
            else:
                text, cost, seconds = claude.ask(prompt, lambda _: None, system=RETRO_PROMPT, kind="retro")
                retro = parse_retro(text, stats)
                with open(practice / ".cka" / "server-log.jsonl", "a") as log:
                    log.write(json.dumps({"at": int(time.time()), "kind": "retro", "seconds": seconds,
                                          "cost_usd": cost, "warning": ""}, ensure_ascii=False) + "\n")
            reports = sorted((practice / ".cka").glob("exam-report-*.md"))
            if reports:
                with open(reports[-1], "a") as md:
                    md.write(retro_markdown(retro))
            meta["retro"] = retro
            exams.meta_file.write_text(json.dumps(meta))
            self._json(200, retro)

        def save(self, body):
            """편집기 저장(:w, Ctrl+O). Claude 없이 state.json 에 바로 쓰고 history 에 남긴다."""
            meta = self._running()
            if time.time() >= (meta.get("ends_at") or float("inf")):
                raise ValueError("시험 시간이 끝났습니다. 시험을 종료하세요.")
            host, text, editor = body.get("host"), body.get("text"), body.get("editor") or "vim"
            if not isinstance(host, str) or not re.fullmatch(r"[\w.-]+", host) or not isinstance(text, str) \
                    or len(text) > 512 * 1024 or editor not in ("vim", "vi", "nano"):
                raise ValueError("host, 내용, 편집기 종류가 필요합니다.")
            cka = practice / ".cka"
            pid, state_path, state = current_problem(cka)
            path = file_path(state, body.get("path"))
            state, line = save_file(state, host, path, text)
            state.setdefault("meta", {})["cmd_count"] = int(state["meta"].get("cmd_count") or 0) + 1
            tmp = state_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
            os.replace(tmp, state_path)
            with open(cka / pid / "history.md", "a") as hist:
                hist.write(history_entry(state["meta"]["cmd_count"], f"{editor} {path}", "", [line]))
            with open(cka / "server-log.jsonl", "a") as log:
                log.write(json.dumps({"at": int(time.time()), "kind": "file", "seconds": 0, "cost_usd": 0,
                                      "warning": ""}, ensure_ascii=False) + "\n")
            self._json(200, {"path": path, "bytes": len(text.encode())})

        def cmd(self, body):
            """명령 하나: Claude 한 번(도구 없음)으로 <output> 을 흘리고, 끝나면 <changes> 를 코드로 state.json 에 적용한다.
            local_output 이 오면(브라우저 command-check 가 잡은 오타) Claude 없이 기록만 한다."""
            meta = self._running()
            if time.time() >= (meta.get("ends_at") or float("inf")):
                raise ValueError("시험 시간이 끝났습니다. 시험을 종료하세요.")
            text, terminal, host, local = body.get("text"), body.get("terminal"), body.get("host"), body.get("local_output")
            if not isinstance(text, str) or not text.strip() or terminal not in (1, 2) \
                    or not isinstance(host, str) or not re.fullmatch(r"[\w.-]+", host):
                raise ValueError("명령, 터미널 번호, host 가 필요합니다.")
            if local is not None and (not isinstance(local, str) or len(local) > 4000):
                raise ValueError("local_output 형식이 잘못됐습니다.")
            cka = practice / ".cka"
            pid = (cka / "current").read_text().strip() if (cka / "current").exists() else ""
            if not pid or "/" in pid or not (cka / pid / "state.json").exists():
                raise ValueError("진행 중인 문제가 없습니다.")
            state_path = cka / pid / "state.json"
            state = json.loads(state_path.read_text())
            state.setdefault("meta", {})["host"] = host  # 터미널마다 host 가 다를 수 있다
            ctx = state["meta"].get("context", "k8s-c1")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def send(data, event=None):  # 브라우저가 끊어도 상태 적용과 기록은 끝까지 한다
                try:
                    payload = json.dumps(data, ensure_ascii=False)
                    self.wfile.write((f"event: {event}\n" if event else "").encode() + f"data: {payload}\n\n".encode())
                    self.wfile.flush()
                except OSError:
                    pass
            # 화면용 머리줄과 명령 반복은 terminal-ui 가 숨긴다. host 추적은 마지막 머리줄을 쓴다.
            send(f"````console\n# [SIM] host={host} ctx={ctx}\n$ {text}\n")
            lines, warn, cost, seconds = [], "", 0, 0
            if local is not None:
                output = local
                send(output)
            else:
                stream = OutputStream()

                def on_text(chunk):
                    piece = stream.feed(chunk)
                    if piece:
                        send(piece)
                try:
                    reply, cost, seconds = claude.ask(build_cmd_input(cka, pid, state, terminal, host, text), on_text)
                except RuntimeError as e:
                    send({"message": str(e)}, "error")
                    return
                output, changes, warn = parse_reply(reply)
                if not stream.started and output:
                    send(output)  # 태그 없이 답한 경우
                if changes is not None:
                    try:
                        state, lines = apply_changes(state, changes)
                    except ValueError as e:
                        warn = str(e)
            state["meta"]["cmd_count"] = int(state["meta"].get("cmd_count") or 0) + 1
            tmp = state_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
            os.replace(tmp, state_path)
            if warn:
                lines = [f"변경: 적용 안 함 ({warn})"]
            with open(cka / pid / "history.md", "a") as hist:
                hist.write(history_entry(state["meta"]["cmd_count"], text, output, lines))
            with open(cka / "server-log.jsonl", "a") as log:
                log.write(json.dumps({"at": int(time.time()), "kind": "cmd-local" if local is not None else "cmd",
                                      "seconds": seconds, "cost_usd": cost, "warning": warn}, ensure_ascii=False) + "\n")
            m = state["meta"]
            send(f"\n````\n````console\n# [SIM] host={m.get('host', host)} ctx={m.get('context', ctx)}\n````\n")
            send({}, "done")

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--practice", default=str(Path.home() / "cka-practice"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--browser-url", help="화면 안 Firefox 창에 띄울 진짜 Firefox 웹 화면 (예: http://127.0.0.1:5800/)")
    a = ap.parse_args()
    practice = Path(a.practice).expanduser().resolve()
    (practice / ".cka").mkdir(parents=True, exist_ok=True)  # .cka 가 있어야 guard 훅이 켜진다
    claude, exams = Claude(practice, a.model), Exams(practice)
    server = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(practice, claude, exams, a.port, a.browser_url))
    print(f"http://127.0.0.1:{a.port}/  (연습 폴더 {practice}, 모델 {a.model})", file=sys.stderr)
    server.serve_forever()


def _selftest():
    session, result = parse_stream([
        '{"type":"system","subtype":"init","session_id":"s1"}',
        '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}},"session_id":"s1"}',
        "not json", "[1]",
        '{"type":"result","subtype":"success","is_error":false,"result":"```console\\nok\\n```","session_id":"s1","total_cost_usd":0.1}',
    ])
    assert session == "s1" and result["result"].endswith("```"), (session, result)
    assert parse_stream([]) == (None, None)

    for url, want in [("https://kubernetes.io/docs/concepts/", True), ("https://kubernetes.io/ko/docs/x", True),
                      ("https://kubernetes.io/zh-cn/docs/", True), ("https://kubernetes.io/blog/2024/", True),
                      ("https://kubernetes.io/search/?q=pvc", True), ("https://helm.sh/docs/intro/", True),
                      ("https://gateway-api.sigs.k8s.io/guides/", True), ("https://kubernetes.io/community/", False),
                      ("https://kubernetes.io/", False), ("https://kubernetes.io/docsx", False), ("https://helm.sh/", False),
                      ("https://github.com/kubernetes/website", False), ("https://www.google.com/search?q=k", False),
                      ("about:blank", None), ("about:newtab", None)]:
        assert doc_allowed(url) is want, (url, want)
    visit = lambda url, reload=False: {"at": 1, "url": url, "reload": reload}
    ok, bad = "https://kubernetes.io/docs/", "https://github.com/x"
    assert doc_report([visit(ok), visit("about:blank")]) == {"visits": [{**visit(ok), "allowed": True}], "violations": 0, "verdict": "문제 없음"}
    assert doc_report([visit(bad), visit(bad, True), visit(ok)])["verdict"] == "경고"
    assert doc_report([visit(bad)] * 3)["verdict"] == "실제 시험이면 종료(탈락)"
    assert "| 위반 |" in doc_markdown(doc_report([visit(bad)])) and "읽지 못" in doc_markdown({"error": "읽지 못했습니다"})

    hist = "# history q\n### #1  2026-11-17 21:21\n$ k get po\n### #2  2026-11-17 21:49\n$ k get deploy\n"
    assert history_span(hist) == (2, 29) and history_span("# history q\n") == (0, 0)
    axes = [{"axis": a, "grade": "보통", "evidence": "#1 | x"} for a in RETRO_AXES]
    retro = parse_retro('설명 {"problems": [{"n": 1, "title": "t", "axes": %s}], "habits": ["a", "b"]} 끝' % json.dumps(axes), {1: {"minutes": 29, "commands": 2}})
    assert retro["problems"][0]["minutes"] == 29 and retro["problems"][0]["commands"] == 2
    md = retro_markdown(retro)
    assert "## 행동 회고" in md and "(명령 2개, 29분)" in md and "#1 / x" in md and "2. b" in md
    for broken in ("없음", '{"problems": 1, "habits": []}', '{"problems": [{"n": 1}], "habits": []}'):
        try:
            parse_retro(broken, {})
            raise AssertionError(broken)
        except RuntimeError:
            pass

    with tempfile.TemporaryDirectory() as tmp:
        practice = Path(tmp)
        (practice / "exams").mkdir()
        (practice / ".cka").mkdir()
        assert exam_file(practice, "cka.md") == (practice / "exams" / "cka.md").resolve()
        for bad in ["../x.md", "a/b.md", ".x.md", "x.answers.md", "x.setup.md", "x.txt", "", None, "..md/../y.md"]:
            try:
                exam_file(practice, bad)
                raise AssertionError(f"should reject {bad!r}")
            except ValueError:
                pass

        problems = "# T\n\n## Q1\ndomain: Storage\nweight: 60\n\nmake a pvc\n\n## Q2\ndomain: Workloads\nweight: 40\n\nrun a pod\n"
        answers = ("# T 풀이\n\n## Q1\n\n```bash\nSECRET-ANSWER-1\n```\n\n(원본: [Q1](https://example.com/q1))\n\n"
                   "## Q2\n\n```bash\nSECRET-ANSWER-2\n```\n\n(원본: [Q2](https://example.com/q2))\n")
        (practice / "exams" / "t.md").write_text(problems)
        (practice / "exams" / "t.answers.md").write_text(answers)
        (practice / "exams" / "t.setup.md").write_text("# setup\n\n## Q1\nSECRET-SETUP\n")
        (practice / ".cka" / "exam.json").write_text(json.dumps(
            {"exam": "exams/t.md", "current": 1, "problems": [{"n": 1, "id": "q01-pvc"}, {"n": 2, "id": None}]}))
        (practice / ".cka" / "q01-pvc").mkdir()
        (practice / ".cka" / "q01-pvc" / "state.json").write_text(json.dumps({"meta": {"host": "node01", "context": "k8s-c2"}}))
        (practice / ".cka" / "q01-pvc" / "answer-key.md").write_text("SECRET-KEY")
        exams = Exams(practice)
        exams.meta_file.write_text(json.dumps({"file": "t.md", "minutes": 30, "started_at": 1, "ends_at": 1801}))
        s = exams.summary()
        dumped = json.dumps([s, exams.list()])
        assert "SECRET" not in dumped, "answers, setup or answer-key leaked before end"
        assert s["problems"][0]["host"] == "node01" and s["problems"][0]["visited"] and not s["problems"][1]["visited"]
        assert exams.list() == [{"name": "t.md", "count": 2, "error": "", "solution": True, "attempts": 0}]
        (practice / ".cka" / "exam-attempts.jsonl").write_text(json.dumps(
            {"exam": "exams/t.md", "attempt": 1, "total": 60.0, "passed": False, "problems": [{"n": 1, "score": 60.0}]}) + "\n")
        r = exams.report()
        assert r["total"] == 60.0 and r["problems"][0]["answer"]["bash"] == "SECRET-ANSWER-1" and r["problems"][1]["score"] == 0

    try:
        parse_problems("# T\n\n## Q1\ndomain: x\nweight: 50\n\ntext\n")
        raise AssertionError("weights must sum to 100")
    except ValueError:
        pass
    # <output> 스트리밍: 태그가 조각 사이에서 잘려도 안쪽만, 한 번씩
    reply = "생각 <outp" + "ut>\nNAME   STATUS\nweb    Running</ou" + "tput>\n<changes>[]</changes>"
    for size in (1, 2, 3, 7, len(reply)):
        s = OutputStream()
        got = "".join(s.feed(reply[i:i + size]) for i in range(0, len(reply), size))
        assert got == "NAME   STATUS\nweb    Running", (size, got)
    assert OutputStream().feed("no tags at all") == ""
    assert parse_reply(reply) == ("NAME   STATUS\nweb    Running", [], "")
    assert parse_reply("<output>x</output>")[1] is None
    assert parse_reply("<output>x</output><changes>[oops</changes>")[1] is None

    # changes 검증 · 적용: 잘못된 것이 하나라도 있으면 아무것도 안 바뀐다
    st = {"meta": {"host": "cp", "cmd_count": 3}, "clusters": {"c": {"objects": {"d/pod/a": {"spec": {"x": [1, 2]}}}}}}
    new, lines = apply_changes(st, [
        {"op": "set", "path": ["clusters", "c", "objects", "d/namespace/n", "status", "phase"], "value": "Active"},
        {"op": "set", "path": ["clusters", "c", "objects", "d/pod/a", "spec", "x", 1], "value": 9},
        {"op": "set", "path": ["meta", "cmd_count"], "value": 99},
        {"op": "delete", "path": ["clusters", "c", "objects", "d/pod/gone"]},
        {"op": "set", "path": ["meta", "host"], "value": "node01"}])
    assert new["clusters"]["c"]["objects"]["d/namespace/n"] == {"status": {"phase": "Active"}}
    assert new["clusters"]["c"]["objects"]["d/pod/a"]["spec"]["x"] == [1, 9]
    assert new["meta"] == {"host": "node01", "cmd_count": 3}, new["meta"]
    assert st["meta"]["host"] == "cp" and len(lines) == 4, lines
    for bad in ([{"op": "set", "path": ["answer"], "value": 1}], [{"op": "rm", "path": ["meta"]}],
                [{"op": "set", "path": ["meta", "host"]}], [{"op": "set", "path": ["clusters", "c", "objects", "d/pod/a", "spec", "x", "k"], "value": 1}],
                {"op": "set"}):
        try:
            apply_changes(st, bad)
            raise AssertionError(f"should reject {bad}")
        except ValueError:
            pass

    # 입력에 answer-key · 풀이 · 환경 파일 내용이 들어가지 않는다
    with tempfile.TemporaryDirectory() as tmp:
        cka = Path(tmp) / ".cka"
        (cka / "q01").mkdir(parents=True)
        (cka / "q01" / "problem.md").write_text("Create ns")
        (cka / "q01" / "history.md").write_text("# history q01\n### #1  x\n$ ls\n> a\n변경: 없음\n")
        (cka / "q01" / "answer-key.md").write_text("SECRET-ANSWER")
        (Path(tmp) / "exams").mkdir()
        (Path(tmp) / "exams" / "x.answers.md").write_text("SECRET-SOLUTION")
        prompt = build_cmd_input(cka, "q01", {"meta": {}}, 1, "cp", "kubectl create deployment web --image=nginx")
        assert "SECRET" not in prompt and "Create ns" in prompt and "$ ls" in prompt
        assert "kubectl_create_deployment.md" in prompt and "# terminal=1 host=cp" in prompt
        files = {"hosts": {"cp": {"files": {"/root/a.yaml": "kind: Pod\n이름\n", "/opt/x.db": "<binary: snapshot>"}}}}
        sized = build_cmd_input(cka, "q01", files, 1, "cp", "ll")
        assert "cp /root/a.yaml: 17" in sized and "/opt/x.db" not in sized.split("## 파일 크기")[1].split("##")[0]
    assert set(kubectl_refs("cat <<EOF | kubectl apply -f -")) == {"kubectl_apply.md"}
    assert set(kubectl_refs("kubectl -n dev get pods")) == {"kubectl_get.md"}
    assert set(kubectl_refs("kubectl gte po")) == {"kubectl.md"}
    assert "### #2" in history_entry(2, "ls", "a\nb\nc\nd", []) and "> d" not in history_entry(2, "ls", "a\nb\nc\nd", [])
    # 편집기 경로: ~ · 상대 경로(cwd) · normpath, 이상한 경로 거부
    st = {"meta": {"user": "root", "cwd": "/root/app"}}
    assert file_path(st, "~/a.yaml") == "/root/a.yaml" and file_path(st, "b.yaml") == "/root/app/b.yaml"
    assert file_path(st, "../etc/../x") == "/root/x" and file_path(st, "/etc/kubernetes/manifests/etcd.yaml").endswith("etcd.yaml")
    for bad in ("", "/", "a\x00b", "x" * 600, None):
        try:
            file_path(st, bad)
            raise AssertionError(f"should reject {bad!r}")
        except ValueError:
            pass
    saved, line = save_file({"hosts": {"cp": {"file_attrs": {"/root/a": {"mode": "-rw-------", "size": 9}}}}}, "cp", "/root/a", "hi\n")
    assert saved["hosts"]["cp"]["files"]["/root/a"] == "hi\n" and "3 bytes" in line
    assert saved["hosts"]["cp"]["file_attrs"]["/root/a"]["mode"] == "-rw-------" and "size" not in saved["hosts"]["cp"]["file_attrs"]["/root/a"]
    # 파일 API: 실제 핸들러로 읽기 · 저장 (Claude 호출 없음), answer-key 는 응답에 없다
    import socket
    import urllib.request
    with tempfile.TemporaryDirectory() as tmp:
        practice = Path(tmp)
        cka = practice / ".cka"
        (cka / "q01").mkdir(parents=True)
        (cka / "current").write_text("q01")
        (cka / "q01" / "state.json").write_text(json.dumps({"meta": {"user": "root", "cwd": "/root", "cmd_count": 2},
            "hosts": {"cp": {"files": {"/root/d.yaml": "kind: Pod\n", "/root/.vimrc": "set et sw=2\n"}}}}))
        (cka / "q01" / "history.md").write_text("# history q01\n")
        (cka / "q01" / "answer-key.md").write_text("SECRET-ANSWER")
        (cka / "exam.json").write_text(json.dumps({"problems": []}))
        (cka / "server-exam.json").write_text(json.dumps({"file": "x.md", "ends_at": int(time.time()) + 600}))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(practice, Claude(practice, "sonnet"), Exams(practice), port))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{port}"
        try:
            got = urllib.request.urlopen(f"{base}/api/file?host=cp&path=~/d.yaml").read().decode()
            assert "SECRET" not in got and json.loads(got) == {"path": "/root/d.yaml", "exists": True, "text": "kind: Pod\n", "vimrc": "set et sw=2\n"}
            req = urllib.request.Request(f"{base}/api/file", method="POST", headers={"Content-Type": "application/json", "X-Sim": "1"},
                                         data=json.dumps({"host": "cp", "path": "d.yaml", "text": "kind: Service\n", "editor": "vim"}).encode())
            assert json.loads(urllib.request.urlopen(req).read())["path"] == "/root/d.yaml"
            state = json.loads((cka / "q01" / "state.json").read_text())
            assert state["hosts"]["cp"]["files"]["/root/d.yaml"] == "kind: Service\n" and state["meta"]["cmd_count"] == 3
            hist = (cka / "q01" / "history.md").read_text()
            assert "$ vim /root/d.yaml" in hist and 'files["/root/d.yaml"] 저장 (14 bytes)' in hist
        finally:
            srv.shutdown()
            srv.server_close()
    print("selftest ok")


if __name__ == "__main__":
    _selftest() if sys.argv[1:] == ["--selftest"] else main()
