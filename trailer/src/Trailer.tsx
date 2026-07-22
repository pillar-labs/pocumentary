import React from 'react';
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  Sequence,
  interpolate,
  staticFile,
} from 'remotion';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';

import {CLIPS, CTA_DUR, CTA_FADE, START, TOTAL, M, COPY} from './edl';
import {COLORS} from './theme';
import {CTA} from './beats/CTA';
import {Grade} from './components/Grade';
import {Grain} from './components/Grain';
import {Letterbox} from './components/Letterbox';
import {Chyron} from './components/Chyron';
import {Subtitle} from './components/Subtitle';
import {KineticCaption} from './components/KineticCaption';
import {LogoOverlay} from './components/LogoOverlay';

const videoStyle: React.CSSProperties = {
  width: '100%',
  height: '100%',
  objectFit: 'cover',
};

// Music bed: forward during the wordless sit-down, ducked under the interview VO,
// nudged up under the announcement, then full for the bright CTA, with an end fade.
const duck = (f: number): number =>
  interpolate(
    f,
    [
      0,
      START.listen - 8,
      START.listen + 10,
      START.revealA - 6,
      START.revealA + 20,
      START.cta - 18,
      START.cta + 8,
      TOTAL - 16,
      TOTAL,
    ],
    [0.48, 0.48, 0.16, 0.16, 0.24, 0.24, 0.62, 0.62, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );

export const Trailer: React.FC = () => {
  const clipEls: React.ReactNode[] = [];
  CLIPS.forEach((c, i) => {
    if (i > 0 && c.overlapBefore > 0) {
      clipEls.push(
        <TransitionSeries.Transition
          key={`t-${c.id}`}
          presentation={fade()}
          timing={linearTiming({durationInFrames: c.overlapBefore})}
        />,
      );
    }
    clipEls.push(
      <TransitionSeries.Sequence key={c.id} durationInFrames={c.dur}>
        <OffthreadVideo src={staticFile(c.file)} muted={c.muted} style={videoStyle} />
      </TransitionSeries.Sequence>,
    );
  });
  // Cross-dissolve the final clip into the bright CTA card.
  clipEls.push(
    <TransitionSeries.Transition
      key="t-cta"
      presentation={fade()}
      timing={linearTiming({durationInFrames: CTA_FADE})}
    />,
  );
  clipEls.push(
    <TransitionSeries.Sequence key="cta" durationInFrames={CTA_DUR}>
      <CTA />
    </TransitionSeries.Sequence>,
  );

  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {/* base footage */}
      <TransitionSeries>{clipEls}</TransitionSeries>

      {/* filmic grade over the footage (fades out before the CTA) */}
      <Grade />

      {/* cinematic bars */}
      <Letterbox />

      {/* documentary lower-third */}
      <Chyron />

      {/* subtitle for the mumbled "Cursor / Codex" line */}
      <Subtitle text={COPY.subCursor} from={M.subCursor[0]} to={M.subCursor[1]} />

      {/* kinetic emphasis captions */}
      <KineticCaption text={COPY.kcPocs} from={M.kcPocs[0]} to={M.kcPocs[1]} variant="lower" />
      <KineticCaption text={COPY.kcVulns} from={M.kcVulns[0]} to={M.kcVulns[1]} variant="lower" />
      <KineticCaption
        text={COPY.kcGtfo}
        from={M.kcGtfo[0]}
        to={M.kcGtfo[1]}
        variant="hero"
        color={COLORS.onDark}
      />

      {/* logo pops on the word "PoCumentary" */}
      <LogoOverlay />

      {/* subtle film grain over the footage only */}
      <Sequence durationInFrames={START.cta} layout="none">
        <Grain opacity={0.05} />
      </Sequence>

      {/* music bed */}
      <Audio src={staticFile('music.mp3')} volume={duck} />
    </AbsoluteFill>
  );
};
