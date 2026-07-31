interface PlaybackControlsProps {
  playing: boolean;
  frameIndex: number;
  frameCount: number;
  onPlay: () => void;
  onPause: () => void;
  onRestart: () => void;
  onScrub: (index: number) => void;
}

export function PlaybackControls({
  playing,
  frameIndex,
  frameCount,
  onPlay,
  onPause,
  onRestart,
  onScrub,
}: PlaybackControlsProps) {
  const max = Math.max(0, frameCount - 1);
  return (
    <div className="playback" data-testid="playback-controls">
      <div className="playback-buttons">
        {playing ? (
          <button type="button" onClick={onPause} aria-label="Pause">
            Pause
          </button>
        ) : (
          <button type="button" onClick={onPlay} aria-label="Play">
            Play
          </button>
        )}
        <button type="button" onClick={onRestart} aria-label="Restart">
          Restart
        </button>
      </div>
      <label className="scrub">
        <span>
          Frame {frameIndex}/{max}
        </span>
        <input
          type="range"
          min={0}
          max={max}
          value={frameIndex}
          onChange={(e) => onScrub(Number(e.target.value))}
          aria-label="Scrub timeline"
        />
      </label>
    </div>
  );
}
