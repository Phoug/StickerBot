"""Real FFmpeg checks; runnable without installing the API dependencies."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.services.media.studio_renderer import probe, normalize, render
from backend.services.media.sticker_converter import StickerConversionError
from backend.services.media.sticker_preview import make_video_preview
from backend.services.file_service import cleanup_files


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

    def test_original_shape_keeps_landscape_and_portrait_dimensions(self):
        output = Path(self.folder.name) / "original.webm"
        render(self.source, output, 0, 1, "original", 1, .5, .5)
        self.assertEqual(probe(output)[1:], (512, 288))
        portrait = Path(self.folder.name) / "portrait.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(self.source), "-vf", "transpose=1", "-t", "1", "-an", str(portrait)], check=True)
        render(portrait, output, 0, .5, "original", 1, .5, .5)
        self.assertEqual(probe(output)[1:], (288, 512))

    def test_editing_imported_video_retains_transparent_pixels(self):
        original = Path(self.folder.name) / "imported.original.webm"
        render(self.source, original, 0, .5, "circle", 1, .5, .5)
        for shape in ("original", "rounded"):
            output = Path(self.folder.name) / ("edited-"+shape+".webm")
            render(original, output, 0, .5, shape, 1, .5, .5)
            rgba = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", str(output),
                                   "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                                  check=True, capture_output=True).stdout
            self.assertLessEqual(rgba[3], 3)
            # This point is outside the original circle, inside the rounded mask.
            self.assertLessEqual(rgba[(30 * 512 + 30) * 4 + 3], 3)
            self.assertEqual(rgba[(256 * 512 + 256) * 4 + 3], 255)

    def test_compatible_h264_editor_source_is_remuxed_without_reencoding(self):
        output = Path(self.folder.name)/"fast-normalized.mp4"
        normalize(self.source,output)
        def video_hash(path):
            return subprocess.run(["ffmpeg","-v","error","-i",str(path),"-map","0:v:0","-c:v","copy","-f","hash","-hash","sha256","-"],capture_output=True,check=True).stdout
        self.assertEqual(video_hash(self.source),video_hash(output))

    def test_invalid_ranges_are_rejected(self):
        for start, end in ((0, 4), (3, 2), (-1, 1), (3.5, 5), (0, .01)):
            with self.subTest(start=start, end=end):
                with self.assertRaises(StickerConversionError):
                    render(self.source, Path(self.folder.name)/"invalid.webm", start, end, "circle", 1, .5, .5)

    def test_browser_preview_is_h264_and_composites_transparency(self):
        sticker = Path(self.folder.name) / "preview-source.webm"
        render(self.source, sticker, 0, 1, "circle", 1, .5, .5)
        output = make_video_preview(sticker.read_bytes())
        try:
            data = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)], check=True, capture_output=True).stdout)
            self.assertEqual(data["streams"][0]["codec_name"], "h264")
            self.assertEqual(data["streams"][0]["pix_fmt"], "yuv420p")
            self.assertEqual(len(data["streams"]), 1)
            rgb = subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
            self.assertTrue(all(abs(channel-31)<8 for channel in rgb[:3]))
        finally:
            cleanup_files(output.parent)

    def test_non_square_preview_keeps_native_canvas(self):
        from backend.services.media.sticker_converter import convert_video_to_sticker
        sticker = Path(self.folder.name) / "wide.webm"
        convert_video_to_sticker(str(self.source), str(sticker), 0, 1)
        output = make_video_preview(sticker.read_bytes())
        try:
            _, width, height = probe(output)
            self.assertEqual((width, height), (512, 288))
        finally:
            cleanup_files(output.parent)

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
