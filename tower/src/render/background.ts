import {W, type Painter} from './pixel';

// The seaside training ground from the whale-tail study. The battle view lifts
// it by GROUND_LIFT so feet stand at y=147 and the hand has room underneath.
export const GROUND_LIFT = 28;

export function beach(p: Painter, t: number, lift = 0) {
  const {rect, poly, line, noise, ctx} = p;
  rect(0, 0, W, 216, '#dace9e');
  ctx.save();
  ctx.translate(0, -lift);
  const sky = ['#71898e', '#829b9a', '#9eb2a7', '#bdc9b2', '#d8d8b5', '#e8dfba'];
  rect(0, -lift, W, lift + 1, sky[0]);
  sky.forEach((c, i) => rect(0, i * 17, W, 17, c));
  rect(267, 40, 25, 25, '#f9e8b5'); rect(263, 45, 33, 15, '#f9e8b5');
  ([[40, 47, 44], [183, 30, 26], [320, 60, 39]] as const).forEach(([x, y, w]) => { rect(x, y, w, 3, '#dce0c1'); rect(x + 9, y - 3, w / 2, 3, '#dce0c1'); });
  poly([[0, 99], [23, 85], [48, 90], [70, 66], [90, 69], [122, 98], [163, 81], [189, 91], [220, 101]], '#819f9a');
  poly([[0, 103], [37, 100], [68, 86], [80, 89], [98, 103], [124, 94], [156, 106], [222, 100], [256, 89], [280, 95], [305, 76], [322, 87], [345, 83], [384, 100], [384, 118], [0, 118]], '#6c9392');
  rect(0, 109, W, 27, '#7baca6'); rect(0, 120, W, 18, '#8fbbb1');
  for (let i = 0; i < 29; i++) {
    const x = (noise(i + 7) * W + t * .004 * (i % 2 ? 1 : -1) + W * 10) % W;
    rect(x, 113 + noise(i + 11) * 21, 4 + noise(i + 21) * 19, 1, i % 3 ? '#abd0bd' : '#d5dfc0');
  }
  poly([[0, 140], [60, 132], [123, 141], [182, 132], [238, 137], [290, 131], [384, 139], [384, 216 + lift], [0, 216 + lift]], '#cbc79b');
  poly([[0, 153], [44, 144], [99, 150], [154, 143], [213, 148], [265, 141], [327, 146], [384, 139], [384, 216 + lift], [0, 216 + lift]], '#dace9e');
  poly([[0, 183], [74, 176], [142, 182], [221, 175], [290, 184], [384, 172], [384, 216 + lift], [0, 216 + lift]], '#c6bc8d');
  for (let i = 0; i < 160; i++) { const x = noise(i + 89) * W, y = 143 + noise(i + 198) * (54 + lift); rect(x, y, i % 4 ? 2 : 4, 1, i % 3 ? '#b9b48a' : '#eee1b2'); }
  for (let i = 0; i < 8; i++) { const x = 8 + i * 5, y = 147 + noise(i) * 7; line([[x - 2, y], [x - 3, y - 5], [x, y - 1], [x + 2, y - 7]], '#798e72'); }
  rect(362, 102, 2, 54, '#6b7d72'); poly([[364, 103], [384, 108], [382, 119], [364, 116]], '#718b83');
  ([[43, 179], [331, 186], [19, 163], [180, 196]] as const).forEach(([x, y]) => { poly([[x, y], [x + 3, y - 4], [x + 10, y - 3], [x + 12, y + 1]], '#969e85'); rect(x + 4, y - 3, 5, 1, '#c6c8a4'); });
  ctx.restore();
}
