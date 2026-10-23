"""Network-free Runway campaign planning and labeled end-to-end mock generation.

This command deliberately has no live mode until approval and price verification.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from .config import load_config, prompts
from .media import assemble, probe, run, validate
from .runway import CAP_CENTS, Ledger, RunwayError, task_key


def campaign(cfg, video_cents=120, sound_cents=None):
    jobs = []
    for scene in prompts(cfg)['scenes']:
        if scene['required_edited_seconds'] != 10:
            raise RunwayError('This generation workflow requires 10 seconds per fruit')
        fruit = scene['fruit']
        video = {'model': 'gen4.5', 'duration': 10, 'ratio': '720:1280',
                 'promptText': scene['prompt'] + ' Complete the main knife contact and fracture around second 5.'}
        if len(video['promptText'].encode('utf-16-le')) // 2 > 1000:
            raise RunwayError('Video prompt exceeds 1000 UTF-16 code units')
        audio = {'model': 'eleven_text_to_sound_v2', 'duration': 10, 'loop': False,
                 'promptText': f'10-second close-mic ASMR: a knife slices a rigid transparent glass {fruit}. '
                 'Dry sharp crystalline fracture, brittle ticks and short delicate glass ringing. '
                 'One slow cut around the middle of the clip. No wet crunch, vegetable sound, music, speech or narration.'}
        for kind, payload, cents in [('video', video, video_cents), ('audio', audio, sound_cents)]:
            jobs.append(dict(key=task_key(kind, payload), fruit=fruit, kind=kind, payload=payload, cents=cents))
    known = all(type(j['cents']) is int and j['cents'] > 0 for j in jobs)
    total = sum(j['cents'] for j in jobs) if known else None
    return {'jobs': jobs, 'ceiling_cents': CAP_CENTS, 'estimated_cents': total,
            'pricing_verified': False, 'live_enabled': False,
            'status': 'price-review-required' if not known else ('over-budget' if total > CAP_CENTS else 'mock-only'),
            'note': 'Historical video rate, unknown current audio price. Mock prices are fixtures, never a quote.'}


class MockRunway:
    def __init__(self):
        self.submissions = 0

    def create(self, kind, payload):
        self.submissions += 1
        return 'mock-' + task_key(kind, payload)

    def materialize(self, job, task_id, target):
        mock_file(job, target)


def mock_file(job, target):
    partial = target.with_name(target.stem + '.partial' + target.suffix)
    if job['kind'] == 'video':
        run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i',
             'color=c=darkred:s=180x320:r=30', '-vf',
             "drawtext=text='SYNTHETIC MOCK - NOT AI FOOTAGE':fontsize=7:fontcolor=white:x=5:y=h/2",
             '-t', '10', '-c:v', 'libx264', '-threads', '2', partial])
    else:
        run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i',
             'sine=frequency=1200:sample_rate=48000', '-t', '10', '-c:a', 'pcm_s16le', partial])
    partial.replace(target)


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def generate_mock(cfg, directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    # Lock both media and ledger for the full run, including subprocesses.
    with (directory / 'campaign.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _generate_campaign(cfg, directory, MockRunway(), campaign(cfg, 120, 10), 'mock')


def generate_live(cfg, directory, client, *, video_cents, sound_cents,
                  user_approved=False, pricing_verified=False, account_cap_verified=False):
    """Internal integration seam; no CLI/workflow exposes it before the required review."""
    if not all(value is True for value in (user_approved, pricing_verified, account_cap_verified, client.allow_paid)):
        raise RunwayError('Live production needs user approval, verified prices and provider account cap')
    plan = campaign(cfg, video_cents, sound_cents)
    if plan['estimated_cents'] is None or plan['estimated_cents'] > CAP_CENTS:
        raise RunwayError('Unknown price or plan above $10; no API request sent')
    plan.update(pricing_verified=True, live_enabled=True, status='approved-live',
                note='Caller verified prices, user approval and provider account cap')
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'campaign.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _generate_campaign(cfg, directory, client, plan, 'live')


def _generate_campaign(cfg, directory, client, plan, mode):
    fingerprint = hashlib.sha256(json.dumps([mode, cfg, plan], sort_keys=True).encode()).hexdigest()
    identity = directory / 'campaign.json'
    if identity.exists() and json.loads(identity.read_text())['fingerprint'] != fingerprint:
        raise RunwayError('Campaign changed; keep its ledger and use a new directory')
    identity.write_text(json.dumps({'fingerprint': fingerprint, 'mode': mode, 'plan': plan}, indent=2))
    ledger = Ledger(directory / 'ledger.sqlite')
    try:
        reserved = ledger.reserve(plan['jobs'])
        manifest = {'synthetic_demo': mode == 'mock', 'scenes': []}
        for scene in cfg['scenes']:
            paths = {}
            for job in [j for j in plan['jobs'] if j['fruit'] == scene['fruit']]:
                task_id = ledger.submit(job, client)
                target = directory / (job['key'] + ('.mp4' if job['kind'] == 'video' else '.wav'))
                checksum = target.with_suffix(target.suffix + '.sha256')
                if not target.exists():
                    if checksum.exists():
                        raise RunwayError('Previously retained media is missing; restore checkpoint, do not regenerate')
                    client.materialize(job, task_id, target)
                    checksum.write_text(digest(target))
                elif not checksum.exists() or digest(target) != checksum.read_text():
                    raise RunwayError('Media integrity mismatch; no automatic regeneration')
                probe(target)
                ledger.update(job['key'], 'succeeded')
                paths[job['kind']] = str(target)
            manifest['scenes'].append({'fruit': scene['fruit'], 'clips': [
                {'video': paths['video'], 'audio': paths['audio'], 'duration': 10, 'audio_profile': 'original'}]})
        manifest_path = directory / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest, indent=2))
        output = directory / ('SYNTHETIC-MOCK-70S.mp4' if mode == 'mock' else 'GLASS-FRUIT.mp4')
        output_checksum = output.with_suffix('.mp4.sha256')
        if output.exists():
            if not output_checksum.exists() or digest(output) != output_checksum.read_text():
                raise RunwayError('Completed output integrity mismatch')
            report = validate(output, cfg)
        else:
            report = assemble(manifest_path, cfg, output)
            output_checksum.write_text(digest(output))
        report.update(mode='synthetic-mock' if mode == 'mock' else 'live',
                      reserved_ceiling_cents=reserved, visual_quality_reviewed=False,
                      semantic_audio_sync_reviewed=False)
        if mode == 'mock':
            report.update(paid_api_requests=0, actual_api_cost_cents=0,
                          simulated_reserved_cents=reserved, new_mock_submissions=client.submissions)
        (directory / 'run-report.json').write_text(json.dumps(report, indent=2))
        return report
    finally:
        ledger.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Runway plan or labeled offline mock; no live API mode')
    parser.add_argument('--config', default='configs/shorts-seven.yaml')
    parser.add_argument('--mode', choices=['plan', 'mock'], default='plan')
    parser.add_argument('--output-dir', default='outputs/runway-mock')
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
        result = campaign(cfg) if args.mode == 'plan' else generate_mock(cfg, args.output_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
