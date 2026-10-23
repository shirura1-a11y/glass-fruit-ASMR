"""Exercise the actual workflow shell steps when only strawberry footage exists."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/assemble-local.yml').read_text())
STEPS = {s.get('name'): s for s in WORKFLOW['jobs']['assemble']['steps'] if 'name' in s}


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class WorkflowPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'configs').mkdir()
        shutil.copyfile(ROOT / 'configs/prototype.yaml', self.root / 'configs/prototype.yaml')
        shutil.copyfile(ROOT / 'config.yaml', self.root / 'config.yaml')
        folder = self.root / 'assets/strawberry'
        folder.mkdir(parents=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=180x320:r=30',
                        '-f', 'lavfi', '-i', 'sine=frequency=900:sample_rate=48000', '-t', '7',
                        '-c:v', 'libx264', '-threads', '2', '-c:a', 'aac', str(folder / 'default.mp4')],
                       check=True)

    def run_step(self, name, config):
        environment = dict(os.environ, PYTHONPATH=str(ROOT), CONFIG=config, AUDIO_PROFILE='original')
        return subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', STEPS[name]['run']],
                              cwd=self.root, env=environment, capture_output=True, text=True, timeout=120)

    def test_default_six_seconds_succeeds_without_other_fruits(self):
        inputs = WORKFLOW.get('on', WORKFLOW.get(True))['workflow_dispatch']['inputs']
        self.assertEqual(inputs['audio_profile']['default'], 'original')
        result = self.run_step('Prepare and assemble', inputs['config']['default'])
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((self.root / 'outputs/GLASS-FRUIT.validation.json').read_text())
        self.assertEqual(report['duration_seconds'], 6)
        self.assertTrue(report['decoded'])
        self.assertEqual(report['audio_profiles'], ['original'])

    def test_70s_shortage_preserves_independent_preview_and_audio(self):
        result = self.run_step('Save independent six-second strawberry preview', 'config.yaml')
        self.assertEqual(result.returncode, 0, result.stderr)
        before = (self.root / 'outputs/STRAWBERRY-6S.mp4').read_bytes()
        result = self.run_step('Prepare and assemble', 'config.yaml')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual((self.root / 'outputs/STRAWBERRY-6S.mp4').read_bytes(), before)
        report = json.loads((self.root / 'outputs/strawberry-preview/manifest.json').read_text())
        clip = report['scenes'][0]['clips'][0]
        self.assertEqual(clip['audio_profile'], 'original')
        self.assertNotIn('audio', clip)  # Keep source audio, no external replacement.
        self.assertIn('always()', STEPS['Upload six-second MP4']['if'])
