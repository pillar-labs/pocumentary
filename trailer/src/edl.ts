// Single source of truth for timing + copy. All durations are in FRAMES at 30fps.
// Clip files are the exact-trimmed segments produced by scripts/prep.sh, so the
// composition just plays each one whole; timing here mirrors the TransitionSeries.

export const FPS = 30;
export const WIDTH = 1080;
export const HEIGHT = 1920;

export type Clip = {
  id: string;
  file: string;
  dur: number; // frames
  overlapBefore: number; // transition frames that overlap the previous clip (0 = hard cut)
  muted?: boolean;
};

// Order == timeline order. overlapBefore>0 means a crossfade with the previous clip.
export const CLIPS: Clip[] = [
  // Sit-down montage: longer holds + slow crossfades so it breathes.
  {id: 'sit1', file: 'clips/s1_sit.mp4', dur: 69, overlapBefore: 0, muted: true}, // empty beat -> walks in
  {id: 'sit2', file: 'clips/s2_sit.mp4', dur: 69, overlapBefore: 12, muted: true}, // sets the laptop down
  {id: 'sit3', file: 'clips/s3_sit.mp4', dur: 63, overlapBefore: 12, muted: true}, // lowering into the seat
  {id: 'sit4', file: 'clips/s4_sit.mp4', dur: 72, overlapBefore: 12, muted: true}, // settles, holds
  {id: 'listen', file: 'clips/listen.mp4', dur: 96, overlapBefore: 10}, // dissolve in: "what they know. oh boy."
  {id: 'probCursor', file: 'clips/prob_cursor.mp4', dur: 102, overlapBefore: 0}, // "cursor here, our codex here"
  {id: 'probA', file: 'clips/prob_a.mp4', dur: 263, overlapBefore: 0}, // "...racking up the vulnerabilities" + breath
  {id: 'probGtfo', file: 'clips/prob_gtfo.mp4', dur: 91, overlapBefore: 0}, // "it's either PoC or GTFO"
  {id: 'revealA', file: 'clips/reveal_a.mp4', dur: 108, overlapBefore: 0}, // "today we're releasing PoCumentary"
  {id: 'revealB', file: 'clips/reveal_b.mp4', dur: 206, overlapBefore: 0}, // "give back... exploits you found" + breath
];

export const CTA_DUR = 120; // generated end card
export const CTA_FADE = 20; // slow crossfade from the reveal into the CTA card

// Absolute start frame of each clip (mirrors TransitionSeries overlap math).
export const START: Record<string, number> = (() => {
  const s: Record<string, number> = {};
  let cur = 0;
  CLIPS.forEach((c, i) => {
    cur = i === 0 ? 0 : cur - c.overlapBefore;
    s[c.id] = cur;
    cur += c.dur;
  });
  s.cta = cur - CTA_FADE;
  return s;
})();

export const TOTAL = START.cta + CTA_DUR;

// Named frame windows for the overlay layers. Tweak these while reviewing.
export const M = {
  letterboxIn: [0, 22] as const,
  letterboxOut: [START.cta - 18, START.cta] as const,
  chyron: [START.listen + 10, START.listen + 84] as const, // during the "listen" beat only
  subCursor: [START.probCursor + 8, START.probCursor + 96] as const, // "Is... is Cursor here?"
  kcPocs: [START.probA + 50, START.probA + 122] as const, // "this many PoCs"
  kcVulns: [START.probA + 190, START.probA + 258] as const, // holds through "vulnerabilities" + breath
  kcGtfo: [START.probGtfo + 14, START.probGtfo + 91] as const, // "PoC or GTFO"
  logo: [START.revealA + 66, START.revealA + 164] as const, // pops on "PoCumentary", ~3.2s hold, then clears
  grade: [0, START.cta] as const,
};

export const COPY = {
  chyronName: 'Ariel Fogel',
  chyronRole: 'AI Security Researcher',
  subCursor: 'Is… is Cursor here?  Codex here?',
  kcPocs: 'THIS MANY POCs',
  kcVulns: 'RACKING UP\nVULNERABILITIES',
  kcGtfo: 'PoC or GTFO',
  tagline: 'Turn a proof-of-concept into a narrated screen-recording.',
  kicker: 'NOW OPEN SOURCE',
  install: 'uv tool install pocumentary',
  repo: 'github.com/pillar-labs/pocumentary',
  streaming: 'STREAMING NOW · GITHUB',
};
