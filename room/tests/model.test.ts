import {describe, expect, it} from 'vitest';
import catalogJson from '../../content/room/catalog.json';
import {
  cellsOf, depthOf, footprint, itemPolys, placementError, pointInPoly, project, rotateBox, rotatePoint, slotsOf, unproject,
} from '../src/model';
import type {Catalog, Item, Placed} from '../src/model';

const cat = catalogJson as unknown as Catalog;
const byId = new Map(cat.items.map(i => [i.id, i]));
const item = (id: string) => byId.get(id)!;
const place = (id: string, itemId: string, x: number, y: number, rot = 0): Placed => ({id, item: itemId, x, y, rot});

describe('projection', () => {
  it('unproject inverts project on the floor', () => {
    for (const [x, y] of [[0, 0], [3.5, 1.25], [8, 8], [0.2, 7.9]]) {
      const [sx, sy] = project(x, y);
      const [gx, gy] = unproject(sx, sy);
      expect(gx).toBeCloseTo(x);
      expect(gy).toBeCloseTo(y);
    }
  });

  it('height moves points straight up', () => {
    const [x0, y0] = project(2, 3, 0), [x1, y1] = project(2, 3, 1);
    expect(x1).toBe(x0);
    expect(y1).toBeLessThan(y0);
  });
});

describe('rotation', () => {
  it('footprint swaps on odd turns', () => {
    expect(footprint(item('shell_bed'), 0)).toEqual([2, 3]);
    expect(footprint(item('shell_bed'), 1)).toEqual([3, 2]);
    expect(footprint(item('shell_bed'), 2)).toEqual([2, 3]);
  });

  it('every box stays inside the rotated footprint, and four turns are identity', () => {
    for (const it of cat.items) {
      for (const b of it.boxes) {
        for (let r = 0; r < 4; r++) {
          const rb = rotateBox(b, it.size, r);
          const [fw, fd] = footprint(it, r);
          expect(rb.at[0]).toBeGreaterThanOrEqual(-1e-9);
          expect(rb.at[1]).toBeGreaterThanOrEqual(-1e-9);
          expect(rb.at[0] + rb.size[0]).toBeLessThanOrEqual(fw + 1e-9);
          expect(rb.at[1] + rb.size[1]).toBeLessThanOrEqual(fd + 1e-9);
        }
        const back = rotateBox(b, it.size, 4);
        back.at.forEach((v, i) => expect(v).toBeCloseTo(b.at[i]));
      }
    }
  });

  it('points rotate with the footprint', () => {
    // 2×3 bed, the slot near the foot end; a quarter turn puts the bed 3 wide and 2 deep
    expect(rotatePoint([1, 1.6], [2, 3], 1)).toEqual([1.4, 1]);
    expect(rotatePoint([1, 1.6], [2, 3], 2)).toEqual([1, 3 - 1.6]);
  });
});

describe('placement rules (same cases as tests/test_room.py)', () => {
  const err = (placed: Placed[], c: Placed, ignore?: string) => placementError(cat, byId, placed, c, ignore);

  it('accepts a free spot', () => {
    expect(err([], place('a', 'shell_bed', 0, 0))).toBeNull();
  });

  it('rejects out of bounds, honouring rotation', () => {
    expect(err([], place('a', 'shell_bed', 7, 0))).toMatch('出界');
    expect(err([], place('a', 'shell_bed', 5, 0, 1))).toBeNull();
    expect(err([], place('a', 'shell_bed', 6, 0, 1))).toMatch('出界');
  });

  it('rejects overlap on the same layer only', () => {
    const bed = place('a', 'shell_bed', 0, 0);
    expect(err([bed], place('b', 'coral_stool', 1, 2))).toMatch('叠在一起');
    const rug = place('a', 'round_rug', 2, 2);
    expect(err([rug], place('b', 'coral_stool', 3, 3))).toBeNull();
    expect(err([rug], place('b', 'lifebuoy_rug', 3, 3))).toMatch('叠在一起');
  });

  it('ignores the piece being moved', () => {
    const bed = place('a', 'shell_bed', 0, 0);
    expect(err([bed], place('a', 'shell_bed', 0, 1), 'a')).toBeNull();
  });

  it('cellsOf covers the footprint', () => {
    expect(cellsOf(item('study_desk'), {x: 3, y: 4, rot: 1})).toEqual([[3, 4], [3, 5]]);
  });
});

describe('drawing and slots', () => {
  it('each box gives three faces, and clicking the middle of the top face hits', () => {
    const stool = item('coral_stool');
    const polys = itemPolys(stool, {x: 2, y: 2, rot: 0});
    expect(polys).toHaveLength(stool.boxes.length * 3);
    const [cx, cy] = project(2.5, 2.5, 0.42);
    expect(polys.some(p => pointInPoly(cx, cy, p.points))).toBe(true);
    expect(polys.some(p => pointInPoly(cx + 500, cy, p.points))).toBe(false);
  });

  it('depth grows towards the viewer', () => {
    const it0 = item('pothos');
    expect(depthOf(it0, {x: 5, y: 5, rot: 0})).toBeGreaterThan(depthOf(it0, {x: 1, y: 1, rot: 0}));
  });

  it('slots land inside the room, lying ones on top of the bed', () => {
    const slots = slotsOf(item('shell_bed'), place('a', 'shell_bed', 0, 0), cat.room);
    expect(slots.map(s => s.pose)).toEqual(['sleep', 'lie']);
    expect(slots[0].z).toBeGreaterThan(0.3);
    const table = slotsOf(item('driftwood_table'), place('t', 'driftwood_table', 6, 6), cat.room);
    expect(table[0].y).toBeLessThanOrEqual(cat.room.d - 0.3);
    const stool = slotsOf(item('coral_stool'), place('s', 'coral_stool', 1, 1), cat.room);
    expect(stool[0]).toMatchObject({pose: 'sit', x: 1.5, y: 1.5, z: 0.42});
  });

  it('every item has something to draw', () => {
    for (const it of cat.items as Item[]) expect(itemPolys(it, {x: 0, y: 0, rot: 0}).length).toBeGreaterThan(0);
  });
});
