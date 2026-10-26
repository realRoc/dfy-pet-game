import {outlined, type Painter} from './pixel';

// Q-style monsters drawn in code: round bodies, big eyes, two-tone shading and
// a dark outline added afterwards. All of them face left, toward the hero.
export type EnemyPose = 'idle' | 'wind' | 'attack' | 'hurt';

export interface EnemyArt {
  w: number;
  h: number;
  /** Hovering monsters float this far above the ground line. */
  hover: number;
  outline: string;
  draw(p: Painter, t: number, pose: EnemyPose): void;
}

const eye = (p: Painter, x: number, y: number, pose: EnemyPose, t: number, r = 3) => {
  if (pose === 'hurt') { p.line([[x - 2, y - 2], [x + 1, y], [x - 2, y + 2]], '#2a1d24'); return; }
  if (Math.floor(t / 2900) % 4 === 1 && t % 2900 < 120) { p.rect(x - r, y, r * 2, 1, '#2a1d24'); return; }
  p.ellipse(x, y, r, r, '#fffdf4');
  p.rect(x - r + 1, y - 1, 2, 3, '#2a1d24');
  p.rect(x - r + 1, y - 1, 1, 1, '#ffffff');
};

const ART: Record<string, EnemyArt> = {
  dummy: {
    w: 46, h: 68, hover: 0, outline: '#3d3626',
    draw(p, _t, pose) {
      const {rect, poly, ellipse} = p, x = 23, y = 67, lean = pose === 'hurt' ? 2 : pose === 'attack' ? -3 : 0;
      p.ctx.save(); p.ctx.translate(lean, 0);
      rect(x - 3, y - 49, 7, 49, '#625c48'); rect(x - 1, y - 49, 2, 47, '#b3a477'); rect(x - 7, y - 3, 15, 4, '#77735b');
      poly([[x - 19, y - 54], [x - 16, y - 58], [x + 16, y - 58], [x + 19, y - 53], [x + 17, y - 49], [x - 17, y - 49]], '#9c835d');
      rect(x - 16, y - 53, 32, 23, '#ad9366'); rect(x - 17, y - 50, 2, 19, '#6b6349'); rect(x + 14, y - 52, 3, 22, '#7e7151');
      for (let yy = -50; yy <= -32; yy += 4) { rect(x - 14, y + yy, 28, 1, '#ceb482'); rect(x - 13, y + yy + 1, 26, 1, '#9c835d'); }
      rect(x - 21, y - 50, 42, 4, '#776c4e'); rect(x - 23, y - 51, 5, 6, '#c0aa76'); rect(x + 18, y - 51, 5, 6, '#c0aa76');
      ellipse(x, y - 41, 7, 7, '#d5be8d'); ellipse(x, y - 41, 5, 5, '#9c654d'); ellipse(x, y - 41, 2, 2, '#e6cf99');
      rect(x - 8, y - 65, 16, 8, '#a78a60'); rect(x - 10, y - 64, 20, 5, '#b79b6c'); rect(x - 7, y - 66, 14, 2, '#d7bd88');
      if (pose === 'hurt') { p.line([[x - 6, y - 63], [x - 3, y - 61]], '#5c6150'); p.line([[x + 3, y - 61], [x + 6, y - 63]], '#5c6150'); }
      else { rect(x - 5, y - 62, 2, 2, '#5c6150'); rect(x + 4, y - 62, 2, 2, '#5c6150'); }
      p.ctx.restore();
    },
  },

  crab: {
    w: 50, h: 34, hover: 0, outline: '#5a1f1a',
    draw(p, t, pose) {
      const {rect, ellipse, line} = p;
      const bob = pose === 'idle' ? Math.round(Math.sin(t / 260)) : 0;
      const raise = pose === 'wind' ? -5 : pose === 'attack' ? -2 : 0;
      const snap = pose === 'attack' || Math.floor(t / 420) % 3 === 0;
      for (let i = 0; i < 3; i++) {
        line([[12 + i * 4, 25 + bob], [8 + i * 4, 32]], '#b8473a', 2);
        line([[34 + i * 4, 25 + bob], [38 + i * 4, 32]], '#b8473a', 2);
      }
      // Claws on stubby arms, the left one bigger because it does the pinching.
      for (const [cx, r] of [[6, 7], [44, 5]] as const) {
        const cy = 13 + raise + bob;
        line([[cx < 25 ? 12 : 38, 20 + bob], [cx, cy + 3]], '#c4503d', 3);
        ellipse(cx, cy, r, r - 1, '#e0674f');
        rect(cx - r + 2, cy - r + 2, r, 2, '#f39a7c');
        if (snap) line([[cx - r, cy - 1], [cx, cy + 1]], '#7a2a22', 1);
      }
      ellipse(25, 22 + bob, 17, 9, '#e0674f');
      ellipse(25, 18 + bob, 12, 3, '#f2906e');
      rect(14, 27 + bob, 22, 2, '#f4c39a');
      rect(20, 8 + bob, 2, 8, '#c4503d'); rect(30, 8 + bob, 2, 8, '#c4503d');
      eye(p, 20, 7 + bob, pose, t); eye(p, 30, 7 + bob, pose, t + 600);
      rect(15, 23 + bob, 3, 1, '#f6a3a0'); rect(32, 23 + bob, 3, 1, '#f6a3a0');
      if (pose === 'attack' || pose === 'hurt') ellipse(24, 23 + bob, 2, 2, '#7a2a22');
      else { rect(22, 23 + bob, 2, 1, '#7a2a22'); rect(25, 23 + bob, 2, 1, '#7a2a22'); }
    },
  },

  gull: {
    w: 46, h: 36, hover: 30, outline: '#3a4350',
    draw(p, t, pose) {
      const {rect, ellipse, poly} = p;
      const flap = pose === 'hurt' ? 0 : Math.sin(t / (pose === 'wind' ? 50 : 110));
      const dive = pose === 'attack' ? 3 : 0;
      // Far wing, body, near wing, so the flap reads in front of the body.
      poly([[24, 15 + dive], [30, 2 + flap * 8], [38, 4 + flap * 6], [32, 17 + dive]], '#8e9aa8');
      poly([[32, 18 + dive], [45, 13 + dive], [44, 21 + dive], [33, 23 + dive]], '#d8dee4');
      ellipse(24, 19 + dive, 12, 7, '#fbfbf6');
      rect(16, 23 + dive, 16, 2, '#dfe5ea');
      ellipse(12, 13 + dive, 7, 6, '#fbfbf6');
      poly([[6, 13 + dive], [0, 15 + dive], [6, 17 + dive]], '#f0a43a');
      rect(4, 15 + dive, 2, 1, '#c8742a');
      eye(p, 10, 11 + dive, pose, t, 2);
      rect(13, 15 + dive, 2, 1, '#f6b3b0');
      poly([[18, 15 + dive], [24, 1 - flap * 9], [32, 3 - flap * 7], [28, 18 + dive]], '#b3bec9');
      rect(21, 26 + dive, 2, 3, '#f0a43a'); rect(27, 26 + dive, 2, 3, '#f0a43a');
      // The stolen rice ball.
      poly([[20, 35], [25, 27], [30, 35]], '#fbf6ea');
      rect(22, 32, 6, 3, '#2c3a33');
    },
  },

  jelly: {
    w: 66, h: 76, hover: 8, outline: '#4a2a63',
    draw(p, t, pose) {
      const {rect, ellipse, line} = p;
      const pulse = Math.sin(t / 380), squash = pose === 'hurt' ? 3 : pose === 'wind' ? -3 : Math.round(pulse * 1.5);
      for (let i = 0; i < 6; i++) {
        const x0 = 12 + i * 8.4, pts: [number, number][] = [];
        for (let y = 38; y <= 74; y += 3) pts.push([x0 + Math.sin(t / 220 + i + y * .14) * (pose === 'attack' ? 4 : 2) - (pose === 'attack' ? (y - 38) * .25 : 0), y]);
        line(pts, i % 2 ? '#a77cd0' : '#c49ae6', 2);
      }
      ellipse(33, 38, 27, 4, '#8f62bb');
      ellipse(33, 25 + squash / 2, 28 - squash, 22 + squash, '#c79be6');
      rect(4, 26, 58, 14, '#c79be6');
      ellipse(33, 38, 29, 3, '#b07fd8');
      ellipse(24, 12 + squash, 9, 4, '#e6cbf7');
      rect(17, 10 + squash, 4, 2, '#ffffff');
      if (pose === 'hurt') { line([[22, 25], [26, 27], [22, 29]], '#3b2150'); line([[44, 25], [40, 27], [44, 29]], '#3b2150'); }
      else { rect(21, 23, 3, 6, '#3b2150'); rect(39, 23, 3, 6, '#3b2150'); rect(21, 23, 1, 2, '#ffffff'); rect(39, 23, 1, 2, '#ffffff'); }
      rect(15, 30, 4, 2, '#f2a5c6'); rect(44, 30, 4, 2, '#f2a5c6');
      if (pose === 'attack') ellipse(31, 32, 3, 2, '#3b2150'); else rect(29, 32, 5, 1, '#3b2150');
    },
  },

  // 野鸡进程: a little program window that grew a comb, a beak and chicken feet.
  process: {
    w: 34, h: 34, hover: 0, outline: '#2a2f3a',
    draw(p, t, pose) {
      const {rect, poly} = p;
      const bob = pose === 'idle' ? Math.round(Math.sin(t / 180)) : 0, lean = pose === 'attack' ? -3 : pose === 'hurt' ? 2 : 0;
      p.ctx.save(); p.ctx.translate(lean, 0);
      rect(13, 1 + bob, 3, 5, '#e0473a'); rect(16, 0 + bob, 3, 6, '#f05a4a'); rect(19, 2 + bob, 3, 4, '#e0473a');
      rect(5, 6 + bob, 26, 20, '#e8ecf2'); rect(5, 6 + bob, 26, 4, '#4f86d8'); rect(5, 24 + bob, 26, 2, '#c3cbd6');
      rect(26, 7 + bob, 2, 2, '#e0473a'); rect(23, 7 + bob, 2, 2, '#f2c75c'); rect(20, 7 + bob, 2, 2, '#6fbf73');
      eye(p, 12, 15 + bob, pose, t, 2); eye(p, 22, 15 + bob, pose, t + 400, 2);
      rect(9, 21 + bob, 8, 1, '#9aa7b4'); rect(19, 21 + bob, 6, 1, '#9aa7b4');
      poly([[5, 16 + bob], [0, 18 + bob], [5, 20 + bob]], '#f0a43a');
      for (const x of [11, 23]) { rect(x, 26, 2, 5, '#f0a43a'); rect(x - 2, 31, 6, 2, '#f0a43a'); }
      p.ctx.restore();
    },
  },

  // 幻觉海星: very sure of itself, hence the sunglasses.
  starfish: {
    w: 40, h: 40, hover: 0, outline: '#6b2a3a',
    draw(p, t, pose) {
      const {rect, poly} = p;
      const bob = pose === 'idle' ? Math.round(Math.sin(t / 240)) : 0, spin = pose === 'attack' ? .25 : pose === 'hurt' ? -.12 : 0;
      const pts: [number, number][] = [];
      for (let i = 0; i < 10; i++) {
        const a = -Math.PI / 2 + i * Math.PI / 5 + spin, r = i % 2 ? 8 : 19;
        pts.push([20 + Math.cos(a) * r, 21 + bob + Math.sin(a) * r]);
      }
      poly(pts, '#f08a9a');
      for (let i = 0; i < 5; i++) { const a = -Math.PI / 2 + i * Math.PI * .4 + spin; rect(20 + Math.cos(a) * 11, 21 + bob + Math.sin(a) * 11, 2, 2, '#ffd0d6'); }
      if (pose === 'hurt') { p.line([[13, 16 + bob], [17, 19 + bob]], '#3b2150'); p.line([[27, 16 + bob], [23, 19 + bob]], '#3b2150'); }
      else { rect(11, 16 + bob, 8, 4, '#1f2a3a'); rect(21, 16 + bob, 8, 4, '#1f2a3a'); rect(19, 17 + bob, 2, 1, '#1f2a3a'); rect(12, 16 + bob, 2, 1, '#8ddde8'); rect(22, 16 + bob, 2, 1, '#8ddde8'); }
      rect(16, 25 + bob, 7, 1, '#7a2a3a'); rect(22, 24 + bob, 2, 1, '#7a2a3a');
    },
  },

  // 权限不足防火墙: a brick wall on fire with a padlock for a nose.
  firewall: {
    w: 56, h: 62, hover: 0, outline: '#3a1410',
    draw(p, t, pose) {
      const {rect, poly} = p;
      const shake = pose === 'hurt' ? 2 : 0, lean = pose === 'attack' ? -3 : 0;
      p.ctx.save(); p.ctx.translate(lean + shake, 0);
      for (let i = 0; i < 6; i++) {
        const x = 3 + i * 9, h = 10 + Math.round(Math.sin(t / 90 + i * 1.7) * 3);
        poly([[x, 22], [x + 4, 22 - h], [x + 9, 22]], i % 2 ? '#f2a03a' : '#e8642f');
        poly([[x + 2, 22], [x + 4, 26 - h], [x + 7, 22]], '#ffe08a');
      }
      rect(2, 20, 52, 41, '#5a1f1a');
      for (let row = 0; row < 6; row++) for (let i = -1; i < 6; i++) {
        const x = 3 + i * 10 + (row % 2 ? 5 : 0), y = 21 + row * 7;
        const l = Math.max(3, x), r = Math.min(53, x + 9);
        if (r > l) rect(l, y, r - l, 6, (row + i) % 3 ? '#b8473a' : '#a33e33');
      }
      eye(p, 17, 31, pose, t, 3); eye(p, 38, 31, pose, t + 800, 3);
      rect(12, 26, 9, 2, '#3a1410'); rect(34, 26, 9, 2, '#3a1410');
      rect(24, 38, 9, 8, '#f2c75c'); rect(25, 34, 2, 5, '#d5dde4'); rect(30, 34, 2, 5, '#d5dde4'); rect(25, 33, 7, 2, '#d5dde4');
      rect(28, 41, 1, 3, '#5a3c10');
      p.ctx.restore();
    },
  },

  // 下周见老海龟: slow, sleepy, and always about to ship.
  turtle: {
    w: 72, h: 44, hover: 0, outline: '#24361c',
    draw(p, t, pose) {
      const {rect, ellipse} = p;
      const head = pose === 'attack' ? -6 : pose === 'wind' ? 4 : pose === 'hurt' ? 3 : Math.round(Math.sin(t / 700));
      for (const x of [22, 50]) { rect(x, 36, 7, 7, '#8fb86a'); rect(x - 1, 41, 9, 2, '#6f9a4e'); }
      ellipse(15 + head, 26, 11, 9, '#9cc47a');
      ellipse(11 + head, 22, 4, 3, '#b8d898');
      if (pose === 'hurt') p.line([[6 + head, 22], [10 + head, 24], [6 + head, 26]], '#24361c');
      else { rect(5 + head, 22, 6, 1, '#24361c'); rect(6 + head, 23, 4, 2, '#24361c'); rect(7 + head, 23, 1, 1, '#ffffff'); }
      rect(4 + head, 19, 8, 1, '#e6eee0');
      rect(6 + head, 30, 6, 1, '#4f6e3c');
      ellipse(42, 24, 27, 17, '#5f8f4e');
      ellipse(42, 20, 22, 11, '#78a862');
      for (const [x, y] of [[32, 16], [44, 13], [55, 18], [38, 25], [50, 26]] as const) { ellipse(x, y, 4, 3, '#4c7a3d'); rect(x - 1, y - 2, 2, 1, '#9cc47a'); }
      rect(16, 37, 54, 3, '#c9b77a');
    },
  },

  // 乱码虫: segments flicker between colours, as if decoded with the wrong charset.
  glitch: {
    w: 54, h: 30, hover: 4, outline: '#14101c',
    draw(p, t, pose) {
      const {rect, ellipse} = p, f = Math.floor(t / 120);
      const cols = ['#5fe2ff', '#ff5fa8', '#f2c75c', '#9a6bc4', '#6fbf73', '#fbf6ea'];
      for (let i = 5; i >= 0; i--) {
        const x = 9 + i * 8 + (pose === 'attack' ? -i : 0), y = 16 + Math.round(Math.sin(t / 150 + i) * 2);
        ellipse(x, y, 7, 7, cols[Math.floor(p.noise(i * 13 + f) * cols.length)]);
        rect(x - 4, y - 1, 8, 1, '#14101c80');
        if (p.noise(i + f * 7) > .7) rect(x - 7 + Math.round((p.noise(f + i) - .5) * 6), y - 3, 14, 2, cols[(i + f) % cols.length]);
      }
      eye(p, 7, 14, pose, t, 3);
      rect(2, 4, 2, 6, '#14101c'); rect(9, 3, 2, 6, '#14101c'); rect(1, 3, 3, 2, '#ff5fa8'); rect(9, 2, 3, 2, '#5fe2ff');
      rect(3, 20, 6, 1, '#14101c');
    },
  },

  // 黑鲸 · 更强的Agent: the black whale of the Harness icon, red-eyed and wired up.
  blackWhale: {
    w: 116, h: 72, hover: 6, outline: '#0b0f16',
    draw(p, t, pose) {
      const {rect, ellipse, poly} = p;
      const sway = Math.round(Math.sin(t / 500) * 2), lunge = pose === 'attack' ? -6 : pose === 'wind' ? 4 : 0;
      p.ctx.save(); p.ctx.translate(lunge, 0);
      poly([[92, 38], [108, 12 + sway], [115, 10 + sway], [110, 26 + sway], [114, 40 + sway], [104, 40]], '#232a37');
      ellipse(54, 42, 50, 24, '#2a3140');
      ellipse(48, 52, 40, 12, '#c9d0d8');
      for (let i = 0; i < 6; i++) rect(20 + i * 10, 50, 2, 10, '#9aa3ae');
      ellipse(50, 34, 40, 10, '#323b4c');
      poly([[46, 60], [60, 70], [66, 58]], '#1c2230');
      // Red-lit eye and the cables of the harness.
      rect(16, 34, 9, 6, '#0b0f16'); rect(18, 35, 6, 4, pose === 'hurt' ? '#ffffff' : '#ff3b3b'); rect(19, 35, 2, 1, '#ffd0d0');
      p.line([[30, 24], [40, 14], [56, 16], [70, 22]], '#4f86d8', 2);
      p.line([[36, 26], [48, 20], [64, 24]], '#e0473a', 1);
      rect(38, 12, 5, 5, '#8ddde8'); rect(54, 14, 5, 5, '#8ddde8'); rect(68, 20, 5, 5, '#8ddde8');
      rect(5, 46, 12, 2, '#0b0f16');
      if (pose === 'attack') ellipse(10, 47, 6, 3, '#5a1f1a');
      for (let i = 0; i < 3; i++) { const y = 6 - ((t / 6 + i * 20) % 30) / 3; rect(46 + i * 3, 14 + y, 2, 3, '#9ddce4'); }
      p.ctx.restore();
    },
  },
};

export const enemyArt = (kind: string) => ART[kind];

export function renderEnemy(kind: string, t: number, pose: EnemyPose): HTMLCanvasElement {
  const a = ART[kind];
  return outlined(a.w, a.h, a.outline, p => a.draw(p, t, pose));
}
