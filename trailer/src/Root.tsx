import React from 'react';
import {Composition} from 'remotion';
import {Trailer} from './Trailer';
import {FPS, WIDTH, HEIGHT, TOTAL} from './edl';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Trailer"
      component={Trailer}
      durationInFrames={TOTAL}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
};
