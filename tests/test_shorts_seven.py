import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from glass_fruit.automation import prepare, shot_plan
from glass_fruit.config import load_config
from glass_fruit.import_assets import fruit_for, import_assets
from glass_fruit.media import assemble

ROOT = Path(__file__).resolve().parents[1]
FRUITS = ['strawberry', 'apple', 'grapes', 'watermelon', 'orange', 'kiwi', 'peach']


class SevenFruitTests(unittest.TestCase):
    def test_exact_timeline_and_new_fruit_prompts(self):
        cfg = load_config(ROOT / 'configs/shorts-seven.yaml')
        self.assertEqual([s['fruit'] for s in cfg['scenes']], FRUITS)
        self.assertEqual([(s['start'], s['end']) for s in cfg['scenes']],
                         [(i*10, (i+1)*10) for i in range(7)])
        self.assertEqual(sum(s['edited_seconds'] for s in shot_plan(cfg)['shots']), 70)
        for fruit, alias in [('orange', 'オレンジ'), ('kiwi', 'キウイ'), ('peach', '桃')]:
            self.assertEqual(fruit_for(alias + '-01.MP4', 'strawberry'), fruit)
            self.assertTrue(all(s['fruit'] == fruit for s in shot_plan(cfg, fruit)['shots']))

    def test_seven_direct_mp4s_assemble_exact_70_seconds_with_source_audio(self):
        cfg = load_config(ROOT / 'configs/shorts-seven.yaml')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'release'; source.mkdir()
            # Generated labeled fixtures only, never presented as realistic AI footage.
            for index, fruit in enumerate(FRUITS):
                name = 'default.mp4' if fruit == 'strawberry' else fruit + '.mp4'
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                                'color=c=darkred:s=180x320:r=30', '-f', 'lavfi', '-i',
                                f'sine=frequency={400+index*100}:sample_rate=48000',
                                '-vf', "drawtext=text='SYNTHETIC TEST':fontsize=12:fontcolor=white:x=10:y=100",
                                '-t', '10', '-c:v', 'libx264', '-threads', '2', '-c:a', 'aac',
                                str(source / name)], check=True)
            import_assets(source, root / 'assets')
            # The existing strawberry alone is sufficient for its 10s slot, not the other six.
            for fruit in FRUITS[1:]:
                (root / 'assets' / fruit).rename(root / fruit)
            missing = prepare(cfg, root / 'assets', root / 'missing')
            self.assertEqual(missing['status'], 'needs-assets')
            self.assertEqual(missing['missing'], [dict(fruit=f, missing_seconds=10) for f in FRUITS[1:]])
            self.assertFalse((root / 'missing/manifest.json').exists())
            for fruit in FRUITS[1:]:
                (root / fruit).rename(root / 'assets' / fruit)
            self.assertEqual(prepare(cfg, root / 'assets', root / 'ready')['status'], 'ready-to-assemble')
            manifest = root / 'ready/manifest.json'
            data = json.loads(manifest.read_text())
            for scene in data['scenes']:
                self.assertEqual(scene['clips'][0]['audio_profile'], 'original')
                self.assertNotIn('audio', scene['clips'][0])
            data['synthetic_demo'] = True
            manifest.write_text(json.dumps(data))
            result = assemble(manifest, cfg, root / 'SYNTHETIC-SEVEN.mp4')
            self.assertEqual(result['source_clips'], 7)
            self.assertEqual(result['duration_seconds'], 70)
            self.assertEqual((result['width'], result['height']), (1080, 1920))
            self.assertTrue(result['decoded'])
            self.assertEqual(result['audio_profiles'], ['original'])
