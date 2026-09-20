"""Convert concatenated frame indices using each recording's own frame rate."""
def frame_seconds(frame, timeline, fallback_fps=60.0):
    seconds = 0.0
    remaining = frame
    for count, fps in timeline:
        if remaining <= count:
            return seconds + remaining / fps
        remaining -= count
        seconds += count / fps
    return seconds + remaining / fallback_fps


def format_video_time(frame, video_index, timeline, fallback_fps=60.0):
    """Format a frame's local time using the selected video's frame rate."""
    import math
    fps = timeline[video_index][1] if 0 <= video_index < len(timeline) else fallback_fps
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('Invalid video frame rate')
    seconds = max(0, int(frame / fps))
    return f'{seconds // 60}:{seconds % 60:02d}'
