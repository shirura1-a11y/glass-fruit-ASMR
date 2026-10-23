import argparse
import json
import sys

import yaml

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
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
        if args.command == "prompts":
            result = prompts(cfg)
        elif args.command == "demo":
            result = demo(cfg, args.output_dir)
        elif args.command == "assemble":
            result = assemble(args.manifest, cfg, args.output)
        else:
            result = validate(args.video, cfg)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, yaml.YAMLError, ZeroDivisionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
