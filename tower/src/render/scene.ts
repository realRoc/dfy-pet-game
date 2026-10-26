import heroPng from '../assets/hero.png';
import heroMeta from '../assets/hero.json';
import closePng from '../assets/hero-closeup.png';
import closeMeta from '../assets/hero-closeup.json';
import whalePng from '../assets/whale.png';
import {beach, GROUND_LIFT} from './background';
import {CUTIN_DURATION, cutinMotion, cutinPose, renderCutin} from './cutin';
import {enemyArt, renderEnemy, type EnemyPose} from './enemy-art';
import {icon} from './icons';
import {clamp, ease, H, mix, noise, painter, silhouette, W, type Painter} from './pixel';

export const GROUND = 147;
export const HERO_X = 92;

interface Frame { x: number; y: number; w: number; h: number; ax: number; ay: number }
interface Atlas { img: HTMLImageElement; frames: Record<string, Frame>; cuts: Map<string, HTMLCanvasElement>; flashes: Map<string, HTMLCanvasElement> }

export interface Actor {
  id: string;
  kind: string;
  x: number;
  pose: EnemyPose;
  flashUntil: number;
  dyingAt: number | null;
  w: number;
  h: number;
  hover: number;
}

interface Floater { text: string; x: number; y: number; at: number; color: string; size: number }
interface Particle { x: number; y: number; vx: number; vy: number; at: number; life: number; color: string; size: number; gravity: number }
interface Tween { at: number; ms: number; fn(p: number): void; done(): void }
interface Projectile { from: [number, number]; to: [number, number]; at: number; ms: number }

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('像素素材加载失败：' + src));
    img.src = src;
  });
}

async function loadAtlas(src: string, frames: Record<string, Frame>): Promise<Atlas> {
  return {img: await loadImage(src), frames, cuts: new Map(), flashes: new Map()};
}

function cut(a: Atlas, name: string): HTMLCanvasElement {
  let c = a.cuts.get(name);
  if (!c) {
    const f = a.frames[name];
    c = document.createElement('canvas'); c.width = f.w; c.height = f.h;
    c.getContext('2d')!.drawImage(a.img, f.x, f.y, f.w, f.h, 0, 0, f.w, f.h);
    a.cuts.set(name, c);
  }
  return c;
}

function cropToContent(img: HTMLImageElement): HTMLCanvasElement {
  const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
  const ctx = c.getContext('2d')!; ctx.drawImage(img, 0, 0);
  const d = ctx.getImageData(0, 0, c.width, c.height).data;
  let l = c.width, r = 0, t = c.height, b = 0;
  for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) if (d[(y * c.width + x) * 4 + 3] > 128) { l = Math.min(l, x); r = Math.max(r, x); t = Math.min(t, y); b = Math.max(b, y); }
  const out = document.createElement('canvas'); out.width = r - l + 1; out.height = b - t + 1;
  out.getContext('2d')!.drawImage(c, l, t, out.width, out.height, 0, 0, out.width, out.height);
  return out;
}

const SLOTS: Record<number, number[]> = {1: [292], 2: [252, 334], 3: [226, 288, 350]};

/**
 * Everything drawn on the 384×216 canvas. Animation helpers return promises on
 * the scene clock, so the event player can simply await each beat.
 */
export class Scene {
  readonly ctx: CanvasRenderingContext2D;
  readonly p: Painter;
  time = 0;
  speed = 1;
  hero = {x: HERO_X, pose: 'idle', flashUntil: 0, hidden: false};
  actors: Actor[] = [];
  thinking: {at: number} | null = null;
  basin: {at: number} | null = null;
  overhead: {name: string; at: number} | null = null;
  /** 波峰 / 波谷 aura around the hero; set by the HUD as stance events play. */
  stance: 'none' | 'crest' | 'trough' = 'none';
  private hero$!: Atlas;
  private close$!: Atlas;
  private whale!: HTMLCanvasElement;
  private whaleSmall!: HTMLCanvasElement;
  private floaters: Floater[] = [];
  private particles: Particle[] = [];
  private tweens: Tween[] = [];
  private waiters: {at: number; resolve(): void}[] = [];
  private projectiles: Projectile[] = [];
  private shake = {until: 0, mag: 0};
  private screenFlash = {until: 0, color: '#ffffff'};
  private cut: {at: number; damage: number; target: Actor | null; title: string; resolve(): void} | null = null;
  private last = 0;

  constructor(readonly canvas: HTMLCanvasElement) {
    this.ctx = canvas.getContext('2d', {alpha: false})!;
    this.ctx.imageSmoothingEnabled = false;
    this.p = painter(this.ctx);
  }

  async load() {
    [this.hero$, this.close$] = await Promise.all([loadAtlas(heroPng, heroMeta), loadAtlas(closePng, closeMeta)]);
    this.whale = cropToContent(await loadImage(whalePng));
    const s = document.createElement('canvas'); s.width = 34; s.height = Math.round(34 * this.whale.height / this.whale.width);
    s.getContext('2d')!.drawImage(this.whale, 0, 0, s.width, s.height);
    this.whaleSmall = s;
    requestAnimationFrame(now => { this.last = now; this.loop(now); });
  }

  // ── setup ────────────────────────────────────────────────────────────────

  setEnemies(list: {id: string; kind: string}[]) {
    const slots = SLOTS[list.length] ?? list.map((_, i) => 220 + i * 50);
    this.actors = list.map((e, i) => {
      const art = enemyArt(e.kind);
      return {id: e.id, kind: e.kind, x: slots[i], pose: 'idle', flashUntil: 0, dyingAt: null, w: art.w, h: art.h, hover: art.hover};
    });
    this.hero.x = HERO_X; this.hero.pose = 'idle'; this.hero.hidden = false; this.stance = 'none';
    this.floaters = []; this.particles = []; this.projectiles = [];
  }

  actor(id: string) { return this.actors.find(a => a.id === id)!; }

  /** The small whale sprite, for the map marker. */
  get whaleIcon() { return this.whaleSmall; }

  /** One battle pose as its own canvas, for card illustrations. */
  heroFrame(name: string) { return cut(this.hero$, name); }

  /** Box around a unit in canvas pixels, for the DOM overlay. */
  box(id: string) {
    if (id === 'p') return {x: HERO_X - 30, y: GROUND - 72, w: 60, h: 72};
    const a = this.actor(id);
    return {x: a.x - a.w / 2, y: GROUND - a.hover - a.h, w: a.w, h: a.h};
  }

  // ── clock ────────────────────────────────────────────────────────────────

  wait(ms: number): Promise<void> { return new Promise(resolve => this.waiters.push({at: this.time + ms, resolve})); }

  tween(ms: number, fn: (p: number) => void): Promise<void> {
    return new Promise(done => this.tweens.push({at: this.time, ms, fn, done}));
  }

  private loop(now: number) {
    const dt = Math.min(now - this.last, 64);
    this.last = now;
    this.time += dt * this.speed;
    for (const tw of [...this.tweens]) {
      const p = clamp((this.time - tw.at) / tw.ms);
      tw.fn(p);
      if (p >= 1) { this.tweens.splice(this.tweens.indexOf(tw), 1); tw.done(); }
    }
    for (const w of [...this.waiters]) if (this.time >= w.at) { this.waiters.splice(this.waiters.indexOf(w), 1); w.resolve(); }
    this.draw();
    requestAnimationFrame(n => this.loop(n));
  }

  // ── hero beats ───────────────────────────────────────────────────────────

  pose(name: string) { this.hero.pose = name; }

  private heroTo(x: number, ms: number) {
    const from = this.hero.x;
    return this.tween(ms, p => { this.hero.x = Math.round(mix(from, x, ease(p))); });
  }

  /** 鲸尾: coil, charge, a 40 ms smear and the strike frame at contact. */
  async tailWindup(target: Actor) {
    this.pose('coil'); await this.wait(90);
    this.pose('charged'); await this.wait(80);
    const f = this.hero$.frames.strike, tx = target.x - target.w / 2 + 8 - (f.w - f.ax);
    this.pose('smear');
    await this.heroTo(Math.max(HERO_X, tx), 50);
    this.pose('strike');
  }

  async tailRestrike() { this.pose('sweep'); await this.wait(60); this.pose('strike'); }

  async spinWindup() {
    this.pose('coil'); await this.wait(80);
    this.pose('twist'); await this.heroTo(HERO_X + 36, 90);
    this.pose('smear'); await this.wait(40);
    this.pose('sweep');
    for (const a of this.actors) if (!a.dyingAt) this.splash(a.x, GROUND - a.hover - a.h / 2, 10);
  }

  async thinkWindup(target: Actor) {
    this.pose('ult-eureka'); this.think(); await this.wait(150);
    this.pose('ult-brace'); await this.wait(130);
    this.pose('ult-release');
    const from: [number, number] = [this.hero.x + 30, GROUND - 46], to: [number, number] = [target.x, GROUND - target.hover - target.h / 2];
    const proj = {from, to, at: this.time, ms: 170};
    this.projectiles.push(proj);
    await this.wait(170);
    this.projectiles.splice(this.projectiles.indexOf(proj), 1);
  }

  async recover(kind: 'tail' | 'think') {
    if (kind === 'tail') { this.pose('rebound'); await this.wait(110); this.pose('hips'); }
    else { this.pose('ult-recover'); await this.wait(140); }
    await this.heroTo(HERO_X, 180);
    this.pose('idle');
  }

  async ponder() {
    this.pose('ult-chin'); this.think(); await this.wait(110);
    this.pose('ult-ponder'); await this.wait(260);
    this.pose('ult-eureka'); await this.wait(130);
    this.pose('idle');
  }

  private think() { this.thinking = {at: this.time}; }

  async raiseBowl() {
    this.pose('hips'); this.basin = {at: this.time};
    await this.wait(240);
    this.pose('idle');
  }

  async smug(overhead?: string) {
    this.pose('ult-smug');
    if (overhead) this.overhead = {name: overhead, at: this.time};
    for (let i = 0; i < 8; i++) this.particle(HERO_X - 20 + noise(this.time + i) * 40, GROUND - 60 + noise(i * 7 + this.time) * 30, 0, -.02, 600, '#fff1bd', 2, 0);
    await this.wait(320);
    this.pose('idle');
  }

  async heroHurt(amount: number, blocked: number) {
    this.hero.flashUntil = this.time + 90;
    this.burst(HERO_X + 8, GROUND - 40, amount ? '#ffe2c4' : '#c9d6e4', amount ? 10 : 6);
    if (amount) { this.number(String(amount), HERO_X, GROUND - 80, '#ffe9d6'); this.shakeScreen(3, 160); this.pose('sink'); }
    if (blocked) this.number(String(blocked), HERO_X - 18, GROUND - 66, '#a9c8ec', 8);
    const from = this.hero.x;
    await this.tween(70, p => { this.hero.x = Math.round(from - 5 * p); });
    await this.heroTo(HERO_X, 140);
    if (this.hero.pose === 'sink') this.pose('idle');
  }

  heroDown() { this.pose('sink'); }
  victory() { this.pose('ult-smug'); }

  // ── enemy beats ──────────────────────────────────────────────────────────

  async enemyWindup(a: Actor) {
    a.pose = 'wind';
    const home = a.x;
    await this.tween(130, p => { a.x = Math.round(home + 5 * ease(p)); });
    a.pose = 'attack';
    await this.tween(70, p => { a.x = Math.round(home + 5 - 30 * p * p); });
  }

  async enemyRecover(a: Actor, home: number) {
    await this.tween(170, p => { a.x = Math.round(mix(home - 25, home, ease(p))); });
    if (!a.dyingAt) a.pose = 'idle';
  }

  async enemyAct(a: Actor) {
    a.pose = 'wind'; await this.wait(180);
    if (!a.dyingAt) a.pose = 'idle';
  }

  async hitActor(a: Actor, amount: number, blocked: number) {
    a.flashUntil = this.time + 80;
    a.pose = 'hurt';
    const cy = GROUND - a.hover - a.h / 2;
    this.burst(a.x - a.w / 4, cy, '#fff2bd', amount ? 12 : 5);
    if (amount) { this.number(String(amount), a.x, GROUND - a.hover - a.h - 6, '#fff5d7'); this.shakeScreen(2, 120); }
    if (blocked) this.number(String(blocked), a.x - 16, GROUND - a.hover - a.h + 6, '#a9c8ec', 8);
    const home = a.x;
    await this.tween(60, p => { a.x = Math.round(home + 4 * p); });
    this.tween(150, p => { a.x = Math.round(mix(home + 4, home, p)); }).then(() => { if (!a.dyingAt && a.pose === 'hurt') a.pose = 'idle'; });
  }

  kill(a: Actor) {
    a.dyingAt = this.time;
    for (let i = 0; i < 26; i++) {
      const ang = noise(i + this.time) * Math.PI * 2, v = .03 + noise(i * 3 + this.time) * .07;
      this.particle(a.x, GROUND - a.hover - a.h / 2, Math.cos(ang) * v, Math.sin(ang) * v - .04, 700, i % 2 ? '#fbf6ea' : '#c9dde4', 2, .00012);
    }
  }

  blockFx(id: string, amount: number) {
    const b = this.box(id);
    this.number('+' + amount, b.x + b.w / 2, b.y - 4, '#a9d8ff', 8);
    for (let i = 0; i < 6; i++) this.particle(b.x + noise(i + this.time) * b.w, b.y + b.h * .5, 0, -.03, 500, '#d5e8f7', 2, 0);
  }

  healFx(amount: number) {
    this.number('+' + amount, HERO_X, GROUND - 82, '#9ff0a6', 9);
    for (let i = 0; i < 10; i++) this.particle(HERO_X - 16 + noise(i + this.time) * 32, GROUND - 10, 0, -.04 - noise(i) * .03, 800, '#bff5c0', 2, 0);
  }

  flash(color = '#ffffff', ms = 60) { this.screenFlash = {until: this.time + ms, color}; }

  // ── the 巨鲸 close-up ────────────────────────────────────────────────────

  cutIn(damage: number, target: Actor | null, title: string): Promise<void> {
    return new Promise(resolve => { this.cut = {at: this.time, damage, target, title, resolve}; });
  }

  skipCutIn() { if (this.cut) this.cut.at = this.time - CUTIN_DURATION; }
  get inCutIn() { return !!this.cut; }

  // ── effects ──────────────────────────────────────────────────────────────

  private number(text: string, x: number, y: number, color: string, size = 11) { this.floaters.push({text, x, y, at: this.time, color, size}); }

  private particle(x: number, y: number, vx: number, vy: number, life: number, color: string, size: number, gravity: number) {
    this.particles.push({x, y, vx, vy, at: this.time, life, color, size, gravity});
  }

  private burst(x: number, y: number, color: string, n: number) {
    for (let i = 0; i < n; i++) {
      const ang = noise(i + this.time * .37) * Math.PI * 2, v = .04 + noise(i * 5 + this.time) * .08;
      this.particle(x, y, Math.cos(ang) * v, Math.sin(ang) * v, 260 + noise(i) * 200, i % 3 ? color : '#ffffff', 1 + (i % 2), .0002);
    }
  }

  private splash(x: number, y: number, n: number) {
    for (let i = 0; i < n; i++) this.particle(x + (noise(i + x) - .5) * 20, y, (noise(i * 3 + x) - .5) * .08, -.05 - noise(i * 7) * .06, 600, i % 3 ? '#9ddce4' : '#e4faf0', 2, .00035);
  }

  shakeScreen(mag: number, ms: number) { this.shake = {until: this.time + ms, mag}; }

  // ── drawing ──────────────────────────────────────────────────────────────

  private drawFrame(a: Atlas, name: string, x: number, y: number, flash: boolean) {
    const f = a.frames[name];
    const img = cut(a, name);
    this.ctx.drawImage(img, Math.round(x - f.ax), Math.round(y - f.ay));
    if (flash) {
      let s = a.flashes.get(name);
      if (!s) { s = silhouette(img); a.flashes.set(name, s); }
      this.ctx.save(); this.ctx.globalAlpha = .85; this.ctx.drawImage(s, Math.round(x - f.ax), Math.round(y - f.ay)); this.ctx.restore();
    }
  }

  private draw() {
    const {ctx, p, time} = this;
    if (this.cut) return this.drawCutIn();
    ctx.save();
    if (time < this.shake.until) {
      const k = (this.shake.until - time) / 160;
      ctx.translate(Math.round(Math.sin(time * .9) * this.shake.mag * k), Math.round(Math.cos(time * .7) * this.shake.mag * .5 * k));
    }
    beach(p, time, GROUND_LIFT);

    for (const a of this.actors) {
      if (a.dyingAt && time - a.dyingAt > 500) continue;
      const r = a.hover ? Math.round(a.w / 4) : Math.round(a.w / 2.4);
      p.ctx.globalAlpha = a.dyingAt ? 1 - (time - a.dyingAt) / 500 : 1;
      p.ellipse(a.x, GROUND + 1, r, 3, '#b3a57c');
      p.ctx.globalAlpha = 1;
    }
    if (!this.hero.hidden) p.ellipse(this.hero.x, GROUND + 1, 17, 3, '#b3a57c');

    for (const a of this.actors) this.drawActor(a);
    if (!this.hero.hidden) {
      const bob = this.hero.pose === 'idle' ? Math.floor(time / 650) % 2 : 0;
      this.drawFrame(this.hero$, this.hero.pose, this.hero.x, GROUND + bob, time < this.hero.flashUntil);
    }
    this.drawHeroExtras();

    for (const pr of this.projectiles) {
      const q = clamp((time - pr.at) / pr.ms), x = mix(pr.from[0], pr.to[0], q), y = mix(pr.from[1], pr.to[1], q) - Math.sin(q * Math.PI) * 10;
      for (let i = 1; i < 5; i++) p.rect(x - i * 7 - 6, y + (i % 2) - 1, 6, 2, i % 2 ? '#8ddde8' : '#4e95bb');
      ctx.drawImage(this.whaleSmall, Math.round(x - this.whaleSmall.width / 2), Math.round(y - this.whaleSmall.height / 2));
    }

    this.particles = this.particles.filter(pt => time - pt.at < pt.life);
    for (const pt of this.particles) {
      const dt = time - pt.at;
      p.rect(pt.x + pt.vx * dt, pt.y + pt.vy * dt + pt.gravity * dt * dt, pt.size, pt.size, pt.color);
    }
    this.floaters = this.floaters.filter(f => time - f.at < 760);
    for (const f of this.floaters) {
      const q = (time - f.at) / 760, y = f.y - ease(q * 1.4) * 14;
      ctx.globalAlpha = q < .75 ? 1 : 1 - (q - .75) / .25;
      ctx.font = `bold ${f.size}px monospace`; ctx.textAlign = 'center';
      ctx.fillStyle = '#1d2c38'; ctx.fillText(f.text, Math.round(f.x) + 1, Math.round(y) + 1);
      ctx.fillStyle = f.color; ctx.fillText(f.text, Math.round(f.x), Math.round(y));
      ctx.globalAlpha = 1;
    }
    if (time < this.screenFlash.until) { ctx.globalAlpha = .18; p.rect(0, 0, W, H, this.screenFlash.color); ctx.globalAlpha = 1; }
    ctx.restore();
  }

  private drawActor(a: Actor) {
    const {ctx, time} = this;
    if (a.dyingAt && time - a.dyingAt > 500) return;
    const sprite = renderEnemy(a.kind, time + a.x * 13, a.pose);
    const bob = a.hover ? Math.round(Math.sin(time / 300 + a.x) * 2) : 0;
    const sink = a.dyingAt ? (time - a.dyingAt) / 500 * 8 : 0;
    const x = Math.round(a.x - sprite.width / 2), y = Math.round(GROUND - a.hover - sprite.height + 1 + bob + sink);
    ctx.globalAlpha = a.dyingAt ? 1 - (time - a.dyingAt) / 500 : 1;
    // 服务器繁忙 tears into offset slices now and then; 乱码虫 does it all the time.
    const glitch = (a.kind === 'jelly' && time % 2300 < 150) || (a.kind === 'glitch' && time % 700 < 220) || (a.kind === 'blackWhale' && time % 3100 < 90);
    if (glitch) {
      for (let y0 = 0; y0 < sprite.height; y0 += 4) {
        const dx = Math.round((noise(y0 + Math.floor(time / 50)) - .5) * 8);
        ctx.drawImage(sprite, 0, y0, sprite.width, 4, x + dx, y + y0, sprite.width, 4);
      }
    } else ctx.drawImage(sprite, x, y);
    if (time < a.flashUntil) { ctx.globalAlpha = .85; ctx.drawImage(silhouette(sprite), x, y); }
    ctx.globalAlpha = 1;
    if (a.kind === 'jelly' && !a.dyingAt) {
      // A loading spinner, because the server is always busy.
      for (let i = 0; i < 8; i++) {
        const ang = i * Math.PI / 4 + Math.floor(time / 90) * Math.PI / 4, lit = i === 0;
        this.p.rect(a.x + 30 + Math.cos(ang) * 6 - 1, y + 4 + Math.sin(ang) * 6, 2, 2, lit ? '#fbf6ea' : i < 3 ? '#c79be6' : '#6d5590');
      }
    }
  }

  private drawHeroExtras() {
    const {p, time, ctx} = this;
    if (this.stance === 'crest' && !this.hero.hidden) {
      // 波峰: a crest of spray rising off the hero.
      for (let i = 0; i < 14; i++) {
        const k = (time / 500 + noise(i)) % 1, x = this.hero.x - 22 + noise(i * 3) * 44, y = GROUND - 4 - k * 70;
        p.rect(x, y, 2, 3 - Math.floor(k * 2), k < .5 ? '#ffb46b' : '#ff7a5c');
      }
      p.ring(this.hero.x, GROUND, 24 + Math.sin(time / 120) * 2, 5, '#ff8a5c', .8);
    } else if (this.stance === 'trough' && !this.hero.hidden) {
      // 波谷: slow ripples spreading at her feet.
      for (let i = 0; i < 3; i++) {
        const k = (time / 1400 + i / 3) % 1;
        p.ring(this.hero.x, GROUND + 1, 10 + k * 26, 2 + k * 4, '#8ddde8', 1 - k);
      }
    }
    if (this.thinking) {
      const dt = time - this.thinking.at;
      if (dt > 620) this.thinking = null;
      else for (let i = 0; i < 3; i++) {
        const on = dt >= 60 + i * 120, x = this.hero.x - 16 + i * 9, y = GROUND - 88;
        p.rect(x, y, 6, 6, '#354f60'); p.rect(x + 1, y + 1, 4, 4, on ? '#e5f8e6' : '#577e8d'); if (on) p.rect(x + 2, y, 2, 1, '#fff9d4');
      }
    }
    if (this.basin) {
      const dt = time - this.basin.at;
      if (dt > 520) this.basin = null;
      else {
        const rise = ease(dt / 140) * 10, img = icon('ironBasin', 2);
        ctx.globalAlpha = dt > 400 ? 1 - (dt - 400) / 120 : 1;
        ctx.drawImage(img, Math.round(this.hero.x + 2), Math.round(GROUND - 60 - rise));
        if (dt > 120 && dt < 260) { p.ring(this.hero.x + 18, GROUND - 52 - rise, 22, 12, '#fff6d3', 1 - (dt - 120) / 140); p.star(this.hero.x + 8, GROUND - 64 - rise, 4, '#fffbe8'); }
        ctx.globalAlpha = 1;
      }
    }
    if (this.overhead) {
      const dt = time - this.overhead.at;
      if (dt > 700) this.overhead = null;
      else {
        ctx.globalAlpha = dt > 520 ? 1 - (dt - 520) / 180 : 1;
        ctx.drawImage(icon(this.overhead.name, 1), Math.round(this.hero.x - 8), Math.round(GROUND - 96 - ease(dt / 200) * 6));
        ctx.globalAlpha = 1;
      }
    }
  }

  private drawCutIn() {
    const c = this.cut!, t = this.time - c.at;
    if (t >= CUTIN_DURATION) { this.cut = null; c.resolve(); this.draw(); return; }
    const p = this.p, target = c.target;
    renderCutin(t, {
      p, whale: this.whale, damage: c.damage, title: c.title,
      background: f => beach(p, f),
      target: (f, hit) => {
        if (!target) return;
        const art = enemyArt(target.kind);
        const sprite = renderEnemy(target.kind, f, hit ? 'hurt' : 'idle');
        let shake = 0;
        if (t >= 1840 && t < 1980) shake = 3;
        const q = (t - 1980) / 1000;
        if (q > 0 && q < .7) shake = Math.sin(q * 32) * 7 * Math.exp(-q * 5);
        p.ellipse(289, 177, Math.round(art.w / 2.4), 4, '#aba781');
        this.ctx.drawImage(sprite, Math.round(289 + shake - sprite.width / 2), Math.round(176 - art.hover - sprite.height));
        if (hit) { this.ctx.globalAlpha = .7; this.ctx.drawImage(silhouette(sprite), Math.round(289 + shake - sprite.width / 2), Math.round(176 - art.hover - sprite.height)); this.ctx.globalAlpha = 1; }
      },
      character: f => {
        const m = cutinMotion(f);
        p.ellipse(m.x, 177, 17, 3, '#a3a684');
        this.drawFrame(this.close$, cutinPose(f), m.x, m.y, false);
      },
    });
  }
}
