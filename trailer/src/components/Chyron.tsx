import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {M, COPY} from '../edl';
import {poppins, COLORS} from '../theme';

// Documentary lower-third: a red spine, name in bold, role beneath. Slides in and out.
export const Chyron: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const [inA, outA] = M.chyron;

  const enter = spring({frame: frame - inA, fps, config: {damping: 200}, durationInFrames: 18});
  const exit = interpolate(frame, [outA - 14, outA], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const p = enter - exit;
  if (p <= 0.001) return null;

  const x = interpolate(p, [0, 1], [-80, 0]);

  return (
    <div
      style={{
        position: 'absolute',
        left: 70,
        bottom: 300,
        transform: `translateX(${x}px)`,
        opacity: Math.max(0, Math.min(1, p)),
        display: 'flex',
        alignItems: 'stretch',
        gap: 22,
      }}
    >
      <div style={{width: 8, background: COLORS.red, borderRadius: 4}} />
      <div>
        <div
          style={{
            fontFamily: poppins,
            fontWeight: 700,
            fontSize: 54,
            color: '#fff',
            letterSpacing: 1,
            textShadow: '0 2px 18px rgba(0,0,0,0.6)',
            lineHeight: 1.05,
          }}
        >
          {COPY.chyronName}
        </div>
        <div
          style={{
            fontFamily: poppins,
            fontWeight: 500,
            fontSize: 30,
            color: 'rgba(255,255,255,0.86)',
            letterSpacing: 3,
            textTransform: 'uppercase',
            marginTop: 8,
            textShadow: '0 2px 14px rgba(0,0,0,0.6)',
          }}
        >
          {COPY.chyronRole}
        </div>
      </div>
    </div>
  );
};
