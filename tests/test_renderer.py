"""Real FFmpeg checks; runnable without installing the API dependencies."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.services.media.studio_renderer import probe, normalize, render
from backend.services.media.sticker_converter import StickerConversionError


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.source = Path(cls.folder.name) / "input.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
                        "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-pix_fmt",
                        "yuv420p", "-c:a", "aac", str(cls.source)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_shapes_are_valid_stickers_with_correct_alpha(self):
        for shape in ("square", "circle", "rounded"):
            with self.subTest(shape=shape):
                output = Path(self.folder.name) / (shape + ".webm")
                render(self.source, output, .5, 2.5, shape, 1.3, .25, .75)
                self.assertLessEqual(output.stat().st_size, 256 * 1024)
                result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                         "-of", "json", str(output)], check=True, capture_output=True)
                data = json.loads(result.stdout)
                self.assertEqual(len(data["streams"]), 1)
                stream = data["streams"][0]
                self.assertEqual(stream["codec_name"], "vp9")
                self.assertEqual((stream["width"], stream["height"]), (512, 512))
                self.assertLessEqual(float(data["format"]["duration"]), 3)
                # Native FFmpeg VP9 decoder does not expose alpha; select libvpx explicitly.
                rgba = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", str(output),
                                       "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                                      check=True, capture_output=True).stdout
                self.assertEqual(rgba[(256 * 512 + 256) * 4 + 3], 255)
                if shape == "square":
                    self.assertEqual(rgba[3], 255)
                else:
                    # VP9 alpha is lossy: a transparent corner may decode as 1/255.
                    self.assertLessEqual(rgba[3], 3)

    def test_invalid_ranges_are_rejected(self):
        for start, end in ((0, 4), (3, 2), (-1, 1), (3.5, 5)):
            with self.subTest(start=start, end=end):
                with self.assertRaises(StickerConversionError):
                    render(self.source, Path(self.folder.name)/"invalid.webm", start, end, "circle", 1, .5, .5)

    def test_normalized_source_is_browser_video_without_audio(self):
        output = Path(self.folder.name) / "normalized.mp4"
        self.assertAlmostEqual(normalize(self.source, output), 4, delta=.1)
        duration, width, height = probe(output)
        self.assertLessEqual(max(width, height), 1280)
        data = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)],
                                         check=True, capture_output=True).stdout)
        self.assertEqual([s["codec_type"] for s in data["streams"]], ["video"])

if __name__ == "__main__":
    unittest.main()
