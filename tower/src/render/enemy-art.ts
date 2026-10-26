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
};

export const enemyArt = (kind: string) => ART[kind];

export function renderEnemy(kind: string, t: number, pose: EnemyPose): HTMLCanvasElement {
  const a = ART[kind];
  return outlined(a.w, a.h, a.outline, p => a.draw(p, t, pose));
}
