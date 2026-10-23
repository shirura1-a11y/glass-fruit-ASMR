"""Offline shot planning and deterministic local asset ingestion."""
import json
import math
from pathlib import Path

from .config import FRUITS, prompts
from .media import probe, stream_duration


def shot_plan(cfg, fruit=None, shot_seconds=8):
    if fruit is not None and fruit not in FRUITS:
        raise ValueError('Unsupported fruit')
    if type(shot_seconds) is not int or not 4 <= shot_seconds <= 10:
        raise ValueError('shot_seconds must be an integer from 4 to 10')
    scenes = prompts(cfg)['scenes']
    shots = []
    for scene in scenes:
        selected = fruit or scene['fruit']
        remaining = round(scene['required_edited_seconds'] * cfg['video']['fps'])
        count = math.ceil(remaining / (shot_seconds * cfg['video']['fps']))
        for index in range(count):
            frames = min(remaining, shot_seconds * cfg['video']['fps'])
            remaining -= frames
            prompt_cfg = dict(cfg, scenes=[dict(fruit=selected, start=0, end=frames / cfg['video']['fps'])])
            base = prompts(prompt_cfg)['scenes'][0]['prompt']
            shots.append({'id': f"scene-{scene['scene']:02d}-shot-{index+1:02d}",
                          'fruit': selected, 'edited_seconds': frames / cfg['video']['fps'],
                          'requested_generation_seconds': shot_seconds,
                          'prompt': base + ' ' + [
                              'Extreme macro side view of the first knife contact and a clean fracture.',
                              'Three-quarter view of a second distinct slice; rigid transparent fragments settle.',
                              'Close view of a final slice revealing the refractive interior, with a natural pause.'
                          ][index % 3],
                          'audio_prompt': 'Dry sharp crystalline snap at blade contact, bright brittle glass ticks and short delicate ringing decay. No wet crunch, vegetable chopping, squelch, voice or music.'})
    return {'mode': 'offline-shot-plan', 'api_requests': 0, 'requires_paid_approval': True,
            'total_edited_seconds': cfg['duration_seconds'], 'shots': shots,
            'note': 'Generation durations are planning assumptions, not a provider request. No automatic retries or API calls.'}


def prepare(cfg, assets, directory, profile='original'):
    if profile not in ('original', 'glass-bright'):
        raise ValueError('Unknown audio profile')
    assets = Path(assets).resolve(strict=True)
    directory = Path(directory).resolve()
    if directory.exists():
        raise ValueError('Output directory already exists')
    scenes, missing, used = [], [], set()
    fps = cfg['video']['fps']
    for scene in cfg['scenes']:
        remaining = round((scene['end'] - scene['start']) * fps)
        entries = []
        for path in sorted((assets / scene['fruit']).glob('*.mp4')):
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(assets):
                raise ValueError('Assets must remain inside the asset directory')
            if resolved in used:
                continue
            info = probe(resolved)
            video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
            if video is None:
                raise ValueError(f'No video stream: {path.name}')
            frames = min(remaining, math.floor(stream_duration(video, info) * fps + 1e-6))
            if frames < 1:
                continue
            entries.append({'video': str(resolved), 'duration': frames / fps, 'audio_profile': profile})
            used.add(resolved)
            remaining -= frames
            if remaining == 0:
                break
        scenes.append({'fruit': scene['fruit'], 'clips': entries})
        if remaining:
            missing.append({'fruit': scene['fruit'], 'missing_seconds': remaining / fps})
    directory.mkdir(parents=True, exist_ok=False)
    report = {'status': 'needs-assets' if missing else 'ready-to-assemble', 'missing': missing,
              'audio_profile': profile, 'human_audio_review_required': True,
              'note': 'EQ cannot turn vegetable sounds into authentic glass or infer cut timing. No loops or synthetic substitutes.'}
    (directory / 'asset-report.json').write_text(json.dumps(report, indent=2) + '\n')
    (directory / 'shot-plan.json').write_text(json.dumps(shot_plan(cfg), indent=2) + '\n')
    if not missing:
        (directory / 'manifest.json').write_text(json.dumps({'scenes': scenes}, indent=2) + '\n')
    return report
