#!/usr/bin/env python3
"""ai-k8s-make-believe state diagram: .cka/<id>/state.json -> mermaid flowchart (for humans, after a problem ends).

Usage: diagram.py <state.json> | --write <problem_dir> | --selftest
<state.json>: print the mermaid flowchart.
--write: write <problem_dir>/diagram.md with the initial (state.init.json) and final (state.json) diagrams.
Edges come only from spec references (selector, nodeName, volumeName, backends, roleRef, subjects), never from guesses.
"""
import json
import sys
from pathlib import Path


def esc(text):
    """Quoted mermaid labels: neutralize characters the parser treats specially."""
    text = str(text).replace("#", "#35;")
    for ch, code in (('"', "#quot;"), ("<", "#lt;"), (">", "#gt;")):
        text = text.replace(ch, code)
    return text


def label(*lines):
    return '["' + "<br/>".join(esc(l) for l in lines if l) + '"]'


def summary(kind, obj):
    """One or two short lines of the status that matters for this kind."""
    spec, status = obj.get("spec") or {}, obj.get("status") or {}
    out = []
    if kind == "service":
        ports = ",".join(f"{p.get('port')}->{p.get('targetPort', p.get('port'))}" for p in spec.get("ports") or [])
        out.append(" ".join(x for x in (spec.get("type", "ClusterIP"), ports) if x))
    elif kind in ("deployment", "statefulset", "replicaset"):
        out.append(f"replicas {status.get('readyReplicas', '?')}/{spec.get('replicas', '?')}")
    if status.get("phase"):
        out.append(status["phase"])
    return out


def split_key(key):
    ns, kind, name = (key.split("/", 2) + ["", ""])[:3]
    return ns, kind, name


def render(state):
    out = ["flowchart LR"]
    ids, edges = {}, []

    def nid(key):
        if key not in ids:
            ids[key] = f"n{len(ids)}"
        return ids[key]

    for ci, (cname, cluster) in enumerate(sorted((state.get("clusters") or {}).items())):
        cid = f"c{ci}"
        out.append(f'  subgraph {cid}{label(f"cluster {cname}", cluster.get("version"))}')
        nodes = cluster.get("nodes") or {}
        objects = cluster.get("objects") or {}
        if nodes:
            out.append(f'    subgraph {cid}_nodes["nodes"]')
            for name, n in sorted(nodes.items()):
                flags = ["Ready" if n.get("ready", True) else "NotReady"]
                if n.get("unschedulable"):
                    flags.append("SchedulingDisabled")
                lines = [f"node {name}", ", ".join(flags)] + [f"taint {t}" for t in n.get("taints") or []]
                out.append(f"      {nid((cname, 'node', name))}{label(*lines)}")
            out.append("    end")
        by_ns = {}
        for key in sorted(objects):
            by_ns.setdefault(split_key(key)[0], []).append(key)
        for si, (ns, keys) in enumerate(sorted(by_ns.items())):
            title = "cluster-scoped" if ns == "_" else f"ns {ns}"
            out.append(f'    subgraph {cid}_s{si}["{esc(title)}"]')
            for key in keys:
                _, kind, name = split_key(key)
                out.append(f"      {nid((cname, key))}{label(f'{kind}/{name}', *summary(kind, objects[key]))}")
            out.append("    end")
        refs = []
        for key in sorted(objects):
            refs += [(key, tgt, txt) for tgt, txt in references(key, objects[key], objects)]
        for src, tgt, txt in refs:
            if isinstance(tgt, tuple):  # node or non-object subject
                tkey = (cname,) + tgt
                if tgt[0] == "node" and tgt[1] not in nodes and tkey not in ids:
                    out.append(f"    {nid(tkey)}{label(f'node {tgt[1]} (missing)')}")
                elif tgt[0] == "subject" and tkey not in ids:
                    out.append(f"    {nid(tkey)}{label(tgt[1])}")
            else:
                tkey = (cname, tgt)
                if tgt not in objects and tkey not in ids:
                    _, kind, name = split_key(tgt)
                    out.append(f"    {nid(tkey)}{label(f'{kind}/{name} (missing)')}")
            edges.append(f"  {nid((cname, src))} -->|{esc(txt)}| {nid(tkey)}")
        out.append("  end")

    for hi, (hname, host) in enumerate(sorted((state.get("hosts") or {}).items())):
        lines = [f"host {hname}"]
        lines += [f"svc {k}: {v}" for k, v in sorted((host.get("services") or {}).items())]
        lines += [f"pkg {k}: {v}" for k, v in sorted((host.get("packages") or {}).items())]
        lines += [f"file {p}" for p in sorted(host.get("files") or {})]
        out.append(f"  h{hi}{label(*lines)}")
    return "\n".join(out + edges) + "\n"


def references(key, obj, objects):
    """(target, edge text) pairs. target is an object key, ("node", name) or ("subject", text)."""
    ns, kind, _ = split_key(key)
    spec = obj.get("spec") or {}
    if kind == "service" and spec.get("selector"):
        sel = spec["selector"]
        for other in sorted(objects):
            ons, okind, _ = split_key(other)
            labels = (objects[other].get("metadata") or {}).get("labels") or {}
            if ons == ns and okind == "pod" and all(labels.get(k) == v for k, v in sel.items()):
                yield other, "selects"
    if kind == "pod" and spec.get("nodeName"):
        yield ("node", spec["nodeName"]), "on"
    if kind == "persistentvolumeclaim" and spec.get("volumeName"):
        yield f"_/persistentvolume/{spec['volumeName']}", "bound"
    if kind == "ingress":
        backends = [spec.get("defaultBackend") or {}]
        for rule in spec.get("rules") or []:
            backends += [p.get("backend") or {} for p in (rule.get("http") or {}).get("paths") or []]
        for name in sorted({(b.get("service") or {}).get("name") for b in backends} - {None}):
            yield f"{ns}/service/{name}", "backend"
    if kind == "httproute":
        for rule in spec.get("rules") or []:
            for ref in rule.get("backendRefs") or []:
                if ref.get("kind", "Service") == "Service" and ref.get("name"):
                    yield f"{ref.get('namespace', ns)}/service/{ref['name']}", "backend"
    if kind in ("rolebinding", "clusterrolebinding"):
        ref = obj.get("roleRef") or {}
        if ref.get("name"):
            rkind = (ref.get("kind") or "Role").lower()
            yield (f"_/{rkind}/{ref['name']}" if rkind == "clusterrole" else f"{ns}/{rkind}/{ref['name']}"), "roleRef"
        for s in obj.get("subjects") or []:
            if s.get("kind") == "ServiceAccount":
                yield f"{s.get('namespace', ns)}/serviceaccount/{s.get('name')}", "subject"
            else:
                yield ("subject", f"{s.get('kind')} {s.get('name')}"), "subject"


def write(problem_dir):
    d = Path(problem_dir)
    parts = [f"# diagram {d.name}\n"]
    for title, fname in (("초기 상태", "state.init.json"), ("최종 상태", "state.json")):
        state = json.loads((d / fname).read_text(encoding="utf-8"))
        parts.append(f"## {title}\n\n```mermaid\n{render(state)}```\n")
    (d / "diagram.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {d / 'diagram.md'}")


def _selftest():
    state = {
        "clusters": {"k8s-c1": {
            "version": "v1.34.1",
            "nodes": {"cp": {"ready": True, "taints": ["node-role.kubernetes.io/control-plane:NoSchedule"]},
                      "node01": {"ready": False, "unschedulable": True}},
            "objects": {
                "prod/pod/web": {"metadata": {"labels": {"app": "web"}}, "spec": {"nodeName": "node01"},
                                 "status": {"phase": "Running"}},
                "prod/pod/db": {"metadata": {"labels": {"app": "db"}}, "spec": {"nodeName": "ghost"}},
                "prod/service/web-svc": {"spec": {"selector": {"app": "web"}, "ports": [{"port": 80, "targetPort": 8080}]}},
                "prod/ingress/web": {"spec": {"rules": [{"http": {"paths": [{"backend": {"service": {"name": "web-svc"}}}]}}]}},
                "prod/persistentvolumeclaim/data": {"spec": {"volumeName": "pv1"}, "status": {"phase": "Bound"}},
                "prod/rolebinding/rb": {"roleRef": {"kind": "ClusterRole", "name": "view"},
                                        "subjects": [{"kind": "User", "name": 'a"<b>'}]},
            },
        }},
        "hosts": {"cp": {"services": {"kubelet": "inactive"}, "files": {"/opt/x.db": "<binary>"}}},
    }
    out = render(state)
    assert out == render(json.loads(json.dumps(state))), "not deterministic"
    ids = {line.split("[", 1)[1]: line.split("[", 1)[0].strip() for line in out.splitlines() if '["' in line}

    def node(text):
        return next(v for k, v in ids.items() if k.startswith(f'"{text}'))

    assert f"{node('pod/web')} -->|selects| " not in out
    assert f"{node('service/web-svc')} -->|selects| {node('pod/web')}" in out
    assert f"{node('service/web-svc')} -->|selects| {node('pod/db')}" not in out
    assert f"{node('pod/web')} -->|on| {node('node node01')}" in out
    assert f"{node('pod/db')} -->|on| {node('node ghost (missing)')}" in out
    assert f"{node('ingress/web')} -->|backend| {node('service/web-svc')}" in out
    assert f"{node('persistentvolumeclaim/data')} -->|bound| {node('persistentvolume/pv1 (missing)')}" in out
    assert f"{node('rolebinding/rb')} -->|roleRef| {node('clusterrole/view (missing)')}" in out
    assert "User a#quot;#lt;b#gt;" in out and 'a"<b>' not in out  # escaped subject name
    assert "NotReady, SchedulingDisabled" in out and "file /opt/x.db" in out and "<binary>" not in out
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
    elif len(sys.argv) == 3 and sys.argv[1] == "--write":
        write(sys.argv[2])
    elif len(sys.argv) == 2:
        print(render(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))), end="")
    else:
        sys.exit(__doc__)
