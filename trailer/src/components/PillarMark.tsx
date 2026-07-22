import React from 'react';
import {COLORS} from '../theme';

// The Pillar icon mark: red square with three off-white bars (from the brand SVG).
export const PillarMark: React.FC<{size?: number; bars?: string; square?: string}> = ({
  size = 40,
  bars = COLORS.canvas,
  square = COLORS.red,
}) => {
  return (
    <svg width={size} height={size} viewBox="0 0 173 173" fill="none" aria-label="Pillar">
      <rect x="0.197266" y="0.546875" width="172.209" height="172.209" fill={square} />
      <rect x="44.1797" y="38.5156" width="25.8313" height="96.4369" fill={bars} />
      <rect x="73.3984" y="38.5156" width="25.8313" height="96.4369" fill={bars} />
      <rect x="102.695" y="38.5156" width="25.8313" height="61.9952" fill={bars} />
    </svg>
  );
};
