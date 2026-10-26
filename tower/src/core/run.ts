import {CARDS, canUpgrade, REWARD_POOL, STARTER_DECK, upgradeOf} from '../content/cards';
import {BOSS, BUG_FIGHT, EASY, ELITES, NORMAL, type Encounter} from '../content/enemies';
import {EVENT_BY_ID, EVENTS} from '../content/events';
import {RELIC_REWARDS, RELICS} from '../content/relics';
import {Combat} from './combat';
import {FLOORS, generateMap, nextChoices, type GameMap, type MapNode, type RoomType} from './map';
import {Rng} from './rng';

export const START_HP = 50;
export const START_GOLD = 99;
const RARITY_WEIGHT: Record<string, number> = {common: 60, uncommon: 32, rare: 8};
const ELITE_WEIGHT: Record<string, number> = {common: 50, uncommon: 38, rare: 12};
export const PRICE = {common: 50, uncommon: 75, rare: 150, relic: 150, remove: 75, removeStep: 25};
/** Where the boss sits: one floor above the map, in the middle. */
export const BOSS_NODE: MapNode = {floor: FLOORS, col: 3, type: 'boss', next: []};

export type Stage = 'map' | 'combat' | 'reward' | 'event' | 'shop' | 'rest' | 'chest' | 'bug' | 'cleared' | 'dead';

export interface Reward {
  gold: number;
  cards: string[];
  relic: string | null;
  /** Bug 房修好了：还要从牌组删一张牌。 */
  removeCard: boolean;
}

export interface ShopItem { id: string; price: number; sold: boolean; sale?: boolean }
export interface Shop { cards: ShopItem[]; relics: ShopItem[]; removePrice: number; removed: boolean }

/** Starting odds of what a ? room turns into; the fight chance grows every time it isn't one. */
export const QUESTION_ODDS = {monster: .1, shop: .03, chest: .02};

/**
 * One climb: the map, where the player stands, and whatever room they are in.
 * Every choice goes through a method here, so the whole run replays from the
 * seed and the UI only draws what this says.
 */
export class Run {
  readonly rng: Rng;
  readonly map: GameMap;
  hp = START_HP;
  maxHp = START_HP;
  gold = START_GOLD;
  deck = [...STARTER_DECK];
  relics = ['leftovers'];
  stage: Stage = 'map';
  /** Null until the first room. */
  pos: {floor: number; col: number} | null = null;
  /** Every node stepped on, bottom first, for drawing the trail on the map. */
  path: {floor: number; col: number}[] = [];
  /** The room the player is in. A ? room records what it turned into in `question`. */
  room: RoomType | null = null;
  question: RoomType | null = null;
  combat: Combat | null = null;
  encounter: Encounter | null = null;
  reward: Reward | null = null;
  shop: Shop | null = null;
  chest: {relic: string | null; gold: number} | null = null;
  event: {id: string; result: string | null} | null = null;
  odds = {...QUESTION_ODDS};
  healed = 0;
  removals = 0;
  fights = 0;
  private lastFight = '';
  private lastElite = '';
  private seenEvents: string[] = [];

  constructor(readonly seed: number) {
    this.rng = new Rng(seed);
    this.map = generateMap(this.rng.int(1, 2 ** 31 - 1));
  }

  get floor(): number { return this.pos ? this.pos.floor : -1; }

  /** Rooms the player can step into next. */
  choices(): MapNode[] {
    if (this.stage !== 'map') return [];
    if (this.pos?.floor === FLOORS - 1) return [BOSS_NODE];
    return nextChoices(this.map, this.pos);
  }

  move(col: number) {
    const node = this.choices().find(n => n.col === col);
    if (!node) throw new Error('那里走不过去');
    this.pos = {floor: node.floor, col: node.col};
    this.path.push(this.pos);
    this.room = node.type;
    this.question = null;
    this.enter(node.type);
  }

  private enter(type: RoomType): void {
    switch (type) {
      case 'monster': return this.fight(this.pickFight());
      case 'elite': return this.fight(this.pickElite());
      case 'boss': return this.fight(BOSS);
      case 'event': return this.enterQuestion();
      case 'shop': return this.openShop();
      case 'rest': this.stage = 'rest'; return;
      case 'bug': this.stage = 'bug'; return;
      case 'chest': {
        const open = this.unownedRelics();
        this.chest = {relic: open.length ? this.rng.pick(open) : null, gold: this.rng.int(20, 40)};
        if (this.chest.relic) this.relics.push(this.chest.relic);
        this.gold += this.chest.gold;
        this.stage = 'chest';
      }
    }
  }

  /** A ? room is usually an event; the fight chance climbs each time it isn't one. */
  private enterQuestion(): void {
    const o = this.odds, r = this.rng.next();
    let type: RoomType;
    if (r < o.monster) { type = 'monster'; o.monster = QUESTION_ODDS.monster; }
    else if (r < o.monster + o.shop) { type = 'shop'; o.shop = QUESTION_ODDS.shop; o.monster += .1; }
    else if (r < o.monster + o.shop + o.chest) { type = 'chest'; o.chest = QUESTION_ODDS.chest; o.monster += .1; }
    else { type = 'event'; o.monster += .1; o.shop += .03; o.chest += .02; }
    this.question = type;
    if (type !== 'event') return this.enter(type);
    let pool = EVENTS.filter(e => !this.seenEvents.includes(e.id));
    if (!pool.length) { this.seenEvents = []; pool = EVENTS; }
    const ev = this.rng.pick(pool);
    this.seenEvents.push(ev.id);
    this.event = {id: ev.id, result: null};
    this.stage = 'event';
  }

  private pickFight(): Encounter {
    const pool = (this.fights < 3 ? EASY : NORMAL).filter(e => e.id !== this.lastFight);
    const e = this.rng.pick(pool);
    this.lastFight = e.id;
    return e;
  }

  private pickElite(): Encounter {
    const e = this.rng.pick(ELITES.filter(x => x.id !== this.lastElite));
    this.lastElite = e.id;
    return e;
  }

  fight(encounter: Encounter) {
    this.encounter = encounter;
    this.stage = 'combat';
    this.combat = new Combat({deck: this.deck, hp: this.hp, maxHp: this.maxHp, relics: this.relics,
      enemies: encounter.enemies, seed: this.rng.int(1, 2 ** 31 - 1)});
  }

  /** Call once the combat reports a result. */
  finishCombat() {
    const c = this.combat!, enc = this.encounter!;
    this.hp = c.player.hp;
    if (c.result === 'defeat') { this.stage = 'dead'; return; }
    if (!enc.elite && !enc.boss) this.fights++;
    const before = this.hp;
    for (const id of this.relics) this.hp = Math.min(this.maxHp, this.hp + (RELICS[id].combatEndHeal ?? 0));
    this.healed = this.hp - before;
    if (enc.boss) { this.stage = 'cleared'; return; }
    const bug = enc === BUG_FIGHT;
    const gold = enc.elite ? this.rng.int(25, 35) : this.rng.int(10, 20);
    this.gold += gold;
    const relic = enc.elite && !bug ? this.gainRandomRelic() : null;
    this.reward = {gold, relic, removeCard: bug, cards: bug ? this.rollRare(3) : this.rollCards(3, enc.elite ? ELITE_WEIGHT : RARITY_WEIGHT)};
    this.stage = 'reward';
  }

  takeReward(card: string | null, removeIndex?: number) {
    if (this.stage !== 'reward' || !this.reward) throw new Error('现在没有奖励可拿');
    // Check everything before touching the deck, so a bad call leaves the reward as it was.
    if (card && !this.reward.cards.includes(card)) throw new Error('没有这张牌');
    if (this.reward.removeCard) {
      if (removeIndex === undefined || !this.deck[removeIndex]) throw new Error('先选一张要删掉的牌');
      this.removeCard(removeIndex);
    } else if (removeIndex !== undefined) throw new Error('这次奖励不删牌');
    if (card) this.deck.push(card);
    this.reward = null;
    this.leave();
  }

  /** Back to the map from any finished room. */
  leave() {
    this.combat = null;
    this.encounter = null;
    this.shop = null;
    this.chest = null;
    this.event = null;
    this.stage = 'map';
  }

  // ── rooms ────────────────────────────────────────────────────────────────

  /** 打盹点: 睡一觉回 30% 生命，或者想一想升级一张牌。 */
  rest(choice: 'sleep' | 'think', deckIndex?: number): number {
    if (this.stage !== 'rest') throw new Error('这里不是打盹点');
    let healed = 0;
    if (choice === 'sleep') healed = this.heal(Math.ceil(this.maxHp * .3));
    else this.upgrade(deckIndex!);
    this.leave();
    return healed;
  }

  /** Bug 房: fix (fight 乱码虫), exploit (copy a card, take a 锟斤拷) or ignore. */
  bug(choice: 'fix' | 'exploit' | 'ignore', deckIndex?: number) {
    if (this.stage !== 'bug') throw new Error('这里没有 Bug');
    if (choice === 'fix') return this.fight(BUG_FIGHT);
    if (choice === 'exploit') {
      const id = this.deck[deckIndex!];
      if (!id) throw new Error('选一张要复制的牌');
      this.deck.push(id, 'garbled');
    }
    this.leave();
  }

  chooseEvent(option: number, deckIndex?: number): string | null {
    if (this.stage !== 'event' || !this.event || this.event.result) throw new Error('现在没有事件');
    const opt = EVENT_BY_ID[this.event.id].options[option];
    if (!opt) throw new Error('没有这个选项');
    const why = opt.can?.(this);
    if (why) throw new Error(why);
    if (opt.pick && deckIndex === undefined) throw new Error('先选一张牌');
    if (opt.fight) { this.fight(opt.fight); return null; }
    this.event.result = opt.apply!(this, deckIndex);
    return this.event.result;
  }

  private openShop() {
    const cards = this.rollCards(5, RARITY_WEIGHT).map(id => ({id, price: this.price(PRICE[CARDS[id].rarity as 'common']), sold: false} as ShopItem));
    // 错峰优惠: one card at half price.
    const sale = this.rng.pick(cards);
    sale.price = Math.round(sale.price / 2); sale.sale = true;
    const relics = this.rng.shuffle(this.unownedRelics()).slice(0, 3).map(id => ({id, price: this.price(PRICE.relic), sold: false}));
    this.shop = {cards, relics, removePrice: PRICE.remove + PRICE.removeStep * this.removals, removed: false};
    this.stage = 'shop';
  }

  private price(base: number) { return Math.round(base * (.9 + this.rng.next() * .2)); }

  buy(kind: 'cards' | 'relics', index: number) {
    const item = this.shop?.[kind][index];
    if (!item || item.sold) throw new Error('卖完了');
    if (this.gold < item.price) throw new Error('Token 不够');
    this.gold -= item.price;
    item.sold = true;
    if (kind === 'cards') this.deck.push(item.id); else this.relics.push(item.id);
  }

  buyRemoval(deckIndex: number) {
    const s = this.shop;
    if (!s || s.removed) throw new Error('删牌服务今天用过了');
    if (this.gold < s.removePrice) throw new Error('Token 不够');
    this.removeCard(deckIndex);  // throws on a bad index before any Token is spent
    this.gold -= s.removePrice;
    s.removed = true;
    this.removals++;
  }

  // ── deck and stats ───────────────────────────────────────────────────────

  upgrade(deckIndex: number) {
    const id = this.deck[deckIndex];
    if (!id || !canUpgrade(id)) throw new Error('这张牌不能升级');
    this.deck[deckIndex] = upgradeOf(id);
  }

  removeCard(deckIndex: number) {
    if (!this.deck[deckIndex]) throw new Error('没有这张牌');
    this.deck.splice(deckIndex, 1);
  }

  heal(n: number): number {
    const before = this.hp;
    this.hp = Math.min(this.maxHp, this.hp + n);
    return this.hp - before;
  }

  /** Events hurt but never kill. */
  hurt(n: number) { this.hp = Math.max(1, this.hp - n); }

  unownedRelics() { return RELIC_REWARDS.filter(id => !this.relics.includes(id)); }
  relicName(id: string) { return RELICS[id].name; }

  gainRandomRelic(): string | null {
    const open = this.unownedRelics();
    if (!open.length) return null;
    const id = this.rng.pick(open);
    this.relics.push(id);
    return id;
  }

  private rollCards(n: number, weights: Record<string, number>): string[] {
    const picked: string[] = [];
    while (picked.length < n) {
      const pool = REWARD_POOL.filter(id => !picked.includes(id));
      const total = pool.reduce((s, id) => s + weights[CARDS[id].rarity], 0);
      let roll = this.rng.next() * total;
      for (const id of pool) { roll -= weights[CARDS[id].rarity]; if (roll <= 0) { picked.push(id); break; } }
    }
    return picked;
  }

  private rollRare(n: number): string[] {
    return this.rng.shuffle(REWARD_POOL.filter(id => CARDS[id].rarity === 'rare')).slice(0, n);
  }
}
