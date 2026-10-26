import {CARDS, KEYWORDS, SCHOOLS} from '../content/cards';
import type {CardDef} from '../core/types';
import {icon} from '../render/icons';
import {noise} from '../render/pixel';
import type {Scene} from '../render/scene';

const TYPE_NAME = {attack: '攻击', skill: '技能', power: '能力', status: '状态', curse: '诅咒'} as const;
const POSE_ART: Record<string, string> = {
  strike: 'strike', sweep: 'sweep', smear: 'smear', twist: 'twist',
  ponder: 'ult-ponder', chin: 'ult-chin', eureka: 'ult-eureka', release: 'ult-release', smug: 'ult-smug',
};
const ART_W = 57, ART_H = 35;
const artCache = new Map<string, HTMLCanvasElement>();

/** The small pixel illustration at the top of a card, drawn at 2× by CSS. */
function art(scene: Scene, def: CardDef): HTMLCanvasElement {
  const key = def.art + def.type + (def.cutIn ? 'cut' : '');
  let cached = artCache.get(key);
  if (!cached) {
    const c = document.createElement('canvas'); c.width = ART_W; c.height = ART_H;
    const ctx = c.getContext('2d')!;
    const bands = {attack: ['#e9c8a2', '#e2b48e', '#d69f7e'], skill: ['#b3d6cd', '#9cc6bd', '#86b5ae'], power: ['#ecdca8', '#e2cc8c', '#d4b977'], status: ['#7b7f8c', '#6b6f7c', '#5c606c'], curse: ['#4a3550', '#3d2b44', '#30213a']}[def.type];
    bands.forEach((col, i) => { ctx.fillStyle = col; ctx.fillRect(0, i * 12, ART_W, 12); });
    ctx.fillStyle = '#00000018'; ctx.fillRect(0, ART_H - 6, ART_W, 6);
    const pose = POSE_ART[def.art];
    if (pose) {
      const f = scene.heroFrame(pose), w = Math.round(f.width / 2), h = Math.round(f.height / 2);
      const t = document.createElement('canvas'); t.width = w; t.height = h;
      const tc = t.getContext('2d')!; tc.imageSmoothingQuality = 'high'; tc.drawImage(f, 0, 0, w, h);
      const d = tc.getImageData(0, 0, w, h);
      for (let i = 3; i < d.data.length; i += 4) d.data[i] = d.data[i] > 110 ? 255 : 0;
      tc.putImageData(d, 0, 0);
      ctx.drawImage(t, Math.round((ART_W - w) / 2), ART_H - h + 1);
      // 巨鲸破浪 gets the whale itself behind the hero.
      if (def.cutIn) { ctx.globalCompositeOperation = 'destination-over'; ctx.drawImage(scene.whaleIcon, 2, 4, 30, 18); ctx.globalCompositeOperation = 'source-over'; }
    } else if (def.art === 'busy') {
      for (let i = 0; i < 8; i++) {
        const a = i * Math.PI / 4;
        ctx.fillStyle = i === 0 ? '#fbf6ea' : i < 3 ? '#c79be6' : '#9095a3';
        ctx.fillRect(Math.round(28 + Math.cos(a) * 9), Math.round(16 + Math.sin(a) * 9), 3, 3);
      }
      for (let y = 0; y < ART_H; y += 3) { ctx.fillStyle = noise(y) > .6 ? '#ff5fa840' : '#5fe2ff30'; ctx.fillRect(Math.round(noise(y * 3) * 30), y, 20, 1); }
    } else if (def.art === 'bug') {
      const ic = icon('room-bug', 3);
      ctx.drawImage(ic, Math.round((ART_W - ic.width) / 2), Math.round((ART_H - ic.height) / 2));
      for (let y = 0; y < ART_H; y += 2) if (noise(y * 5) > .55) { ctx.fillStyle = noise(y) > .5 ? '#ff5fa860' : '#5fe2ff50'; ctx.fillRect(Math.round(noise(y * 3) * 40), y, 16, 1); }
    } else {
      const ic = icon(def.art === 'bowl' ? 'ironBasin' : 'leftovers', 2);
      ctx.drawImage(ic, Math.round((ART_W - ic.width) / 2), ART_H - ic.height + 2);
    }
    artCache.set(key, cached = c);
  }
  const copy = document.createElement('canvas'); copy.width = ART_W; copy.height = ART_H;
  copy.getContext('2d')!.drawImage(cached, 0, 0);
  copy.className = 'art';
  return copy;
}

// Longest first, so 思考完毕 wins over 思考.
const KEYWORD_RE = new RegExp(Object.keys(KEYWORDS).sort((a, b) => b.length - a.length).join('|'), 'g');

export function cardText(def: CardDef, dmg: number | null): string {
  const base = def.ops.find(o => o.op === 'damage');
  let html = def.text.replace(KEYWORD_RE, k => `<em>${k}</em>`);
  if (base && base.op === 'damage' && dmg !== null) {
    const cls = dmg > base.n ? 'up' : dmg < base.n ? 'down' : '';
    html = html.replace('{d}', `<b class="${cls}">${dmg}</b>`);
  }
  return html;
}

export function keywordTips(def: CardDef): string {
  const found = [...new Set(def.text.match(KEYWORD_RE) ?? [])];
  const lines = found.map(k => `<p><b>${k}</b>　${KEYWORDS[k]}</p>`);
  if (def.school) lines.unshift(`<p class="school ${def.school}"><b>${SCHOOLS[def.school].name}</b>　${SCHOOLS[def.school].tip}</p>`);
  if (def.exhaust && !found.includes('消耗')) lines.push(`<p><b>消耗</b>　${KEYWORDS.消耗}</p>`);
  if (def.flavor) lines.push(`<p class="flavor">${def.flavor}</p>`);
  return lines.join('');
}

export function cardElement(scene: Scene, id: string, dmg: number | null, cost = CARDS[id].cost): HTMLDivElement {
  const def = CARDS[id], el = document.createElement('div');
  el.className = `card ${def.type} ${def.rarity}${def.school ? ' school-' + def.school : ''}`;
  const kind = TYPE_NAME[def.type] + (def.school ? ' · ' + SCHOOLS[def.school].name : '');
  if (def.upgraded) el.classList.add('upgraded');
  const costCls = cost < def.cost ? ' cheap' : '';
  // Long meme names shrink to fit the title bar instead of being cut off.
  const width = [...def.name].reduce((w, ch) => w + (ch.charCodeAt(0) > 255 ? 1 : .55), 0);
  const size = Math.min(15, Math.floor(100 / width * 10) / 10);
  el.innerHTML = `${def.unplayable ? '' : `<div class="cost${costCls}">${cost}</div>`}<div class="name" style="font-size:${size}px">${def.name}</div><div class="frame"></div><div class="kind">${kind}</div><div class="text">${cardText(def, dmg)}</div>`;
  el.querySelector('.frame')!.append(art(scene, def));
  return el;
}
