/* Mock shell for the screen prototype: no cluster state, but every answer has the real tool's format.
 * An empty cluster (default namespaces, two nodes, kube-system pods) is assumed. Nothing is remembered between commands.
 * respond(text, host) -> output string ('' = the real command prints nothing).
 */
window.MockShell = (() => {
  const version = `${(window.KUBECTL_INDEX && window.KUBECTL_INDEX.version) || 'v1.37'}.0`;
  // alias list, plural.group shown in errors, kind shown in "kind/name created", namespaced
  const TYPES = [
    [['po', 'pod', 'pods'], 'pods', 'pod', true],
    [['deploy', 'deployment', 'deployments'], 'deployments.apps', 'deployment.apps', true],
    [['svc', 'service', 'services'], 'services', 'service', true],
    [['ns', 'namespace', 'namespaces'], 'namespaces', 'namespace', false],
    [['no', 'node', 'nodes'], 'nodes', 'node', false],
    [['pvc', 'persistentvolumeclaim', 'persistentvolumeclaims'], 'persistentvolumeclaims', 'persistentvolumeclaim', true],
    [['pv', 'persistentvolume', 'persistentvolumes'], 'persistentvolumes', 'persistentvolume', false],
    [['cm', 'configmap', 'configmaps'], 'configmaps', 'configmap', true],
    [['secret', 'secrets'], 'secrets', 'secret', true],
    [['sa', 'serviceaccount', 'serviceaccounts'], 'serviceaccounts', 'serviceaccount', true],
    [['sc', 'storageclass', 'storageclasses'], 'storageclasses.storage.k8s.io', 'storageclass.storage.k8s.io', false],
    [['ing', 'ingress', 'ingresses'], 'ingresses.networking.k8s.io', 'ingress.networking.k8s.io', true],
    [['ingressclass', 'ingressclasses'], 'ingressclasses.networking.k8s.io', 'ingressclass.networking.k8s.io', false],
    [['netpol', 'networkpolicy', 'networkpolicies'], 'networkpolicies.networking.k8s.io', 'networkpolicy.networking.k8s.io', true],
    [['ds', 'daemonset', 'daemonsets'], 'daemonsets.apps', 'daemonset.apps', true],
    [['sts', 'statefulset', 'statefulsets'], 'statefulsets.apps', 'statefulset.apps', true],
    [['rs', 'replicaset', 'replicasets'], 'replicasets.apps', 'replicaset.apps', true],
    [['job', 'jobs'], 'jobs.batch', 'job.batch', true],
    [['cj', 'cronjob', 'cronjobs'], 'cronjobs.batch', 'cronjob.batch', true],
    [['ep', 'endpoints'], 'endpoints', 'endpoints', true],
    [['ev', 'event', 'events'], 'events', 'event', true],
    [['hpa', 'horizontalpodautoscaler', 'horizontalpodautoscalers'], 'horizontalpodautoscalers.autoscaling', 'horizontalpodautoscaler.autoscaling', true],
    [['role', 'roles'], 'roles.rbac.authorization.k8s.io', 'role.rbac.authorization.k8s.io', true],
    [['rolebinding', 'rolebindings'], 'rolebindings.rbac.authorization.k8s.io', 'rolebinding.rbac.authorization.k8s.io', true],
    [['clusterrole', 'clusterroles'], 'clusterroles.rbac.authorization.k8s.io', 'clusterrole.rbac.authorization.k8s.io', false],
    [['clusterrolebinding', 'clusterrolebindings'], 'clusterrolebindings.rbac.authorization.k8s.io', 'clusterrolebinding.rbac.authorization.k8s.io', false],
    [['pc', 'priorityclass', 'priorityclasses'], 'priorityclasses.scheduling.k8s.io', 'priorityclass.scheduling.k8s.io', false],
    [['crd', 'crds', 'customresourcedefinition', 'customresourcedefinitions'], 'customresourcedefinitions.apiextensions.k8s.io', 'customresourcedefinition.apiextensions.k8s.io', false],
    [['gateway', 'gateways', 'gtw'], 'gateways.gateway.networking.k8s.io', 'gateway.gateway.networking.k8s.io', true],
    [['httproute', 'httproutes'], 'httproutes.gateway.networking.k8s.io', 'httproute.gateway.networking.k8s.io', true],
  ];
  const typeOf = word => {
    const base = word.toLowerCase().split('.')[0];
    const t = TYPES.find(([aliases]) => aliases.includes(base));
    return t && {plural: t[1], kind: t[2], namespaced: t[3]};
  };
  const KIND_TO_ALIAS = {Pod: 'pod', Deployment: 'deployment', Service: 'service', Namespace: 'namespace', PersistentVolumeClaim: 'pvc',
    PersistentVolume: 'pv', ConfigMap: 'cm', Secret: 'secret', ServiceAccount: 'sa', StorageClass: 'sc', Ingress: 'ingress',
    IngressClass: 'ingressclass', NetworkPolicy: 'netpol', DaemonSet: 'ds', StatefulSet: 'sts', Job: 'job', CronJob: 'cj',
    HorizontalPodAutoscaler: 'hpa', Role: 'role', RoleBinding: 'rolebinding', ClusterRole: 'clusterrole',
    ClusterRoleBinding: 'clusterrolebinding', PriorityClass: 'pc', CustomResourceDefinition: 'crd', Gateway: 'gateway', HTTPRoute: 'httproute'};

  const NAMESPACES = [['default', '2d'], ['kube-node-lease', '2d'], ['kube-public', '2d'], ['kube-system', '2d']];
  const NODES = [['controlplane', 'Ready', 'control-plane', '2d'], ['node01', 'Ready', '<none>', '2d']];
  const SYSTEM_PODS = [
    ['coredns-7c65d6cfc9-4xk2p', '1/1', 'Running', '0', '2d'], ['coredns-7c65d6cfc9-9tqzl', '1/1', 'Running', '0', '2d'],
    ['etcd-controlplane', '1/1', 'Running', '0', '2d'], ['kube-apiserver-controlplane', '1/1', 'Running', '0', '2d'],
    ['kube-controller-manager-controlplane', '1/1', 'Running', '0', '2d'], ['kube-proxy-7w5zb', '1/1', 'Running', '0', '2d'],
    ['kube-proxy-q8n4c', '1/1', 'Running', '0', '2d'], ['kube-scheduler-controlplane', '1/1', 'Running', '0', '2d'],
  ];

  // kubectl-style column alignment: each column padded to its widest cell + 3 spaces.
  function table(rows) {
    const widths = rows[0].map((_, i) => Math.max(...rows.map(r => r[i].length)));
    return rows.map(r => r.map((c, i) => (i === r.length - 1 ? c : c.padEnd(widths[i] + 3))).join('')).join('\n');
  }

  function parseArgs(args) {
    const o = {pos: [], ns: null, all: false, out: null, dry: false, image: null, name: null, filename: null};
    for (let i = 0; i < args.length; i++) {
      const a = args[i], next = () => args[++i];
      const [flag, value] = a.includes('=') ? [a.slice(0, a.indexOf('=')), a.slice(a.indexOf('=') + 1)] : [a, null];
      if (flag === '-n' || flag === '--namespace') o.ns = value ?? next();
      else if (flag === '-A' || flag === '--all-namespaces') o.all = true;
      else if (flag === '-o' || flag === '--output') o.out = value ?? next();
      else if (flag === '--dry-run') o.dry = (value ?? 'unchanged') !== 'none';
      else if (flag === '--image') o.image = value ?? next();
      else if (flag === '--name') o.name = value ?? next();
      else if (flag === '-f' || flag === '--filename') o.filename = value ?? next();
      else if (/^-n.+/.test(a) && !a.startsWith('--')) o.ns = a.slice(2);
      else if (/^-o.+/.test(a) && !a.startsWith('--')) o.out = a.slice(2).replace(/^=/, '');
      else if (a.startsWith('-')) { if (value === null && /^(-l|--selector|-c|--container|--port|--target-port|--replicas|--type|-p|--patch|--timeout|--sort-by|--field-selector|--from-literal|--from-file|--verb|--resource|--role|--clusterrole|--serviceaccount|--user|--group|--value|--protocol|--rule|--class|--namespace)$/.test(flag)) i++; }
      else o.pos.push(a);
    }
    return o;
  }

  const emptyList = o => (o.out === 'yaml' ? 'apiVersion: v1\nitems: []\nkind: List\nmetadata:\n  resourceVersion: ""'
    : o.out === 'json' ? '{\n    "apiVersion": "v1",\n    "items": [],\n    "kind": "List",\n    "metadata": {\n        "resourceVersion": ""\n    }\n}' : null);

  // One type -> {head, rows} | null (nothing found) | error string.
  function getRows(t, o, names) {
    const ns = o.ns || 'default';
    if (names.length) {
      const known = t.plural === 'namespaces' ? NAMESPACES.map(n => n[0]) : t.plural === 'nodes' ? NODES.map(n => n[0])
        : t.plural === 'pods' && ns === 'kube-system' ? SYSTEM_PODS.map(p => p[0]) : [];
      const missing = names.find(n => !known.includes(n));
      if (missing) return `Error from server (NotFound): ${t.plural} "${missing}" not found`;
    }
    const pick = rows => (names.length ? rows.filter(r => names.includes(r[0])) : rows);
    if (t.plural === 'namespaces') return {head: ['NAME', 'STATUS', 'AGE'], rows: pick(NAMESPACES).map(([n, a]) => [n, 'Active', a])};
    if (t.plural === 'nodes') return {head: ['NAME', 'STATUS', 'ROLES', 'AGE', 'VERSION'], rows: pick(NODES).map(n => [...n, version])};
    if (t.plural === 'pods' && (o.all || ns === 'kube-system'))
      return {head: ['NAME', 'READY', 'STATUS', 'RESTARTS', 'AGE'], rows: pick(SYSTEM_PODS).map(r => (o.all ? ['kube-system', ...r] : r)), nsCol: o.all};
    if (t.plural === 'services' && (o.all || ns === 'default')) {
      const rows = [['kubernetes', 'ClusterIP', '10.96.0.1', '<none>', '443/TCP', '2d']].map(r => (o.all ? ['default', ...r] : r));
      if (o.all) rows.push(['kube-system', 'kube-dns', 'ClusterIP', '10.96.0.10', '<none>', '53/UDP,53/TCP,9153/TCP', '2d']);
      return {head: ['NAME', 'TYPE', 'CLUSTER-IP', 'EXTERNAL-IP', 'PORT(S)', 'AGE'], rows, nsCol: o.all};
    }
    return null;
  }

  function get(o) {
    const [what, ...names] = o.pos;
    if (!what) return 'You must specify the type of resource to get. Use "kubectl api-resources" for a complete list of supported resources.\n\nerror: Required resource not specified.\nUse "kubectl explain <resource>" for a detailed description of that resource (e.g. kubectl explain pods).\nSee \'kubectl get -h\' for help and examples';
    const [typeList, slashName] = what.split('/');
    if (slashName) names.push(slashName);
    const ALL = ['po', 'svc', 'ds', 'deploy', 'rs', 'sts', 'job', 'cj']; // what "kubectl get all" lists
    const words = typeList.split(',').filter(Boolean).flatMap(w => (w === 'all' ? ALL : [w]));
    const types = words.map(typeOf), bad = words.find((w, i) => !types[i]);
    if (bad) return `error: the server doesn't have a resource type "${bad}"`;
    const multi = types.length > 1 || typeList === 'all', parts = [];
    for (const t of types) {
      const r = getRows(t, o, names);
      if (typeof r === 'string') return r;
      if (!r || !r.rows.length) continue;
      // several types at once: kubectl prefixes names with kind (service/kubernetes)
      const at = r.nsCol ? 1 : 0, rows = multi ? r.rows.map(row => row.map((c, i) => (i === at ? `${t.kind}/${c}` : c))) : r.rows;
      parts.push(table([r.nsCol ? ['NAMESPACE', ...r.head] : r.head, ...rows]));
    }
    if (parts.length) return parts.join('\n\n');
    const anyNamespaced = types.some(t => t.namespaced);
    return emptyList(o) || (anyNamespaced && !o.all ? `No resources found in ${o.ns || 'default'} namespace.` : 'No resources found');
  }

  function describe(o) {
    const [what, name] = o.pos;
    const [typeWord, slashName] = (what || '').split('/');
    const t = typeOf(typeWord || '');
    if (!t) return `error: the server doesn't have a resource type "${typeWord}"`;
    const n = slashName || name;
    if (t.plural === 'namespaces' && NAMESPACES.some(x => x[0] === n))
      return `Name:         ${n}\nLabels:       kubernetes.io/metadata.name=${n}\nAnnotations:  <none>\nStatus:       Active\n\nNo resource quota.\n\nNo LimitRange resource.`;
    if (!n) return t.namespaced ? `No resources found in ${o.ns || 'default'} namespace.` : 'No resources found';
    return `Error from server (NotFound): ${t.plural} "${n}" not found`;
  }

  // "kubectl apply -f - <<EOF" or "cat <<EOF | kubectl apply -f -": read kind/name of each document from the heredoc body.
  function manifests(text) {
    return text.split(/^---$/m).map(doc => {
      const kind = (doc.match(/^kind:\s*(\S+)/m) || [])[1], name = (doc.match(/^metadata:\s*\n(?:\s+.*\n)*?\s+name:\s*(\S+)/m) || [])[1];
      return kind && name ? {kind, name} : null;
    }).filter(Boolean);
  }

  function kubectl(args, text, verb) {
    const rest = args.slice(1), vi = rest.indexOf(verb);
    const o = parseArgs(vi >= 0 ? [...rest.slice(0, vi), ...rest.slice(vi + 1)] : rest), dry = o.dry ? ' (dry run)' : '';
    const kindName = (alias, name) => `${typeOf(alias).kind}/${name}`;
    switch (verb) {
      case 'get': return get(o);
      case 'describe': return describe(o);
      case 'version': return `Client Version: ${version}\nKustomize Version: v5.7.1\nServer Version: ${version}`;
      case 'cluster-info': return 'Kubernetes control plane is running at https://controlplane:6443\nCoreDNS is running at https://controlplane:6443/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy\n\nTo further debug and diagnose cluster problems, use \'kubectl cluster-info dump\'.';
      case 'run': return o.pos[0] ? `pod/${o.pos[0]} created${dry}` : 'error: NAME is required for run';
      case 'create': {
        const sub = o.pos[0], name = sub === 'secret' || sub === 'service' ? o.pos[2] : o.pos[1];
        if (o.filename) return createFromFile(text, 'created', dry, o);
        if (!sub || !typeOf(sub === 'secret' ? 'secret' : sub === 'service' ? 'svc' : sub === 'quota' ? 'cm' : sub)) return '';
        if (!name) return `error: exactly one NAME is required, got 0\nSee 'kubectl create ${sub} -h' for help and examples`;
        return `${kindName(sub === 'service' ? 'svc' : sub, name)} created${dry}`;
      }
      case 'apply': return createFromFile(text, 'created', dry, o);
      case 'delete': {
        if (o.filename) return createFromFile(text, 'deleted', '', o);
        const [what, ...names] = o.pos, [typeWord, slashName] = (what || '').split('/');
        const t = typeOf(typeWord || '');
        if (!t) return `error: the server doesn't have a resource type "${typeWord}"`;
        const n = slashName || names[0];
        return n ? `Error from server (NotFound): ${t.plural} "${n}" not found` : 'error: resource(s) were provided, but no name was specified';
      }
      case 'expose': {
        const [what, maybeName] = o.pos, [, slashName] = (what || '').split('/'), n = slashName || maybeName;
        return `Error from server (NotFound): ${typeOf((what || 'deploy').split('/')[0])?.plural || 'deployments.apps'} "${n}" not found`;
      }
      case 'config':
        if (o.pos[0] === 'get-contexts') return table([['CURRENT', 'NAME', 'CLUSTER', 'AUTHINFO', 'NAMESPACE'], ['*', 'kubernetes-admin@kubernetes', 'kubernetes', 'kubernetes-admin', '']]);
        return '';
      default: return '';
    }
  }

  function createFromFile(text, verb, dry, o) {
    const items = manifests(text);
    if (o.filename && o.filename !== '-' && !items.length) return `error: the path "${o.filename}" does not exist`;
    return items.map(m => `${typeOf(KIND_TO_ALIAS[m.kind] || m.kind)?.kind || m.kind.toLowerCase()}/${m.name} ${verb}${dry}`).join('\n');
  }

  function respond(text, host) {
    const err = window.CommandCheck && window.CommandCheck.check(text);
    if (err) return err;
    const first = text.split('\n')[0];
    const words = (window.CommandCheck ? window.CommandCheck._tokenize(first).filter(t => typeof t === 'string') : first.split(/\s+/))
      .map(w => w.replace(/^~(?=\/|$)/, '/root')); // bash expands ~ for root
    // kubectl may come after a pipe (cat <<EOF | kubectl apply -f -): use the last kubectl/k in the line.
    const at = words.map((w, i) => (w === 'kubectl' || w === 'k' ? i : -1)).filter(i => i >= 0).at(-1);
    if (at !== undefined) {
      const args = words.slice(at);
      // first word that is neither a flag nor the value of a global flag (kubectl -n dev get pvc)
      let verb;
      for (let i = 1; i < args.length; i++) {
        if (/^(-n|--namespace|--context|--kubeconfig|--cluster|--user|-s|--server)$/.test(args[i])) { i++; continue; }
        if (!args[i].startsWith('-')) { verb = args[i]; break; }
      }
      return kubectl(args, text, verb);
    }
    const cmd = words.find(w => !/^[A-Za-z_]\w*=/.test(w) && w !== 'sudo');
    if (cmd === 'cat' || cmd === 'less' || cmd === 'head' || cmd === 'tail') {
      const file = words.slice(1).find(w => !w.startsWith('-') && w !== 'sudo');
      if (file && !/[<>|]/.test(first)) return `${cmd}: ${file}: No such file or directory`;
    }
    if (cmd === 'hostname') return host;
    if (cmd === 'whoami') return 'root';
    if (cmd === 'pwd') return '/root';
    return '';
  }

  return {respond};
})();
