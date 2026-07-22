import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {poppins} from '../theme';

// Plain documentary subtitle: bottom-centered, sentence case, soft fade in/out.
export const Subtitle: React.FC<{text: string; from: number; to: number}> = ({
  text,
  from,
  to,
}) => {
  const frame = useCurrentFrame();
  if (frame < from - 2 || frame > to + 2) return null;

  const opacity = interpolate(
    frame,
    [from, from + 8, to - 8, to],
    [0, 1, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );

  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 250,
        textAlign: 'center',
        padding: '0 90px',
        opacity,
      }}
    >
      <span
        style={{
          fontFamily: poppins,
          fontWeight: 500,
          fontSize: 50,
          lineHeight: 1.2,
          color: '#fff',
          textShadow: '0 2px 20px rgba(0,0,0,0.85), 0 0 2px rgba(0,0,0,0.6)',
        }}
      >
        {text}
      </span>
    </div>
  );
};
