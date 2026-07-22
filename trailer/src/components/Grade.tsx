import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {M} from '../edl';

// Subtle filmic grade over the footage: vignette + a cool-shadow / warm-highlight wash.
// Fades out just before the CTA so the bright end card reads clean.
export const Grade: React.FC = () => {
  const frame = useCurrentFrame();
  const on = interpolate(frame, [M.grade[1] - 16, M.grade[1]], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill style={{opacity: on}}>
      {/* vignette */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(ellipse 75% 62% at 50% 42%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.55) 100%)',
        }}
      />
      {/* cool shadows / warm highlights wash */}
      <AbsoluteFill
        style={{
          mixBlendMode: 'soft-light',
          background:
            'linear-gradient(180deg, rgba(255,196,120,0.16) 0%, rgba(0,0,0,0) 45%, rgba(30,60,90,0.22) 100%)',
        }}
      />
      {/* gentle contrast lift */}
      <AbsoluteFill style={{mixBlendMode: 'multiply', background: 'rgba(20,22,30,0.10)'}} />
    </AbsoluteFill>
  );
};
