// Headless execution of a built page: stub the browser, run the scripts,
// tick animation frames, fire a scrub event. Any uncaught error fails.
// Two passes per page, one with prefers-reduced-motion off and one with
// it on, so both render paths execute.
import { readFileSync } from 'fs';
const file = process.argv[2];
const html = readFileSync(file, 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)]
  .map(m => m[1]).join('\n;');

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
  function makeEl(id){ return {
    id, innerHTML:'', textContent:'', value:'0', max:'1', min:'0',
    style:{}, dataset:{},
    classList:{ add(){}, remove(){}, toggle(){} },
    appendChild(){}, querySelector(){ return { onclick:null, addEventListener(){} }; },
    querySelectorAll(){ return []; },
    addEventListener(ev, fn){ (listeners[id+':'+ev] ||= []).push(fn); },
    getContext(){ return ctx; },
    getBoundingClientRect(){ return { left:0, top:0, width:980, height:605 }; },
    clientWidth:980, clientHeight:605, width:1960, height:1210,
    parentElement:{ clientWidth:980 },
  };}
  const els = {};
  const raf = [];
  globalThis.document = {
    getElementById(id){ return els[id] ||= makeEl(id); },
    querySelectorAll(){ return [makeEl('x')]; },
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
console.log('OK', file, '(both motion passes)');
