/* bash-style Tab completion for the virtual terminal. No Claude call.
 * complete(text, cursor, data) -> {text, cursor, candidates}
 *   data = {files: [abs paths on this host], objects: ["<ns>/<kind>/<name>"], nodes: [names]} (from /api/complete, may be empty)
 * One match: fill it (+ space, or "/" for a directory). Several: fill the common prefix and return the list.
 */
window.Completion = (() => {
  const HOME = '/root';
  const COMMANDS = ['kubectl', 'k', 'etcdctl', 'etcdutl', 'kubeadm', 'systemctl', 'journalctl', 'crictl', 'helm', 'kustomize',
    'ssh', 'exit', 'sudo', 'cd', 'ls', 'cat', 'vim', 'vi', 'nano', 'less', 'head', 'tail', 'grep', 'cp', 'mv', 'rm', 'mkdir',
    'touch', 'echo', 'curl', 'wget', 'nslookup', 'ps', 'df', 'tar', 'base64', 'openssl', 'yq', 'jq', 'watch', 'sysctl', 'dpkg', 'apt', 'apt-get'];
  const TYPES = ['pods', 'deployments', 'services', 'namespaces', 'nodes', 'persistentvolumeclaims', 'persistentvolumes',
    'configmaps', 'secrets', 'serviceaccounts', 'storageclasses', 'ingresses', 'ingressclasses', 'networkpolicies', 'daemonsets',
    'statefulsets', 'replicasets', 'jobs', 'cronjobs', 'endpoints', 'events', 'horizontalpodautoscalers', 'roles', 'rolebindings',
    'clusterroles', 'clusterrolebindings', 'priorityclasses', 'customresourcedefinitions', 'gateways', 'httproutes', 'all'];
  // what the user typed -> kind used in state.json object keys
  const ALIAS = {po: 'pod', deploy: 'deployment', svc: 'service', ns: 'namespace', no: 'node', pvc: 'persistentvolumeclaim',
    pv: 'persistentvolume', cm: 'configmap', sa: 'serviceaccount', sc: 'storageclass', ing: 'ingress', netpol: 'networkpolicy',
    ds: 'daemonset', sts: 'statefulset', rs: 'replicaset', cj: 'cronjob', ep: 'endpoints', ev: 'event', hpa: 'horizontalpodautoscaler',
    pc: 'priorityclass', crd: 'customresourcedefinition', ingresses: 'ingress', endpoints: 'endpoints', networkpolicies: 'networkpolicy',
    priorityclasses: 'priorityclass', storageclasses: 'storageclass', ingressclasses: 'ingressclass'};
  const kindOf = word => { const w = word.toLowerCase().split('.')[0]; return ALIAS[w] || w.replace(/s$/, ''); };
  const NAME_VERBS = new Set(['get', 'describe', 'delete', 'edit', 'label', 'annotate', 'patch', 'logs', 'exec', 'scale',
    'rollout', 'expose', 'cordon', 'uncordon', 'drain', 'taint', 'top', 'port-forward', 'set', 'autoscale']);
  const VALUE_FLAGS = /^(-n|--namespace|-o|--output|-l|--selector|-c|--container|--context|-f|--filename|--image|--port|--replicas|--type|-p|--patch)$/;

  function commonPrefix(list) {
    let p = list[0] || '';
    for (const s of list) while (!s.startsWith(p)) p = p.slice(0, -1);
    return p;
  }

  // Children of a directory from the flat file list: "/root/a.yaml", "/root/x/b" -> "a.yaml", "x/"
  function pathCandidates(word, files, dirsOnly) {
    const expanded = word.replace(/^~(?=\/|$)/, HOME);
    const cut = expanded.lastIndexOf('/');
    const dir = cut >= 0 ? expanded.slice(0, cut + 1) : `${HOME}/`, base = cut >= 0 ? expanded.slice(cut + 1) : expanded;
    const typedDir = cut >= 0 ? word.slice(0, word.lastIndexOf('/') + 1) : '';
    const out = new Set();
    for (const f of files) {
      if (!f.startsWith(dir)) continue;
      const rest = f.slice(dir.length), slash = rest.indexOf('/');
      const entry = slash >= 0 ? rest.slice(0, slash + 1) : rest;
      if (entry.startsWith(base) && (!dirsOnly || entry.endsWith('/'))) out.add(typedDir + entry);
    }
    return [...out].sort();
  }

  function kubectlCandidates(before, word, data) {
    const index = window.KUBECTL_INDEX, cmds = index ? index.commands : {};
    const path = [], positional = []; let ns = null, prev = '';
    for (const a of before.slice(1)) {
      if (VALUE_FLAGS.test(prev)) { if (prev === '-n' || prev === '--namespace') ns = a; prev = ''; continue; }
      prev = a;
      if (a.startsWith('-')) { const m = a.match(/^(?:-n|--namespace)=(.+)$/); if (m) ns = m[1]; continue; }
      const here = cmds[path.join(' ')];
      if (!positional.length && here && here.subs.includes(a)) path.push(a); else positional.push(a);
    }
    if (prev === '-f' || prev === '--filename') return {list: pathCandidates(word, data.files, false), path: true};
    if (prev === '-n' || prev === '--namespace') {
      const names = new Set(['default', 'kube-system', 'kube-public', 'kube-node-lease']);
      data.objects.forEach(k => { const [n, kind, name] = k.split('/'); if (kind === 'namespace') names.add(name); else if (n !== '_') names.add(n); });
      return {list: [...names].sort().filter(n => n.startsWith(word))};
    }
    const here = cmds[path.join(' ')] || {flags: {}, subs: []}, root = cmds[''] || {flags: {}};
    if (word.startsWith('-')) return {list: [...new Set([...Object.keys(here.flags), ...Object.keys(root.flags)])].map(f => `--${f}`).filter(f => f.startsWith(word)).sort()};
    if (!positional.length && here.subs.length) return {list: here.subs.filter(s => s.startsWith(word))};
    if (!NAME_VERBS.has(path[0])) return {list: []};
    if (!positional.length) return {list: TYPES.filter(t => t.startsWith(word))};
    const typeWord = positional[0].split('/')[0], kind = kindOf(typeWord);
    if (kind === 'node') return {list: data.nodes.filter(n => n.startsWith(word))};
    const names = data.objects.map(k => k.split('/')).filter(([n, k]) => k === kind && (n === '_' || n === (ns || 'default'))).map(([, , name]) => name);
    return {list: names.filter(n => n.startsWith(word)).sort()};
  }

  function complete(text, cursor, data = {}) {
    data = {files: data.files || [], objects: data.objects || [], nodes: data.nodes || []};
    const head = text.slice(0, cursor), tail = text.slice(cursor);
    if (head.includes('\n')) return {text, cursor, candidates: []}; // heredoc / YAML: leave Tab alone
    const start = head.search(/\S*$/), word = head.slice(start);
    const before = head.slice(0, start).trim().split(/\s+/).filter(Boolean);
    const cmdAt = before.findIndex(w => !/^[A-Za-z_]\w*=/.test(w) && w !== 'sudo');
    let result;
    if (cmdAt === -1) result = {list: COMMANDS.filter(c => c.startsWith(word))};
    else if (['kubectl', 'k'].includes(before[cmdAt])) result = kubectlCandidates(before.slice(cmdAt), word, data);
    else result = {list: pathCandidates(word, data.files, before[cmdAt] === 'cd'), path: true};
    const list = result.list;
    if (!list.length) return {text, cursor, candidates: []};
    const fill = list.length === 1 ? list[0] + (list[0].endsWith('/') ? '' : ' ') : commonPrefix(list);
    const next = head.slice(0, start) + fill;
    return {text: next + tail, cursor: next.length, candidates: list.length > 1 ? list : []};
  }

  return {complete, _pathCandidates: pathCandidates};
})();
