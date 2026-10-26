import {describe, expect, it} from 'vitest';
import {COLS, FLOORS, generateMap, MAX_BUGS, mapEdges, nextChoices, PATHS, type GameMap, type RoomType} from '../src/core/map';

const SEEDS = Array.from({length: 300}, (_, i) => i * 7919 + 1);
const nodes = (m: GameMap) => m.floors.flat().filter(n => n !== null);

describe('map layout', () => {
  it('is 7 columns by 15 floors with the paths reaching the top', () => {
    for (const seed of SEEDS) {
      const m = generateMap(seed);
      expect(m.floors).toHaveLength(FLOORS);
      for (const row of m.floors) expect(row).toHaveLength(COLS);
      // Every node but the top floor leads somewhere, and every node above the bottom is reachable.
      for (const n of nodes(m)) {
        if (n.floor < FLOORS - 1) expect(n.next.length).toBeGreaterThan(0);
        if (n.floor > 0) expect(m.floors[n.floor - 1].some(p => p?.next.includes(n.col))).toBe(true);
        for (const c of n.next) expect(Math.abs(c - n.col)).toBeLessThanOrEqual(1);
      }
      expect(m.floors[0].filter(Boolean).length).toBeGreaterThanOrEqual(2);
      expect(m.floors[0].filter(Boolean).length).toBeLessThanOrEqual(PATHS);
    }
  });

  it('never crosses two edges between the same floors', () => {
    for (const seed of SEEDS) {
      const edges = mapEdges(generateMap(seed));
      for (const [f, a, b] of edges) for (const [g, c, d] of edges) {
        if (f !== g || a >= c) continue;
        // a is left of c, so a's edge must not end right of c's.
        expect(b, `seed ${seed} floor ${f}: ${a}->${b} vs ${c}->${d}`).toBeLessThanOrEqual(d);
      }
    }
  });

  it('is the same map for the same seed and a different one for another', () => {
    expect(JSON.stringify(generateMap(42))).toBe(JSON.stringify(generateMap(42)));
    expect(JSON.stringify(generateMap(42))).not.toBe(JSON.stringify(generateMap(43)));
  });

  it('only offers connected nodes', () => {
    const m = generateMap(5);
    expect(nextChoices(m, null).map(n => n.floor)).toEqual(m.floors[0].filter(Boolean).map(() => 0));
    const start = nextChoices(m, null)[0];
    expect(nextChoices(m, start).map(n => n.col)).toEqual(start.next);
  });
});

describe('room rules', () => {
  it('fixes floor 1, 9 and 15', () => {
    for (const seed of SEEDS) {
      const m = generateMap(seed);
      for (const [f, type] of [[0, 'monster'], [8, 'chest'], [14, 'rest']] as const) {
        for (const n of m.floors[f]) if (n) expect(n.type).toBe(type);
      }
    }
  });

  it('keeps elites and naps out of floors 1-5, naps out of floor 14, and caps Bug rooms', () => {
    for (const seed of SEEDS) {
      const m = generateMap(seed);
      let bugs = 0;
      for (const n of nodes(m)) {
        if (n.floor < 5) expect(['elite', 'rest']).not.toContain(n.type);
        if (n.floor === 13) expect(n.type).not.toBe('rest');
        if (n.type === 'bug') { bugs++; expect(n.floor).toBeGreaterThanOrEqual(3); }
        expect(n.type).not.toBe('boss');
      }
      expect(bugs).toBeLessThanOrEqual(MAX_BUGS);
    }
  });

  it('never puts the same special room twice in a row along a path', () => {
    for (const seed of SEEDS) {
      const m = generateMap(seed);
      for (const n of nodes(m)) for (const c of n.next) {
        const child = m.floors[n.floor + 1]?.[c];
        if (child && ['elite', 'rest', 'shop', 'bug'].includes(n.type) && n.floor + 1 !== 14) expect(child.type).not.toBe(n.type);
      }
    }
  });

  it('rolls the free floors close to the target mix', () => {
    const count: Partial<Record<RoomType, number>> = {};
    let total = 0;
    for (const seed of SEEDS) for (const n of nodes(generateMap(seed))) {
      if (n.floor < 5 || n.floor === 8 || n.floor >= 13) continue; // floors where every type is allowed
      count[n.type] = (count[n.type] ?? 0) + 1; total++;
    }
    const share = (t: RoomType) => (count[t] ?? 0) / total;
    expect(share('monster')).toBeGreaterThan(.35); expect(share('monster')).toBeLessThan(.55);
    expect(share('event')).toBeGreaterThan(.15); expect(share('event')).toBeLessThan(.3);
    expect(share('rest')).toBeGreaterThan(.06); expect(share('rest')).toBeLessThan(.16);
    expect(share('elite')).toBeGreaterThan(.05); expect(share('elite')).toBeLessThan(.15);
    expect(share('shop')).toBeGreaterThan(.02); expect(share('shop')).toBeLessThan(.1);
    expect(share('bug')).toBeGreaterThan(.01); expect(share('bug')).toBeLessThan(.08);
  });
});
