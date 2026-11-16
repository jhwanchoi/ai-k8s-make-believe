# vendor

`codemirror-vim.js` 는 웹 터미널의 `vim` · `nano` 편집기(`../editor.js`)가 쓰는 CodeMirror 6 묶음이다. 인터넷 없이 동작하고 버전을 고정하려고 한 번 묶어서 넣었다. 직접 고치지 않는다.

| 패키지 | 버전 | 라이선스 |
|---|---|---|
| @codemirror/state | 6.7.6 | MIT |
| @codemirror/view | 6.43.15 | MIT |
| @codemirror/commands | 6.11.1 | MIT |
| @codemirror/language | 6.13.1 | MIT |
| @codemirror/lang-yaml | 6.1.3 | MIT |
| @codemirror/theme-one-dark | 6.1.3 | MIT |
| @replit/codemirror-vim | 6.4.0 | MIT |
| esbuild (묶기 도구, 포함되지 않음) | 0.28.2 | MIT |

CodeMirror: Copyright (C) 2018-2021 by Marijn Haverbeke and others. codemirror-vim: Copyright (C) 2023 Replit. 모두 MIT 라이선스이며 전문은 각 패키지(npm)에 있다.

## 다시 묶기

```bash
mkdir /tmp/cm-build && cd /tmp/cm-build && npm init -y
npm i @codemirror/state @codemirror/view @codemirror/commands @codemirror/language @codemirror/lang-yaml @codemirror/theme-one-dark @replit/codemirror-vim esbuild
cp <repo>/simulator/static/vendor/codemirror-vim.entry.js entry.js
npx esbuild entry.js --bundle --minify --format=iife --legal-comments=none --outfile=<repo>/simulator/static/vendor/codemirror-vim.js
```

`codemirror-vim.entry.js` 가 `window.CM` 으로 내보내는 것만 쓴다. basicSetup 의 자동완성 · 린트 · 검색 패널은 빼서 크기를 줄였다(검색은 vim 의 `/`). 줄 번호는 `.vimrc` 의 `set number` 일 때만 켠다.
