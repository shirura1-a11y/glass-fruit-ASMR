import copy
import json
import math
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from glass_fruit.cli import main
from glass_fruit.config import load_config, prompts
from glass_fruit.media import assemble, demo, read_manifest, validate

ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(ROOT / "config.yaml")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "settings.yaml"

    def check_bad(self, cfg):
        self.path.write_text(yaml.safe_dump(cfg))
        with self.assertRaises(ValueError):
            load_config(self.path)

    def test_prompt_order_and_no_execution(self):
        plan = prompts(self.cfg)
        self.assertFalse(plan["paid_api_enabled"])
        self.assertEqual([s["fruit"] for s in plan["scenes"]], ["strawberry", "apple", "grapes", "watermelon"])
        self.assertEqual(sum(s["required_edited_seconds"] for s in plan["scenes"]), 70)

    def test_paid_mode_cannot_be_enabled(self):
        self.cfg["cost"]["enable_paid_api"] = True
        self.check_bad(self.cfg)

    def test_nonzero_budget_rejected(self):
        self.cfg["cost"]["max_usd_per_run"] = 1
        self.check_bad(self.cfg)

    def test_gapped_timeline_rejected(self):
        self.cfg["scenes"][1]["start"] = 16
        self.check_bad(self.cfg)

    def test_nonfinite_duration_rejected(self):
        self.cfg["duration_seconds"] = float("nan")
        self.check_bad(self.cfg)

    def test_frame_misalignment_rejected(self):
        self.cfg["scenes"][0]["end"] = 15.01
        self.cfg["scenes"][1]["start"] = 15.01
        self.check_bad(self.cfg)

    def test_landscape_rejected(self):
        self.cfg["video"]["width"] = 1920
        self.cfg["video"]["height"] = 1080
        self.check_bad(self.cfg)

    def test_missing_and_malformed_config_rejected(self):
        self.check_bad({})
        self.check_bad([])

    def test_cli_returns_nonzero_for_missing_config(self):
        self.assertEqual(main(["--config", str(self.path), "prompts"]), 1)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.cfg = load_config(ROOT / "config.yaml")
        cls.cfg.update(duration_seconds=4, min_duration_seconds=4, max_duration_seconds=4)
        cls.cfg["video"].update(width=360, height=640)
        for index, scene in enumerate(cls.cfg["scenes"]):
            scene.update(start=index, end=index + 1)
        cls.report = demo(cls.cfg, cls.root / "demo")
        cls.movie = cls.root / "demo" / "SYNTHETIC-DEMO.mp4"
        cls.manifest = cls.root / "demo" / "manifest.json"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def changed_manifest(self, change, name):
        data = json.loads(self.manifest.read_text())
        change(data)
        path = self.manifest.parent / name
        path.write_text(json.dumps(data))
        return path

    def test_four_scene_encode_probe_decode(self):
        self.assertEqual(self.report["status"], "passed")
        self.assertEqual(self.report["source_clips"], 4)
        self.assertTrue(self.report["synthetic_demo"])
        self.assertAlmostEqual(self.report["duration_seconds"], 4, places=2)
        self.assertTrue(self.movie.with_suffix(".validation.json").is_file())

    def test_audio_positive_offset_is_audible_after_delay(self):
        data = subprocess.check_output(["ffmpeg", "-nostdin", "-v", "error", "-i", str(self.movie),
                                        "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"])
        samples = struct.unpack(f"<{len(data)//2}h", data)
        rms = lambda a, b: math.sqrt(sum(x*x for x in samples[int(a*48000):int(b*48000)]) / int((b-a)*48000))
        self.assertLess(rms(0, 0.05), 10)
        self.assertGreater(rms(0.2, 0.25), 500)

    def test_negative_offset_trims_audio_and_pads_end(self):
        audio = self.root / "delayed-tone.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                        r"aevalsrc=if(lt(t\,0.3)\,0\,0.4*sin(2*PI*440*t)):s=48000:d=1",
                        str(audio)], check=True)
        cfg = copy.deepcopy(self.cfg)
        cfg.update(duration_seconds=1, min_duration_seconds=1, max_duration_seconds=1)
        cfg["scenes"] = [{"fruit": "strawberry", "start": 0, "end": 1}]
        manifest = self.root / "negative.json"
        manifest.write_text(json.dumps({"scenes": [{"fruit": "strawberry", "clips": [
            {"video": str(self.root / "demo" / "synthetic-00.mp4"), "audio": str(audio),
             "duration": 1, "audio_offset": -0.2}]}]}))
        output = self.root / "negative.mp4"
        assemble(manifest, cfg, output)
        data = subprocess.check_output(["ffmpeg", "-nostdin", "-v", "error", "-i", str(output),
                                       "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"])
        samples = struct.unpack(f"<{len(data)//2}h", data)
        self.assertLess(max(abs(s) for s in samples[:2400]), 100)
        self.assertGreater(max(abs(s) for s in samples[9600:12000]), 1000)
        self.assertLess(max(abs(s) for s in samples[43200:45600]), 100)

    def test_wrong_resolution_rejected(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["video"].update(width=1080, height=1920)
        with self.assertRaisesRegex(ValueError, "resolution"):
            validate(self.movie, cfg)

    def test_wrong_duration_rejected(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["duration_seconds"] = 5
        with self.assertRaisesRegex(ValueError, "duration"):
            validate(self.movie, cfg)

    def test_wrong_fps_rejected(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["video"]["fps"] = 24
        with self.assertRaisesRegex(ValueError, "frame rate"):
            validate(self.movie, cfg)

    def test_corrupt_movie_rejected(self):
        bad = self.root / "bad.mp4"
        bad.write_bytes(b"not a video")
        with self.assertRaises(ValueError):
            validate(bad, self.cfg)

    def test_short_source_is_not_looped(self):
        path = self.changed_manifest(lambda m: m["scenes"][0]["clips"][0].update(video_start=0.5), "short.json")
        with self.assertRaisesRegex(ValueError, "too short"):
            read_manifest(path, self.cfg)

    def test_missing_scene_rejected(self):
        path = self.changed_manifest(lambda m: m["scenes"].pop(), "missing.json")
        with self.assertRaisesRegex(ValueError, "exactly"):
            read_manifest(path, self.cfg)

    def test_scene_duration_mismatch_rejected(self):
        path = self.changed_manifest(lambda m: m["scenes"][0]["clips"][0].update(duration=0.5), "duration.json")
        with self.assertRaisesRegex(ValueError, "exactly fill"):
            read_manifest(path, self.cfg)

    def test_existing_output_preserved(self):
        before = self.movie.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            assemble(self.manifest, self.cfg, self.movie)
        self.assertEqual(self.movie.read_bytes(), before)

    def test_original_audio_is_retained(self):
        cfg = copy.deepcopy(self.cfg)
        cfg.update(duration_seconds=1, min_duration_seconds=1, max_duration_seconds=1)
        cfg["scenes"] = [{"fruit": "strawberry", "start": 0, "end": 1}]
        path = self.root / "original-audio.json"
        path.write_text(json.dumps({"scenes": [{"fruit": "strawberry", "clips": [
            {"video": str(self.movie), "video_start": 1, "duration": 1}]}]}))
        output = self.root / "original-audio.mp4"
        assemble(path, cfg, output)
        data = subprocess.check_output(["ffmpeg", "-nostdin", "-v", "error", "-i", str(output),
                                       "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"])
        samples = struct.unpack(f"<{len(data)//2}h", data)
        self.assertGreater(max(abs(s) for s in samples[9600:12000]), 500)

    def test_audio_without_overlap_rejected(self):
        path = self.changed_manifest(lambda m: m["scenes"][0]["clips"][0].update(audio_offset=1), "no-overlap.json")
        with self.assertRaisesRegex(ValueError, "no overlap"):
            read_manifest(path, self.cfg)

    def test_split_shots_silent_fallback_and_video_start(self):
        cfg = copy.deepcopy(self.cfg)
        cfg.update(duration_seconds=1, min_duration_seconds=1, max_duration_seconds=1)
        cfg["scenes"] = [{"fruit": "strawberry", "start": 0, "end": 1}]
        path = self.root / "split.json"
        source = str(self.root / "demo" / "synthetic-00.mp4")
        path.write_text(json.dumps({"scenes": [{"fruit": "strawberry", "clips": [
            {"video": source, "duration": 0.5},
            {"video": source, "video_start": 0.5, "duration": 0.5}]}]}))
        report = assemble(path, cfg, self.root / "split.mp4")
        self.assertEqual(report["source_clips"], 2)
        self.assertEqual(report["status"], "passed")


if __name__ == "__main__":
    unittest.main()
