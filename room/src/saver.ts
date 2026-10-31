// Saves go one at a time, each sending the newest layout, so a slow response can't
// overwrite a later edit and the pet never ends up with an older layout than the page.
// A response only replaces the page's layout when no edit came after it: a failed save
// with a newer edit queued leaves that edit alone, and the newer save sends it.

export interface SaveIO<L, R extends {layout: L}> {
  get(): L;
  set(layout: L): void;
  put(layout: L): Promise<R>;
  /** After each save lands. */
  saved(r: R): void;
  /** After each save fails, once the page is back on the last saved layout or a newer edit. */
  failed(e: Error): void;
}

export function saveQueue<L, R extends {layout: L}>(io: SaveIO<L, R>) {
  let saved = structuredClone(io.get());
  let queue = Promise.resolve();
  let edits = 0;

  async function save(mine: number) {
    if (mine !== edits) return;   // a newer edit is queued and will send this one's changes too
    try {
      const r = await io.put(io.get());
      saved = structuredClone(r.layout);
      if (mine === edits) io.set(r.layout);
      io.saved(r);
    } catch (e) {
      if (mine === edits) io.set(structuredClone(saved));
      io.failed(e as Error);
    }
  }

  /** Show `next` now and queue it to be saved; resolves once every save so far has settled. */
  return function commit(next: L): Promise<void> {
    io.set(next);
    const mine = ++edits;
    queue = queue.then(() => save(mine));
    return queue;
  };
}
