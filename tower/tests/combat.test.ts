import {describe, expect, it} from 'vitest';
import {Combat, MAX_HAND} from '../src/core/combat';
import {Run} from '../src/core/run';
import {CARDS} from '../src/content/cards';
import type {GameEvent, Intent} from '../src/core/types';

const setup = (deck: string[], enemies = ['dummy'], relics: string[] = []) =>
  new Combat({deck, hp: 50, maxHp: 50, relics, enemies, seed: 7});
/** Like setup, but draws the deck in the order given. */
const ordered = (deck: string[], enemies = ['dummy'], relics: string[] = []) => {
  const c = setup(deck, enemies, relics);
  c.piles.draw.sort((a, b) => b.uid - a.uid);
  return c;
};
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

describe('手牌上限', () => {
  it('满手时抽到的牌标成 burned 进弃牌堆，界面靠它把抽牌堆数字减掉', () => {
    const c = setup(Array(15).fill('tailSlap'));
    c.start();
    while (c.piles.hand.length < MAX_HAND) c.piles.hand.push(c.piles.draw.pop()!);
    const before = c.piles.draw.length;
    c.draw(1);
    const events = c['flush'](); // draw() is public, but its events normally leave through play()
    expect(c.piles.draw.length).toBe(before - 1);
    expect(events).toContainEqual(expect.objectContaining({t: 'cardTo', pile: 'discard', reason: 'burned'}));
  });
});

describe('虚弱 / 易伤', () => {
  // Each endTurn runs the enemy's current intent, then plans a new one; tests overwrite it to script the fight.
  const script = (c: Combat, intent: Intent) => { c.enemies[0].intent = intent; };

  it('敌人给的易伤 2 撑到它下一次攻击，意图上的数字就是实际伤害', () => {
    const c = setup(Array(10).fill('ironBowl'));
    c.start();
    script(c, {kind: 'debuff', status: 'vulnerable', n: 2});
    c.endTurn();
    expect(c.player.status.vulnerable).toBe(2);
    script(c, {kind: 'idle'});
    c.endTurn();
    expect(c.player.status.vulnerable).toBe(1);
    script(c, {kind: 'attack', dmg: 10, times: 1});
    const shown = c.intentDamage(c.enemies[0]);
    expect(shown).toBe(15);
    const hp = c.player.hp;
    c.endTurn();
    expect(hp - c.player.hp).toBe(shown);
    expect(c.player.status.vulnerable).toBeUndefined();
  });

  it('敌人给的虚弱 1 正好管玩家一个回合', () => {
    const c = setup(Array(10).fill('tailSlap'));
    c.start();
    const full = c.cardDamage(CARDS.tailSlap);
    script(c, {kind: 'attackDebuff', dmg: 1, times: 1, status: 'weak', n: 1});
    c.endTurn();
    expect(c.cardDamage(CARDS.tailSlap)).toBeLessThan(full!);
    script(c, {kind: 'idle'});
    c.endTurn();
    expect(c.player.status.weak).toBeUndefined();
    expect(c.cardDamage(CARDS.tailSlap)).toBe(full);
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

describe('深度思考', () => {
  it('每消耗 1 张牌思考 1 秒，已思考3秒正好 3 秒', () => {
    const c = setup(['hallucinate', 'think3s', 'ironBowl', 'ironBowl', 'silentOS', 'tailSlap', 'tailSlap', 'tailSlap']);
    c.start();
    expect(c.cardDamage(CARDS.hallucinate)).toBe(6);
    c.play(inHand(c, 'think3s'));          // 思考 2 秒，再消耗自己 +1
    expect(c.thinking).toBe(3);
    expect(c.cardDamage(CARDS.hallucinate)).toBe(12);
  });

  it('思考满 10 秒时把巨鲸破浪放进手牌，余下的秒数留着', () => {
    const c = ordered(['greyTest+', 'greyTest+', ...Array(8).fill('ironBowl')]);
    c.start();
    c.play(inHand(c, 'greyTest+'));        // 5 + 1
    expect(c.thinking).toBe(6);
    const events = c.play(inHand(c, 'greyTest+'));
    expect(events.some(e => e.t === 'thinkDone')).toBe(true);
    expect(c.thinking).toBe(2);
    expect(c.piles.hand.map(x => x.id)).toContain('whaleBreach');
  });

  it('思考跨回合累计，开启深度思考每回合再加', () => {
    const c = setup(['deepThinkOn', ...Array(12).fill('ironBowl')]);
    c.start();
    c.play(inHand(c, 'deepThinkOn'));
    c.endTurn();
    expect(c.thinking).toBe(2);
    c.endTurn();
    expect(c.thinking).toBe(4);
  });

  it('满血版让思考完毕给的巨鲸是升级版且 0 费；蒸馏小模型把门槛降到 8 秒', () => {
    const c = ordered(['fullSize', 'greyTest', 'greyTest', ...Array(8).fill('ironBowl')], ['dummy'], ['distilled']);
    c.start();
    expect(c.thinkLimit).toBe(8);
    c.play(inHand(c, 'fullSize'));
    c.play(inHand(c, 'greyTest'));
    c.play(inHand(c, 'greyTest'));
    const whale = c.piles.hand.find(x => x.id === 'whaleBreach+')!;
    expect(whale).toBeTruthy();
    expect(c.costOf(whale)).toBe(0);
  });

  it('满手牌时思考完毕的巨鲸进弃牌堆不带 0 费，洗回来重抽是原价；打出后也恢复原价', () => {
    const c = ordered(['fullSize', ...Array(12).fill('ironBowl')], ['dummy'], ['distilled']);
    c.start();
    c.enemies[0].hp = c.enemies[0].maxHp = 500;
    c.play(inHand(c, 'fullSize'));
    const base = CARDS['whaleBreach+'].cost;
    // 手牌塞满 10 张，再思考完毕：巨鲸直接进弃牌堆
    while (c.piles.hand.length < MAX_HAND) c.piles.hand.push(c.piles.draw.pop()!);
    c.think(c.thinkLimit);
    const full = c.piles.discard.find(x => x.id === 'whaleBreach+')!;
    expect(full).toBeTruthy();
    expect(c.costOf(full)).toBe(base);
    // 手牌有空位时进手牌是 0 费；打出去（消耗）后恢复原价
    c.piles.hand.pop();
    c.think(c.thinkLimit);
    const played = c.piles.hand.find(x => x.id === 'whaleBreach+')!;
    expect(c.costOf(played)).toBe(0);
    c.play(played.uid);
    expect(c.costOf(played)).toBe(base);
    // 抽牌堆清空，下回合从弃牌堆洗回来重抽
    c.piles.discard.push(...c.piles.draw.splice(0));
    c.endTurn();
    const whales = [...c.piles.hand, ...c.piles.draw, ...c.piles.discard].filter(x => x.id === 'whaleBreach+');
    expect(whales).toEqual([full]);
    expect(c.costOf(full)).toBe(base);
  });

  it('巨鲸破浪每打出过一次，下一次 +8', () => {
    const c = setup(Array(10).fill('whaleBreach'), ['jelly']);
    c.start();
    c.enemies[0].hp = c.enemies[0].maxHp = 500;
    c.energy = 9;
    const hit = () => (c.play(c.piles.hand.find(x => x.id === 'whaleBreach')!.uid).find(e => e.t === 'damage') as {amount: number; blocked: number});
    const a = hit(), b = hit();
    expect(a.amount + a.blocked).toBe(24);
    expect(b.amount + b.blocked).toBe(32);
  });

  it('不语只是一味地OS exhausts every non-attack and redraws as many', () => {
    const c = setup(['silentOS', 'ironBowl', 'ironBowl', 'tailSlap', 'think3s', 'tailSlap', 'tailSlap', 'tailSlap']);
    c.start();
    const nonAttacks = c.piles.hand.filter(x => CARDS[x.id].type !== 'attack' && x.id !== 'silentOS').length;
    c.play(inHand(c, 'silentOS'));
    expect(c.exhaustedThisTurn).toBe(nonAttacks);
    expect(c.piles.exhaust).toHaveLength(nonAttacks);
    expect(c.thinking).toBe(nonAttacks);
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
    expect(c.thinking).toBe(2);
  });
});

describe('relics', () => {
  it('剩饭 heals 6 after a won fight', () => {
    const run = new Run(1);
    run.move(run.choices()[0].col);
    const c = run.combat!;
    c.start();
    c.player.hp = 30;
    for (const e of c.enemies) e.hp = 1;
    c.play(c.piles.hand.find(x => x.id === 'tailSlap')!.uid, 'e0');
    while (!c.result) c.play(c.piles.hand.find(x => x.id === 'tailSlap')!.uid, c.living()[0].id);
    run.finishCombat();
    expect(run.hp).toBe(36);
    expect(run.stage).toBe('reward');
    expect(run.reward!.cards).toHaveLength(3);
  });

  it('吃饭的铁盆 block lasts through the first enemy turn and clears on the next player turn', () => {
    const c = setup(Array(20).fill('tailSlap'), ['gull'], ['ironBasin']);
    c.start();
    expect(c.player.block).toBe(10);
    expect(c.enemies[0].moveName).toBe('叼走饭碗'); // opens with a 5 damage hit
    c.endTurn();
    expect(c.player.hp).toBe(50);
    expect(c.turn).toBe(2);
    expect(c.player.block).toBe(0);
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

describe('波峰 / 波谷', () => {
  it('波峰让造成和受到的伤害都翻倍', () => {
    const c = setup(['noFat', ...Array(9).fill('tailSlap')], ['crab']);
    c.start();
    const crab = c.enemies[0];
    crab.hp = crab.maxHp = 100;
    c.play(inHand(c, 'noFat'), 'e0');      // 9 damage, then 波峰
    expect(crab.hp).toBe(91);
    expect(c.player.stance).toBe('crest');
    expect(c.cardDamage(CARDS.tailSlap, 'e0')).toBe(12);
    const dmg = c.intentDamage(crab)!;
    expect(dmg).toBe(2 * ('dmg' in crab.intent ? crab.intent.dmg : 0));
  });

  it('离开波谷时获得 2 点算力', () => {
    const c = setup(['goEat', 'notFreeloader', 'ironBowl', 'ironBowl', 'ironBowl']);
    c.start();
    c.play(inHand(c, 'goEat'));            // 2 费
    expect(c.player.stance).toBe('trough');
    expect(c.energy).toBe(1);
    c.play(inHand(c, 'notFreeloader'));    // 1 费，回到海平面 +2
    expect(c.player.stance).toBe('none');
    expect(c.energy).toBe(2);
  });

  it('等等，我再检查一下：在波谷里抽牌，否则进入波谷；不对容我再想想每次切换给格挡', () => {
    const c = ordered(['rethink', 'recheck', 'recheck', ...Array(10).fill('ironBowl')]);
    c.start();
    c.play(inHand(c, 'rethink'));
    c.play(inHand(c, 'recheck'));
    expect(c.player.stance).toBe('trough');
    expect(c.player.block).toBe(4);
    const hand = c.piles.hand.length;
    c.play(inHand(c, 'recheck'));
    expect(c.piles.hand.length).toBe(hand - 1 + 3);
  });

  it('嗯，用户想要……只在敌人打算攻击时进入波谷', () => {
    const c = setup(['readUser', 'readUser', ...Array(8).fill('ironBowl')], ['dummy']);
    c.start();                              // the dummy dazes first
    c.play(inHand(c, 'readUser'), 'e0');
    expect(c.player.stance).toBe('none');
    c.endTurn();                            // now it means to hit
    const card = c.piles.hand.find(x => x.id === 'readUser');
    if (card) { c.play(card.uid, 'e0'); expect(c.player.stance).toBe('trough'); }
  });
});

describe('铁盆', () => {
  it('铁盆头槌造成等于格挡的伤害，波峰也不翻倍', () => {
    const c = setup(['headbutt', 'ironBowl', 'ironBowl', 'ironBowl', 'ironBowl'], ['jelly']);
    c.start();
    c.play(inHand(c, 'ironBowl')); c.play(inHand(c, 'ironBowl'));
    expect(c.cardDamage(CARDS.headbutt, 'e0')).toBe(10);
    const before = c.enemies[0].hp;
    c.play(inHand(c, 'headbutt'), 'e0');
    expect(c.enemies[0].hp).toBe(before - 10);
  });

  it('饭盆不离身留住格挡，再来一碗翻倍，先养着吧回合结束给格挡', () => {
    const c = ordered(['bowlForever', 'anotherBowl+', 'keepPet', ...Array(10).fill('ironBowl')], ['dummy']);
    c.start();
    c.energy = 10;
    c.play(inHand(c, 'bowlForever'));
    c.play(inHand(c, 'keepPet'));
    c.play(inHand(c, 'anotherBowl+'));     // 0 → 0
    c.play(inHand(c, 'ironBowl'));
    expect(c.player.block).toBe(5);
    c.endTurn();                            // +3 at turn end, dummy dazes, block kept
    expect(c.player.block).toBe(8);
  });

  it('护食在被攻击时反击', () => {
    const c = setup(['guardFood', ...Array(9).fill('ironBowl')], ['gull']);
    c.start();
    const gull = c.enemies[0], hp = gull.hp;
    c.play(inHand(c, 'guardFood'));
    c.endTurn();                            // 叼走饭碗: one hit
    expect(gull.hp).toBe(hp - 4);
    expect(c.player.status.guard).toBeUndefined();
  });
});

describe('upgrades and curses', () => {
  it('upgraded cards are their own ids with a + name', () => {
    expect(CARDS['tailSlap+'].name).toBe('鲸尾拍击+');
    expect(CARDS['noFat+'].cost).toBe(1);
    expect(CARDS['whaleBreach+'].cutIn).toBe(true);
    expect(CARDS['busy+']).toBeUndefined();
  });

  it('锟斤拷 hurts at turn end while held', () => {
    const c = setup(Array(5).fill('garbled'));
    c.start();
    c.endTurn();
    expect(c.player.hp).toBe(50 - 10);
  });
});
