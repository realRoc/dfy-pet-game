// The 巨鲸 close-up, ported from demos/whale-tail/deep-sea.js. It is a
// separate full-screen shot, like the battle animation screen in the GBA Fire
// Emblem games: its own camera, ground line at y=175 and a bigger hero.
import {clamp, ease, mix, smooth, type Painter} from './pixel';

export const CUTIN_DURATION = 3200;
export const CUTIN_HIT = 1840;
const HOLD = 140;

const drawings = [
  {start: 0, end: 240}, {start: 240, end: 380}, {start: 380, end: 840}, {start: 840, end: 1100},
  {start: 1100, end: 1420}, {start: 1420, end: 2080}, {start: 2080, end: 2520}, {start: 2520, end: 3201},
];
const POSES = ['stand', 'chin', 'ponder', 'eureka', 'brace', 'release', 'recover', 'smug'];
export const cutinPose = (t: number) => POSES[Math.max(0, drawings.findIndex(d => t >= d.start && t < d.end))];

// Time-based cubic interpolation keeps the whale's velocity continuous; only
// the authored impact stop freezes motion.
const track = [
  {t: 1020, cx: 145, cy: 145, w: 140, angle: -.22, alpha: 0, solid: 0},
  {t: 1220, cx: 160, cy: 118, w: 205, angle: -.18, alpha: .65, solid: .18},
  {t: 1460, cx: 166, cy: 106, w: 300, angle: -.14, alpha: 1, solid: .78},
  {t: 1700, cx: 170, cy: 96, w: 420, angle: -.09, alpha: 1, solid: 1},
  {t: 1840, cx: 172, cy: 108, w: 450, angle: 0, alpha: 1, solid: 1},
  {t: 2000, cx: 218, cy: 123, w: 480, angle: .035, alpha: .93, solid: 1},
  {t: 2200, cx: 275, cy: 142, w: 525, angle: .06, alpha: .58, solid: 1},
  {t: 2420, cx: 328, cy: 175, w: 545, angle: .09, alpha: 0, solid: 1},
] as const;
type Key = 'cx' | 'cy' | 'w' | 'angle' | 'alpha' | 'solid';
interface WhaleState extends Record<Key, number> { phase: number; dissolve: number; smear: number }

function whaleState(t: number): WhaleState {
  const clock = t < CUTIN_HIT ? t : t < CUTIN_HIT + HOLD ? CUTIN_HIT : t - HOLD;
  let i = track.findIndex((key, j) => j < track.length - 1 && clock >= key.t && clock < track[j + 1].t);
  if (i < 0) i = clock < track[0].t ? 0 : track.length - 2;
  const a = track[i], b = track[i + 1], before = track[Math.max(0, i - 1)], after = track[Math.min(track.length - 1, i + 2)];
  const p = clamp((clock - a.t) / (b.t - a.t)), span = b.t - a.t;
  const r = {phase: clock} as WhaleState;
  for (const k of ['cx', 'cy', 'w', 'angle', 'alpha', 'solid'] as Key[]) {
    const ma = (b[k] - before[k]) / (b.t - before.t), mb = (after[k] - a[k]) / (after.t - a.t);
    r[k] = (2 * p ** 3 - 3 * p * p + 1) * a[k] + (p ** 3 - 2 * p * p + p) * ma * span + (-2 * p ** 3 + 3 * p * p) * b[k] + (p ** 3 - p * p) * mb * span;
  }
  r.alpha = clamp(r.alpha); r.solid = clamp(r.solid);
  r.dissolve = smooth((clock - 1980) / 440);
  r.smear = clock < 1800 ? 0 : clock <= 1840 ? smooth((clock - 1800) / 40) : 1 - smooth((clock - 1840) / 120);
  return r;
}

let rigSource: HTMLCanvasElement | null = null, body!: HTMLCanvasElement, warped!: HTMLCanvasElement, wire!: HTMLCanvasElement;
function drawWhale(ctx: CanvasRenderingContext2D, sprite: HTMLCanvasElement, p: WhaleState) {
  if (sprite !== rigSource) {
    rigSource = sprite;
    body = document.createElement('canvas'); body.width = 320; body.height = Math.round(320 * sprite.height / sprite.width);
    const c = body.getContext('2d')!; c.imageSmoothingEnabled = false; c.drawImage(sprite, 0, 0, body.width, body.height);
    warped = document.createElement('canvas'); warped.width = 320; warped.height = body.height + 32;
    wire = document.createElement('canvas'); wire.width = warped.width; wire.height = warped.height;
  }
  const c = warped.getContext('2d')!; c.clearRect(0, 0, warped.width, warped.height); c.imageSmoothingEnabled = false;
  // The head stays heavy; the tail carries most of the follow-through.
  for (let x = 0; x < 320; x += 4) {
    const u = x / 320, tail = Math.pow(1 - u, 3), dy = Math.round(Math.sin(p.phase * .010 - u * 7) * tail * 10);
    const breathing = Math.round(Math.sin(p.phase * .006 - u * 2) * 2 * (1 - u * .5));
    c.drawImage(body, x, 0, 4, body.height, x, 16 + dy - breathing, 5, body.height + breathing * 2);
  }
  if (p.dissolve > 0) {
    c.globalCompositeOperation = 'destination-out';
    for (let y = 0; y < warped.height; y += 8) for (let x = 0; x < 320; x += 8) {
      const seed = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453, random = seed - Math.floor(seed);
      if (random < p.dissolve * .8) c.fillRect(x, y, Math.ceil(p.dissolve * 8), Math.ceil(p.dissolve * 8));
    }
    c.globalCompositeOperation = 'source-over';
  }
  const wc = wire.getContext('2d')!;
  if (p.solid < 1) {
    wc.clearRect(0, 0, wire.width, wire.height); wc.drawImage(warped, 0, 0);
    wc.globalCompositeOperation = 'source-in'; wc.fillStyle = '#153b61'; wc.fillRect(0, 0, wire.width, wire.height);
    wc.globalCompositeOperation = 'source-atop'; wc.strokeStyle = '#8ddde8'; wc.lineWidth = 1; wc.beginPath();
    for (let x = -wire.height; x < wire.width + wire.height; x += 24) { wc.moveTo(x, 0); wc.lineTo(x + wire.height, wire.height); wc.moveTo(x, 0); wc.lineTo(x - wire.height, wire.height); }
    for (let y = 12; y < wire.height; y += 20) { wc.moveTo(0, y); wc.lineTo(wire.width, y); }
    wc.stroke(); wc.globalCompositeOperation = 'source-over';
  }
  const w = p.w * (1 + p.smear * .045), h = warped.height / 320 * p.w * (1 - p.smear * .04);
  ctx.save(); ctx.translate(p.cx, p.cy); ctx.rotate(p.angle); ctx.imageSmoothingEnabled = false;
  if (p.solid < 1) { ctx.globalAlpha = p.alpha * (1 - p.solid); ctx.drawImage(wire, Math.round(-w / 2), Math.round(-h / 2), Math.round(w), Math.round(h)); }
  ctx.globalAlpha = p.alpha * p.solid; ctx.drawImage(warped, Math.round(-w / 2), Math.round(-h / 2), Math.round(w), Math.round(h));
  ctx.restore();
}

export function cutinMotion(t: number) {
  let x = 85, y = 175;
  if (t >= 1100 && t < 1420) x -= Math.round(3 * ease((t - 1100) / 320));
  else if (t >= 1420 && t < 2080) { x = 89; y -= t < CUTIN_HIT ? Math.round(Math.sin(clamp((t - 1420) / 350) * Math.PI) * 2) : 0; }
  else if (t >= 2080 && t < 2520) x = mix(89, 85, ease((t - 2080) / 440));
  return {x: Math.round(x), y: Math.round(y)};
}

export interface CutinScene {
  p: Painter;
  background(t: number): void;
  /** Draws the struck enemy with its feet at (289, 175). */
  target(t: number, hit: boolean): void;
  character(t: number): void;
  whale: HTMLCanvasElement;
  damage: number;
  title: string;
}

export function renderCutin(t: number, s: CutinScene) {
  const {p, whale} = s, {ctx, rect, poly, line, text, ring, star, noise} = p;
  const HIT = CUTIN_HIT;
  // Everything except screen shake uses a frozen action clock at contact.
  const f = t >= HIT && t < HIT + HOLD ? HIT : t;
  const dark = t < 760 ? 0 : t < 1040 ? ease((t - 760) / 280) : t < 2200 ? 1 : 1 - ease((t - 2200) / 450);
  rect(0, 0, 384, 216, dark > .2 ? '#152c3a' : '#9cb3a8');
  ctx.save();
  if (t >= HIT && t < HIT + 260) { const q = (t - HIT) / 260; ctx.translate(Math.round(Math.sin(q * 64) * 5 * (1 - q)), Math.round(Math.cos(q * 49) * 2 * (1 - q))); }
  s.background(f);
  ctx.globalAlpha = dark * .83; rect(0, 0, 384, 197, '#041a32'); ctx.globalAlpha = 1;
  if (dark > 0) {
    ctx.globalAlpha = dark * .65;
    for (let i = 0; i < 30; i++) { const x = noise(i + 18) * 384, y = 40 + noise(i + 87) * 139; rect(x, y - Math.floor(f / 170 + i) % 12, 1, i % 3 ? 1 : 2, i % 3 ? '#558ba6' : '#add9dc'); }
    ctx.globalAlpha = 1;
  }
  if (f >= 920 && f < 2500) {
    const q = clamp((f - 920) / 500), fade = f < 2180 ? 1 : 1 - clamp((f - 2180) / 320);
    ring(197, 178, 80 * q, 8 * q, '#3a849f', fade * .8); ring(197, 178, 70 * q, 6 * q, '#8cd0d5', fade * .7);
    if (f >= 1260) for (let i = 0; i < 15; i++) { const xx = 137 + i * 9, yy = 178 - Math.sin(i * .8 + f * .012) * 2; rect(xx, yy, 7, 1, '#99d7dc'); }
  }
  s.target(f, t >= HIT && t < HIT + 600);
  // Three thinking beats: 已思考3秒.
  if (f >= 320 && f < 900) for (let i = 0; i < 3; i++) {
    const on = f >= 360 + i * 150;
    rect(73 + i * 9, 61, 6, 6, '#354f60'); rect(74 + i * 9, 62, 4, 4, on ? '#e5f8e6' : '#577e8d'); if (on) rect(75 + i * 9, 61, 2, 1, '#fff9d4');
  }
  if (f >= 840 && f < 1440) {
    const points: [number, number][] = [[110, 125], [140, 103], [175, 115], [207, 79], [246, 91], [274, 122], [226, 149], [170, 150]];
    const paths = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 0], [1, 7], [2, 6], [2, 4], [4, 6], [2, 7]];
    const progress = clamp((f - 840) / 430), fade = f < 1260 ? 1 : 1 - clamp((f - 1260) / 180);
    ctx.globalAlpha = fade;
    paths.forEach(([u, v], i) => { const q = clamp(progress * paths.length - i); if (q > 0) line([points[u], [mix(points[u][0], points[v][0], q), mix(points[u][1], points[v][1], q)]], '#73c6dc', 1); });
    points.forEach(([x, y], i) => { if (progress > i / points.length) rect(x - 1, y - 1, 3, 3, '#c0f0e8'); });
    ctx.globalAlpha = 1;
  }
  if (t >= 1020 && t < 2560) {
    drawWhale(ctx, whale, whaleState(t));
    if (t >= 1320 && t < 2300) {
      const q = clamp((t - 1320) / 420), fade = 1 - clamp((t - 2080) / 220);
      ctx.globalAlpha = fade;
      for (let i = 0; i < 48; i++) { const xx = noise(i + 41) * 384, flight = noise(i + 20); rect(xx, 180 - Math.sin(q * Math.PI * .7 + flight) * q * (12 + flight * 27), 2 + i % 3, 2 + i % 4, i % 3 ? '#9ddce4' : '#e4faf0'); }
      ctx.globalAlpha = 1;
    }
  }
  if (t >= 1800 && t < 2140) {
    ctx.globalAlpha = t < HIT ? smooth((t - 1800) / 40) : t < HIT + HOLD ? 1 : 1 - smooth((t - HIT - HOLD) / 160);
    for (let i = 0; i < 9; i++) { const yy = 58 + i * 14; line([[-8, yy + 9], [150 + i * 13, yy]], i % 3 ? '#518caf' : '#b0e8ed', i % 2 ? 1 : 2); }
    ctx.globalAlpha = 1;
  }
  s.character(f);
  if (t >= HIT && t < HIT + HOLD) {
    const x = 300, y = 156;
    poly([[x - 19, y], [x - 7, y - 7], [x - 6, y - 21], [x + 2, y - 9], [x + 15, y - 18], [x + 9, y - 3], [x + 26, y + 1], [x + 9, y + 6], [x + 10, y + 21], [x, y + 11], [x - 14, y + 19], [x - 9, y + 4]], '#d9fbef'); star(x, y, 10, '#fff6d3');
    for (let i = 0; i < 7; i++) { const a = i * Math.PI * 2 / 7; line([[x + Math.cos(a) * 24, y + Math.sin(a) * 24], [x + Math.cos(a) * 38, y + Math.sin(a) * 38]], '#a1dae8', 1); }
  }
  if (t >= HIT + HOLD && t < 2500) {
    const q = (t - HIT - HOLD) / 520;
    for (let i = 0; i < 110; i++) { const a = -Math.PI + noise(i + 26) * Math.PI, v = 40 + noise(i + 66) * 240; rect(270 + Math.cos(a) * v * q, 123 + Math.sin(a) * v * q + 75 * q * q, 2 + i % 4, 2 + i % 3, i % 3 ? '#a2e2e3' : '#4e95bb'); }
    ring(235, 178, 50 + q * 145, 4 + q * 10, '#c2f0e3', 1 - q);
  }
  if (t >= 1420 && t < 2470) {
    const fade = t < 2100 ? clamp((t - 1420) / 300) : 1 - clamp((t - 2100) / 370);
    ctx.globalAlpha = fade * .9;
    const wave: [number, number][] = [[0, 197]];
    for (let xx = 0; xx <= 384; xx += 4) wave.push([xx, 183 - Math.max(0, Math.sin(xx * .04 - f * .012)) * 8]);
    wave.push([384, 197]); poly(wave, '#397eaa');
    for (let xx = 0; xx < 384; xx += 7) rect(xx, 182 - Math.max(0, Math.sin(xx * .04 - f * .012)) * 8, 5, 2, '#b3ebed');
    ctx.globalAlpha = 1;
  }
  if (t >= HIT + 35 && t < 2470) {
    const q = clamp((t - HIT - HOLD) / 420), n = String(s.damage);
    text(n, 289, 104 - q * 19, '#132e46', 18, 'center'); text(n, 288, 103 - q * 19, '#fff0bd', 18, 'center'); text('CRITICAL', 288, 88 - q * 9, '#e2d7a9', 6, 'center');
  }
  if (t >= 2590 && t < 3040) {
    rect(108, 95, 70, 17, '#203d47'); line([[109, 95], [177, 95]], '#81a49f'); poly([[111, 111], [116, 111], [111, 116]], '#203d47');
    text('思考完毕。', 143, 106, '#f0ead2', 8, 'center'); star(61, 116, 3, '#ecd7a4');
  }
  ctx.restore();
  rect(0, 197, 384, 19, '#263e44'); rect(0, 197, 384, 1, '#79918a'); rect(9, 204, 3, 3, '#b4d6c0');
  text(s.title, 18, 210, '#e3ead4', 8); text('必杀 / 深度思考', 373, 209, '#abc1b1', 7, 'right');
}
