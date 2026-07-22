import React from 'react';
import {interpolate, useCurrentFrame, Easing} from 'remotion';
import {M} from '../edl';

// Cinematic top/bottom bars that slide in over the sit-down and retract before the CTA.
export const Letterbox: React.FC = () => {
  const frame = useCurrentFrame();
  const barMax = 96;

  const inH = interpolate(frame, [M.letterboxIn[0], M.letterboxIn[1]], [0, barMax], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  const outH = interpolate(frame, [M.letterboxOut[0], M.letterboxOut[1]], [0, barMax], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.in(Easing.cubic),
  });
  const h = inH - outH;

  const bar: React.CSSProperties = {
    position: 'absolute',
    left: 0,
    right: 0,
    height: h,
    background: '#000',
  };
  return (
    <>
      <div style={{...bar, top: 0}} />
      <div style={{...bar, bottom: 0}} />
    </>
  );
};
