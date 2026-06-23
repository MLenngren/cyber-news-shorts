"""Tests for the post-render quality gate (_util.verify_render_output).

The gate is the in-process safeguard that stops the pipeline from publishing a
technically-valid-but-visually-broken render — specifically an all-black short,
which an exit-code-only cron happily publishes. It must:

  * pass a normal (bright, full-size) render,
  * reject a near-black render and quarantine it out of the publish glob,
  * reject a truncated/too-small or missing file,
  * never block a publish merely because luma could not be measured.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _util import (  # noqa: E402
    RenderQualityError,
    mean_frame_luma,
    verify_render_output,
)


def _have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _make_clip(path: Path, color: str, *, seconds: int = 10) -> None:
    """Render a solid-colour vertical clip so the test is deterministic."""
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:d={seconds}",
            "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
            str(path),
        ],
        check=True,
    )


@unittest.skipUnless(_have_ffmpeg(), "ffmpeg required")
class TestRenderQualityGate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.black = self.tmp / "black.mp4"
        self.bright = self.tmp / "bright.mp4"
        self.qdir = self.tmp / "_rejects"
        _make_clip(self.black, "black")
        _make_clip(self.bright, "gray")  # solid mid-gray ≈ luma 128

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_mean_luma_distinguishes_black_from_bright(self) -> None:
        self.assertLess(mean_frame_luma(self.black), 30.0)
        self.assertGreater(mean_frame_luma(self.bright), 60.0)

    def test_passes_bright_render(self) -> None:
        # min_bytes lowered: synthetic solid-colour clips are small, but we are
        # exercising the luma/duration gate, not the size gate, here.
        metrics = verify_render_output(self.bright, min_bytes=1000)
        self.assertGreater(metrics["mean_luma"], 60.0)
        self.assertTrue(self.bright.exists(), "a good render must NOT be quarantined")

    def test_rejects_and_quarantines_black_render(self) -> None:
        with self.assertRaises(RenderQualityError) as ctx:
            verify_render_output(self.black, min_bytes=1000, quarantine_dir=self.qdir)
        self.assertIn("near-black", ctx.exception.reason)
        self.assertFalse(self.black.exists(), "black render must be moved out of place")
        self.assertTrue((self.qdir / "black.mp4").exists(), "must land in _rejects/")

    def test_default_size_gate_catches_black(self) -> None:
        # Real black H.264 compresses to ~1MB, well under the 2MB floor, so even
        # without the luma check the default gate rejects it.
        with self.assertRaises(RenderQualityError):
            verify_render_output(self.black, quarantine_dir=self.qdir)

    def test_rejects_truncated_file(self) -> None:
        tiny = self.tmp / "tiny.mp4"
        tiny.write_bytes(self.black.read_bytes()[:4096])
        with self.assertRaises(RenderQualityError) as ctx:
            verify_render_output(tiny, quarantine_dir=self.qdir)
        self.assertEqual(ctx.exception.reason.split()[0], "file")  # "file too small"

    def test_rejects_missing_file(self) -> None:
        with self.assertRaises(RenderQualityError) as ctx:
            verify_render_output(self.tmp / "nope.mp4")
        self.assertEqual(ctx.exception.reason, "missing")


if __name__ == "__main__":
    unittest.main()
