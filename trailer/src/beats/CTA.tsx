import React from 'react';
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  Easing,
} from 'remotion';
import {COPY} from '../edl';
import {poppins, lato, fira, COLORS} from '../theme';
import {PillarMark} from '../components/PillarMark';

// Local-frame helper: a value that eases up over [delay, delay+dur].
const rise = (frame: number, delay: number, dur = 16) =>
  interpolate(frame, [delay, delay + dur], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

export const CTA: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const bg = interpolate(frame, [0, 14], [0, 1], {extrapolateRight: 'clamp'});
  const logoPop = spring({frame: frame - 6, fps, config: {damping: 12, stiffness: 130}});
  const logoScale = interpolate(logoPop, [0, 1], [0.82, 1]);

  const kicker = rise(frame, 20);
  const tagline = rise(frame, 30);
  const pill = rise(frame, 40);
  const repo = rise(frame, 54);
  const byline = rise(frame, 66);

  // Typewriter for the install command.
  const typeStart = 44;
  const chars = Math.max(0, Math.min(COPY.install.length, Math.floor((frame - typeStart) * 1.3)));
  const typed = COPY.install.slice(0, chars);
  const cursorOn = Math.floor(frame / 8) % 2 === 0;

  const up = (v: number) => `translateY(${interpolate(v, [0, 1], [24, 0])}px)`;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.canvas,
        opacity: bg,
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: lato,
      }}
    >
      {/* soft Pillar-red brand glow */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(ellipse 72% 46% at 50% 38%, rgba(247,74,83,0.14) 0%, rgba(246,240,241,0) 70%)',
        }}
      />

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 40,
          padding: '0 80px',
          width: '100%',
        }}
      >
        <div
          style={{
            opacity: kicker,
            transform: up(kicker),
            fontFamily: poppins,
            fontWeight: 600,
            fontSize: 30,
            letterSpacing: 10,
            color: COLORS.red,
          }}
        >
          {COPY.kicker}
        </div>

        <Img
          src={staticFile('pocumentary_logo.png')}
          style={{width: 840, transform: `scale(${logoScale})`, display: 'block'}}
        />

        <div
          style={{
            opacity: tagline,
            transform: up(tagline),
            fontFamily: poppins,
            fontWeight: 500,
            fontSize: 44,
            lineHeight: 1.25,
            color: COLORS.ink,
            textAlign: 'center',
            maxWidth: 900,
            letterSpacing: -0.3,
          }}
        >
          {COPY.tagline}
        </div>

        {/* terminal pill with typewriter install command */}
        <div
          style={{
            opacity: pill,
            transform: up(pill),
            background: COLORS.ink,
            borderRadius: 22,
            padding: '30px 44px',
            display: 'flex',
            alignItems: 'center',
            gap: 18,
            boxShadow: '0 24px 60px rgba(21,26,36,0.30)',
            minWidth: 720,
          }}
        >
          <span style={{color: COLORS.green, fontFamily: fira, fontSize: 40, fontWeight: 700}}>
            $
          </span>
          <span style={{color: '#EDEDE7', fontFamily: fira, fontSize: 40}}>
            {typed}
            <span style={{opacity: cursorOn ? 1 : 0, color: COLORS.greenBright}}>▋</span>
          </span>
        </div>

        <div
          style={{
            opacity: repo,
            transform: up(repo),
            fontFamily: fira,
            fontSize: 34,
            color: COLORS.muted,
          }}
        >
          {COPY.repo}
        </div>

        {/* Pillar byline + Netflix-parody streaming gag */}
        <div
          style={{
            opacity: byline,
            transform: up(byline),
            marginTop: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            fontFamily: poppins,
            fontWeight: 600,
            fontSize: 26,
            letterSpacing: 5,
            color: COLORS.ink,
          }}
        >
          <PillarMark size={34} bars={COLORS.canvas} square={COLORS.red} />
          <span>BY PILLAR</span>
          <span style={{color: COLORS.mutedSoft, fontWeight: 400}}>·</span>
          <span style={{color: COLORS.red}}>{COPY.streaming}</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
