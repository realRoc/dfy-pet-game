import {describe, expect, it} from 'vitest';
import {Combat} from '../src/core/combat';
import {Run} from '../src/core/run';
import {CARDS} from '../src/content/cards';
import type {GameEvent} from '../src/core/types';

const setup = (deck: string[], enemies = ['dummy'], relics: string[] = []) =>
  new Combat({deck, hp: 50, maxHp: 50, relics, enemies, seed: 7});
const inHand = (c: Combat, id: string) => c.piles.hand.find(x => x.id === id)!.uid;

describe('combat basics', () => {
  it('starts each turn with 3 energy and 5 cards', () => {
    const c = setup(Array(10).fill('tailSlap'));
    c.start();
    expect(c.energy).toBe(3);
    expect(c.piles.hand).toHaveLength(5);
    expect(c.enemies[0].intent.kind).toBe('idle');
  });

  it('blocks before losing HP and clears block next turn', () => {
    const c = setup(Array(10).fill('ironBowl'));
    c.start();
    c.play(c.piles.hand[0].uid);
    c.endTurn(); // dummy dazes on turn one
    expect(c.player.block).toBe(0);
    c.play(c.piles.hand[0].uid);
    c.endTurn(); // bonk for 5 into 5 block
    expect(c.player.hp).toBe(50);
  });

  it('enemies follow their move pattern turn by turn', () => {
    const c = setup(Array(20).fill('ironBowl'), ['dummy', 'jelly']);
    c.start();
    const moves = () => c.enemies.map(e => e.moveName);
    expect(moves()).toEqual(['发呆', '服务器繁忙']);
    c.endTurn();
    expect(moves()).toEqual(['回弹', '过载电击']);
    expect(c.piles.discard.filter(x => x.id === 'busy')).toHaveLength(2);
    c.endTurn();
    expect(moves()).toEqual(['扎稳', '请稍后再试']);
  });

  it('replays identically from the same seed', () => {
    const play = () => {
      const c = setup(['tailSlap', 'tailSlap', 'ironBowl', 'think3s', 'doubleSlap', 'innerOS', 'tailSlap'], ['crab', 'gull']);
      const log: GameEvent[] = [...c.start()];
      for (let t = 0; t < 4 && !c.result; t++) {
        const card = c.piles.hand.find(x => !c.blocked(x.uid) && !CARDS[x.id].ops.some(o => o.op === 'exhaustChoose'));
        if (card) log.push(...c.play(card.uid, c.living()[0].id));
        log.push(...c.endTurn());
      }
      return JSON.stringify(log);
    };
    expect(play()).toBe(play());
  });

  it('wins when the last enemy dies', () => {
    const c = setup(Array(10).fill('whaleBreach'), ['crab', 'gull']);
    c.start();
    const events = c.play(c.piles.hand[0].uid);
    expect(c.result).toBe('victory');
    expect(events.filter(e => e.t === 'death')).toHaveLength(2);
  });
});

describe('鲸尾 combo scaling', () => {
  it('鲸落 grows with attacks played earlier this turn', () => {
    const c = setup(['whaleFall', 'riceDash', 'riceDash', 'ironBowl', 'ironBowl']);
    c.start();
    expect(c.cardDamage(CARDS.whaleFall)).toBe(8);
    c.play(inHand(c, 'riceDash'), 'e0');
    c.play(inHand(c, 'riceDash'), 'e0');
    expect(c.attacksThisTurn).toBe(2);
    expect(c.cardDamage(CARDS.whaleFall)).toBe(14);
  });

  it('strength adds to every hit', () => {
    const c = setup(['fullBelly', 'doubleSlap', 'ironBowl', 'ironBowl', 'ironBowl']);
    c.start();
    c.play(inHand(c, 'fullBelly'));
    const hits = c.play(inHand(c, 'doubleSlap'), 'e0').filter(e => e.t === 'damage');
    expect(hits.map(h => h.t === 'damage' && h.amount)).toEqual([5, 5]);
  });
});

describe('深度思考 exhaust scaling', () => {
  it('思考完毕 gains 4 per card exhausted this turn', () => {
    const c = setup(['thinkDone', 'think3s', 'ironBowl', 'ironBowl', 'silentOS', 'tailSlap', 'tailSlap', 'tailSlap']);
    c.start();
    expect(c.cardDamage(CARDS.thinkDone)).toBe(6);
    c.play(inHand(c, 'think3s'));          // think3s exhausts itself
    expect(c.exhaustedThisTurn).toBe(1);
    expect(c.cardDamage(CARDS.thinkDone)).toBe(10);
  });

  it('不语只是一味地OS exhausts every non-attack and redraws as many', () => {
    const c = setup(['silentOS', 'ironBowl', 'ironBowl', 'tailSlap', 'think3s', 'tailSlap', 'tailSlap', 'tailSlap']);
    c.start();
    const nonAttacks = c.piles.hand.filter(x => CARDS[x.id].type !== 'attack' && x.id !== 'silentOS').length;
    c.play(inHand(c, 'silentOS'));
    expect(c.exhaustedThisTurn).toBe(nonAttacks);
    expect(c.piles.exhaust).toHaveLength(nonAttacks);
  });

  it('内心OS asks which card to exhaust and then continues', () => {
    const c = setup(['innerOS', 'tailSlap', 'tailSlap', 'tailSlap', 'tailSlap', 'ironBowl', 'ironBowl', 'ironBowl', 'ironBowl']);
    c.start();
    const events = c.play(inHand(c, 'innerOS'));
    expect(events.at(-1)).toMatchObject({t: 'choose', count: 1});
    expect(c.blocked(c.piles.hand[0].uid)).toBe('先选完要消耗的牌');
    c.choose([c.piles.hand[0].uid]);
    expect(c.pending).toBeNull();
    expect(c.exhaustedThisTurn).toBe(1);
    expect(c.piles.discard.map(x => x.id)).toContain('innerOS');
  });

  it('服务器繁忙 is ethereal and is exhausted at turn end without counting', () => {
    const c = setup(['longCoT', 'tailSlap', 'tailSlap', 'tailSlap', 'tailSlap', 'tailSlap', 'tailSlap', 'tailSlap', 'tailSlap']);
    c.start();
    c.play(inHand(c, 'longCoT'));
    expect(c.blocked(inHand(c, 'busy'))).toBe('这张牌无法打出');
    c.endTurn();
    expect(c.piles.exhaust.map(x => x.id)).toEqual(['busy']);
    expect(c.exhaustedThisTurn).toBe(0);
  });
});

describe('relics', () => {
  it('剩饭 heals 6 after a won fight', () => {
    const run = new Run(1);
    run.combat.start();
    run.combat.player.hp = 30;
    run.combat.enemies[0].hp = 1;
    run.combat.play(run.combat.piles.hand.find(x => x.id === 'tailSlap')!.uid, 'e0');
    run.finishCombat();
    expect(run.hp).toBe(36);
    expect(run.stage).toBe('reward');
    expect(run.cardChoices).toHaveLength(3);
  });

  it('电饭煲 gives 2 energy on turn 3', () => {
    const c = setup(Array(20).fill('ironBowl'), ['dummy'], ['riceCooker']);
    c.start();
    c.endTurn();
    expect(c.energy).toBe(3);
    c.endTurn();
    expect(c.turn).toBe(3);
    expect(c.energy).toBe(5);
  });

  it('呆毛 draws on the first exhaust each turn', () => {
    const c = setup(['think3s', ...Array(12).fill('ironBowl')], ['dummy'], ['ahoge']);
    c.start();
    c.play(inHand(c, 'think3s'));
    expect(c.piles.hand).toHaveLength(4 + 2 + 1);
  });
});
