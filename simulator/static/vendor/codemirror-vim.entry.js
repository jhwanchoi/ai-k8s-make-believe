import {EditorState} from "@codemirror/state";
import {EditorView, keymap, lineNumbers, drawSelection, highlightActiveLine, highlightSpecialChars} from "@codemirror/view";
import {indentUnit, bracketMatching, indentOnInput} from "@codemirror/language";
import {history, defaultKeymap, historyKeymap, indentWithTab} from "@codemirror/commands";
import {yaml} from "@codemirror/lang-yaml";
import {oneDark} from "@codemirror/theme-one-dark";
import {vim, Vim, getCM} from "@replit/codemirror-vim";
// 편집기에 필요한 것만 (자동완성 · 린트 · 검색 패널은 빼서 번들을 줄인다. 검색은 vim 의 /). 줄 번호는 .vimrc 의 number 로 켠다
const setup = [highlightSpecialChars(), history(), drawSelection(), indentOnInput(), bracketMatching(), highlightActiveLine(),
  keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab])];
window.CM = {EditorView, EditorState, setup, lineNumbers, keymap, indentUnit, yaml, oneDark, vim, Vim, getCM};
