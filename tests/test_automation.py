import copy
import math
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from glass_fruit.automation import prepare, shot_plan
from glass_fruit.config import load_config
from glass_fruit.media import demo, normalize, read_manifest

ROOT = Path(__file__).resolve().parents[1]


class PlanningTests(unittest.TestCase):
    def test_plan_covers_timeline_and_all_fruits(self):
        cfg = load_config(ROOT / 'config.yaml')
        plan = shot_plan(cfg)
        self.assertEqual(sum(s['edited_seconds'] for s in plan['shots']), 70)
        self.assertEqual({s['fruit'] for s in plan['shots']}, {'strawberry', 'apple', 'grapes', 'watermelon'})
        self.assertEqual(plan['api_requests'], 0)
        self.assertTrue(all('crystalline' in s['audio_prompt'] for s in plan['shots']))
        self.assertTrue(all(s['edited_seconds'] <= 8 for s in plan['shots']))

    def test_single_fruit_and_invalid_duration(self):
        cfg = load_config(ROOT / 'config.yaml')
        self.assertTrue(all(s['fruit'] == 'apple' for s in shot_plan(cfg, 'apple')['shots']))
        with self.assertRaises(ValueError):
            shot_plan(cfg, shot_seconds=0)


class AssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.cfg = load_config(ROOT / 'configs/prototype.yaml')
        cls.cfg.update(duration_seconds=1, min_duration_seconds=1, max_duration_seconds=1)
        cls.cfg['video'].update(width=180, height=320)
        cls.cfg['scenes'][0]['end'] = 1
        demo(cls.cfg, cls.root / 'assets' / 'strawberry')
        # Only the final labeled synthetic MP4 is used as the input test asset.
        (cls.root / 'assets' / 'strawberry' / 'synthetic-00.mp4').unlink()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_inventory_and_bright_audio_processing(self):
        result = prepare(self.cfg, self.root / 'assets', self.root / 'prepared', 'glass-bright')
        self.assertEqual(result['status'], 'ready-to-assemble')
        _, clips = read_manifest(self.root / 'prepared' / 'manifest.json', self.cfg)
        self.assertEqual(clips[0]['audio_profile'], 'glass-bright')
        normalize(clips[0], self.cfg, self.root / 'bright.mov')
        # Verify real samples change while remaining finite and bounded.
        def samples(path):
            data = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', '48000', '-f', 's16le', '-'])
            return struct.unpack(f'<{len(data)//2}h', data)
        original = samples(clips[0]['video'])
        bright = samples(self.root / 'bright.mov')
        self.assertNotEqual(original, bright)
        self.assertGreater(max(abs(s) for s in bright), 100)
        self.assertLess(max(abs(s) for s in bright), 32000)

    def test_glass_eq_increases_high_to_low_frequency_ratio(self):
        tone = self.root / 'two-tones.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'aevalsrc=0.1*sin(2*PI*80*t)+0.1*sin(2*PI*3200*t):s=48000:d=1',
                        str(tone)], check=True)
        clip = {'video': self.root / 'assets' / 'strawberry' / 'SYNTHETIC-DEMO.mp4',
                'audio': tone, 'has_audio': True, 'video_start': 0,
                'duration': 1, 'audio_offset': 0, 'audio_profile': 'glass-bright'}
        target = self.root / 'frequency-check.mov'
        normalize(clip, self.cfg, target)
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(target), '-vn',
                                       '-ac', '1', '-ar', '48000', '-f', 's16le', '-'])
        values = struct.unpack(f'<{len(raw)//2}h', raw)[9600:33600]
        def magnitude(frequency):
            real = sum(v * math.cos(2*math.pi*frequency*i/48000) for i,v in enumerate(values))
            imag = sum(v * math.sin(2*math.pi*frequency*i/48000) for i,v in enumerate(values))
            return math.hypot(real, imag)
        self.assertGreater(magnitude(3200) / magnitude(80), 4)

    def test_shortage_no_loop_or_partial_manifest(self):
        cfg = copy.deepcopy(self.cfg)
        cfg['scenes'][0]['end'] = 2
        result = prepare(cfg, self.root / 'assets', self.root / 'short')
        self.assertEqual(result['status'], 'needs-assets')
        self.assertEqual(result['missing'][0]['missing_seconds'], 1)
        self.assertFalse((self.root / 'short' / 'manifest.json').exists())

    def test_symlink_cannot_escape_asset_root(self):
        folder = self.root / 'escaped' / 'strawberry'
        folder.mkdir(parents=True)
        (folder / 'outside.mp4').symlink_to(self.root / 'assets' / 'strawberry' / 'SYNTHETIC-DEMO.mp4')
        with self.assertRaisesRegex(ValueError, 'inside'):
            prepare(self.cfg, folder.parent, self.root / 'escape-result')
        self.assertFalse((self.root / 'escape-result').exists())

    def test_invalid_profile_and_preserve_existing_directory(self):
        with self.assertRaises(ValueError):
            prepare(self.cfg, self.root / 'assets', self.root / 'bad', 'unknown')
        with self.assertRaises(ValueError):
            prepare(self.cfg, self.root / 'assets', self.root / 'assets')
