import React from 'react';
import {AbsoluteFill, useCurrentFrame, random} from 'remotion';
import {WIDTH, HEIGHT} from '../edl';

// Lightweight animated film grain via an inline SVG turbulence, re-seeded each frame.
export const Grain: React.FC<{opacity?: number}> = ({opacity = 0.06}) => {
  const frame = useCurrentFrame();
  const seed = Math.floor(random(`grain-${frame}`) * 1000);
  return (
    <AbsoluteFill style={{opacity, mixBlendMode: 'overlay', pointerEvents: 'none'}}>
      <svg width={WIDTH} height={HEIGHT}>
        <filter id={`n${frame}`}>
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.9"
            numOctaves={2}
            seed={seed}
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width={WIDTH} height={HEIGHT} filter={`url(#n${frame})`} />
      </svg>
    </AbsoluteFill>
  );
};
