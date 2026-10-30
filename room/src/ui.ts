// DOM side of the room: furniture catalog, wallpaper and floor pickers, the
// set progress card, the toolbar for a selected piece, hints and toasts.
import {itemPolys, project} from './model';
import type {Catalog, Item, Layout, SetState} from './model';

interface Actions {
  pick(itemId: string): void;
  wallpaper(id: string): void;
  floor(id: string): void;
  rotate(): void;
  stash(): void;
  move(): void;
}

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const esc = (s: string) => s.replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]!));

export class Ui {
  private tab: 'items' | 'walls' | 'floors' = 'items';
  private toastTimer = 0;
  private previews = new Map<string, string>();

  constructor(private cat: Catalog, private act: Actions) {
    for (const it of cat.items) this.previews.set(it.id, preview(it));
    $('tabs').addEventListener('click', e => {
      const t = (e.target as HTMLElement).dataset.tab as typeof this.tab | undefined;
      if (t) { this.tab = t; this.renderList(this.last!); }
    });
    $('list').addEventListener('click', e => {
      const el = (e.target as HTMLElement).closest<HTMLElement>('[data-id]');
      if (!el) return;
      const id = el.dataset.id!;
      if (this.tab === 'items') this.act.pick(id);
      else if (this.tab === 'walls') this.act.wallpaper(id);
      else this.act.floor(id);
    });
    $('toolbar').addEventListener('click', e => {
      const a = (e.target as HTMLElement).dataset.act;
      if (a === 'move') this.act.move();
      if (a === 'rotate') this.act.rotate();
      if (a === 'stash') this.act.stash();
    });
    $('toolbar').addEventListener('pointerdown', e => e.stopPropagation());
  }

  private last: Layout | null = null;

  render(layout: Layout, sets: SetState[], selected: string | null) {
    this.last = layout;
    this.renderList(layout);
    this.renderSets(sets);
    const sel = selected ? layout.placed.find(p => p.id === selected) : null;
    $('toolbar-name').textContent = sel ? this.cat.items.find(i => i.id === sel.item)?.name ?? '' : '';
  }

  private renderList(layout: Layout) {
    for (const b of $('tabs').querySelectorAll<HTMLElement>('[data-tab]')) b.classList.toggle('on', b.dataset.tab === this.tab);
    const counts = new Map<string, number>();
    for (const p of layout.placed) counts.set(p.item, (counts.get(p.item) ?? 0) + 1);
    const setName = new Map(this.cat.sets.map(s => [s.id, s.name]));
    let html = '';
    if (this.tab === 'items') {
      for (const it of this.cat.items) {
        const n = counts.get(it.id) ?? 0;
        html += `<button class="card" data-id="${it.id}">
          <img src="${this.previews.get(it.id)}" alt="">
          <span class="name">${esc(it.name)}</span>
          ${it.set ? `<span class="meta"><i>${esc(setName.get(it.set) ?? '')}</i></span>` : ''}
          ${n ? `<span class="count">已摆 ${n}</span>` : ''}
        </button>`;
      }
    } else {
      const list = this.tab === 'walls' ? this.cat.wallpapers : this.cat.floors;
      const cur = this.tab === 'walls' ? layout.wallpaper : layout.floor;
      for (const s of list) {
        html += `<button class="card swatch${s.id === cur ? ' on' : ''}" data-id="${s.id}">
          <span class="chip" style="background:${s.color};border-color:${s.trim ?? s.alt ?? s.color}"></span>
          <span class="name">${esc(s.name)}</span>${s.id === cur ? '<span class="count">使用中</span>' : ''}
        </button>`;
      }
    }
    $('list').innerHTML = html;
  }

  private renderSets(sets: SetState[]) {
    const itemName = new Map(this.cat.items.map(i => [i.id, i.name]));
    const done = sets.filter(s => s.complete).length;
    $('sets').innerHTML = `
      <div class="score"><b>${done}</b>/${sets.length} 套装集齐</div>
      <ul>${sets.map(s => `<li class="${s.complete ? 'done' : ''}" title="${s.complete ? '已集齐' : '还差：' + esc(s.missing.map(m => itemName.get(m) ?? m).join('、'))}">
        <span>${s.complete ? '✅' : '◻️'} ${esc(s.name)}</span><span>${s.have}/${s.total}</span></li>`).join('')}</ul>`;
  }

  showToolbar(x: number, y: number) {
    const t = $('toolbar');
    t.style.display = 'flex';
    t.style.left = `${Math.round(x - t.offsetWidth / 2)}px`;
    t.style.top = `${Math.max(8, Math.round(y - t.offsetHeight - 10))}px`;
  }

  hideToolbar() {
    $('toolbar').style.display = 'none';
  }

  hint(text: string) {
    $('hint').textContent = text;
  }

  toast(text: string, bad = false) {
    const t = $('toast');
    t.textContent = text;
    t.className = bad ? 'show bad' : 'show';
    clearTimeout(this.toastTimer);
    this.toastTimer = window.setTimeout(() => (t.className = ''), 2600);
  }
}

/** A small picture of a piece of furniture for its catalog card, same polygons as the room. */
function preview(item: Item): string {
  const W = 120, H = 96, dpr = Math.min(2, devicePixelRatio || 1);
  const c = document.createElement('canvas');
  c.width = W * dpr;
  c.height = H * dpr;
  const g = c.getContext('2d');
  if (!g) return '';
  const polys = itemPolys(item, {x: 0, y: 0, rot: 0});
  const xs = polys.flatMap(p => p.points.filter((_, i) => i % 2 === 0)), ys = polys.flatMap(p => p.points.filter((_, i) => i % 2));
  const [fx0] = project(0, item.size[1]), [fx1] = project(item.size[0], 0);
  const minX = Math.min(...xs, fx0), maxX = Math.max(...xs, fx1), minY = Math.min(...ys), maxY = Math.max(...ys);
  const s = Math.min((W - 12) / (maxX - minX), (H - 12) / (maxY - minY), 1.6);
  g.scale(dpr, dpr);
  g.translate((W - (maxX - minX) * s) / 2 - minX * s, (H - (maxY - minY) * s) / 2 - minY * s);
  g.scale(s, s);
  for (const p of polys) {
    g.beginPath();
    for (let i = 0; i < p.points.length; i += 2) (i ? g.lineTo : g.moveTo).call(g, p.points[i], p.points[i + 1]);
    g.closePath();
    g.fillStyle = `#${p.color.toString(16).padStart(6, '0')}`;
    g.fill();
    g.strokeStyle = 'rgba(0,0,0,0.12)';
    g.stroke();
  }
  return c.toDataURL();
}
