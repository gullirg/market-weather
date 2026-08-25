// Headless execution of a built page: stub the browser, run the scripts,
// tick animation frames, fire a scrub event. Any uncaught error fails.
// Two passes per page, one with prefers-reduced-motion off and one with
// it on, so both render paths execute.
import { readFileSync } from 'fs';
const file = process.argv[2];
// --expect-id=NAME asserts that the page ended up with that element,
// whether it was in the markup or created at runtime. It turns "this
// branch renders" into something a test can hold the page to.
const expectIds = process.argv.slice(3)
  .filter(a => a.startsWith('--expect-id='))
  .map(a => a.slice('--expect-id='.length));
// --expect-class=NAME and --expect-text=STRING do the same job for
// markup the page writes without an id: a class it must have produced,
// or a phrase it must have said. Between them a test can hold a page to
// rendering a branch whatever the design chose to mark it with.
const expectClasses = process.argv.slice(3)
  .filter(a => a.startsWith('--expect-class='))
  .map(a => a.slice('--expect-class='.length));
const expectTexts = process.argv.slice(3)
  .filter(a => a.startsWith('--expect-text='))
  .map(a => a.slice('--expect-text='.length));
const seenIds = new Set();
const seenClasses = new Set();
let written = '';
function noteHtml(h) {
  const s = String(h);
  written += s;
  for (const m of s.matchAll(/class=["']?([A-Za-z0-9 _-]+)/g))
    m[1].trim().split(/\s+/).forEach(c => c && seenClasses.add(c));
}
const html = readFileSync(file, 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)]
  .map(m => m[1]).join('\n;');

// Ids the page actually has. Scripts are stripped first so the embedded
// data payload cannot invent ids. getElementById returns null for
// anything not here, which is what a browser does and what the old stub
// did not: it fabricated an element for every id, so a page referring to
// an element it does not have went green headless and threw in Chrome.
const markup = html.replace(/<script>[\s\S]*?<\/script>/g, '');
function idsIn(s) {
  return [...String(s).matchAll(/id=["']?([A-Za-z0-9_-]+)/g)].map(m => m[1]);
}

const CTX_NOOPS = ['quadraticCurveTo', 'arc', 'fill', 'stroke', 'save',
  'restore', 'scale', 'translate', 'beginPath', 'closePath', 'moveTo',
  'lineTo', 'clearRect', 'fillRect', 'fillText', 'strokeText',
  'setTransform', 'setLineDash', 'drawImage', 'rect', 'clip'];

function runPass(reduceMotion) {
  const ctx = new Proxy({}, { get: (t, k) => {
    if (k === 'createRadialGradient') return () => ({ addColorStop(){} });
    if (k === 'createLinearGradient') return () => ({ addColorStop(){} });
    if (k === 'measureText') return () => ({ width: 10 });
    if (CTX_NOOPS.includes(k)) return () => {};
    return typeof t[k] !== 'undefined' ? t[k] : (() => {});
  }, set: () => true });
  const listeners = {};
  const known = new Set(idsIn(markup));
  known.forEach(i => seenIds.add(i));
  function makeEl(id){
    const el = {
      value:'0', max:'1', min:'0',
      style:{}, dataset:{},
      classList:{ add(){}, remove(){}, toggle(){} },
      appendChild(){},
      querySelector(){ return { onclick:null, addEventListener(){} }; },
      querySelectorAll(){ return []; },
      addEventListener(ev, fn){ (listeners[el.id+':'+ev] ||= []).push(fn); },
      // markup written at runtime can introduce ids, so they are learned
      insertAdjacentHTML(pos, h){
        noteHtml(h);
        idsIn(h).forEach(i => { known.add(i); seenIds.add(i); }); },
      className:'', title:'', remove(){},
      getContext(){ return ctx; },
      getBoundingClientRect(){ return { left:0, top:0, width:980, height:605 }; },
      clientWidth:980, clientHeight:605, width:1960, height:1210,
      parentElement:{ clientWidth:980 },
    };
    let _id = id, _html = '', _text = '';
    // text the page renders counts as output too. Without this,
    // --expect-text is blind to anything written with textContent,
    // which is how a page says a plain sentence with no markup in it.
    Object.defineProperty(el, 'textContent', {
      get(){ return _text; },
      set(v){ _text = String(v); noteHtml(_text); },
      enumerable: true });
    Object.defineProperty(el, 'id', {
      get(){ return _id; },
      set(v){ _id = v; if (v) { known.add(v); seenIds.add(v); } },
      enumerable: true });
    Object.defineProperty(el, 'innerHTML', {
      get(){ return _html; },
      set(v){ _html = v; noteHtml(v);
        idsIn(v).forEach(i => { known.add(i); seenIds.add(i); }); },
      enumerable: true });
    return el;
  }
  const els = {};
  const raf = [];
  globalThis.document = {
    getElementById(id){
      if (!known.has(id)) return null;
      return els[id] ||= makeEl(id);
    },
    querySelector(sel){ return els['sel'+sel] ||= makeEl('sel'+sel); },
    querySelectorAll(){ return [makeEl('x')]; },
    createElement(tag){ return makeEl('new:'+tag); },
    documentElement: makeEl('root'),
    body: makeEl('body'),
    hidden: false,
    addEventListener(){},
  };
  globalThis.window = globalThis;
  globalThis.addEventListener = () => {};
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => '#495158' });
  globalThis.devicePixelRatio = 2;
  globalThis.performance = { now: () => 0 };
  globalThis.matchMedia = () => ({
    matches: reduceMotion, addEventListener(){}, removeEventListener(){},
    addListener(){}, removeListener(){},
  });
  globalThis.requestAnimationFrame = (cb) => { raf.push(cb); return raf.length; };

  new Function(scripts)();
  for (let t = 0; t < 3 && raf.length; t++) {
    const cb = raf.shift();
    cb(16 * (t + 1));
  }
  const scrub = listeners['scrub:input'];
  if (scrub) {
    for (const fn of scrub) fn({ target: { value: '100' } });
    for (let t = 0; t < 2 && raf.length; t++) raf.shift()(200 + t);
    for (const fn of scrub) fn({ target: { value: String(1e6) } });
    if (raf.length) raf.shift()(400);
  }
  const move = listeners['g:mousemove'];
  if (move) for (const fn of move) fn({ clientX: 490, clientY: 242 });
  const click = listeners['g:click'];
  if (click) for (const fn of click) fn({ clientX: 490, clientY: 242 });
  if (raf.length) raf.shift()(500);
  // v6 tabs: both panes must render headlessly. TODAY first, since it
  // is the landing pane, then MAP, then back, so neither is left
  // unexercised and setTab runs in both directions.
  for (const t of ['tab-today', 'tab-map', 'tab-today', 'tab-map']) {
    const fns = listeners[t + ':click'];
    if (fns) {
      for (const fn of fns) fn({});
      if (raf.length) raf.shift()(700);
    }
  }
  // OUTLOOK toggle: exercise the cone, plume and meteogram paths with a
  // card open, then toggle back so the analysis-only path runs again.
  const outlook = listeners['voutlook:click'];
  if (outlook) {
    for (const fn of outlook) fn({ stopPropagation(){} });
    if (click) for (const fn of click) fn({ clientX: 490, clientY: 242 });
    // the browser reaches the outlook card path through the global
    // showCard; headless, the page exposes it under a named hook
    if (typeof globalThis.mwOutlookCard === 'function')
      for (const b of ['energy', 'fx', 'liquidity'])
        globalThis.mwOutlookCard(b);
    if (raf.length) raf.shift()(550);
    for (const fn of outlook) fn({ stopPropagation(){} });
    if (click) for (const fn of click) fn({ clientX: 490, clientY: 242 });
  }
  const streak = listeners['streaktbl:click'];
  if (streak) {
    for (const fn of streak) fn({ target: {
      className: 'srow', getAttribute: () => '0', parentElement: null } });
    for (const fn of streak) fn({ target: {
      className: 'nothing', parentElement: null } });
  }
  const legend = listeners['legendbtn:click'];
  if (legend) for (const fn of legend) fn({ stopPropagation(){}, target:{} });
  if (click) for (const fn of click) fn({ clientX: 5, clientY: 5 });
  if (raf.length) raf.shift()(600);
}

for (const reduce of [false, true]) {
  try {
    runPass(reduce);
  } catch (e) {
    const mode = reduce ? 'reduce' : 'no-preference';
    console.error('SCRIPT ERROR in', file,
      '(prefers-reduced-motion: ' + mode + '):', e.message);
    process.exit(1);
  }
}
const missing = expectIds.filter(i => !seenIds.has(i));
const missingC = expectClasses.filter(c => !seenClasses.has(c));
const missingT = expectTexts.filter(t => !written.includes(t));
if (missing.length || missingC.length || missingT.length) {
  console.error('EXPECTED OUTPUT NEVER RENDERED in', file, ':',
    JSON.stringify({ ids: missing, classes: missingC, text: missingT }));
  process.exit(1);
}
const n = expectIds.length + expectClasses.length + expectTexts.length;
console.log('OK', file, '(both motion passes)'
  + (n ? ' [' + n + ' expectation' + (n === 1 ? '' : 's') + ' met]' : ''));
