/* Deterministic pre-check before the mock (later: Claude) answers a command.
 * Returns the real tool's error text for an unknown command, kubectl subcommand or kubectl flag, else null.
 * Only rejects what it is sure about: unknown words after a known subcommand are treated as arguments.
 * kubectl data comes from kubectl-flags.js (generated from the official reference, see scripts/build_kubectl_flags_js.py).
 */
window.CommandCheck = (() => {
  const KNOWN = new Set(`kubectl k etcdctl etcdutl kubeadm kubelet systemctl journalctl crictl ctr helm kustomize ssh scp exit logout
    sudo cd pwd ls cat echo printf vim vi nano less more head tail grep egrep awk sed cut tr sort uniq wc tee xargs find
    cp mv rm mkdir rmdir touch chmod chown ln stat file diff curl wget nslookup dig host ping ip ss netstat ps top kill
    df du free whoami id hostname uname date sleep tar gzip base64 openssl yq jq watch time man apt apt-get dpkg snap
    sysctl modprobe mount umount env export source alias history clear true false test which type bash sh
    demo-error demo-plain demo-mixed`.split(/\s+/));
  const SEPARATORS = new Set(['|', '||', '&&', ';', '&']);

  // Shell-like split of one line: quotes and backslashes respected, operators become their own tokens.
  function tokenize(line) {
    const out = []; let cur = '', quote = null, has = false;
    const push = () => { if (has) out.push(cur); cur = ''; has = false; };
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (quote) { if (ch === quote) quote = null; else if (ch === '\\' && quote === '"' && i + 1 < line.length) cur += line[++i]; else cur += ch; continue; }
      if (ch === "'" || ch === '"') { quote = ch; has = true; continue; }
      if (ch === '\\' && i + 1 < line.length) { cur += line[++i]; has = true; continue; }
      if (/\s/.test(ch)) { push(); continue; }
      const op = line.slice(i).match(/^(\|\||&&|\d?>>|\d?>&\d|\d?>|<<-?|<|\||;|&)/);
      if (op) { push(); out.push({op: op[0]}); i += op[0].length - 1; continue; }
      cur += ch; has = true;
    }
    push();
    return out;
  }

  // Split tokens into simple commands, dropping redirections and their targets.
  function segments(tokens) {
    const segs = [[]];
    for (let i = 0; i < tokens.length; i++) {
      const t = tokens[i];
      if (typeof t === 'string') { segs.at(-1).push(t); continue; }
      if (SEPARATORS.has(t.op)) segs.push([]);
      else if (!/&\d$/.test(t.op)) i++; // > file, << EOF, < file: skip the target word
    }
    return segs.filter(s => s.length);
  }

  function distance(a, b) {
    const d = Array.from({length: a.length + 1}, (_, i) => [i, ...Array(b.length).fill(0)]);
    for (let j = 1; j <= b.length; j++) d[0][j] = j;
    for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    return d[a.length][b.length];
  }

  function checkKubectl(args) {
    const index = window.KUBECTL_INDEX;
    if (!index) return null;
    const cmds = index.commands, root = cmds[''];
    const flagType = (path, name, short) => {
      for (const c of [cmds[path.join(' ')], root]) {
        const t = c && (short ? c.short[name] : c.flags[name]);
        if (t) return t;
      }
      return null;
    };
    // Pass 1: find the subcommand path, skipping flag values. Unknown flags are read as bool here.
    const path = []; let positional = 0;
    for (let i = 0; i < args.length; i++) {
      const a = args[i];
      if (a === '--') break;
      if (a.startsWith('--')) { if (!a.includes('=') && (flagType(path, a.slice(2), false) || 'bool') !== 'bool') i++; continue; }
      if (a.startsWith('-') && a.length > 1) { const t = flagType(path, a[1], true); if (a.length === 2 && t && t !== 'bool') i++; continue; }
      const here = cmds[path.join(' ')];
      if (positional === 0 && here && here.subs.includes(a)) { path.push(a); continue; }
      // The index has no aliases (create deploy, create cm ...): not sure which command this is, so don't judge.
      if (positional === 0 && path.length && here && here.subs.length) return null;
      if (path.length === 0 && positional === 0) {
        const near = root.subs.filter(s => distance(s, a) <= 2);
        return `error: unknown command "${a}" for "kubectl"` + (near.length ? `\n\nDid you mean this?\n${near.map(s => `\t${s}`).join('\n')}` : '') + `\nRun 'kubectl --help' for usage.`;
      }
      positional++;
    }
    // Pass 2: every flag must exist on the command or globally.
    const usage = `See 'kubectl ${path.join(' ')}${path.length ? ' ' : ''}--help' for usage.`;
    for (let i = 0; i < args.length; i++) {
      const a = args[i];
      if (a === '--') break;
      if (a.startsWith('--')) {
        const name = a.slice(2).split('=')[0], t = flagType(path, name, false);
        if (!t) return `error: unknown flag: --${name}\n${usage}`;
        if (!a.includes('=') && t !== 'bool') i++;
      } else if (a.startsWith('-') && a.length > 1 && !/^-\d/.test(a)) {
        for (let j = 1; j < a.length; j++) {
          if (a[j] === '=') break;
          const t = flagType(path, a[j], true);
          if (!t) return `error: unknown shorthand flag: '${a[j]}' in ${a}\n${usage}`;
          if (t !== 'bool') { if (j === a.length - 1) i++; break; } // rest of the word (or next word) is the value
        }
      }
    }
    return null;
  }

  function checkSegment(words) {
    let i = 0;
    while (i < words.length && /^[A-Za-z_]\w*=/.test(words[i])) i++; // FOO=bar cmd
    if (words[i] === 'sudo') { i++; while (i < words.length && words[i].startsWith('-')) i++; }
    if (i >= words.length) return null;
    const cmd = words[i];
    if (cmd.includes('/')) return null; // ./script.sh, /usr/bin/x: not checked
    if (!KNOWN.has(cmd)) return `${cmd}: command not found`;
    if (cmd === 'kubectl' || cmd === 'k') return checkKubectl(words.slice(i + 1));
    return null;
  }

  // Only the first line: later lines are usually heredoc bodies or pasted YAML.
  function check(text) {
    const first = (text || '').split('\n')[0].trim();
    if (!first) return null;
    for (const seg of segments(tokenize(first))) {
      const err = checkSegment(seg);
      if (err) return err;
    }
    return null;
  }

  return {check, _tokenize: tokenize};
})();
