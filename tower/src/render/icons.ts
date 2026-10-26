// Hand-placed pixel icons. One character per pixel, '.' is transparent.
const PALETTE: Record<string, string> = {
  k: '#1f2a3a', w: '#fbf6ea', r: '#e2d6bb', b: '#4d7fb8', B: '#2f5a8c', s: '#d5dde4', S: '#9aa7b4', d: '#66727f',
  y: '#f2c75c', o: '#d9853b', R: '#d0574e', g: '#6fbf73', p: '#9a6bc4', P: '#6a3f99', c: '#8ddde8', h: '#4f78d8', H: '#2b438f',
};

const ICONS: Record<string, string[]> = {
  // 剩饭: a bowl with a lopsided mound and a stray grain
  leftovers: [
    '................',
    '..........w.....',
    '.....w.ww.......',
    '....wwwrwww.....',
    '...wwrwwwwww....',
    '..wwwwwwrwwww...',
    '.kkkkkkkkkkkkkk.',
    '.kbbbbbbbbbbbbk.',
    '.kbwbbbbwbbbwbk.',
    '..kbbbbbbbbbbk..',
    '..kBbbbbbbbbBk..',
    '...kBBbbbbBBk...',
    '....kkkkkkkk....',
    '.....kBBBBk.....',
    '....kkkkkkkk....',
    '................',
  ],
  riceCooker: [
    '................',
    '......kkkk......',
    '.....kSSSSk.....',
    '..kkkkkkkkkkkk..',
    '.kwwwwwwwwwwwwk.',
    '.kswwwwwwwwwwsk.',
    '.kkkkkkkkkkkkkk.',
    '.kwwwwwwwwwwwwk.',
    '.kwwkkkkkkkkwwk.',
    '.kwwkcRkkcckwwk.',
    '.kwwkkkkkkkkwwk.',
    '.kwwwwwwwwwwwwk.',
    '.kssssssssssssk.',
    '..kkkkkkkkkkkk..',
    '..kk........kk..',
    '................',
  ],
  ironBasin: [
    '................',
    '................',
    '................',
    '.......w........',
    '......www.......',
    '.......w........',
    'kkkkkkkkkkkkkkkk',
    'kssssssssssssssk',
    'kSswwssssssssSdk',
    '.kSSssssssssSdk.',
    '.kdSSSSSSSSSddk.',
    '..kdSSSSSSSSdk..',
    '...kkddddddkk...',
    '....kkkkkkkk....',
    '................',
    '................',
  ],
  ahoge: [
    '..........kkk...',
    '.........khhhk..',
    '........khhkhk..',
    '........khk.kk..',
    '.......khhk.....',
    '.......khk......',
    '......khhk......',
    '......khk.......',
    '.....khhk.......',
    '.....khk........',
    '....khhk........',
    '...khhk.........',
    '..kkhhhkk.......',
    '.khhhhhhhk......',
    'kHHHHHHHHHk.....',
    '................',
  ],
  attack: [
    '.........kk',
    '........kwk',
    '.......kwk.',
    '......kwsk.',
    '.k...kwsk..',
    '.kk.kwsk...',
    '..kkwsk....',
    '...kkk.....',
    '..kRkkk....',
    '.kRk..k....',
    'kkk........',
  ],
  defend: [
    'kkkkkkkkkkk',
    'kbbbbsbbbbk',
    'kbbbbsbbbbk',
    'kbbbbsbbbbk',
    'kssssssssk.',
    'kbbbbsbbbbk',
    '.kbbbsbbbk.',
    '.kbbbsbbbk.',
    '..kbbsbbk..',
    '...kbsbk...',
    '....kkk....',
  ],
  debuff: [
    '....kkk....',
    '...kpppk...',
    '..kpppppk..',
    '..kpPpPpk..',
    '.kpppppppk.',
    '.kppPPPppk.',
    '.kpPpppPpk.',
    'kpppppppppk',
    'kpppppppppk',
    '.kpppppppk.',
    '..kkkkkkk..',
  ],
  buff: [
    '.....k.....',
    '....kgk....',
    '...kgggk...',
    '..kgggggk..',
    '.kkkgggkkk.',
    '...kgggk...',
    '...kgggk...',
    '...kgggk...',
    '...kgggk...',
    '...kkkkk...',
    '...........',
  ],
  stuff: [
    '.kkkkkkk...',
    '.kwwwwwkkk.',
    '.kwRwRwkwk.',
    '.kwwwwwkwk.',
    '.kwRRRwkwk.',
    '.kwwwwwkwk.',
    '.kwwRwwkwk.',
    '.kwwwwwkwk.',
    '.kkkkkkkwk.',
    '...kwwwwwk.',
    '...kkkkkkk.',
  ],
  idle: [
    '...kkkkk...',
    '..kwwwwwk..',
    '.kwwkkkwwk.',
    '.kwk...kwk.',
    '.kk...kwwk.',
    '.....kwwk..',
    '....kwwk...',
    '....kwk....',
    '....kkk....',
    '....kwk....',
    '....kkk....',
  ],
};

const cache = new Map<string, HTMLCanvasElement>();

export function icon(name: string, scale = 1): HTMLCanvasElement {
  const key = name + '@' + scale;
  const hit = cache.get(key);
  if (hit) return hit;
  const rows = ICONS[name], c = document.createElement('canvas');
  c.width = Math.max(...rows.map(r => r.length)) * scale;
  c.height = rows.length * scale;
  const ctx = c.getContext('2d')!;
  rows.forEach((row, y) => [...row].forEach((ch, x) => {
    if (ch === '.') return;
    ctx.fillStyle = PALETTE[ch];
    ctx.fillRect(x * scale, y * scale, scale, scale);
  }));
  cache.set(key, c);
  return c;
}

export const iconUrl = (name: string) => icon(name).toDataURL();
