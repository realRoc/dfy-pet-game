// Pixel drawing helpers shared by the battle scene and the ultimate close-up.
// Every coordinate is rounded so shapes stay on the 384×216 grid.

export const W = 384, H = 216;

export const clamp = (n: number, a = 0, b = 1) => Math.min(b, Math.max(a, n));
export const mix = (a: number, b: number, t: number) => a + (b - a) * t;
export const ease = (n: number) => 1 - Math.pow(1 - clamp(n), 3);
export const smooth = (n: number) => { const p = clamp(n); return p * p * (3 - 2 * p); };
export const noise = (n: number) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

export type Pt = [number, number];

export interface Painter {
  ctx: CanvasRenderingContext2D;
  rect(x: number, y: number, w: number, h: number, c: string): void;
  poly(points: Pt[], c: string): void;
  line(points: Pt[], c: string, width?: number): void;
  text(value: string, x: number, y: number, color?: string, size?: number, align?: CanvasTextAlign): void;
  ellipse(x: number, y: number, rx: number, ry: number, c: string): void;
  ring(x: number, y: number, rx: number, ry: number, c: string, alpha?: number): void;
  star(x: number, y: number, r: number, c: string): void;
  noise(n: number): number;
}

export function painter(ctx: CanvasRenderingContext2D): Painter {
  const R = Math.round;
  const p: Painter = {
    ctx,
    rect(x, y, w, h, c) { ctx.fillStyle = c; ctx.fillRect(R(x), R(y), R(w), R(h)); },
    poly(points, c) {
      ctx.fillStyle = c; ctx.beginPath();
      points.forEach(([x, y], i) => (i ? ctx.lineTo(R(x), R(y)) : ctx.moveTo(R(x), R(y))));
      ctx.closePath(); ctx.fill();
    },
    line(points, c, width = 1) {
      ctx.strokeStyle = c; ctx.lineWidth = width; ctx.beginPath();
      points.forEach(([x, y], i) => (i ? ctx.lineTo(R(x), R(y)) : ctx.moveTo(R(x), R(y))));
      ctx.stroke();
    },
    text(value, x, y, color = '#e7ecd8', size = 7, align = 'left') {
      ctx.fillStyle = color; ctx.font = `${size}px monospace`; ctx.textAlign = align; ctx.fillText(value, R(x), R(y));
    },
    ellipse(x, y, rx, ry, c) {
      for (let row = -ry; row <= ry; row++) {
        const half = Math.sqrt(Math.max(0, 1 - (row / ry) ** 2)) * rx;
        p.rect(x - half, y + row, half * 2, 1, c);
      }
    },
    ring(x, y, rx, ry, c, alpha = 1) {
      ctx.save(); ctx.globalAlpha *= clamp(alpha);
      for (let i = 0; i < 32; i++) { const a = i * Math.PI / 16; p.rect(x + Math.cos(a) * rx, y + Math.sin(a) * ry, 2, 1, c); }
      ctx.restore();
    },
    star(x, y, r, c) { p.rect(x - 1, y - r, 2, r * 2 + 1, c); p.rect(x - r, y - 1, r * 2 + 1, 2, c); },
    noise,
  };
  return p;
}

/** Draws into a small offscreen canvas, then rings the silhouette with a 1 px outline. */
export function outlined(w: number, h: number, outline: string, draw: (p: Painter) => void): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = w + 2; c.height = h + 2;
  const ctx = c.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;
  ctx.translate(1, 1);
  draw(painter(ctx));
  const img = ctx.getImageData(0, 0, c.width, c.height), d = img.data, solid = new Uint8Array(c.width * c.height);
  for (let i = 0; i < solid.length; i++) solid[i] = d[i * 4 + 3] > 127 ? 1 : 0;
  const [r, g, b] = hex(outline);
  for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
    const i = y * c.width + x;
    d[i * 4 + 3] = solid[i] ? 255 : 0;
    if (solid[i]) continue;
    const near = (x > 0 && solid[i - 1]) || (x < c.width - 1 && solid[i + 1]) || (y > 0 && solid[i - c.width]) || (y < c.height - 1 && solid[i + c.width]);
    if (near) { d[i * 4] = r; d[i * 4 + 1] = g; d[i * 4 + 2] = b; d[i * 4 + 3] = 255; }
  }
  ctx.putImageData(img, 0, 0);
  return c;
}

export function hex(c: string): [number, number, number] {
  const n = parseInt(c.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** A white-filled copy for hit flashes. */
export function silhouette(src: CanvasImageSource & {width: number; height: number}, color = '#ffffff'): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = src.width; c.height = src.height;
  const ctx = c.getContext('2d')!;
  ctx.drawImage(src, 0, 0);
  ctx.globalCompositeOperation = 'source-in';
  ctx.fillStyle = color; ctx.fillRect(0, 0, c.width, c.height);
  return c;
}
