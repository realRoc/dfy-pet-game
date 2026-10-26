import {CARDS, THINK_LIMIT} from '../content/cards';
import {ENEMIES} from '../content/enemies';
import {RELICS} from '../content/relics';
import {Rng} from './rng';
import type {Card, CardDef, EnemyUnit, GameEvent, Intent, Op, Pile, Player, Stance, StatusId, Unit} from './types';

export const ENERGY_PER_TURN = 3;
export const HAND_SIZE = 5;
export const MAX_HAND = 10;

export interface CombatSetup {
  deck: string[];
  hp: number;
  maxHp: number;
  relics: string[];
  enemies: string[];
  seed: number;
}

interface Pending { card: Card; def: CardDef; target?: string; rest: Op[]; count: number }

/**
 * One fight. Player actions resolve immediately and return the events they
 * produced; the renderer replays those events with timing. Nothing here
 * touches the DOM, so the same fight replays exactly from a seed.
 */
export class Combat {
  readonly rng: Rng;
  readonly player: Player;
  readonly enemies: EnemyUnit[];
  readonly piles: Record<Pile, Card[]> = {draw: [], hand: [], discard: [], exhaust: []};
  readonly relics: string[];
  energy = 0;
  turn = 0;
  attacksThisTurn = 0;
  exhaustedThisTurn = 0;
  /** 巨鲸破浪 played this fight; each one makes the next hit harder. */
  whales = 0;
  pending: Pending | null = null;
  result: 'victory' | 'defeat' | null = null;
  private enemyTurns = 0;
  private nextUid = 1;
  private events: GameEvent[] = [];
  private inPlayerTurn = false;

  constructor(setup: CombatSetup) {
    this.rng = new Rng(setup.seed);
    this.relics = setup.relics;
    this.player = {id: 'p', name: '大肥鱼', hp: setup.hp, maxHp: setup.maxHp, block: 0, status: {}, stance: 'none'};
    this.enemies = setup.enemies.map((kind, i) => {
      const def = ENEMIES[kind], hp = this.rng.int(def.hp[0], def.hp[1]);
      return {id: 'e' + i, kind, name: def.name, hp, maxHp: hp, block: 0, status: {}, intent: {kind: 'idle'}, moveName: '', history: [], alive: true};
    });
    this.piles.draw = this.rng.shuffle(setup.deck.map(id => this.makeCard(id)));
  }

  start(): GameEvent[] {
    for (const e of this.enemies) this.planIntent(e);
    this.startPlayerTurn(true);
    return this.flush();
  }

  // ── queries ──────────────────────────────────────────────────────────────

  unit(id: string): Unit { return id === 'p' ? this.player : this.enemies.find(e => e.id === id)!; }
  living(): EnemyUnit[] { return this.enemies.filter(e => e.alive); }

  /** Why a card can't be played right now, or null when it can. */
  blocked(uid: number): string | null {
    const card = this.piles.hand.find(c => c.uid === uid);
    if (!card) return '这张牌不在手里';
    if (this.result) return '战斗已结束';
    if (this.pending) return '先选完要消耗的牌';
    const def = CARDS[card.id];
    if (def.unplayable) return '这张牌无法打出';
    if (this.costOf(card) > this.energy) return '算力不够';
    return null;
  }

  costOf(card: Card): number { return card.cost ?? CARDS[card.id].cost; }

  get thinking(): number { return this.player.status.think ?? 0; }
  get thinkLimit(): number { return Math.max(1, THINK_LIMIT + this.relics.reduce((n, id) => n + (RELICS[id].thinkLimit ?? 0), 0)); }

  /** Per-hit damage of a card, including counters, strength, weak, stance and the target's vulnerable. */
  cardDamage(def: CardDef, targetId?: string): number | null {
    const op = def.ops.find(o => o.op === 'damage');
    if (!op || op.op !== 'damage') return null;
    // 铁盆头槌 hits with the block itself, so strength and stances don't touch it.
    if (op.fromBlock) return this.player.block;
    const bonus = op.inStance && op.inStance.stance === this.player.stance ? op.inStance.n : 0;
    const base = op.n + bonus + (op.perAttack ?? 0) * this.attacksThisTurn + (op.perThink ?? 0) * this.thinking + (op.perWhale ?? 0) * this.whales;
    return this.attackValue(this.player, targetId ? this.unit(targetId) : null, base);
  }

  intentDamage(e: EnemyUnit): number | null {
    const i = e.intent;
    return 'dmg' in i ? this.attackValue(e, this.player, i.dmg) : null;
  }

  attackValue(src: Unit, dst: Unit | null, base: number): number {
    let d = base + (src.status.strength ?? 0);
    if (src.status.weak) d *= .75;
    if (dst?.status.vulnerable) d *= 1.5;
    // 波峰 doubles both ways: what the player deals and what the player takes.
    if (src === this.player && this.player.stance === 'crest') d *= 2;
    if (dst === this.player && this.player.stance === 'crest') d *= 2;
    return Math.max(0, Math.floor(d));
  }

  // ── player actions ───────────────────────────────────────────────────────

  play(uid: number, target?: string): GameEvent[] {
    const reason = this.blocked(uid);
    if (reason) throw new Error(reason);
    const card = this.piles.hand.find(c => c.uid === uid)!, def = CARDS[card.id];
    if (def.target === 'enemy') {
      const t = target && this.enemies.find(e => e.id === target && e.alive);
      if (!t) throw new Error('需要选择一个敌人');
    }
    this.energy -= this.costOf(card);
    this.remove(card);
    this.emit({t: 'play', card, target, energy: this.energy});
    this.resolve(card, def, target, def.ops);
    return this.flush();
  }

  /** Answers an exhaustChoose prompt with the chosen hand cards. */
  choose(uids: number[]): GameEvent[] {
    const p = this.pending;
    if (!p) throw new Error('现在不需要选牌');
    const picked = this.piles.hand.filter(c => uids.includes(c.uid));
    if (picked.length !== Math.min(p.count, this.piles.hand.length)) throw new Error(`请选 ${p.count} 张牌`);
    this.pending = null;
    for (const c of picked) { this.remove(c); this.exhaust(c, 'exhaust'); }
    this.resolve(p.card, p.def, p.target, p.rest);
    return this.flush();
  }

  endTurn(): GameEvent[] {
    if (this.result || this.pending) throw new Error('现在不能结束回合');
    const p = this.player;
    for (const c of this.piles.hand) {
      const hurt = CARDS[c.id].endTurnHurt;
      if (hurt) { this.loseHp(hurt, CARDS[c.id].name); if (this.result) return this.flush(); }
    }
    if (p.status.blockPerTurn) this.gainBlock(p, p.status.blockPerTurn);
    if (p.status.troughBlock && p.stance === 'trough') this.gainBlock(p, p.status.troughBlock);
    for (const id of this.relics) RELICS[id].turnEnd?.(this);
    this.inPlayerTurn = false;
    for (const c of [...this.piles.hand]) {
      this.remove(c);
      delete c.cost;
      if (CARDS[c.id].ethereal) this.exhaust(c, 'ethereal');
      else this.moveTo(c, 'discard', 'discard');
    }
    this.tickDown(this.player);
    this.enemyPhase();
    if (!this.result) this.startPlayerTurn();
    return this.flush();
  }

  // ── helpers relics and ops share ─────────────────────────────────────────

  relicFlash(id: string, note?: string) { this.emit({t: 'relic', id, note}); }

  gainEnergy(n: number) { this.energy += n; this.emit({t: 'energy', energy: this.energy}); }

  gainBlock(u: Unit, n: number) {
    if (n <= 0) return;
    u.block += n;
    this.emit({t: 'block', unit: u.id, amount: n, block: u.block});
  }

  draw(n: number) {
    for (let i = 0; i < n; i++) {
      if (!this.piles.draw.length) {
        if (!this.piles.discard.length) return;
        this.piles.draw = this.rng.shuffle(this.piles.discard.splice(0));
        this.emit({t: 'shuffle', drawCount: this.piles.draw.length});
      }
      const card = this.piles.draw.pop()!;
      if (this.piles.hand.length >= MAX_HAND) { this.moveTo(card, 'discard', 'discard'); continue; }
      this.piles.hand.push(card);
      this.emit({t: 'draw', card, drawCount: this.piles.draw.length, discardCount: this.piles.discard.length});
    }
  }

  /** Adds seconds of 思考. Each full limit turns into a 巨鲸破浪 in hand. */
  think(n: number) {
    const p = this.player;
    this.applyStatus(p, 'think', n);
    while ((p.status.think ?? 0) >= this.thinkLimit) {
      p.status.think! -= this.thinkLimit;
      const full = !!p.status.fullSize;
      const card = this.makeCard(full ? 'whaleBreach+' : 'whaleBreach');
      if (full) card.cost = 0;
      this.emit({t: 'thinkDone', card});
      this.emit({t: 'status', unit: 'p', status: 'think', amount: -this.thinkLimit, value: p.status.think!});
      if (this.piles.hand.length < MAX_HAND) { this.piles.hand.push(card); this.emit({t: 'cardTo', card, pile: 'hand', reason: 'created'}); }
      else this.moveTo(card, 'discard', 'created');
    }
    this.counters();
  }

  setStance(to: Stance) {
    const p = this.player, from = p.stance;
    if (from === to) return;
    p.stance = to;
    this.emit({t: 'stance', stance: to, from});
    if (from === 'trough') this.gainEnergy(2);
    if (p.status.switchBlock) this.gainBlock(p, p.status.switchBlock);
    if (to === 'crest' && p.status.crestDraw) this.draw(p.status.crestDraw);
  }

  loseHp(n: number, why: string) {
    const p = this.player;
    p.hp = Math.max(0, p.hp - n);
    this.emit({t: 'hpLoss', unit: 'p', amount: n, hp: p.hp, why});
    if (!p.hp) { this.result = 'defeat'; this.emit({t: 'defeat'}); }
  }

  applyStatus(u: Unit, status: StatusId, n: number) {
    u.status[status] = (u.status[status] ?? 0) + n;
    this.emit({t: 'status', unit: u.id, status, amount: n, value: u.status[status]!});
  }

  // ── internals ────────────────────────────────────────────────────────────

  private resolve(card: Card, def: CardDef, target: string | undefined, ops: Op[]) {
    for (let i = 0; i < ops.length; i++) {
      if (this.result) break;
      const op = ops[i];
      if (op.op === 'exhaustChoose') {
        if (this.piles.hand.length > op.n) {
          this.pending = {card, def, target, rest: ops.slice(i + 1), count: op.n};
          this.emit({t: 'choose', count: op.n, prompt: `选择 ${op.n} 张手牌消耗`});
          return;
        }
        for (const c of [...this.piles.hand]) { this.remove(c); this.exhaust(c, 'exhaust'); }
        continue;
      }
      this.runOp(op, def, target);
    }
    if (def.type === 'attack') { this.attacksThisTurn++; this.counters(); }
    if (def.cutIn) this.whales++;
    // Powers stay in play; everything else leaves the table once resolved.
    if (def.type !== 'power') {
      if (def.exhaust) this.exhaust(card, 'exhaust');
      else this.moveTo(card, 'discard', 'played');
    }
  }

  private runOp(op: Op, def: CardDef, target?: string) {
    const p = this.player;
    switch (op.op) {
      case 'if': {
        const t = target ? this.enemies.find(e => e.id === target) : undefined;
        const ok = (op.stance === undefined || p.stance === op.stance) && (!op.targetAttacks || (!!t && 'dmg' in t.intent));
        for (const o of (ok ? op.then : op.else) ?? []) { this.runOp(o, def, target); if (this.result) return; }
        return;
      }
      case 'think': return this.think(op.n);
      case 'stance': return this.setStance(op.to);
      case 'doubleBlock': return this.gainBlock(p, p.block);
      case 'damage': {
        const targets = op.all ? this.living() : this.living().filter(e => e.id === target);
        const times = op.times ?? 1;
        for (let hit = 0; hit < times; hit++) {
          for (const e of targets) {
            if (!e.alive) continue;
            this.hit(p, e, this.cardDamage(def, e.id)!, hit, times);
            if (this.result) return;
          }
        }
        return;
      }
      case 'block': return this.gainBlock(p, op.n);
      case 'draw': return this.draw(op.n);
      case 'energy': return this.gainEnergy(op.n);
      case 'status': {
        const u = op.to === 'self' ? p : target ? this.unit(target) : null;
        if (u) this.applyStatus(u, op.status, op.n);
        return;
      }
      case 'addCard':
        for (let i = 0; i < op.n; i++) {
          const c = this.makeCard(op.id);
          if (op.pile === 'hand' && this.piles.hand.length < MAX_HAND) {
            this.piles.hand.push(c);
            this.emit({t: 'cardTo', card: c, pile: 'hand', reason: 'created'});
          } else this.moveTo(c, op.pile === 'draw' ? 'draw' : 'discard', 'created');
        }
        return;
      case 'exhaustNonAttacks': {
        const gone = this.piles.hand.filter(c => CARDS[c.id].type !== 'attack');
        for (const c of gone) { this.remove(c); this.exhaust(c, 'exhaust'); }
        if (op.drawEach) this.draw(gone.length);
        return;
      }
      case 'redraw': {
        const n = this.piles.hand.length;
        for (const c of [...this.piles.hand]) { this.remove(c); this.moveTo(c, 'discard', 'discard'); }
        return this.draw(n);
      }
    }
  }

  private hit(src: Unit, dst: Unit, amount: number, hit: number, hits: number) {
    const blocked = Math.min(dst.block, amount);
    dst.block -= blocked;
    dst.hp = Math.max(0, dst.hp - (amount - blocked));
    this.emit({t: 'damage', src: src.id, dst: dst.id, amount: amount - blocked, blocked, hp: dst.hp, block: dst.block, hit, hits});
    // 护食 hits back once per enemy hit, even when the block soaked all of it.
    if (dst === this.player && src !== dst && dst.status.guard && dst.hp > 0) this.hit(dst, src, dst.status.guard, 0, 1);
    if (dst.hp > 0) return;
    if (dst === this.player) { this.result = 'defeat'; this.emit({t: 'defeat'}); return; }
    (dst as EnemyUnit).alive = false;
    this.emit({t: 'death', unit: dst.id});
    if (!this.living().length) { this.result = 'victory'; this.emit({t: 'victory'}); }
  }

  private startPlayerTurn(first = false) {
    this.turn++;
    this.inPlayerTurn = true;
    this.attacksThisTurn = 0;
    this.exhaustedThisTurn = 0;
    const p = this.player;
    this.emit({t: 'turnStart', turn: this.turn});
    this.counters();
    if (p.block && !p.status.keepBlock) { p.block = 0; this.emit({t: 'blockClear', unit: 'p'}); }
    if (p.status.guard) this.clearStatus(p, 'guard');
    this.energy = ENERGY_PER_TURN;
    this.emit({t: 'energy', energy: this.energy});
    // Combat-start relics run after the block reset, so opening block such as
    // 吃饭的铁盆 lasts through the first enemy turn.
    if (first) for (const id of this.relics) RELICS[id].combatStart?.(this);
    for (const id of this.relics) RELICS[id].turnStart?.(this);
    if (p.status.strengthPerTurn) this.applyStatus(p, 'strength', p.status.strengthPerTurn);
    if (p.status.thinkPerTurn) this.think(p.status.thinkPerTurn);
    const extra = (p.status.extraDraw ?? 0) + (p.status.drawNext ?? 0);
    if (p.status.drawNext) this.clearStatus(p, 'drawNext');
    if (!this.result) this.draw(HAND_SIZE + extra);
  }

  private enemyPhase() {
    this.emit({t: 'enemyTurn'});
    for (const e of this.living()) {
      if (e.block) { e.block = 0; this.emit({t: 'blockClear', unit: e.id}); }
      this.act(e, e.intent);
      if (this.result) return;
      // 护食 can kill the attacker mid-turn.
      if (!this.living().length) return;
    }
    this.enemyTurns++;
    for (const e of this.living()) { this.tickDown(e); this.planIntent(e); }
  }

  private act(e: EnemyUnit, intent: Intent) {
    this.emit({t: 'enemyMove', unit: e.id, move: e.moveName, intent});
    const p = this.player;
    if ('dmg' in intent) {
      for (let h = 0; h < intent.times; h++) {
        this.hit(e, p, this.attackValue(e, p, intent.dmg), h, intent.times);
        if (this.result || !e.alive) return;
      }
    }
    if (e.alive && (intent.kind === 'attackDefend' || intent.kind === 'defend' || intent.kind === 'stuff')) this.gainBlock(e, intent.block);
    if (intent.kind === 'attackDebuff' || intent.kind === 'debuff') this.applyStatus(p, intent.status, intent.n);
    if (intent.kind === 'buff') { this.applyStatus(e, intent.status, intent.n); if (intent.block) this.gainBlock(e, intent.block); }
    if (intent.kind === 'stuff') for (let i = 0; i < intent.n; i++) this.moveTo(this.makeCard(intent.id), 'discard', 'created');
  }

  private planIntent(e: EnemyUnit) {
    const def = ENEMIES[e.kind], move = def.next(e, this.rng, this.enemyTurns);
    e.history.push(move);
    e.intent = def.moves[move].intent;
    e.moveName = def.moves[move].name;
    this.emit({t: 'intent', unit: e.id, intent: e.intent, move: e.moveName});
  }

  private tickDown(u: Unit) {
    for (const s of ['weak', 'vulnerable'] as const) {
      if (u.status[s]) this.applyStatus(u, s, -1);
      if (u.status[s] === 0) delete u.status[s];
    }
  }

  private clearStatus(u: Unit, s: StatusId) {
    const n = u.status[s] ?? 0;
    delete u.status[s];
    this.emit({t: 'status', unit: u.id, status: s, amount: -n, value: 0});
  }

  private exhaust(card: Card, reason: 'exhaust' | 'ethereal') {
    this.moveTo(card, 'exhaust', reason);
    if (!this.inPlayerTurn) return;
    this.exhaustedThisTurn++;
    if (this.exhaustedThisTurn === 1) for (const id of this.relics) RELICS[id].firstExhaustInTurn?.(this);
    if (!this.result) this.think(1);
  }

  private moveTo(card: Card, pile: Pile, reason: NonNullable<Extract<GameEvent, {t: 'cardTo'}>['reason']>) {
    this.piles[pile].push(card);
    this.emit({t: 'cardTo', card, pile, reason});
  }

  private remove(card: Card) {
    const hand = this.piles.hand, i = hand.indexOf(card);
    if (i >= 0) hand.splice(i, 1);
  }

  private counters() { this.emit({t: 'counters', attacks: this.attacksThisTurn, think: this.thinking, thinkLimit: this.thinkLimit}); }
  private makeCard(id: string): Card { return {uid: this.nextUid++, id}; }
  private emit(e: GameEvent) { this.events.push(e); }
  private flush(): GameEvent[] { return this.events.splice(0); }
}
