import {describe, expect, it} from 'vitest';
import {saveQueue} from '../src/saver';

type L = {n: number};
type R = {layout: L};

/** A page holding layout {n: 0}, whose saves wait until the test settles them one by one. */
function page() {
  let layout: L = {n: 0};
  const sent: L[] = [];
  const pending: {ok(r: R): void; fail(e: Error): void}[] = [];
  const errors: string[] = [];
  const commit = saveQueue<L, R>({
    get: () => layout,
    set: next => { layout = next; },
    put: l => {
      sent.push(l);
      return new Promise((ok, fail) => pending.push({ok, fail}));
    },
    saved: () => {},
    failed: e => errors.push(e.message),
  });
  const flush = () => new Promise(r => setTimeout(r));
  return {commit, sent, pending, errors, flush, layout: () => layout};
}

describe('save queue', () => {
  it('keeps an edit made while an earlier save fails, and sends it next', async () => {
    const p = page();
    p.commit({n: 1});
    await p.flush();
    const done = p.commit({n: 2});   // edit B while A is in flight
    p.pending[0].fail(new Error('A failed'));
    await p.flush();
    expect(p.errors).toEqual(['A failed']);
    expect(p.layout()).toEqual({n: 2});
    expect(p.sent).toEqual([{n: 1}, {n: 2}]);
    p.pending[1].ok({layout: {n: 2}});
    await done;
    expect(p.layout()).toEqual({n: 2});
  });

  it('rolls back to the last saved layout when the newest save fails', async () => {
    const p = page();
    p.commit({n: 1});
    await p.flush();
    p.pending[0].ok({layout: {n: 1}});
    await p.flush();
    const done = p.commit({n: 2});
    await p.flush();
    p.pending[1].fail(new Error('nope'));
    await done;
    expect(p.layout()).toEqual({n: 1});
  });

  it('a late response does not overwrite a newer edit', async () => {
    const p = page();
    p.commit({n: 1});
    await p.flush();
    const done = p.commit({n: 2});
    p.pending[0].ok({layout: {n: 1}});
    await p.flush();
    expect(p.layout()).toEqual({n: 2});
    p.pending[1].ok({layout: {n: 2}});
    await done;
    expect(p.layout()).toEqual({n: 2});
  });

  it('sends only the newest of edits queued behind one save', async () => {
    const p = page();
    p.commit({n: 1});
    await p.flush();
    p.commit({n: 2});
    const done = p.commit({n: 3});
    p.pending[0].ok({layout: {n: 1}});
    await p.flush();
    expect(p.sent).toEqual([{n: 1}, {n: 3}]);
    p.pending[1].ok({layout: {n: 3}});
    await done;
    expect(p.layout()).toEqual({n: 3});
  });
});
