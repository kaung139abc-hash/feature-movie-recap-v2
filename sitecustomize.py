"""Expose imageio-ffmpeg's bundled binary under the standard ffmpeg name.

Python imports sitecustomize automatically during interpreter startup. This makes
yt-dlp and other subprocess-based tools able to discover FFmpeg even when the
hosting image does not provide a system ffmpeg executable.
"""
import os
import shutil
import tempfile
from pathlib import Path

try:
    import imageio_ffmpeg

    real_ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if real_ffmpeg.exists():
        bin_dir = Path(tempfile.gettempdir()) / "movie_recap_ffmpeg_bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        link = bin_dir / "ffmpeg"
        if not link.exists():
            try:
                link.symlink_to(real_ffmpeg)
            except OSError:
                shutil.copy2(real_ffmpeg, link)
                link.chmod(0o755)
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
except Exception:
    # app.py has its own FFmpeg fallback and will report a useful error if needed.
    pass
