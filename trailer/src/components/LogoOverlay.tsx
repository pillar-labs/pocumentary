import React from 'react';
import {Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {M} from '../edl';

// The PoCumentary logo pops on-screen as a framed card exactly when he says the word
// "PoCumentary" — a nod to the tool's own [[overlay]] feature. Holds, then hands off to CTA.
export const LogoOverlay: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const [from, to] = M.logo;
  if (frame < from - 2 || frame > to + 2) return null;

  const pop = spring({frame: frame - from, fps, config: {damping: 11, stiffness: 150}});
  const exit = interpolate(frame, [to - 10, to], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const scale = interpolate(pop, [0, 1], [0.6, 1]) - exit * 0.08;
  const opacity = Math.max(0, Math.min(1, pop - exit));
  const rot = interpolate(pop, [0, 1], [-6, 0]);

  return (
    <div
      style={{
        position: 'absolute',
        top: '68%',
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        transform: `translateY(-50%)`,
      }}
    >
      <div
        style={{
          transform: `scale(${scale}) rotate(${rot}deg)`,
          opacity,
          background: '#fff',
          borderRadius: 40,
          padding: '54px 60px',
          boxShadow: '0 40px 120px rgba(0,0,0,0.55), 0 0 0 1px rgba(0,0,0,0.05)',
        }}
      >
        <Img src={staticFile('pocumentary_logo.png')} style={{width: 720, display: 'block'}} />
      </div>
    </div>
  );
};
