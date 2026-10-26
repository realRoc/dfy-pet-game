import {describe, expect, it} from 'vitest';
import {CARDS} from '../src/content/cards';
import {FLOORS} from '../src/core/map';
import {QUESTION_ODDS, Run} from '../src/core/run';

const internals = (r: Run) => r as unknown as {enterQuestion(): void; openShop(): void};

/** Wins the current fight on the spot. */
const win = (run: Run) => {
  const c = run.combat!;
  c.start();
  for (const e of c.enemies) e.hp = 1;
  c.energy = 99;
  while (!c.result) {
    const card = c.piles.hand.find(x => CARDS[x.id].type === 'attack' && !c.blocked(x.uid));
    if (card) c.play(card.uid, c.living()[0].id); else c.endTurn();
  }
  run.finishCombat();
};

/** Takes the first choice in every room until the boss is beaten. */
function climb(seed: number): Run {
  const run = new Run(seed);
  for (let step = 0; step < 200 && run.stage !== 'cleared' && run.stage !== 'dead'; step++) {
    if (run.stage === 'map') run.move(run.choices()[0].col);
    else if (run.stage === 'combat') win(run);
    else if (run.stage === 'reward') run.takeReward(run.reward!.cards[0], run.reward!.removeCard ? 0 : undefined);
    else if (run.stage === 'rest') run.rest('sleep');
    else if (run.stage === 'bug') run.bug('ignore');
    else if (run.stage === 'event') {
      const i = 0;
      run.chooseEvent(i, 0);
      if (run.stage === 'event') run.leave();
    } else run.leave();
  }
  return run;
}

describe('a run', () => {
  it('climbs 15 floors to the boss and clears', () => {
    for (const seed of [1, 2, 3, 99]) {
      const run = climb(seed);
      expect(run.stage).toBe('cleared');
      expect(run.pos!.floor).toBe(FLOORS);
    }
  });

  it('only moves to connected nodes', () => {
    const run = new Run(8);
    const first = run.choices()[0];
    run.move(first.col);
    win(run);
    run.takeReward(null);
    const options = run.choices().map(n => n.col);
    expect(options).toEqual(first.next);
    const bad = [0, 1, 2, 3, 4, 5, 6].find(c => !options.includes(c))!;
    expect(() => run.move(bad)).toThrow();
  });

  it('a ? room becomes a fight more likely every time it was not one', () => {
    const run = new Run(3), q = internals(run);
    let r = .99;                           // past every odds: an event
    run.rng.next = () => r;
    q.enterQuestion();
    expect(run.question).toBe('event');
    expect(run.odds.monster).toBeCloseTo(QUESTION_ODDS.monster + .1);
    run.leave();
    for (let i = 0; i < 3; i++) { q.enterQuestion(); run.leave(); }
    expect(run.odds.monster).toBeCloseTo(.5);
    r = .45;                               // would have been an event at the start
    q.enterQuestion();
    expect(run.question).toBe('monster');
    expect(run.odds.monster).toBe(QUESTION_ODDS.monster);
  });

  it('naps heal 30% or upgrade a card', () => {
    const run = new Run(4);
    run.hp = 20; run.stage = 'rest';
    expect(run.rest('sleep')).toBe(15);
    run.stage = 'rest';
    run.rest('think', 0);
    expect(run.deck[0]).toBe('tailSlap+');
  });

  it('the shop sells cards and relics for Token and removes a card once', () => {
    const run = new Run(5);
    run.gold = 1000;
    internals(run).openShop();
    const shop = run.shop!;
    expect(shop.cards).toHaveLength(5);
    expect(shop.cards.filter(c => c.sale)).toHaveLength(1);
    run.buy('cards', 0);
    expect(run.deck.at(-1)).toBe(shop.cards[0].id);
    expect(() => run.buy('cards', 0)).toThrow('卖完了');
    run.buy('relics', 0);
    expect(run.relics).toContain(shop.relics[0].id);
    const size = run.deck.length, gold = run.gold;
    expect(() => run.buyRemoval(size)).toThrow('没有这张牌');  // 选错牌不扣 Token，服务也还能用
    expect(run.gold).toBe(gold);
    run.buyRemoval(0);
    expect(run.deck).toHaveLength(size - 1);
    expect(run.gold).toBe(gold - shop.removePrice);
    expect(() => run.buyRemoval(0)).toThrow();
    run.gold = 0;
    expect(() => run.buy('cards', 1)).toThrow('Token 不够');
  });

  it('Bug 房: exploit copies a card and adds 锟斤拷; fix fights 乱码虫 for a removal and a rare', () => {
    const run = new Run(6);
    run.stage = 'bug';
    run.bug('exploit', 9);
    expect(run.deck.slice(-2)).toEqual(['think3s', 'garbled']);
    run.stage = 'bug';
    run.bug('fix');
    expect(run.encounter!.enemies).toEqual(['glitch']);
    win(run);
    expect(run.reward!.removeCard).toBe(true);
    expect(run.reward!.cards.every(id => CARDS[id].rarity === 'rare')).toBe(true);
    const size = run.deck.length, rare = run.reward!.cards[0];
    // 修 Bug 必须删一张：不选、选错位置、拿不存在的牌都拒绝，而且牌组原样不动
    expect(() => run.takeReward(rare)).toThrow();
    expect(() => run.takeReward(rare, size)).toThrow();
    expect(() => run.takeReward('nope', 0)).toThrow();
    expect(run.deck).toHaveLength(size);
    expect(run.stage).toBe('reward');
    run.takeReward(rare, 0);
    expect(run.deck).toHaveLength(size);  // one out, one in
    expect(run.stage).toBe('map');
  });

  it('elites drop a relic, chests too', () => {
    const run = new Run(7);
    run.fight({id: 'x', name: 'x', enemies: ['jelly'], elite: true});
    win(run);
    expect(run.reward!.relic).toBeTruthy();
    expect(run.relics).toContain(run.reward!.relic);
  });
});
