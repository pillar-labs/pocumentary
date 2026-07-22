import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig, Easing} from 'remotion';
import {poppins} from '../theme';

type Variant = 'lower' | 'hero';

export const KineticCaption: React.FC<{
  text: string;
  from: number;
  to: number;
  variant?: Variant;
  color?: string;
}> = ({text, from, to, variant = 'lower', color = '#fff'}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (frame < from - 2 || frame > to + 2) return null;

  const enter = spring({
    frame: frame - from,
    fps,
    config: variant === 'hero' ? {damping: 12, stiffness: 140} : {damping: 200},
    durationInFrames: variant === 'hero' ? undefined : 12,
  });
  const exit = interpolate(frame, [to - 8, to], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.in(Easing.quad),
  });

  const hero = variant === 'hero';
  const scale = interpolate(enter, [0, 1], [hero ? 0.7 : 0.9, 1]) - exit * 0.06;
  const opacity = Math.max(0, Math.min(1, enter - exit));
  const y = hero ? 0 : interpolate(enter, [0, 1], [30, 0]);

  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: hero ? undefined : 360,
        top: hero ? '50%' : undefined,
        transform: `translateY(${hero ? '-50%' : `${y}px`}) scale(${scale})`,
        textAlign: 'center',
        opacity,
        padding: '0 60px',
      }}
    >
      <div
        style={{
          fontFamily: poppins,
          fontWeight: 700,
          fontSize: hero ? 172 : 92,
          lineHeight: 0.96,
          color,
          textTransform: 'uppercase',
          letterSpacing: hero ? -1 : 0.5,
          whiteSpace: 'pre-line',
          textShadow: '0 6px 40px rgba(0,0,0,0.7)',
          WebkitTextStroke: hero ? '2px rgba(0,0,0,0.25)' : undefined,
        }}
      >
        {text}
      </div>
    </div>
  );
};
