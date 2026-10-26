import {CARDS, REWARD_POOL, STARTER_DECK} from '../content/cards';
import {GAUNTLET} from '../content/enemies';
import {RELIC_REWARDS, RELICS} from '../content/relics';
import {Combat} from './combat';
import {Rng} from './rng';

export const START_HP = 50;
const RARITY_WEIGHT = {common: 60, uncommon: 32, rare: 8} as Record<string, number>;

export type Stage = 'combat' | 'reward' | 'cleared' | 'dead';

/**
 * The prototype run: three fights in a row with a card pick after each and a
 * relic pick before the elite. The full map replaces GAUNTLET later.
 */
export class Run {
  readonly rng: Rng;
  hp = START_HP;
  maxHp = START_HP;
  deck = [...STARTER_DECK];
  relics = ['leftovers'];
  floor = 0;
  stage: Stage = 'combat';
  combat: Combat;
  cardChoices: string[] = [];
  relicChoices: string[] = [];
  healed = 0;

  constructor(readonly seed: number) {
    this.rng = new Rng(seed);
    this.combat = this.newCombat();
  }

  get encounter() { return GAUNTLET[this.floor]; }

  private newCombat() {
    return new Combat({deck: this.deck, hp: this.hp, maxHp: this.maxHp, relics: this.relics,
      enemies: this.encounter.enemies, seed: this.rng.int(1, 2 ** 31 - 1)});
  }

  /** Call once the combat reports a result. */
  finishCombat() {
    const c = this.combat;
    this.hp = c.player.hp;
    if (c.result === 'defeat') { this.stage = 'dead'; return; }
    const before = this.hp;
    for (const id of this.relics) this.hp = Math.min(this.maxHp, this.hp + (RELICS[id].combatEndHeal ?? 0));
    this.healed = this.hp - before;
    if (this.floor === GAUNTLET.length - 1) { this.stage = 'cleared'; return; }
    this.stage = 'reward';
    this.cardChoices = this.rollCards(3);
    const open = RELIC_REWARDS.filter(id => !this.relics.includes(id));
    this.relicChoices = this.floor === GAUNTLET.length - 2 ? this.rng.shuffle([...open]).slice(0, 3) : [];
  }

  private rollCards(n: number): string[] {
    const picked: string[] = [];
    while (picked.length < n) {
      const pool = REWARD_POOL.filter(id => !picked.includes(id));
      const total = pool.reduce((s, id) => s + RARITY_WEIGHT[CARDS[id].rarity], 0);
      let roll = this.rng.next() * total;
      for (const id of pool) { roll -= RARITY_WEIGHT[CARDS[id].rarity]; if (roll <= 0) { picked.push(id); break; } }
    }
    return picked;
  }

  takeReward(card: string | null, relic: string | null) {
    if (this.stage !== 'reward') throw new Error('现在没有奖励可拿');
    if (card) this.deck.push(card);
    if (relic) this.relics.push(relic);
    this.floor++;
    this.stage = 'combat';
    this.combat = this.newCombat();
  }
}
