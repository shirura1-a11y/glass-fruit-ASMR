import argparse
import json
import sys
import zipfile

import yaml

from .automation import prepare, shot_plan
from .import_assets import import_assets
from .config import load_config, prompts
from .media import assemble, demo, validate


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline Glass Fruit ASMR preparation (no API client)")
    parser.add_argument("--config", default="config.yaml", help="YAML settings path")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prompts", help="Print prompt/timeline plan as JSON; never calls an API")
    demo_cmd = commands.add_parser("demo", help="Generate visibly labeled synthetic toolchain test")
    demo_cmd.add_argument("--output-dir", required=True, help="New directory for test media and report")
    edit_cmd = commands.add_parser("assemble", help="Assemble local media from a JSON manifest")
    edit_cmd.add_argument("--manifest", required=True)
    edit_cmd.add_argument("--output", required=True)
    check_cmd = commands.add_parser("validate", help="Probe and fully decode an existing MP4")
    check_cmd.add_argument("video")
    plan_cmd = commands.add_parser("plan", help="Offline per-shot video and glass-audio prompts")
    plan_cmd.add_argument("--fruit", choices=["strawberry", "apple", "grapes", "watermelon"])
    plan_cmd.add_argument("--shot-seconds", type=int, default=8)
    prepare_cmd = commands.add_parser("prepare", help="Inventory fruit/*.mp4 and prepare a non-looping manifest")
    prepare_cmd.add_argument("--assets", required=True)
    prepare_cmd.add_argument("--output-dir", required=True)
    prepare_cmd.add_argument("--audio-profile", choices=["original", "glass-bright"], default="original")
    import_cmd = commands.add_parser("import-assets", help="Import direct Release MP4s or a legacy ZIP")
    import_cmd.add_argument("--source", required=True)
    import_cmd.add_argument("--assets", required=True)
    import_cmd.add_argument("--fruit", choices=["strawberry", "apple", "grapes", "watermelon"], default="strawberry")
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
        if args.command == "import-assets":
            result = import_assets(args.source, args.assets, args.fruit)
        elif args.command == "plan":
            result = shot_plan(cfg, args.fruit, args.shot_seconds)
        elif args.command == "prepare":
            result = prepare(cfg, args.assets, args.output_dir, args.audio_profile)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "ready-to-assemble" else 2
        elif args.command == "prompts":
            result = prompts(cfg)
        elif args.command == "demo":
            result = demo(cfg, args.output_dir)
        elif args.command == "assemble":
            result = assemble(args.manifest, cfg, args.output)
        else:
            result = validate(args.video, cfg)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, yaml.YAMLError, ZeroDivisionError, zipfile.BadZipFile) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
