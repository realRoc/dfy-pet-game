import {CARDS} from '../content/cards';
import {GAUNTLET} from '../content/enemies';
import {RELICS} from '../content/relics';
import type {Combat} from '../core/combat';
import {Run} from '../core/run';
import type {Card, EnemyUnit, GameEvent, Intent, StatusId} from '../core/types';
import {iconUrl} from '../render/icons';
import {GROUND, Scene, type Actor} from '../render/scene';
import {cardElement, keywordTips} from './cards';
import {play as sfx, sound} from './sound';

const S = 3; // CSS pixels per canvas pixel; the stage is 1152×648 before fitting the window
const STAGE_W = 1152, STAGE_H = 648;
const STATUS: Record<StatusId, {name: string; char: string; tip: string; good: boolean}> = {
  strength: {name: '力量', char: '力', tip: '每段攻击伤害 +{n}。', good: true},
  weak: {name: '虚弱', char: '弱', tip: '造成的攻击伤害 -25%，还剩 {n} 回合。', good: false},
  vulnerable: {name: '易伤', char: '伤', tip: '受到的攻击伤害 +50%，还剩 {n} 回合。', good: false},
  extraDraw: {name: '白饭管够', char: '饭', tip: '每回合开始时多抽 {n} 张牌。', good: true},
};

interface UnitView { hp: number; maxHp: number; block: number; status: Partial<Record<StatusId, number>>; alive: boolean; intent?: Intent; move?: string }
interface View {
  units: Record<string, UnitView>;
  hand: Card[];
  energy: number;
  drawCount: number;
  discardCount: number;
  exhaustCount: number;
  attacks: number;
  exhausted: number;
}

type Anim = 'tail' | 'spin' | 'think' | 'bowl' | 'ponder' | 'smug' | 'cutin';

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls = '', html = '') => {
  const e = document.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; return e;
};

/**
 * Owns the DOM around the canvas. Player input goes to the core, and the
 * events that come back are replayed one beat at a time into `view`, which is
 * what the HUD shows while animations run.
 */
export class App {
  readonly scene: Scene;
  run!: Run;
  view!: View;
  busy = false;
  selected: number | null = null;
  choosing: {count: number; picked: number[]} | null = null;
  private stage = document.querySelector<HTMLDivElement>('#stage')!;
  private layer = (id: string) => this.stage.querySelector<HTMLDivElement>('#' + id)!;
  private drag: {uid: number; x0: number; y0: number; moved: boolean; el: HTMLElement} | null = null;
  private scale = 1;

  constructor() {
    this.scene = new Scene(this.stage.querySelector('canvas')!);
    addEventListener('resize', () => this.fit());
    this.fit();
    this.bindInput();
  }

  get combat(): Combat { return this.run.combat; }

  async boot() {
    await this.scene.load();
    // ?seed=123 skips the title and replays the same run.
    const seed = new URLSearchParams(location.search).get('seed');
    if (seed) this.newRun(Number(seed)); else this.titleScreen();
  }

  private fit() {
    this.scale = Math.min(innerWidth / STAGE_W, innerHeight / STAGE_H);
    this.stage.style.transform = `translate(${(innerWidth - STAGE_W * this.scale) / 2}px, ${(innerHeight - STAGE_H * this.scale) / 2}px) scale(${this.scale})`;
  }

  /** Converts a pointer event into stage pixels. */
  private local(e: PointerEvent | MouseEvent) {
    const r = this.stage.getBoundingClientRect();
    return {x: (e.clientX - r.left) / this.scale, y: (e.clientY - r.top) / this.scale};
  }

  // ── run flow ─────────────────────────────────────────────────────────────

  newRun(seed = Math.floor(Math.random() * 2 ** 31)) {
    this.run = new Run(seed);
    this.startCombat();
  }

  private startCombat() {
    const c = this.combat;
    this.scene.setEnemies(c.enemies);
    this.view = {
      units: Object.fromEntries([c.player, ...c.enemies].map(u => [u.id, {hp: u.hp, maxHp: u.maxHp, block: 0, status: {}, alive: true}])),
      hand: [], energy: 0, drawCount: c.piles.draw.length, discardCount: 0, exhaustCount: 0, attacks: 0, exhausted: 0,
    };
    this.selected = null; this.choosing = null;
    this.closeOverlay();
    this.buildUnits();
    this.renderAll();
    this.banner(this.run.encounter.name, this.run.encounter.elite ? 'elite' : '');
    void this.playBatch(c.start());
  }

  private afterCombat() {
    const run = this.run, combat = this.combat, won = combat.result === 'victory';
    run.finishCombat();
    if (won && run.healed) {
      this.scene.healFx(run.healed);
      this.view.units.p.hp = run.hp;
      this.toast('p', `剩饭：恢复 ${run.healed} 点生命`, 'good');
      this.renderTop();
    }
    setTimeout(() => {
      // 重开 is clickable during this pause; a new run must not get the old one's screen.
      if (this.run !== run || run.combat !== combat) return;
      if (run.stage === 'reward') this.rewardScreen();
      else if (run.stage === 'cleared') this.endScreen(true);
      else this.endScreen(false);
    }, won ? 900 : 1200);
  }

  // ── input ────────────────────────────────────────────────────────────────

  private bindInput() {
    addEventListener('keydown', e => {
      if (!this.run || this.layer('overlay').childElementCount) return;
      if (e.key === 'e' || e.key === 'E') this.endTurn();
      else if (e.key === 'Escape') { this.selected = null; this.renderHand(); this.renderUnits(); }
      else if (/^[0-9]$/.test(e.key)) {
        const card = this.view.hand[(Number(e.key) + 9) % 10];
        if (card) this.cardClicked(card.uid);
      }
    });
    addEventListener('pointermove', e => this.dragMove(e));
    addEventListener('pointerup', e => this.dragEnd(e));
    this.stage.addEventListener('contextmenu', e => { e.preventDefault(); this.selected = null; this.renderHand(); this.renderUnits(); });
    this.stage.addEventListener('click', () => { if (this.scene.inCutIn) this.scene.skipCutIn(); });
    this.bindTips();
  }

  /** One floating tooltip for every element with a data-tip. */
  private bindTips() {
    const tip = this.layer('tip');
    this.stage.addEventListener('pointerover', e => {
      const host = (e.target as HTMLElement).closest<HTMLElement>('[data-tip]');
      if (!host || !host.dataset.tip || this.drag?.moved) { tip.hidden = true; return; }
      tip.innerHTML = host.dataset.tip;
      tip.hidden = false;
      const r = host.getBoundingClientRect(), s = this.stage.getBoundingClientRect();
      const x = (r.right - s.left) / this.scale + 10, y = (r.top - s.top) / this.scale;
      const card = host.classList.contains('inhand');
      tip.style.left = `${Math.min(x, STAGE_W - 250)}px`;
      tip.style.top = `${card ? Math.max(8, y - 120) : Math.min(y, STAGE_H - 120)}px`;
    });
    this.stage.addEventListener('pointerout', e => {
      if (!(e.relatedTarget as HTMLElement | null)?.closest?.('[data-tip]')) tip.hidden = true;
    });
  }

  private cardClicked(uid: number) {
    if (this.busy) return;
    if (this.choosing) {
      const pick = this.choosing.picked, i = pick.indexOf(uid);
      if (i >= 0) pick.splice(i, 1); else pick.push(uid);
      if (pick.length >= this.choosing.count) {
        const chosen = [...pick];
        this.choosing = null; this.layer('prompt').hidden = true;
        void this.playBatch(this.combat.choose(chosen));
      } else this.renderHand();
      return;
    }
    if (this.selected === uid) { this.selected = null; this.renderHand(); this.renderUnits(); return; }
    this.tryPlay(uid);
  }

  private tryPlay(uid: number, target?: string) {
    if (this.busy || this.choosing) return;
    const c = this.combat, why = c.blocked(uid);
    if (why) {
      this.toast('p', why, 'bad');
      this.layer('hand').querySelector(`[data-uid="${uid}"]`)?.animate([{translate: '0 0'}, {translate: '-6px 0'}, {translate: '6px 0'}, {translate: '0 0'}], 180);
      return;
    }
    const def = CARDS[c.piles.hand.find(x => x.uid === uid)!.id];
    if (def.target === 'enemy' && !target) {
      const living = c.living();
      if (living.length === 1) target = living[0].id;
      else { this.selected = uid; this.renderHand(); this.renderUnits(); return; }
    }
    this.selected = null;
    void this.playBatch(c.play(uid, target));
  }

  private endTurn() {
    if (this.busy || this.choosing || !this.run || this.combat.result) return;
    this.selected = null;
    void this.playBatch(this.combat.endTurn());
  }

  private dragStart(e: PointerEvent, uid: number, card: HTMLElement) {
    if (this.busy || e.button !== 0) return;
    const p = this.local(e);
    this.drag = {uid, x0: p.x, y0: p.y, moved: false, el: card};
  }

  private dragMove(e: PointerEvent) {
    const d = this.drag;
    if (!d) return;
    const p = this.local(e);
    if (!d.moved && Math.hypot(p.x - d.x0, p.y - d.y0) < 10) return;
    if (this.choosing) return;
    d.moved = true;
    d.el.classList.add('dragging');
    d.el.style.transform = `translate(${p.x - 66}px, ${p.y - 90}px) scale(1.1)`;
    const over = this.enemyAt(p.x, p.y);
    this.layer('units').querySelectorAll('.unit').forEach(u => u.classList.toggle('aimed', (u as HTMLElement).dataset.id === over));
  }

  private dragEnd(e: PointerEvent) {
    const d = this.drag;
    if (!d) return;
    this.drag = null;
    if (!d.moved) { this.cardClicked(d.uid); return; }
    const p = this.local(e);
    d.el.classList.remove('dragging'); d.el.style.transform = '';
    const def = CARDS[this.view.hand.find(c => c.uid === d.uid)?.id ?? 'busy'];
    const over = this.enemyAt(p.x, p.y);
    if (def.target === 'enemy') { if (over) this.tryPlay(d.uid, over); else this.renderUnits(); }
    else if (p.y < 440) this.tryPlay(d.uid);
  }

  private enemyAt(x: number, y: number): string | undefined {
    return this.combat.living().find(en => {
      const b = this.scene.box(en.id);
      return x >= (b.x - 8) * S && x <= (b.x + b.w + 8) * S && y >= (b.y - 20) * S && y <= (GROUND + 12) * S;
    })?.id;
  }

  // ── event replay ─────────────────────────────────────────────────────────

  private async playBatch(events: GameEvent[]) {
    this.busy = true;
    this.stage.classList.add('busy');
    let card: {anim: Anim; done: boolean} | null = null;
    let enemy: {actor: Actor; home: number; hits: number} | null = null;
    const finishCard = async () => {
      if (card && !card.done && (card.anim === 'tail' || card.anim === 'spin')) await this.scene.recover('tail');
      if (card && !card.done && card.anim === 'think') await this.scene.recover('think');
      card = null;
    };
    const finishEnemy = async () => { if (enemy) { await this.scene.enemyRecover(enemy.actor, enemy.home); enemy = null; } };
    const v = this.view;

    for (let i = 0; i < events.length; i++) {
      const e = events[i];
      switch (e.t) {
        case 'turnStart':
          await finishEnemy();
          this.banner(`第 ${e.turn} 回合`, 'turn');
          await this.scene.wait(260);
          break;
        case 'energy': v.energy = e.energy; this.renderBottom(true); break;
        case 'draw':
          v.hand.push(e.card); v.drawCount = e.drawCount; v.discardCount = e.discardCount;
          this.renderHand(e.card.uid); this.renderBottom(); sfx('draw');
          await this.scene.wait(70);
          break;
        case 'shuffle':
          v.drawCount = e.drawCount; v.discardCount = 0; this.renderBottom();
          this.toast('p', '弃牌堆洗回抽牌堆');
          await this.scene.wait(160);
          break;
        case 'play': {
          await finishCard();
          v.energy = e.energy;
          this.flyCard(e.card.uid, 'play');
          v.hand = v.hand.filter(c => c.uid !== e.card.uid);
          this.renderHand(); this.renderBottom();
          const def = CARDS[e.card.id], anim = this.animFor(e.card.id);
          card = {anim, done: false};
          const target = e.target ? this.scene.actor(e.target) : this.scene.actors.find(a => !a.dyingAt) ?? null;
          if (anim === 'cutin') {
            const first = events.slice(i + 1).find(x => x.t === 'damage' && x.src === 'p');
            this.stage.classList.add('cutin');
            sfx('think', 0); setTimeout(() => sfx('think', 1), 150); setTimeout(() => sfx('think', 2), 300);
            setTimeout(() => sfx('heavy'), 1840 / this.scene.speed);
            await this.scene.cutIn(first && first.t === 'damage' ? first.amount + first.blocked : 0, target, def.name);
            this.stage.classList.remove('cutin');
            card.done = true;
          } else if (anim === 'tail' && target) { sfx('swing'); await this.scene.tailWindup(target); }
          else if (anim === 'spin') { sfx('swing'); await this.scene.spinWindup(); }
          else if (anim === 'think' && target) { sfx('think', 2); await this.scene.thinkWindup(target); }
          else if (anim === 'bowl') { sfx('block'); await this.scene.raiseBowl(); }
          else if (anim === 'ponder') { [0, 1, 2].forEach(k => setTimeout(() => sfx('think', k), k * 120 / this.scene.speed)); await this.scene.ponder(); }
          else await this.scene.smug(def.id === 'endlessRice' ? 'leftovers' : undefined);
          break;
        }
        case 'cardTo': {
          if (e.pile === 'hand') { v.hand.push(e.card); this.renderHand(e.card.uid); this.toast('p', `${CARDS[e.card.id].name} 进入手牌`); break; }
          const inHand = v.hand.some(c => c.uid === e.card.uid);
          if (inHand) { this.flyCard(e.card.uid, e.pile === 'exhaust' ? 'exhaust' : 'discard'); v.hand = v.hand.filter(c => c.uid !== e.card.uid); this.renderHand(); }
          if (e.pile === 'discard') v.discardCount++;
          if (e.pile === 'draw') v.drawCount++;
          if (e.pile === 'exhaust') v.exhaustCount++;
          this.renderBottom();
          if (e.reason === 'created' && e.pile === 'discard') this.pulse('discard');
          if (inHand) await this.scene.wait(e.pile === 'exhaust' ? 120 : 45);
          break;
        }
        case 'damage': {
          const u = v.units[e.dst];
          if (e.src === 'p') {
            const a = this.scene.actor(e.dst);
            if (card?.anim === 'tail' && e.hit > 0 && events[i - 1]?.t === 'damage') await this.scene.tailRestrike();
            u.hp = e.hp; u.block = e.block;
            if (!card?.done || card.anim !== 'cutin') { sfx(e.amount >= 15 ? 'heavy' : 'hit'); this.scene.flash('#fffbe8', 50); }
            await this.scene.hitActor(a, e.amount, e.blocked);
            this.renderUnits();
            await this.scene.wait(card?.anim === 'cutin' ? 30 : 70);
          } else {
            if (enemy && e.hit > 0) await this.scene.wait(140);
            u.hp = e.hp; u.block = e.block;
            sfx(e.amount ? 'hurt' : 'block');
            await this.scene.heroHurt(e.amount, e.blocked);
            this.renderUnits(); this.renderTop();
          }
          break;
        }
        case 'block':
          v.units[e.unit].block = e.block;
          this.scene.blockFx(e.unit, e.amount);
          if (e.unit !== 'p') sfx('block');
          this.renderUnits();
          await this.scene.wait(80);
          break;
        case 'blockClear': v.units[e.unit].block = 0; this.renderUnits(); break;
        case 'status': {
          const u = v.units[e.unit];
          u.status[e.status] = e.value;
          if (!e.value) delete u.status[e.status];
          if (e.amount > 0) { this.toast(e.unit, `${STATUS[e.status].name} +${e.amount}`, STATUS[e.status].good ? 'good' : 'bad'); await this.scene.wait(120); }
          this.renderUnits();
          break;
        }
        case 'heal': v.units[e.unit].hp = e.hp; this.scene.healFx(e.amount); this.renderUnits(); break;
        case 'death':
          v.units[e.unit].alive = false;
          this.scene.kill(this.scene.actor(e.unit));
          this.renderUnits();
          await this.scene.wait(160);
          break;
        case 'enemyTurn':
          await finishCard();
          this.banner('敌人回合', 'enemy');
          await this.scene.wait(420);
          break;
        case 'enemyMove': {
          await finishEnemy();
          const a = this.scene.actor(e.unit);
          this.toast(e.unit, e.move);
          if ('dmg' in e.intent) { enemy = {actor: a, home: a.x, hits: 0}; await this.scene.enemyWindup(a); }
          else await this.scene.enemyAct(a);
          break;
        }
        case 'intent': v.units[e.unit].intent = e.intent; v.units[e.unit].move = e.move; this.renderUnits(); break;
        case 'counters': v.attacks = e.attacks; v.exhausted = e.exhausted; this.renderBubbles(); break;
        case 'relic': {
          const r = RELICS[e.id];
          this.toast('p', `${r.name}${e.note ? '：' + e.note : ''}`, 'good');
          this.pulse('relic-' + e.id);
          sfx('coin');
          await this.scene.wait(220);
          break;
        }
        case 'choose':
          await finishCard();
          this.choosing = {count: e.count, picked: []};
          this.layer('prompt').textContent = e.prompt;
          this.layer('prompt').hidden = false;
          break;
        case 'victory': await finishCard(); this.scene.victory(); this.banner('战斗胜利', 'win'); break;
        case 'defeat': await finishEnemy(); this.scene.heroDown(); this.banner('大肥鱼饿晕了…', 'lose'); break;
      }
    }
    await finishCard();
    await finishEnemy();
    this.busy = false;
    this.stage.classList.remove('busy');
    this.renderAll();
    if (this.combat.result) this.afterCombat();
  }

  private animFor(id: string): Anim {
    const def = CARDS[id];
    if (def.cutIn) return 'cutin';
    if (def.type === 'attack') return def.school === 'think' ? 'think' : def.target === 'all' ? 'spin' : 'tail';
    if (def.ops.some(o => o.op === 'block')) return def.id === 'deepSleep' ? 'ponder' : 'bowl';
    if (def.ops.some(o => o.op === 'draw' || o.op === 'redraw' || o.op === 'exhaustNonAttacks')) return 'ponder';
    return 'smug';
  }

  // ── rendering ────────────────────────────────────────────────────────────

  private renderAll() { this.renderTop(); this.renderUnits(); this.renderHand(); this.renderBottom(); this.renderBubbles(); }

  private renderTop() {
    const run = this.run, top = this.layer('top'), p = this.view.units.p;
    top.innerHTML = `
      <div class="who"><b>大肥鱼</b><span class="hp">♥ ${p.hp}/${p.maxHp}</span></div>
      <div class="where">第 ${run.floor + 1}/${GAUNTLET.length} 战 · ${run.encounter.name}</div>
      <div class="relics"></div>
      <div class="tools">
        <button data-act="deck">牌组 ${run.deck.length}</button>
        <button data-act="speed">${this.scene.speed}×</button>
        <button data-act="sound">${sound.enabled ? '音效 开' : '音效 关'}</button>
        <button data-act="restart">重开</button>
      </div>`;
    const relics = top.querySelector('.relics')!;
    for (const id of run.relics) {
      const r = RELICS[id], img = el('img', 'relic');
      img.src = iconUrl(id); img.id = 'relic-' + id;
      img.dataset.tip = `<p><b>${r.name}</b></p><p>${r.text}</p><p class="flavor">${r.flavor}</p>`;
      relics.append(img);
    }
    top.querySelector('[data-act=deck]')!.addEventListener('click', () => this.pileScreen('牌组', run.deck.map((id, uid) => ({uid, id}))));
    top.querySelector('[data-act=speed]')!.addEventListener('click', () => { this.scene.speed = this.scene.speed === 1 ? 2 : 1; this.renderTop(); });
    top.querySelector('[data-act=sound]')!.addEventListener('click', () => { sound.enabled = !sound.enabled; this.renderTop(); });
    top.querySelector('[data-act=restart]')!.addEventListener('click', () => { if (!this.busy) this.newRun(); });
  }

  private buildUnits() {
    const box = this.layer('units');
    box.replaceChildren();
    for (const id of ['p', ...this.combat.enemies.map(e => e.id)]) {
      const b = this.scene.box(id), u = el('div', 'unit' + (id === 'p' ? ' hero' : ' enemy'));
      u.dataset.id = id;
      const cx = (b.x + b.w / 2) * S, barW = Math.max(108, b.w * S * .8);
      u.style.left = `${cx}px`;
      u.innerHTML = `
        ${id === 'p' ? '' : `<div class="intent" style="top:${(b.y - 16) * S}px"></div>`}
        <div class="hit" style="left:${-b.w * S / 2 - 12}px;top:${(b.y - 6) * S}px;width:${b.w * S + 24}px;height:${(GROUND - b.y + 8) * S}px"></div>
        <div class="bar" style="top:${(GROUND + 5) * S}px;width:${barW}px;left:${-barW / 2}px"><i></i><span></span><em class="block"></em></div>
        <div class="statuses" style="top:${(GROUND + 5) * S - 30}px;left:${-barW / 2}px"></div>`;
      if (id !== 'p') {
        const hit = u.querySelector<HTMLElement>('.hit')!;
        hit.dataset.tip = `<p><b>${this.combat.unit(id).name}</b></p>`;
        hit.addEventListener('click', () => { if (this.selected !== null) this.tryPlay(this.selected, id); });
      }
      box.append(u);
    }
    const bubbles = el('div', 'bubbles');
    bubbles.style.left = `${(this.scene.box('p').x + 30) * S}px`;
    bubbles.style.top = `${(GROUND - 108) * S}px`;
    box.append(bubbles);
  }

  private renderUnits() {
    const v = this.view;
    this.layer('units').querySelectorAll<HTMLElement>('.unit').forEach(u => {
      const id = u.dataset.id!, s = v.units[id];
      u.classList.toggle('dead', !s.alive);
      u.classList.toggle('targetable', this.selected !== null && s.alive && id !== 'p');
      u.classList.remove('aimed');
      const bar = u.querySelector<HTMLElement>('.bar')!;
      bar.querySelector('i')!.style.width = `${(s.hp / s.maxHp) * 100}%`;
      bar.querySelector('span')!.textContent = `${s.hp}/${s.maxHp}`;
      bar.classList.toggle('shielded', s.block > 0);
      const blk = bar.querySelector<HTMLElement>('.block')!;
      blk.textContent = s.block ? String(s.block) : '';
      blk.hidden = !s.block;
      u.querySelector('.statuses')!.innerHTML = (Object.entries(s.status) as [StatusId, number][])
        .filter(([, n]) => n)
        .map(([k, n]) => `<span class="st ${STATUS[k].good ? 'good' : 'bad'}" data-tip="<p><b>${STATUS[k].name}</b></p><p>${STATUS[k].tip.replace('{n}', String(n))}</p>">${STATUS[k].char}<sub>${n}</sub></span>`).join('');
      const intent = u.querySelector<HTMLElement>('.intent');
      if (intent) {
        const live = this.combat.enemies.find(e => e.id === id)!;
        intent.hidden = !s.alive || !s.intent || this.combat.result !== null;
        if (s.intent) intent.innerHTML = this.intentHtml(live, s.intent, s.move ?? '');
      }
    });
  }

  private intentHtml(e: EnemyUnit, intent: Intent, move: string): string {
    const dmg = 'dmg' in intent ? this.combat.attackValue(e, this.combat.player, intent.dmg) : 0;
    const times = 'times' in intent && intent.times > 1 ? `×${intent.times}` : '';
    let ico = 'attack', label = `${dmg}${times}`, tip = `造成 ${dmg} 点伤害${times ? ` ${intent.kind === 'attack' ? intent.times : ''} 次` : ''}`;
    switch (intent.kind) {
      case 'attackDefend': tip += `，并获得 ${intent.block} 点格挡`; break;
      case 'attackDebuff': tip += `，并施加 ${intent.n} 层${STATUS[intent.status].name}`; break;
      case 'defend': ico = 'defend'; label = ''; tip = `获得 ${intent.block} 点格挡`; break;
      case 'buff': ico = 'buff'; label = ''; tip = `获得 ${intent.n} 点${STATUS[intent.status].name}`; break;
      case 'stuff': ico = 'stuff'; label = `+${intent.n}`; tip = `把 ${intent.n} 张「${CARDS[intent.id].name}」塞进你的弃牌堆，并获得 ${intent.block} 点格挡`; break;
      case 'idle': ico = 'idle'; label = ''; tip = '它在发呆。'; break;
    }
    const extra = intent.kind === 'attackDefend' ? `<img src="${iconUrl('defend')}">` : intent.kind === 'attackDebuff' ? `<img src="${iconUrl('debuff')}">` : '';
    return `<div data-tip="<p><b>${e.name}打算：${move}</b></p><p>${tip}。</p>"><img src="${iconUrl(ico)}">${extra}<b>${label}</b></div>`;
  }

  private renderBubbles() {
    const v = this.view, b = this.layer('units').querySelector('.bubbles');
    if (!b) return;
    b.innerHTML = (v.attacks ? `<span class="combo">连击 ×${v.attacks}</span>` : '') + (v.exhausted ? `<span class="think">已思考 ${v.exhausted} 秒</span>` : '');
  }

  private renderHand(entering?: number) {
    const hand = this.layer('hand'), v = this.view, c = this.combat;
    const old = new Map([...hand.children].map(n => [Number((n as HTMLElement).dataset.uid), n as HTMLElement]));
    hand.replaceChildren();
    const n = v.hand.length, gap = Math.min(116, n > 1 ? 640 / (n - 1) : 0), mid = (n - 1) / 2;
    v.hand.forEach((card, i) => {
      const def = CARDS[card.id];
      const node = cardElement(this.scene, card.id, c.cardDamage(def));
      node.dataset.uid = String(card.uid);
      node.classList.add('inhand');
      const off = i - mid;
      node.style.setProperty('--x', `${576 - 66 + off * gap}px`);
      node.style.setProperty('--y', `${482 + Math.abs(off) ** 1.6 * 4}px`);
      node.style.setProperty('--r', `${off * 2.4}deg`);
      node.style.zIndex = String(10 + i);
      const playable = !c.blocked(card.uid) || this.busy;
      node.classList.toggle('unplayable', !playable && !this.choosing);
      node.classList.toggle('selected', this.selected === card.uid);
      node.classList.toggle('picked', !!this.choosing?.picked.includes(card.uid));
      if (card.uid === entering && !old.has(card.uid)) node.classList.add('enter');
      node.dataset.tip = keywordTips(def);
      node.addEventListener('pointerdown', e => this.dragStart(e, card.uid, node));
      hand.append(node);
    });
    hand.classList.toggle('choosing', !!this.choosing);
  }

  private renderBottom(pulseEnergy = false) {
    const v = this.view, b = this.layer('bottom');
    b.innerHTML = `
      <div class="energy${pulseEnergy ? ' pop' : ''}" data-tip="<p><b>算力</b></p><p>打牌要花的点数，每回合恢复到 3 点。</p>"><b>${v.energy}</b><span>/3</span><small>算力</small></div>
      <button class="pile draw" data-tip="<p>还没抽到的牌。点开查看（顺序打乱显示）。</p>">抽牌堆<b>${v.drawCount}</b></button>
      <button class="pile discard" id="discard" data-tip="<p>打出或弃掉的牌，抽牌堆空了会洗回去。</p>">弃牌堆<b>${v.discardCount}</b></button>
      <button class="pile exhaust" data-tip="<p>被消耗的牌，本场战斗不会再出现。</p>">消耗<b>${v.exhaustCount}</b></button>
      <button class="end"${this.busy || this.choosing || this.combat.result ? ' disabled' : ''}>结束回合<kbd>E</kbd></button>`;
    const c = this.combat;
    b.querySelector('.draw')!.addEventListener('click', () => this.pileScreen('抽牌堆', [...c.piles.draw].sort((x, y) => x.id.localeCompare(y.id))));
    b.querySelector('.discard')!.addEventListener('click', () => this.pileScreen('弃牌堆', c.piles.discard));
    b.querySelector('.exhaust')!.addEventListener('click', () => this.pileScreen('消耗', c.piles.exhaust));
    b.querySelector('.end')!.addEventListener('click', () => this.endTurn());
  }

  // ── little DOM effects ───────────────────────────────────────────────────

  private flyCard(uid: number, to: 'play' | 'discard' | 'exhaust') {
    const node = this.layer('hand').querySelector<HTMLElement>(`[data-uid="${uid}"]`);
    if (!node) return;
    const r = node.getBoundingClientRect(), s = this.stage.getBoundingClientRect();
    const ghost = node.cloneNode(true) as HTMLElement;
    // cloneNode copies a canvas element but not its pixels.
    ghost.querySelector('canvas')?.getContext('2d')!.drawImage(node.querySelector('canvas')!, 0, 0);
    ghost.className = node.className + ' ghost';
    ghost.style.transform = `translate(${(r.left - s.left) / this.scale}px, ${(r.top - s.top) / this.scale}px)`;
    this.layer('fx').append(ghost);
    const from = ghost.style.transform;
    const frames: Keyframe[] = to === 'play'
      ? [{transform: from, opacity: 1}, {transform: 'translate(510px, 250px) scale(1.15)', opacity: 1, offset: .35}, {transform: 'translate(510px, 230px) scale(1.15)', opacity: 0}]
      : to === 'exhaust'
        ? [{transform: from, opacity: 1, filter: 'none'}, {transform: from + ' scale(1.05)', opacity: 0, filter: 'brightness(2) hue-rotate(200deg) blur(2px)'}]
        : [{transform: from, opacity: 1}, {transform: 'translate(1040px, 560px) scale(.3) rotate(20deg)', opacity: .2}];
    ghost.animate(frames, {duration: (to === 'play' ? 520 : 300) / this.scene.speed, easing: 'ease-out'}).finished.then(() => ghost.remove());
  }

  private toast(unit: string, text: string, tone = '') {
    const b = this.scene.box(unit), t = el('div', 'toast ' + tone, text);
    t.style.left = `${(b.x + b.w / 2) * S}px`;
    t.style.top = `${(b.y - 4) * S}px`;
    this.layer('fx').append(t);
    t.animate([{opacity: 0, translate: '-50% 10px'}, {opacity: 1, translate: '-50% 0', offset: .15}, {opacity: 1, translate: '-50% -18px', offset: .8}, {opacity: 0, translate: '-50% -26px'}], {duration: 1300 / this.scene.speed}).finished.then(() => t.remove());
  }

  private banner(text: string, tone: string) {
    const b = this.layer('banner');
    b.className = tone; b.textContent = text;
    b.getAnimations().forEach(a => a.cancel());
    b.animate([{opacity: 0, transform: 'scaleY(.2)'}, {opacity: 1, transform: 'scaleY(1)', offset: .15}, {opacity: 1, offset: .75}, {opacity: 0}], {duration: 1100 / this.scene.speed, fill: 'forwards'});
  }

  private pulse(id: string) {
    this.stage.querySelector('#' + id)?.animate([{transform: 'scale(1)'}, {transform: 'scale(1.35)'}, {transform: 'scale(1)'}], 300);
  }

  // ── screens ──────────────────────────────────────────────────────────────

  private overlay(cls: string, html: string): HTMLDivElement {
    const o = this.layer('overlay');
    o.replaceChildren();
    const panel = el('div', 'panel ' + cls, html);
    o.append(panel); o.hidden = false;
    return panel;
  }

  private closeOverlay() { const o = this.layer('overlay'); o.replaceChildren(); o.hidden = true; }

  private titleScreen() {
    const p = this.overlay('title', `
      <h1>大肥鱼爬塔</h1><p class="sub">战斗原型 · 海边三连战</p>
      <ul>
        <li>每回合 <b>3 点算力</b>、抽 <b>5 张牌</b>；敌人头顶显示下回合要做什么。</li>
        <li><b class="tail">鲸尾</b>：物理连击，本回合打得越多，「鲸落」越疼。</li>
        <li><b class="think">深度思考</b>：抽牌过牌，本回合消耗的牌越多，「思考完毕」越疼。</li>
        <li>初始遗物 <b>剩饭</b>：每场战斗结束恢复 6 点生命。</li>
      </ul>
      <p class="keys">拖牌到敌人身上，或点牌再点敌人 · 数字键选牌 · E 结束回合 · 右键取消</p>
      <button class="go">开饭！</button>`);
    p.querySelector('.go')!.addEventListener('click', () => { sfx('coin'); this.newRun(); });
  }

  private rewardScreen() {
    const run = this.run;
    let card: string | null = null, relic: string | null = null;
    const p = this.overlay('reward', `
      <h2>战斗胜利</h2>
      ${run.healed ? `<p class="heal"><img src="${iconUrl('leftovers')}"> 剩饭：恢复了 ${run.healed} 点生命</p>` : ''}
      <h3>选一张牌加入牌组</h3><div class="choices cards"></div>
      ${run.relicChoices.length ? '<h3>前面就是精英了，先挑一件遗物</h3><div class="choices relics"></div>' : ''}
      <div class="actions"><button class="skip">跳过卡牌</button><button class="go">继续前进</button></div>`);
    const cards = p.querySelector('.cards')!;
    for (const id of run.cardChoices) {
      const node = cardElement(this.scene, id, CARDS[id].ops.find(o => o.op === 'damage') ? this.baseDamage(id) : null);
      node.dataset.tip = keywordTips(CARDS[id]);
      node.addEventListener('click', () => { card = card === id ? null : id; cards.querySelectorAll('.card').forEach(n => n.classList.toggle('selected', n === node && card === id)); sync(); });
      cards.append(node);
    }
    const relics = p.querySelector('.relics');
    for (const id of run.relicChoices) {
      const r = RELICS[id], node = el('button', 'relic-choice', `<img src="${iconUrl(id)}"><b>${r.name}</b><span>${r.text}</span><i>${r.flavor}</i>`);
      node.addEventListener('click', () => { relic = id; relics!.querySelectorAll('.relic-choice').forEach(n => n.classList.toggle('selected', n === node)); sync(); });
      relics!.append(node);
    }
    const go = p.querySelector<HTMLButtonElement>('.go')!, skip = p.querySelector<HTMLButtonElement>('.skip')!;
    const sync = () => {
      go.disabled = !card || (run.relicChoices.length > 0 && !relic);
      skip.disabled = run.relicChoices.length > 0 && !relic;
    };
    sync();
    go.addEventListener('click', () => { run.takeReward(card, relic); this.startCombat(); });
    skip.addEventListener('click', () => { run.takeReward(null, relic); this.startCombat(); });
  }

  private baseDamage(id: string) {
    const op = CARDS[id].ops.find(o => o.op === 'damage');
    return op && op.op === 'damage' ? op.n : null;
  }

  private endScreen(won: boolean) {
    const run = this.run;
    const p = this.overlay(won ? 'end win' : 'end lose', won
      ? `<h2>原型通关！</h2><p>大肥鱼打赢了三场，剩 ${run.hp}/${run.maxHp} 点生命，回家吃白饭去了。</p><p class="sub">牌组 ${run.deck.length} 张 · 遗物 ${run.relics.map(id => RELICS[id].name).join('、')}</p><button class="go">再来一局</button>`
      : `<h2>大肥鱼饿晕了…</h2><p>倒在了第 ${run.floor + 1} 战「${run.encounter.name}」。</p><p class="sub">「你骂我也没用，因为我是吃白饭的蓝色大肥鱼。」</p><button class="go">再来一局</button>`);
    p.querySelector('.go')!.addEventListener('click', () => this.newRun());
  }

  private pileScreen(title: string, cards: Card[]) {
    if (this.busy && title !== '牌组') return;
    const p = this.overlay('pile', `<h2>${title}<small>${cards.length} 张</small></h2><div class="grid"></div><button class="go">关闭</button>`);
    const grid = p.querySelector('.grid')!;
    if (!cards.length) grid.append(el('p', 'empty', '空的。'));
    for (const c of cards) {
      const node = cardElement(this.scene, c.id, this.baseDamage(c.id));
      node.dataset.tip = keywordTips(CARDS[c.id]);
      grid.append(node);
    }
    p.querySelector('.go')!.addEventListener('click', () => { if (this.run?.stage === 'reward') this.rewardScreen(); else this.closeOverlay(); });
  }

  // ── debugging hooks used by tests in the browser ─────────────────────────

  debug = {
    give: (id: string) => {
      const c = this.combat, card = {uid: 9000 + c.piles.hand.length + Math.floor(Math.random() * 1000), id};
      c.piles.hand.push(card); this.view.hand.push(card); this.renderHand(card.uid);
    },
    energy: (n: number) => { this.combat.energy = n; this.view.energy = n; this.renderBottom(); },
    goto: (floor: number) => {
      const r = this.run as unknown as {floor: number; combat: Combat; newCombat(): Combat};
      r.floor = floor; r.combat = r.newCombat(); this.startCombat();
    },
    weaken: () => { for (const e of this.combat.living()) { e.hp = 1; this.view.units[e.id].hp = 1; } this.renderUnits(); },
  };
}

