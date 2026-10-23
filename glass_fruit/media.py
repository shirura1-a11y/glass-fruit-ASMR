"""Local-only FFmpeg processing. There is intentionally no provider client."""
import json
import math
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

from .config import number


def run(args):
    try:
        completed = subprocess.run([str(arg) for arg in args], capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"{args[0]} exceeded the 300-second command limit; no retry was made") from exc
    if completed.returncode:
        raise ValueError(f"{args[0]} failed ({completed.returncode}): {completed.stderr[-4000:]}")
    return completed.stdout


def tools_ready():
    for name in ("ffmpeg", "ffprobe"):
        if shutil.which(name) is None:
            raise ValueError(f"Required executable not found: {name}")


def probe(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Not a local file: {path}")
    return json.loads(run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                           "-show_streams", "-show_format", "-of", "json", path]))


def stream_duration(stream, info):
    raw = stream.get("duration", info.get("format", {}).get("duration"))
    try:
        duration = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Media duration is unavailable") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Media duration must be positive and finite")
    return duration


def validate(path, cfg):
    tools_ready()
    info = probe(path)
    videos = [s for s in info["streams"] if s["codec_type"] == "video"]
    audios = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if len(videos) != 1 or len(audios) != 1:
        raise ValueError("Expected exactly one video and one audio stream")
    video, audio = videos[0], audios[0]
    expected = cfg["video"]
    if (video["width"], video["height"]) != (expected["width"], expected["height"]):
        raise ValueError("Video resolution does not match config")
    if video["codec_name"] != "h264" or audio["codec_name"] != "aac":
        raise ValueError("Expected H.264 video and AAC audio")
    if video.get("pix_fmt") != "yuv420p":
        raise ValueError("Expected yuv420p video")
    if Fraction(video["avg_frame_rate"]) != expected["fps"]:
        raise ValueError("Video frame rate does not match config")
    duration = stream_duration(video, info)
    audio_duration = stream_duration(audio, info)
    tolerance = max(1 / expected["fps"], 0.05)
    if abs(duration - cfg["duration_seconds"]) > tolerance:
        raise ValueError("Video duration does not match planned timeline")
    if not cfg["min_duration_seconds"] - tolerance <= duration <= cfg["max_duration_seconds"] + tolerance:
        raise ValueError("Video duration is outside allowed bounds")
    if abs(audio_duration - duration) > max(tolerance, 0.1):
        raise ValueError("Audio/video duration mismatch")
    for stream in (video, audio):
        if abs(float(stream.get("start_time", 0))) > max(tolerance, 0.1):
            raise ValueError("Audio/video stream does not start at zero")
    run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-protocol_whitelist", "file,pipe",
         "-i", Path(path).resolve(), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"])
    return {"status": "passed", "path": str(Path(path).resolve()), "duration_seconds": duration,
            "audio_duration_seconds": audio_duration, "width": video["width"], "height": video["height"],
            "fps": expected["fps"], "video_codec": "h264", "audio_codec": "aac",
            "decoded": True, "visual_quality_reviewed": False,
            "note": "Technical checks do not establish realism, semantic audio sync, licensing or platform eligibility."}


def read_manifest(path, cfg):
    path = Path(path).resolve(strict=True)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("scenes"), list):
        raise ValueError("Manifest must contain a scenes list")
    if len(manifest["scenes"]) != len(cfg["scenes"]):
        raise ValueError("Manifest must supply exactly the configured scenes in order")
    clips = []
    for planned, supplied in zip(cfg["scenes"], manifest["scenes"]):
        if not isinstance(supplied, dict) or supplied.get("fruit") != planned["fruit"]:
            raise ValueError("Manifest scene order/fruit does not match config")
        entries = supplied.get("clips")
        if not isinstance(entries, list) or not entries:
            raise ValueError("Each manifest scene requires nonempty clips")
        total = 0
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Each clip must be an object")
            seconds = number(entry.get("duration"), "clip duration", 0.01)
            start = number(entry.get("video_start", 0), "video_start")
            offset = entry.get("audio_offset", 0)
            number(abs(offset) if type(offset) in (float, int) else None, "audio_offset")
            if abs(seconds * cfg["video"]["fps"] - round(seconds * cfg["video"]["fps"])) > 1e-6:
                raise ValueError("Clip durations must align with video frames")
            video_name = entry.get("video")
            if not isinstance(video_name, str) or not video_name:
                raise ValueError("Clip requires a local video path")
            video_path = (path.parent / video_name).resolve(strict=True)
            info = probe(video_path)
            video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
            if video is None or stream_duration(video, info) + 0.001 < start + seconds:
                raise ValueError("Source video is too short; supply distinct shots instead of looping")
            audio_path = None
            has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
            if "audio" in entry:
                if not isinstance(entry["audio"], str) or not entry["audio"]:
                    raise ValueError("audio must be a local path")
                audio_path = (path.parent / entry["audio"]).resolve(strict=True)
                audio_info = probe(audio_path)
                audio = next((s for s in audio_info["streams"] if s["codec_type"] == "audio"), None)
                if audio is None:
                    raise ValueError("External audio file has no audio stream")
                if stream_duration(audio, audio_info) + offset <= 0 or offset >= seconds:
                    raise ValueError("External audio has no overlap with the clip")
            elif has_audio:
                audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
                if stream_duration(audio, info) - start + offset <= 0 or offset >= seconds:
                    raise ValueError("Source audio has no overlap with the clip")
            elif offset != 0:
                raise ValueError("Cannot offset a silent source")
            clips.append({"video": video_path, "audio": audio_path, "has_audio": has_audio,
                          "duration": seconds, "video_start": start, "audio_offset": offset})
            total += seconds
        if abs(total - (planned["end"] - planned["start"])) > 1e-6:
            raise ValueError("Clip durations must exactly fill each scene")
    return manifest, clips


def normalize(clip, cfg, output):
    video = cfg["video"]
    duration = clip["duration"]
    args = ["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
            "-ss", clip["video_start"], "-i", clip["video"]]
    if clip["audio"]:
        args += ["-protocol_whitelist", "file,pipe", "-i", clip["audio"]]
        audio_input = "1:a:0"
    elif clip["has_audio"]:
        audio_input = "0:a:0"
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        audio_input = "1:a:0"
    offset = clip["audio_offset"]
    af = "asetpts=PTS-STARTPTS,aresample=48000"
    if offset < 0:
        af += f",atrim=start={-offset},asetpts=PTS-STARTPTS"
    elif offset > 0:
        af += f",adelay={round(offset * 1000)}:all=1"
    af += f",apad,atrim=duration={duration},asetpts=PTS-STARTPTS"
    vf = (f"scale={video['width']}:{video['height']}:force_original_aspect_ratio=decrease,"
          f"pad={video['width']}:{video['height']}:(ow-iw)/2:(oh-ih)/2,"
          f"setsar=1,fps={video['fps']},trim=duration={duration},setpts=PTS-STARTPTS,format=yuv420p")
    run(args + ["-map", "0:v:0", "-map", audio_input, "-vf", vf, "-af", af,
                "-t", duration, "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-threads", "2",
                "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", output])


def assemble(manifest_path, cfg, output):
    tools_ready()
    manifest, clips = read_manifest(manifest_path, cfg)
    output = Path(output).resolve()
    report_path = output.with_suffix(".validation.json")
    if output.suffix.lower() != ".mp4":
        raise ValueError("Output must be an .mp4 file")
    if output.exists() or report_path.exists():
        raise ValueError("Output/report already exists; choose a new path")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".glass-fruit-", dir=output.parent) as folder:
        folder = Path(folder)
        for index, clip in enumerate(clips):
            normalize(clip, cfg, folder / f"part-{index:03d}.mov")
        listing = folder / "concat.txt"
        listing.write_text("".join(f"file 'part-{i:03d}.mov'\n" for i in range(len(clips))), encoding="utf-8")
        target = folder / "assembled.mp4"
        run(["ffmpeg", "-nostdin", "-v", "error", "-f", "concat", "-safe", "1", "-i", listing,
             "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-t", cfg["duration_seconds"], "-movflags", "+faststart", target])
        report = validate(target, cfg)
        report["path"] = str(output)
        report["synthetic_demo"] = manifest.get("synthetic_demo") is True
        report["source_clips"] = len(clips)
        target.rename(output)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def demo(cfg, directory):
    """Watermarked synthetic sources exercise the same assembler as real local files."""
    tools_ready()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"synthetic_demo": True, "note": "NOT AI FRUIT FOOTAGE. Test pattern and test tones only.", "scenes": []}
    colors = ["darkred", "darkgreen", "indigo", "darkblue"]
    for index, scene in enumerate(cfg["scenes"]):
        duration = scene["end"] - scene["start"]
        source = directory / f"synthetic-{index:02d}.mp4"
        audio = directory / f"test-tone-{index:02d}.wav"
        label = f"SYNTHETIC TEST - NOT AI FOOTAGE - {scene['fruit'].upper()}"
        run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
             f"color=c={colors[index % len(colors)]}:s=360x640:r={cfg['video']['fps']}",
             "-vf", f"drawtext=text='{label}':fontcolor=white:fontsize=10:x=(w-tw)/2:y=h/2",
             "-t", duration, "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2", source])
        run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
             f"sine=frequency={440 + index * 110}:sample_rate=48000", "-t", duration,
             "-c:a", "pcm_s16le", audio])
        manifest["scenes"].append({"fruit": scene["fruit"], "clips": [{"video": source.name,
                                  "audio": audio.name, "audio_offset": 0.1, "duration": duration}]})
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return assemble(manifest_path, cfg, directory / "SYNTHETIC-DEMO.mp4")
