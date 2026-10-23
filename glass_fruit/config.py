"""Strict settings validation; this stage never enables provider calls."""
import math
from pathlib import Path

import yaml

FRUITS = {"strawberry": "strawberry", "apple": "apple", "grapes": "cluster of grapes", "watermelon": "watermelon", "orange": "orange", "kiwi": "kiwi fruit", "peach": "peach"}


def number(value, name, low=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < low:
        raise ValueError(f"{name} must be a finite number >= {low}")
    return value


def load_config(path):
    with Path(path).open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    if not isinstance(cfg, dict):
        raise ValueError("Config must be a mapping")
    try:
        cost = cfg["cost"]
        if cost["enable_paid_api"] is not False or number(cost["max_usd_per_run"], "budget") != 0:
            raise ValueError("Stage 1 is offline only: paid API must be false and budget must be zero")
        duration = number(cfg["duration_seconds"], "duration", 0.1)
        minimum = number(cfg["min_duration_seconds"], "minimum duration", 0.1)
        maximum = number(cfg["max_duration_seconds"], "maximum duration", 0.1)
        if not minimum <= duration <= maximum <= 600:
            raise ValueError("Expected min <= duration <= max <= 600 seconds")
        video = cfg["video"]
        for field in ("width", "height", "fps"):
            value = video[field]
            if type(value) is not int or value <= 0:
                raise ValueError(f"video.{field} must be a positive integer")
        if video["width"] % 2 or video["height"] % 2 or max(video["width"], video["height"]) > 8192:
            raise ValueError("Video dimensions must be even and at most 8192")
        if video["width"] * 16 != video["height"] * 9 or video["fps"] > 60:
            raise ValueError("Expected 9:16 video and fps <= 60")
        if video["codec"] != "libx264" or video["audio_codec"] != "aac":
            raise ValueError("Only libx264 and AAC are supported")
        if video["narration"] is not False or video["bgm"] is not False:
            raise ValueError("Narration and BGM must remain disabled")
        scenes = cfg["scenes"]
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("At least one scene is required")
        previous = 0
        for index, scene in enumerate(scenes):
            if scene["fruit"] not in FRUITS:
                raise ValueError(f"Unsupported fruit at scene {index + 1}")
            start = number(scene["start"], "scene start")
            end = number(scene["end"], "scene end")
            if abs(start - previous) > 1e-6 or end <= start:
                raise ValueError("Scenes must be positive, ordered and contiguous from zero")
            for time in (start, end):
                if abs(time * video["fps"] - round(time * video["fps"])) > 1e-6:
                    raise ValueError("Scene boundaries must align with video frames")
            previous = end
        if abs(previous - duration) > 1e-6:
            raise ValueError("Scene end must equal duration_seconds")
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Missing or invalid config field: {exc}") from exc
    return cfg


def prompts(cfg):
    result = []
    for index, scene in enumerate(cfg["scenes"], 1):
        result.append({
            "scene": index, "fruit": scene["fruit"],
            "timeline_start": scene["start"], "timeline_end": scene["end"],
            "required_edited_seconds": scene["end"] - scene["start"],
            "prompt": (
                f"Photorealistic macro cinematography of a transparent glass {FRUITS[scene['fruit']]} "
                "on a clean wooden cutting board. A realistic knife slowly presses into the glass, "
                "then completes a single physically coherent cut; the separated pieces settle naturally. "
                "Show contact, fracture and separation with consistent geometry, realistic refraction, "
                "soft studio light and a stable camera. Vertical 9:16 composition. "
                "Close dry cutting and delicate glass fracture sounds synchronized to visible contact. "
                "No voice, music, text, logos, looping, morphing or extra fingers."
            ),
            "note": "Planning text only; no API call. Split long scenes into distinct approved shots; do not loop clips.",
        })
    return {"mode": "offline-prompt-plan", "paid_api_enabled": False, "scenes": result}
