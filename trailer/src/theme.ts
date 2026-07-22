import {loadFont as loadPoppins} from '@remotion/google-fonts/Poppins';
import {loadFont as loadLato} from '@remotion/google-fonts/Lato';
import {loadFont as loadFira} from '@remotion/google-fonts/FiraCode';

// Pillar brand type system: Poppins (display), Lato (body), Fira Code (mono).
export const poppins = loadPoppins('normal', {
  weights: ['300', '500', '600', '700'],
  subsets: ['latin'],
}).fontFamily;
export const lato = loadLato('normal', {weights: ['400', '700'], subsets: ['latin']}).fontFamily;
export const fira = loadFira('normal', {weights: ['400', '500', '700'], subsets: ['latin']})
  .fontFamily;

// Pillar brand tokens (from pillar-deck-designer skill) + PoCumentary product green.
export const COLORS = {
  red: '#F74A53', // Pillar primary — accents, CTA button, chyron spine
  redActive: '#D93640',
  canvas: '#F6F0F1', // warm off-white — NOT pure white
  surfaceCard: '#FFFFFF',
  ink: '#151A24', // dark navy — headlines/primary text on light
  body: '#262C38',
  muted: '#424F65',
  mutedSoft: '#6B7280',
  onDark: '#FFFFFF',
  onDarkWarm: '#F6F0F1',
  green: '#5FB646', // PoCumentary product green (logo wordmark)
  greenBright: '#7FD35C',
};
