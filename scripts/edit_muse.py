"""Edit the seven repository Muse clips without padding or speed changes."""
import json
import math
import re
import subprocess
from pathlib import Path

ORDER = ['strawberry', 'apple', 'watermelon', 'kiwi', 'grapes', 'lemon', 'peach']
OUT = Path('outputs/muse-tiktok')


def run(args):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=1200)
    if result.returncode:
        raise RuntimeError(result.stderr[-6000:])
    return result.stdout + result.stderr


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'order': ORDER, 'clips': [], 'status': 'inspecting'}
    try:
        for fruit in ORDER:
            matches = list(Path('.').glob(f'media-generation-glass-{fruit}-*.mp4'))
            if len(matches) != 1:
                raise ValueError(f'{fruit}: expected exactly one source, found {len(matches)}')
            path = matches[0]
            info = probe(path)
            video = next(s for s in info['streams'] if s['codec_type'] == 'video')
            audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
            duration = min(float(video['duration']), float(audio['duration']))
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError(f'{fruit}: invalid duration')
            # Only remove measured leading silence; never remove pauses inside a cut.
            silence = run(['ffmpeg', '-hide_banner', '-i', path, '-t', '2', '-af', 'silencedetect=noise=-40dB:d=0.15', '-vn', '-f', 'null', '-'])
            start = 0.0
            if re.search(r'silence_start: 0(?:\s|\n)', silence):
                end = re.search(r'silence_end: ([0-9.]+)', silence)
                if end:
                    start = min(1.0, max(0.0, float(end[1]) - 0.08))
            report['clips'].append({'fruit': fruit, 'source': str(path), 'source_seconds': duration,
                                    'start': start, 'seconds': duration - start,
                                    'width': video['width'], 'height': video['height']})
        total = sum(c['seconds'] for c in report['clips'])
        raw = sum(c['source_seconds'] for c in report['clips'])
        report.update(source_seconds=raw, trimmed_seconds=total)
        if total < 61:
            raise ValueError(f'Usable footage is {total:.3f}s (original {raw:.3f}s). At least 61s required; no looping, freezing or slowing is allowed.')
        # Trim excess evenly; preserve real-time motion and synchronized original sound.
        target = min(total, 68.0)
        factor = target / total
        width = min(1080, min(c['width'] for c in report['clips']))
        width = max(18, width // 18 * 18)
        height = width * 16 // 9
        parts = []
        for i, clip in enumerate(report['clips']):
            seconds = math.floor(clip['seconds'] * factor * 30) / 30
            clip['output_seconds'] = seconds
            analysis = run(['ffmpeg', '-hide_banner', '-ss', clip['start'], '-i', clip['source'], '-t', seconds,
                            '-vn', '-af', 'loudnorm=I=-20:TP=-2:LRA=11:print_format=json', '-f', 'null', '-'])
            stats = json.loads(analysis[analysis.rfind('{'):analysis.rfind('}') + 1])
            # A fixed gain per clip preserves the glass transients and local dynamics.
            measured = float(stats['input_i'])
            peak = float(stats['input_tp'])
            if not math.isfinite(measured) or not math.isfinite(peak):
                raise ValueError(f"{clip['fruit']}: missing usable sound")
            gain = min(6.0, -20 - measured, -2 - peak)
            gain = max(-12.0, gain)
            clip['gain_db'] = gain
            part = OUT / f'part-{i}.mp4'
            run(['ffmpeg', '-v', 'error', '-y', '-ss', clip['start'], '-i', clip['source'], '-t', seconds,
                 '-map', '0:v:0', '-map', '0:a:0', '-vf',
                 f'scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30',
                 '-af', f'volume={gain}dB,aresample=48000', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
                 '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '256k', '-ac', '2', '-map_metadata', '-1', part])
            parts.append(part)
        listing = OUT / 'concat.txt'
        listing.write_text(''.join(f"file '{p.name}'\n" for p in parts))
        final = OUT / 'GLASS-FRUIT-TIKTOK.mp4'
        run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '1', '-i', listing,
             '-c', 'copy', '-movflags', '+faststart', '-map_metadata', '-1', final])
        info = probe(final)
        duration = float(info['format']['duration'])
        if not 61 <= duration <= 70:
            final.unlink()
            raise ValueError(f'Output duration outside 61–70s: {duration}')
        run(['ffmpeg', '-v', 'error', '-xerror', '-i', final, '-f', 'null', '-'])
        report.update(status='complete', output_seconds=duration, width=width, height=height,
                      note='Leading-silence trim only; visual cutting onset and subjective sound require playback review.')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as exc:
        report.update(status='incomplete', error=str(exc))
        raise
    finally:
        (OUT / 'edit-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
