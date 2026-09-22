// Geometry/musical constants shared with blender/make_guitar.py.
// Blender coords (x, y, z) map to glTF (x, z, -y): +Y_blender (neck) -> -Z_gltf.

export const SCALE_LEN = 0.648;
export const JOINT_Y = 0.25;
export const NUT_Y = JOINT_Y + SCALE_LEN * (1 - Math.pow(2, -14 / 12));
export const BRIDGE_Y = NUT_Y - SCALE_LEN;

export const FB_TOP = 0.007;
export const FB_NUT_W = 0.0437;
export const FB_END_Y = 0.27;
export const FB_END_W = 0.0605;

export const BRIDGE_X = [-0.0265, -0.0159, -0.0053, 0.0053, 0.0159, 0.0265];
export const NUT_X = [-0.02, -0.012, -0.004, 0.004, 0.012, 0.02];
export const STRING_R = [0.0012, 0.0011, 0.001, 0.0009, 0.0008, 0.0007];
export const STRING_Z_BRIDGE = 0.016;
export const STRING_Z_NUT = 0.0125;

// Standard tuning: E2 A2 D3 G3 B3 E4 (string 6 -> string 1)
export const TUNING = [82.41, 110.0, 146.83, 196.0, 246.94, 329.63];
export const STRING_LABELS = ['E', 'A', 'D', 'G', 'B', 'E'];
export const MAX_FRET = 14;
export const NOTE_NAMES = [
  'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B',
];

export function fretY(n) {
  return NUT_Y - SCALE_LEN * (1 - Math.pow(2, -n / 12));
}

export function fbHalfWidth(y) {
  const t = (NUT_Y - y) / (NUT_Y - FB_END_Y);
  return (FB_NUT_W + (FB_END_W - FB_NUT_W) * t) / 2;
}

export function noteFreq(stringIdx, fret) {
  return TUNING[stringIdx] * Math.pow(2, fret / 12);
}

export function noteName(freq) {
  const midi = Math.round(12 * Math.log2(freq / 440) + 69);
  return NOTE_NAMES[((midi % 12) + 12) % 12] + (Math.floor(midi / 12) - 1);
}

export function blenderToGltf(x, y, z) {
  return [x, z, -y];
}
