#!/usr/bin/env python3
"""시뮬레이터 웹 화면의 실서버: simulator/static 을 열고, UIUX.md 의 API 를 백그라운드 Claude Code 세션으로 처리한다.

명령·출제·이동·제출·종료는 연습 폴더를 cwd 로 `claude -p --plugin-dir <repo>` 를 실행해 플러그인 커맨드로 보낸다.
세션은 시험 하나에 하나(--resume)이고, 요청은 한 번에 하나만 처리한다. 127.0.0.1 에만 연다.
풀이(<name>.answers.md)와 환경(<name>.setup.md), answer-key 는 시험이 끝나기 전에 브라우저로 보내지 않는다.

Usage: server.py [--practice ~/cka-practice] [--port 8765] [--model sonnet] | --selftest
표준 라이브러리만 사용한다.
"""
import argparse
import json
import os
import re
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
                 "Bash(mv .cka/:*)", "Bash(rm .cka/current)", "Bash(rm .cka/exam.json)", "Read", "Glob"]
HEADLESS = ("이 세션은 ai-k8s-make-believe 웹 시뮬레이터 서버가 headless 로 실행한다. 사용자에게 질문할 수 없으니 "
            "AskUserQuestion 을 쓰지 않는다. 검토(reviewer)에서 이상이 나오면 '무시'를 고른 것으로 진행하고, "
            "검토 결과는 반환값(모의고사면 리포트)에 남긴다.")
EXAM_NAME = re.compile(r"[\w.-]+\.md")
CMD_PROMPT = REPO / "simulator" / "cmd-prompt.md"
KUBECTL_REFS = REPO / "skills" / "cka-rules" / "references" / "kubectl"
CHANGE_ROOTS = ("clusters", "hosts", "meta")
TIMEOUT = {"cmd": 600, "start": 1200, "goto": 900, "submit": 600, "end": 1800}


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

    def ask(self, prompt, on_text):
        """웹 명령 한 번: 도구 없음, 세션 저장 없음, 기본 시스템 프롬프트 대신 cmd-prompt.md.
        모델 텍스트 조각마다 on_text 를 부르고 (최종 텍스트, 비용, 초) 를 돌려준다."""
        args = ["claude", "-p", "--model", self.model, "--setting-sources", "project,local", "--no-session-persistence",
                "--tools", "", "--system-prompt", CMD_PROMPT.read_text(),
                "--output-format", "stream-json", "--verbose", "--include-partial-messages"]
        started = time.time()
        errors = tempfile.TemporaryFile(mode="w+")
        proc = subprocess.Popen(args, cwd=self.practice, env={**os.environ, "KUBECONFIG": "/dev/null"},
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True)
        timer = threading.Timer(TIMEOUT["cmd"], proc.kill)
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
            raise RuntimeError(f"Claude 실행 실패 (cmd): {detail.strip()}")
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


# ---------- HTTP ----------

def make_handler(practice, claude, exams, port):
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
                data = b"window.SIM_SERVER = true;\n"
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
            if self.path.startswith("/api/complete"):
                host = parse_qs(urlsplit(self.path).query).get("host", [""])[0]
                return self._json(200, exams.completion(host))
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._guard():
                return
            routes = {"/api/exam/start": self.start, "/api/exam/goto": self.goto, "/api/submit": self.submit,
                      "/api/exam/end": self.end, "/api/cmd": self.cmd}
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

        def submit(self, body):
            self._running()
            claude.run("submit", f"{PLUGIN}cka-submit")
            self._json(200, {"message": "제출 기록됨", "exam": exams.summary()})

        def end(self, body):
            meta = self._running()
            claude.run("end", f"{PLUGIN}cka-exam end")
            meta["ended"] = True
            exams.meta_file.write_text(json.dumps(meta))
            self._json(200, exams.report())

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
    a = ap.parse_args()
    practice = Path(a.practice).expanduser().resolve()
    (practice / ".cka").mkdir(parents=True, exist_ok=True)  # .cka 가 있어야 guard 훅이 켜진다
    claude, exams = Claude(practice, a.model), Exams(practice)
    server = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(practice, claude, exams, a.port))
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
    assert set(kubectl_refs("cat <<EOF | kubectl apply -f -")) == {"kubectl_apply.md"}
    assert set(kubectl_refs("kubectl -n dev get pods")) == {"kubectl_get.md"}
    assert set(kubectl_refs("kubectl gte po")) == {"kubectl.md"}
    assert "### #2" in history_entry(2, "ls", "a\nb\nc\nd", []) and "> d" not in history_entry(2, "ls", "a\nb\nc\nd", [])
    print("selftest ok")


if __name__ == "__main__":
    _selftest() if sys.argv[1:] == ["--selftest"] else main()
