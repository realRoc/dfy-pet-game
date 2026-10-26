import {describe, expect, it} from 'vitest';
import {CARDS} from '../src/content/cards';
import {cardText} from '../src/ui/cards';

describe('card text', () => {
  it('战斗外没有伤害数字时不露出 {d}', () => {
    for (const def of Object.values(CARDS)) expect(cardText(def, null)).not.toContain('{d}');
    expect(cardText(CARDS.headbutt, null)).toContain('的伤害。不吃');
    expect(cardText(CARDS.headbutt, 12)).toContain('>12</b>');
  });
});
