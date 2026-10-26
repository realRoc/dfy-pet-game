import {CARDS, canUpgrade, KEYWORDS, upgradeOf} from '../content/cards';
import {ENEMIES} from '../content/enemies';
import {EVENT_BY_ID} from '../content/events';
import {RELICS} from '../content/relics';
import type {Combat} from '../core/combat';
import {COLS, FLOORS, mapEdges, type RoomType} from '../core/map';
import {BOSS_NODE, Run} from '../core/run';
import type {Card, EnemyUnit, GameEvent, Intent, Stance, StatusId} from '../core/types';
import {icon, iconUrl} from '../render/icons';
import {noise, painter} from '../render/pixel';
import {GROUND, Scene, type Actor} from '../render/scene';
import {cardElement, keywordTips} from './cards';
import {play as sfx, sound} from './sound';

const S = 3; // CSS pixels per canvas pixel; the stage is 1152×648 before fitting the window
const STAGE_W = 1152, STAGE_H = 648;
const STATUS: Record<StatusId, {name: string; char: string; tip: string; good: boolean; hidden?: boolean; flag?: boolean}> = {
  strength: {name: '力量', char: '力', tip: '每段攻击伤害 +{n}。', good: true},
  weak: {name: '虚弱', char: '弱', tip: '造成的攻击伤害 -25%，还剩 {n} 回合。', good: false},
  vulnerable: {name: '易伤', char: '伤', tip: '受到的攻击伤害 +50%，还剩 {n} 回合。', good: false},
  extraDraw: {name: '白饭管够', char: '饭', tip: '每回合开始时多抽 {n} 张牌。', good: true},
  strengthPerTurn: {name: '尾鳍模式', char: '尾', tip: '每回合开始时获得 {n} 点力量。', good: true},
  think: {name: '思考', char: '思', tip: '已思考 {n} 秒。', good: true, hidden: true},
  thinkPerTurn: {name: '开启深度思考', char: '思', tip: '每回合开始时思考 {n} 秒。', good: true},
  fullSize: {name: '满血版', char: '满', tip: '思考完毕给的巨鲸破浪是升级版，并且本回合 0 费。', good: true, flag: true},
  keepBlock: {name: '饭盆不离身', char: '盆', tip: '格挡不会在回合开始时清空。', good: true, flag: true},
  blockPerTurn: {name: '先养着吧', char: '养', tip: '回合结束时获得 {n} 点格挡。', good: true},
  guard: {name: '护食', char: '护', tip: '这一轮每被攻击一次，反击 {n} 点伤害。', good: true},
  crestDraw: {name: '傲娇', char: '娇', tip: '每次进入波峰，抽 {n} 张牌。', good: true},
  switchBlock: {name: '不对，容我再想想', char: '想', tip: '每次切换状态，获得 {n} 点格挡。', good: true},
  troughBlock: {name: '聪明但懒', char: '懒', tip: '回合结束时若在波谷，获得 {n} 点格挡。', good: true},
  drawNext: {name: '下周见', char: '周', tip: '下回合多抽 {n} 张牌。', good: true},
};
const STANCE: Record<Stance, {name: string; short: string; tip: string}> = {
  none: {name: '海平面', short: '', tip: ''},
  crest: {name: '波峰', short: '伤害 ×2', tip: `<p><b>波峰</b></p><p>${KEYWORDS.波峰}</p><p class='flavor'>敌人打算攻击时记得先离开波峰。</p>`},
  trough: {name: '波谷', short: '离开 +2 算力', tip: `<p><b>波谷</b></p><p>${KEYWORDS.波谷}</p>`},
};
export const ROOM: Record<RoomType, {name: string; tip: string}> = {
  monster: {name: '普通战斗', tip: '打一场，赢了拿 Token 和一张牌。'},
  elite: {name: '精英', tip: '更难的战斗，赢了额外拿一件遗物。'},
  event: {name: '问号', tip: '多半是事件，也可能是战斗、商店或宝箱。每次没遇到战斗，下次遇到的几率就更高。'},
  shop: {name: '商店', tip: '用 Token 买牌、买遗物、删牌。'},
  rest: {name: '打盹点', tip: '睡一觉回血，或者想一想升级一张牌。'},
  chest: {name: '宝箱', tip: '一件遗物和一些 Token。'},
  bug: {name: 'Bug 房', tip: '修 bug、利用 bug，或者当没看见。'},
  boss: {name: '关底 Boss', tip: '黑鲸 · 更强的Agent。'},
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
  think: number;
  thinkLimit: number;
  stance: Stance;
}

const MAP_COL = 26, MAP_ROW = 22, MAP_TOP = 34, MAP_W = 16 + COLS * MAP_COL, MAP_H = MAP_TOP + FLOORS * MAP_ROW + 8, MAP_S = 3;

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

  get combat(): Combat { return this.run.combat!; }
  private get fighting() { return !!this.run?.combat && this.run.stage === 'combat' && !!this.view; }

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
    this.enterStage();
  }

  /** Shows whatever the run is waiting on. */
  private enterStage() {
    const run = this.run;
    if (run.stage !== 'combat') this.clearBattle();
    switch (run.stage) {
      case 'map': return this.mapScreen();
      case 'combat': return this.startCombat();
      case 'reward': return this.rewardScreen();
      case 'event': return this.eventScreen();
      case 'shop': return this.shopScreen();
      case 'rest': return this.restScreen();
      case 'chest': return this.chestScreen();
      case 'bug': return this.bugScreen();
      case 'cleared': return this.endScreen(true);
      case 'dead': return this.endScreen(false);
    }
  }

  /** Back to whatever was showing under a deck or map peek. */
  private restoreScreen() { if (this.run.stage === 'combat') this.closeOverlay(); else this.enterStage(); }

  /** Empty beach with the hero standing on it, behind the room screens. */
  private clearBattle() {
    this.scene.setEnemies([]);
    this.view = null!;
    this.selected = null; this.choosing = null;
    this.layer('prompt').hidden = true;
    for (const id of ['units', 'hand', 'bottom']) this.layer(id).replaceChildren();
    this.renderTop();
  }

  private startCombat() {
    const c = this.combat;
    this.scene.setEnemies(c.enemies);
    this.view = {
      units: Object.fromEntries([c.player, ...c.enemies].map(u => [u.id, {hp: u.hp, maxHp: u.maxHp, block: 0, status: {}, alive: true}])),
      hand: [], energy: 0, drawCount: c.piles.draw.length, discardCount: 0, exhaustCount: 0, attacks: 0, think: 0, thinkLimit: c.thinkLimit, stance: 'none',
    };
    this.selected = null; this.choosing = null;
    this.closeOverlay();
    this.buildUnits();
    this.renderAll();
    const enc = this.run.encounter!;
    this.banner(enc.name, enc.boss ? 'boss' : enc.elite ? 'elite' : '');
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
      this.enterStage();
    }, won ? 900 : 1200);
  }

  // ── input ────────────────────────────────────────────────────────────────

  private bindInput() {
    addEventListener('keydown', e => {
      if (!this.fighting || this.layer('overlay').childElementCount) return;
      if (e.key === 'e' || e.key === 'E') this.endTurn();
      else if (e.key === 'Escape') { this.selected = null; this.renderHand(); this.renderUnits(); }
      else if (/^[0-9]$/.test(e.key)) {
        const card = this.view.hand[(Number(e.key) + 9) % 10];
        if (card) this.cardClicked(card.uid);
      }
    });
    addEventListener('pointermove', e => this.dragMove(e));
    addEventListener('pointerup', e => this.dragEnd(e));
    this.stage.addEventListener('contextmenu', e => { e.preventDefault(); if (!this.fighting) return; this.selected = null; this.renderHand(); this.renderUnits(); });
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
    if (this.busy || this.choosing || !this.fighting || this.combat.result) return;
    this.selected = null;
    void this.playBatch(this.combat.endTurn());
  }

  private dragStart(e: PointerEvent, uid: number, card: HTMLElement) {
    if (this.busy || e.button !== 0 || !this.fighting) return;
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
    if (!this.fighting) return;
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
      // A new run or room replaced this fight while it was animating.
      if (this.view !== v) {
        if (!this.view) { this.busy = false; this.stage.classList.remove('busy'); }
        return;
      }
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
            this.layer('tip').hidden = true;
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
          if (e.reason === 'burned') { v.drawCount--; this.toast('p', `手牌满了，${CARDS[e.card.id].name} 进了弃牌堆`); }
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
          if (e.status === 'think') { v.think = e.value; this.renderBubbles(); if (e.amount > 0) this.toast('p', `思考 +${e.amount} 秒`, 'think'); }
          else if (e.amount > 0) { this.toast(e.unit, `${STATUS[e.status].name} +${e.amount}`, STATUS[e.status].good ? 'good' : 'bad'); await this.scene.wait(120); }
          this.renderUnits();
          break;
        }
        case 'heal': v.units[e.unit].hp = e.hp; this.scene.healFx(e.amount); this.renderUnits(); break;
        case 'hpLoss':
          v.units[e.unit].hp = e.hp;
          sfx('hurt');
          this.toast('p', `${e.why}：失去 ${e.amount} 点生命`, 'bad');
          await this.scene.heroHurt(e.amount, 0);
          this.renderUnits(); this.renderTop();
          break;
        case 'stance': {
          v.stance = e.stance;
          this.scene.stance = e.stance;
          const s = STANCE[e.stance];
          this.toast('p', e.stance === 'none' ? '回到海平面' : `进入${s.name}：${s.short}`, e.stance === 'crest' ? 'bad' : 'good');
          if (e.from === 'trough') this.toast('energy', '离开波谷 +2 算力', 'good');
          this.scene.flash(e.stance === 'crest' ? '#ff8a5c' : '#8ddde8', 120);
          sfx(e.stance === 'crest' ? 'swing' : 'think', 2);
          this.renderBubbles();
          await this.scene.wait(240);
          break;
        }
        case 'thinkDone':
          await finishCard();
          [0, 1, 2].forEach(k => setTimeout(() => sfx('think', k + 1), k * 110 / this.scene.speed));
          this.banner(`思考完毕（用时 ${v.thinkLimit} 秒）`, 'think');
          await this.scene.ponder();
          break;
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
        case 'counters': v.attacks = e.attacks; v.think = e.think; v.thinkLimit = e.thinkLimit; this.renderBubbles(); break;
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
    const run = this.run, top = this.layer('top');
    if (!run) { top.replaceChildren(); return; }
    const p = this.fighting ? this.view.units.p : {hp: run.hp, maxHp: run.maxHp};
    const floor = run.pos ? (run.pos.floor >= FLOORS ? '关底' : `第 ${run.pos.floor + 1} 层`) : '塔下';
    const room = run.stage === 'combat' ? run.encounter!.name : run.room ? ROOM[run.question ?? run.room].name : '选一条路';
    top.innerHTML = `
      <div class="who"><b>大肥鱼</b><span class="hp">♥ ${p.hp}/${p.maxHp}</span><span class="gold" data-tip="<p><b>Token</b></p><p>这座塔里的货币：打怪、开宝箱、事件都能拿到，在商店花掉。和桌宠互不相通。</p>"><img src="${iconUrl('token')}">${run.gold}</span></div>
      <div class="where">${floor} · ${room}</div>
      <div class="relics"></div>
      <div class="tools">
        <button data-act="map">地图</button>
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
    top.querySelector('[data-act=map]')!.addEventListener('click', () => { if (run.stage !== 'map') this.mapScreen(true); });
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
        const e = this.combat.enemies.find(x => x.id === id)!, note = ENEMIES[e.kind].note;
        hit.dataset.tip = `<p><b>${e.name}</b></p>${note ? `<p class="flavor">${note}</p>` : ''}`;
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
        .filter(([k, n]) => n && !STATUS[k].hidden)
        .map(([k, n]) => `<span class="st ${STATUS[k].good ? 'good' : 'bad'}" data-tip="<p><b>${STATUS[k].name}</b></p><p>${STATUS[k].tip.replace('{n}', String(n))}</p>">${STATUS[k].char}${STATUS[k].flag ? '' : `<sub>${n}</sub>`}</span>`).join('');
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
      case 'buff': ico = 'buff'; label = ''; tip = `获得 ${intent.n} 点${STATUS[intent.status].name}${intent.block ? `和 ${intent.block} 点格挡` : ''}`; break;
      case 'debuff': ico = 'debuff'; label = ''; tip = `给你施加 ${intent.n} 层${STATUS[intent.status].name}`; break;
      case 'charge': ico = 'charge'; label = '…'; tip = '在憋大招。下回合多半是一记重击，别待在波峰里'; break;
      case 'stuff': ico = 'stuff'; label = `+${intent.n}`; tip = `把 ${intent.n} 张「${CARDS[intent.id].name}」塞进你的弃牌堆，并获得 ${intent.block} 点格挡`; break;
      case 'idle': ico = 'idle'; label = ''; tip = '它在发呆。'; break;
    }
    const extra = intent.kind === 'attackDefend' ? `<img src="${iconUrl('defend')}">` : intent.kind === 'attackDebuff' ? `<img src="${iconUrl('debuff')}">` : '';
    return `<div data-tip="<p><b>${e.name}打算：${move}</b></p><p>${tip}。</p>"><img src="${iconUrl(ico)}">${extra}<b>${label}</b></div>`;
  }

  /** Over the hero's head: stance, 已思考 N 秒 and 连击, each with a tooltip. */
  private renderBubbles() {
    const v = this.view, b = this.layer('units').querySelector('.bubbles');
    if (!b || !v) return;
    const s = STANCE[v.stance];
    const thinkTip = `<p><b>深度思考</b></p><p>${KEYWORDS.思考}</p><p class='flavor'>还差 ${v.thinkLimit - v.think} 秒。</p>`;
    b.innerHTML = (v.stance !== 'none' ? `<span class="stance ${v.stance}" data-tip="${s.tip}">${s.name}<small>${s.short}</small></span>` : '')
      + (v.think ? `<span class="think" data-tip="${thinkTip}">已思考 ${v.think}/${v.thinkLimit} 秒<i style="width:${(v.think / v.thinkLimit) * 100}%"></i></span>` : '')
      + (v.attacks ? `<span class="combo" data-tip="<p><b>连击</b></p><p>本回合打出的攻击牌数，鲸落按它加伤害。</p>">连击 ×${v.attacks}</span>` : '');
  }

  private renderHand(entering?: number) {
    const hand = this.layer('hand'), v = this.view, c = this.combat;
    const old = new Map([...hand.children].map(n => [Number((n as HTMLElement).dataset.uid), n as HTMLElement]));
    hand.replaceChildren();
    const n = v.hand.length, gap = Math.min(116, n > 1 ? 640 / (n - 1) : 0), mid = (n - 1) / 2;
    v.hand.forEach((card, i) => {
      const def = CARDS[card.id];
      const node = cardElement(this.scene, card.id, c.cardDamage(def), c.costOf(card));
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
    if (!v) return;
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
    const b = unit === 'energy' ? {x: 24, y: 150, w: 0, h: 0} : this.scene.box(unit), t = el('div', 'toast ' + tone, text);
    // Toasts that land on the same unit stack upwards instead of overprinting.
    const stacked = [...this.layer('fx').querySelectorAll<HTMLElement>('.toast')].filter(x => x.dataset.unit === unit).length;
    t.dataset.unit = unit;
    t.style.left = `${(b.x + b.w / 2) * S}px`;
    t.style.top = `${(b.y - 4) * S - stacked * 24}px`;
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
      <h1>大肥鱼爬塔</h1><p class="sub">海边的塔 · 15 层 · 顶上住着更强的 Agent</p>
      <ul>
        <li>每回合 <b>3 点算力</b>、抽 <b>5 张牌</b>；敌人头顶显示下回合要做什么。</li>
        <li>地图上选路往上爬：战斗、精英、问号、商店、打盹点、宝箱、Bug 房，第 15 层之上是关底 Boss。</li>
        <li><b class="tail">鲸尾</b> 连击 · <b class="basin">铁盆</b> 叠格挡砸人 · <b class="wave">波峰波谷</b> 来回切状态 ·
          <b class="think">深度思考</b> 攒「已思考 N 秒」，满 10 秒巨鲸破浪进手牌。</li>
        <li>初始遗物 <b>剩饭</b>：每场战斗结束恢复 6 点生命。货币是 <b>Token</b>，和桌宠不通用。</li>
      </ul>
      <p class="keys">拖牌到敌人身上，或点牌再点敌人 · 数字键选牌 · E 结束回合 · 右键取消 · 鼠标停在任何东西上都有说明</p>
      <button class="go">开饭！</button>`);
    p.querySelector('.go')!.addEventListener('click', () => { sfx('coin'); this.newRun(); });
  }

  // ── map ──────────────────────────────────────────────────────────────────

  private nodeXY(floor: number, col: number): [number, number] {
    if (floor >= FLOORS) return [Math.round(MAP_W / 2), 16];
    const seed = this.run.map.seed % 997;
    return [Math.round(16 + col * MAP_COL + (noise(seed + floor * 13 + col) - .5) * 8),
      Math.round(MAP_TOP + (FLOORS - 1 - floor) * MAP_ROW + 10 + (noise(seed * 3 + floor * 7 + col * 5) - .5) * 6)];
  }

  /** The climb, drawn as pixel art; lit nodes are where you can go next. */
  private mapScreen(peek = false) {
    const run = this.run, choices = peek ? [] : run.choices();
    const floorText = run.pos ? (run.pos.floor >= FLOORS ? '关底' : `第 ${run.pos.floor + 1} 层`) : '塔下';
    const legend = (['monster', 'elite', 'event', 'shop', 'rest', 'chest', 'bug', 'boss'] as RoomType[])
      .map(t => `<li data-tip="<p><b>${ROOM[t].name}</b></p><p>${ROOM[t].tip}</p>"><img src="${iconUrl('room-' + t)}">${ROOM[t].name}</li>`).join('');
    const p = this.overlay('map', `
      <div class="map-side">
        <h2>爬塔地图</h2>
        <p class="sub">现在在 ${floorText}${peek ? '' : '，点一个亮着的房间往上走'}。</p>
        <ul class="legend">${legend}<li><img class="here" src="${this.scene.whaleIcon.toDataURL()}">你在这里</li></ul>
        <p class="keys">第 1 层普通战斗 · 第 9 层宝箱 · 第 15 层打盹点 · 然后是关底 Boss</p>
        ${peek ? '<button class="go">关闭</button>' : ''}
      </div>
      <div class="map-scroll"><div class="map-wrap"><canvas width="${MAP_W}" height="${MAP_H}"></canvas></div></div>`);
    const canvas = p.querySelector('canvas')!, wrap = p.querySelector<HTMLElement>('.map-wrap')!;
    this.drawMap(canvas, choices.map(n => n.col));
    const nodes = [...run.map.floors.flat().filter(n => n !== null), BOSS_NODE];
    for (const n of nodes) {
      const [x, y] = this.nodeXY(n.floor, n.col), next = choices.some(c => c.floor === n.floor && c.col === n.col);
      const b = el('button', 'node' + (next ? ' next' : '') + (n.type === 'boss' ? ' boss' : ''));
      const size = n.type === 'boss' ? 20 : 12;
      b.style.left = `${(x - size / 2) * MAP_S}px`; b.style.top = `${(y - size / 2) * MAP_S}px`;
      b.style.width = b.style.height = `${size * MAP_S}px`;
      const where = n.floor >= FLOORS ? '关底' : `第 ${n.floor + 1} 层`;
      b.dataset.tip = `<p><b>${where} · ${ROOM[n.type].name}</b></p><p>${ROOM[n.type].tip}</p>${next ? '<p class=\'flavor\'>点一下走过去。</p>' : ''}`;
      if (next) b.addEventListener('click', () => this.travel(n.col));
      wrap.append(b);
    }
    p.querySelector('.go')?.addEventListener('click', () => this.restoreScreen());
    // Keep the current floor in view; the climb starts at the bottom.
    const scroll = p.querySelector<HTMLElement>('.map-scroll')!;
    const focus = run.pos ? this.nodeXY(Math.min(run.pos.floor + 1, FLOORS), run.pos.col)[1] : MAP_H;
    scroll.scrollTop = focus * MAP_S - scroll.clientHeight / 2;
  }

  private drawMap(canvas: HTMLCanvasElement, next: number[]) {
    const run = this.run, ctx = canvas.getContext('2d')!, p = painter(ctx);
    ctx.imageSmoothingEnabled = false;
    p.rect(0, 0, MAP_W, MAP_H, '#16303a');
    for (let i = 0; i < 70; i++) p.rect(noise(i + 3) * MAP_W, noise(i + 40) * MAP_H, 3 + noise(i) * 8, 1, i % 3 ? '#1d3b46' : '#24485a');
    const visited = new Set(run.path.map(s => `${s.floor},${s.col}`));
    const onPath = (f: number, a: number, b: number) => visited.has(`${f},${a}`) && visited.has(`${f + 1},${b}`)
      && run.path.findIndex(s => s.floor === f && s.col === a) + 1 === run.path.findIndex(s => s.floor === f + 1 && s.col === b);
    const dots = (from: [number, number], to: [number, number], color: string, step: number) => {
      const len = Math.hypot(to[0] - from[0], to[1] - from[1]);
      for (let d = 7; d < len - 7; d += step) p.rect(from[0] + (to[0] - from[0]) * d / len - 1, from[1] + (to[1] - from[1]) * d / len - 1, 2, 2, color);
    };
    for (const [f, a, b] of mapEdges(run.map)) dots(this.nodeXY(f, a), this.nodeXY(f + 1, b), onPath(f, a, b) ? '#f2c75c' : '#5d7f86', onPath(f, a, b) ? 2 : 4);
    for (const n of run.map.floors[FLOORS - 1]) if (n) {
      const lit = run.path.at(-1)?.floor === FLOORS && run.path.at(-2)?.col === n.col;
      dots(this.nodeXY(n.floor, n.col), this.nodeXY(FLOORS, 0), lit ? '#f2c75c' : '#5d7f86', lit ? 2 : 4);
    }
    const here = run.pos;
    const draw = (floor: number, col: number, type: RoomType) => {
      const [x, y] = this.nodeXY(floor, col), img = icon('room-' + type, type === 'boss' ? 2 : 1);
      const isNext = floor === FLOORS ? here?.floor === FLOORS - 1 && next.length > 0 : (here ? here.floor === floor - 1 : floor === 0) && next.includes(col);
      const past = here ? floor <= here.floor : false;
      if (visited.has(`${floor},${col}`)) { p.ellipse(x, y, 9, 8, '#f2c75c'); p.ellipse(x, y, 8, 7, '#2a4a52'); }
      else if (isNext) { p.ellipse(x, y, 9, 8, '#fff3c0'); p.ellipse(x, y, 8, 7, '#355e68'); }
      ctx.globalAlpha = past && !visited.has(`${floor},${col}`) ? .35 : 1;
      ctx.drawImage(img, Math.round(x - img.width / 2), Math.round(y - img.height / 2));
      ctx.globalAlpha = 1;
    };
    run.map.floors.forEach(row => row.forEach(n => n && draw(n.floor, n.col, n.type)));
    draw(FLOORS, 0, 'boss');
    if (here) {
      // A small whale beside the current room (right of it in the first column).
      const [x, y] = this.nodeXY(here.floor, here.col), w = this.scene.whaleIcon, mw = 16, mh = Math.round(16 * w.height / w.width);
      ctx.drawImage(w, here.col === 0 ? x + 10 : x - 10 - mw, Math.round(y - mh / 2), mw, mh);
    }
  }

  private travel(col: number) {
    const run = this.run;
    run.move(col);
    sfx('coin');
    const q = run.question;
    this.closeOverlay();
    this.enterStage();
    if (q && run.stage !== 'event') this.banner(`问号房：${ROOM[q].name}！`, q === 'monster' ? 'enemy' : '');
  }

  // ── rooms ────────────────────────────────────────────────────────────────

  /** Shows the deck and resolves with the picked index, or calls `back` on cancel. */
  private pickFromDeck(title: string, mode: 'upgrade' | 'remove' | 'copy', back: () => void, done: (index: number) => void) {
    const run = this.run;
    const p = this.overlay('pile picker', `<h2>${title}</h2><p class="sub">${mode === 'upgrade' ? '显示的是升级以后的样子。' : '点一张牌。'}</p><div class="grid"></div><button class="skip">返回</button>`);
    const grid = p.querySelector('.grid')!;
    run.deck.forEach((id, i) => {
      if (mode === 'upgrade' && !canUpgrade(id)) return;
      const shown = mode === 'upgrade' ? upgradeOf(id) : id;
      const node = cardElement(this.scene, shown, this.baseDamage(shown));
      node.dataset.tip = keywordTips(CARDS[shown]);
      node.addEventListener('click', () => { sfx('coin'); done(i); });
      grid.append(node);
    });
    if (!grid.childElementCount) grid.append(el('p', 'empty', '没有能选的牌。'));
    p.querySelector('.skip')!.addEventListener('click', back);
  }

  private continueButton(p: HTMLElement) {
    p.querySelector('.continue')!.addEventListener('click', () => { this.run.leave(); this.enterStage(); });
  }

  private eventScreen() {
    const run = this.run, ev = EVENT_BY_ID[run.event!.id], result = run.event!.result;
    const p = this.overlay('room event', `
      <h2><img src="${iconUrl('room-event')}">${ev.title}</h2>
      <p class="story">${ev.text}</p>
      ${result ? `<p class="result">${result}</p><button class="go continue">继续</button>` : '<div class="options"></div>'}`);
    if (result) { this.renderTop(); return this.continueButton(p); }
    const box = p.querySelector('.options')!;
    ev.options.forEach((opt, i) => {
      const why = opt.can?.(run) ?? null;
      const b = el('button', 'option', `<b>${opt.label}</b><span>${opt.text}${why ? `（${why}）` : ''}</span>`);
      b.disabled = !!why;
      b.addEventListener('click', () => {
        if (opt.pick) {
          this.pickFromDeck(opt.pick === 'upgrade' ? '选一张牌升级' : '选一张牌删掉', opt.pick, () => this.eventScreen(), idx => { run.chooseEvent(i, idx); this.enterStage(); });
          return;
        }
        sfx('coin');
        run.chooseEvent(i);
        this.enterStage();
      });
      box.append(b);
    });
  }

  private shopScreen() {
    const run = this.run, shop = run.shop!;
    const price = (n: number) => `<span class="price${run.gold < n ? ' poor' : ''}"><img src="${iconUrl('token')}">${n}</span>`;
    const p = this.overlay('room shop', `
      <h2><img src="${iconUrl('room-shop')}">错峰小卖部<small>深夜 API 半价，这里也总有一张牌打五折</small></h2>
      <div class="shelf cards"></div>
      <div class="shelf relics"></div>
      <div class="actions"><button class="skip remove"${shop.removed || run.gold < shop.removePrice ? ' disabled' : ''}>删一张牌 ${price(shop.removePrice)}${shop.removed ? '（今天用过了）' : ''}</button>
      <button class="go leave">离开</button></div>`);
    const buy = (kind: 'cards' | 'relics', i: number) => {
      try { run.buy(kind, i); sfx('coin'); } catch (e) { this.flashMessage(p, (e as Error).message); return; }
      this.shopScreen();
    };
    const cards = p.querySelector('.shelf.cards')!;
    shop.cards.forEach((item, i) => {
      const box = el('div', 'item' + (item.sold ? ' sold' : ''));
      const node = cardElement(this.scene, item.id, this.baseDamage(item.id));
      node.dataset.tip = keywordTips(CARDS[item.id]);
      box.append(node);
      box.insertAdjacentHTML('beforeend', item.sold ? '<span class="price">已售出</span>' : price(item.price) + (item.sale ? '<i class="sale">错峰五折</i>' : ''));
      if (!item.sold) node.addEventListener('click', () => buy('cards', i));
      cards.append(box);
    });
    const relics = p.querySelector('.shelf.relics')!;
    shop.relics.forEach((item, i) => {
      const r = RELICS[item.id];
      const b = el('button', 'relic-choice' + (item.sold ? ' sold' : ''), `<img src="${iconUrl(item.id)}"><b>${r.name}</b><span>${r.text}</span>${item.sold ? '<span class="price">已售出</span>' : price(item.price)}`);
      b.disabled = item.sold;
      b.addEventListener('click', () => buy('relics', i));
      relics.append(b);
    });
    if (!shop.relics.length) relics.append(el('p', 'sub', '遗物卖光了。'));
    p.querySelector('.remove')!.addEventListener('click', () =>
      this.pickFromDeck(`删一张牌（${shop.removePrice} Token）`, 'remove', () => this.shopScreen(), i => { run.buyRemoval(i); this.shopScreen(); }));
    p.querySelector('.leave')!.addEventListener('click', () => { run.leave(); this.enterStage(); });
    this.renderTop();
  }

  private flashMessage(p: HTMLElement, text: string) {
    const m = el('p', 'warn', text);
    p.append(m);
    setTimeout(() => m.remove(), 1500);
  }

  private restScreen() {
    const run = this.run, heal = Math.min(Math.ceil(run.maxHp * .3), run.maxHp - run.hp);
    const p = this.overlay('room rest', `
      <h2><img src="${iconUrl('room-rest')}">打盹点</h2>
      <p class="story">海风很舒服，篝火噼啪响。只来得及做一件事。</p>
      <div class="options big">
        <button class="option sleep"><b>睡一觉（DeepSleep）</b><span>回复 30% 生命（+${heal}）</span></button>
        <button class="option think"><b>想一想</b><span>升级一张牌</span></button>
      </div>`);
    p.querySelector('.sleep')!.addEventListener('click', () => {
      const n = run.rest('sleep');
      this.scene.healFx(n); sfx('coin');
      this.enterStage();
    });
    p.querySelector('.think')!.addEventListener('click', () =>
      this.pickFromDeck('想一想：升级一张牌', 'upgrade', () => this.restScreen(), i => { run.rest('think', i); this.enterStage(); }));
  }

  private chestScreen() {
    const run = this.run, chest = run.chest!, r = chest.relic ? RELICS[chest.relic] : null;
    const p = this.overlay('room chest', `
      <h2><img src="${iconUrl('room-chest')}">宝箱</h2>
      <p class="story">箱子里塞满了饭团，底下还压着点东西。</p>
      ${r ? `<div class="relic-choice owned"><img src="${iconUrl(chest.relic!)}"><b>${r.name}</b><span>${r.text}</span><i>${r.flavor}</i></div>` : '<p class="sub">遗物已经拿全了。</p>'}
      <p class="gain"><img src="${iconUrl('token')}"> +${chest.gold} Token</p>
      <button class="go continue">继续</button>`);
    this.renderTop();
    this.continueButton(p);
  }

  private bugScreen() {
    const run = this.run;
    const p = this.overlay('room bug', `
      <h2><img src="${iconUrl('room-bug')}">Bug 房</h2>
      <p class="story">墙上的告示变成了乱码：<span class="garbled">「涔辩爜铏�　鐑�鐑�鐑�」</span>。角落里有个东西在闪。</p>
      <div class="options">
        <button class="option fix"><b>修 bug</b><span>和「涔辩爜铏�」（乱码虫）打一架。赢了删 1 张牌，再选 1 张稀有牌。</span></button>
        <button class="option exploit"><b>利用 bug</b><span>复制牌组里的 1 张牌。代价：牌组塞进 1 张诅咒「锟斤拷」。</span></button>
        <button class="option ignore"><b>当没看见</b><span>直接离开。</span></button>
      </div>`);
    p.querySelector('.fix')!.addEventListener('click', () => { run.bug('fix'); this.enterStage(); });
    p.querySelector('.exploit')!.addEventListener('click', () =>
      this.pickFromDeck('利用 bug：复制哪一张？', 'copy', () => this.bugScreen(), i => { run.bug('exploit', i); sfx('think', 3); this.enterStage(); }));
    p.querySelector('.ignore')!.addEventListener('click', () => { run.bug('ignore'); this.enterStage(); });
  }

  private rewardScreen() {
    const run = this.run, reward = run.reward!;
    const relic = reward.relic ? RELICS[reward.relic] : null;
    let card: string | null = null;
    const p = this.overlay('reward', `
      <h2>战斗胜利</h2>
      ${run.healed ? `<p class="heal"><img src="${iconUrl('leftovers')}"> 剩饭：恢复了 ${run.healed} 点生命</p>` : ''}
      <p class="gain"><img src="${iconUrl('token')}"> +${reward.gold} Token</p>
      ${relic ? `<h3>精英掉落了遗物</h3><div class="choices relics"><div class="relic-choice owned"><img src="${iconUrl(reward.relic!)}"><b>${relic.name}</b><span>${relic.text}</span><i>${relic.flavor}</i></div></div>` : ''}
      <h3>${reward.removeCard ? 'Bug 修好了：选一张稀有牌，然后删掉一张牌' : '选一张牌加入牌组'}</h3><div class="choices cards"></div>
      <div class="actions"><button class="skip">跳过卡牌</button><button class="go">继续前进</button></div>`);
    const cards = p.querySelector('.cards')!;
    for (const id of reward.cards) {
      const node = cardElement(this.scene, id, this.baseDamage(id));
      node.dataset.tip = keywordTips(CARDS[id]);
      node.addEventListener('click', () => { card = card === id ? null : id; cards.querySelectorAll('.card').forEach(n => n.classList.toggle('selected', n === node && card === id)); sync(); });
      cards.append(node);
    }
    const go = p.querySelector<HTMLButtonElement>('.go')!, skip = p.querySelector<HTMLButtonElement>('.skip')!;
    const sync = () => { go.disabled = !card; };
    sync();
    const finish = (pick: string | null) => {
      if (!reward.removeCard) { run.takeReward(pick); this.enterStage(); return; }
      this.pickFromDeck('修好的 Bug 顺手删掉一张牌', 'remove', () => this.rewardScreen(), i => { run.takeReward(pick, i); this.enterStage(); });
    };
    go.addEventListener('click', () => finish(card));
    skip.addEventListener('click', () => finish(null));
    this.renderTop();
  }

  private baseDamage(id: string) {
    const op = CARDS[id].ops.find(o => o.op === 'damage');
    return op && op.op === 'damage' && !op.fromBlock ? op.n : null;
  }

  private endScreen(won: boolean) {
    const run = this.run, where = run.pos ? (run.pos.floor >= FLOORS ? '关底' : `第 ${run.pos.floor + 1} 层`) : '';
    const p = this.overlay(won ? 'end win' : 'end lose', won
      ? `<h2>爬到塔顶了！</h2><p>更强的 Agent 被打回了后台。大肥鱼剩 ${run.hp}/${run.maxHp} 点生命，回家吃白饭去了。</p><p class="sub">牌组 ${run.deck.length} 张 · ${run.gold} Token · 遗物 ${run.relics.map(id => RELICS[id].name).join('、')}</p><button class="go">再爬一次</button>`
      : `<h2>大肥鱼饿晕了…</h2><p>倒在了${where}「${run.encounter?.name ?? ''}」。</p><p class="sub">「你骂我也没用，因为我是吃白饭的蓝色大肥鱼。」</p><button class="go">再来一局</button>`);
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
    p.querySelector('.go')!.addEventListener('click', () => this.restoreScreen());
  }

  // ── debugging hooks used by tests in the browser ─────────────────────────

  debug = {
    give: (id: string) => {
      const c = this.combat, card = {uid: 9000 + c.piles.hand.length + Math.floor(Math.random() * 1000), id};
      c.piles.hand.push(card); this.view.hand.push(card); this.renderHand(card.uid);
    },
    energy: (n: number) => { this.combat.energy = n; this.view.energy = n; this.renderBottom(); },
    weaken: () => { for (const e of this.combat.living()) { e.hp = 1; this.view.units[e.id].hp = 1; } this.renderUnits(); },
    think: (n: number) => { this.combat.think(n); void this.playBatch((this.combat as unknown as {flush(): GameEvent[]}).flush()); },
    gold: (n: number) => { this.run.gold = n; this.renderTop(); },
    /** Jumps straight into a room of the given type on the current floor. */
    room: (type: RoomType) => {
      const r = this.run as unknown as {enter(t: RoomType): void; stage: string};
      this.closeOverlay(); r.stage = 'map'; this.run.room = type; r.enter(type); this.enterStage();
    },
  };
}
