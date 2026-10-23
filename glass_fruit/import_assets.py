"""Import ordinary Release MP4 attachments or the legacy ZIP, without network access."""
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from .config import FRUITS

ALIASES = {'strawberry': 'strawberry', 'イチゴ': 'strawberry', 'いちご': 'strawberry',
           'apple': 'apple', 'リンゴ': 'apple', 'りんご': 'apple',
           'grapes': 'grapes', 'grape': 'grapes', 'ブドウ': 'grapes', 'ぶどう': 'grapes',
           'watermelon': 'watermelon', 'スイカ': 'watermelon', 'すいか': 'watermelon'}
MAX_BYTES = 2_000_000_000


def fruit_for(name, default):
    prefix = re.split(r'[-_ .]', Path(name).stem.lower(), maxsplit=1)[0]
    return ALIASES.get(prefix, default)


def import_assets(source, destination, default_fruit='strawberry'):
    """Prefer direct MP4s when present; preserve the ZIP workflow as fallback."""
    if default_fruit not in FRUITS:
        raise ValueError('Unsupported default fruit')
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Asset destination already exists')
    mp4s = sorted(p for p in source.iterdir() if p.suffix.lower() == '.mp4')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.import-', dir=destination.parent) as tmp:
        staged = Path(tmp) / 'assets'
        staged.mkdir()
        imported = []
        if mp4s:
            if sum(p.stat().st_size for p in mp4s) > MAX_BYTES:
                raise ValueError('MP4 assets exceed 2 GB')
            for index, path in enumerate(mp4s, 1):
                if path.is_symlink() or not path.is_file():
                    raise ValueError('MP4 input must be a regular file, not a symlink')
                fruit = fruit_for(path.name, default_fruit)
                target = staged / fruit / f'{index:04d}.mp4'
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(path, target)
                imported.append({'source': path.name, 'fruit': fruit, 'video': f'{fruit}/{target.name}'})
            mode = 'direct-mp4'
        else:
            archive_path = source / 'fruit-assets.zip'
            if archive_path.is_symlink():
                raise ValueError('ZIP input cannot be a symlink')
            if not archive_path.is_file():
                raise ValueError('No MP4 attachments or fruit-assets.zip found in the selected release')
            with zipfile.ZipFile(archive_path) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(e.file_size for e in entries) > MAX_BYTES:
                    raise ValueError('Archive exceeds file count or 2 GB limit')
                names = set()
                for entry in sorted(entries, key=lambda item: item.filename):
                    path = staged / entry.filename
                    if not path.resolve().is_relative_to(staged.resolve()) or '\\' in entry.filename:
                        raise ValueError('Unsafe archive path')
                    if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Archive symlinks are not supported')
                    if entry.is_dir():
                        continue
                    parts = Path(entry.filename).parts
                    if len(parts) != 2 or parts[0] not in FRUITS or path.suffix.lower() != '.mp4':
                        raise ValueError('ZIP must contain only fruit/*.mp4 files')
                    if entry.filename in names:
                        raise ValueError('Duplicate archive member')
                    names.add(entry.filename)
                    # Normalize uppercase extensions for the existing editor.
                    target = staged / parts[0] / f'{len(imported)+1:04d}.mp4'
                    target.parent.mkdir(exist_ok=True)
                    with archive.open(entry) as src, target.open('xb') as dst:
                        shutil.copyfileobj(src, dst)
                    imported.append({'source': entry.filename, 'fruit': parts[0],
                                     'video': str(target.relative_to(staged))})
            if not imported:
                raise ValueError('ZIP contains no MP4 assets')
            mode = 'legacy-zip'
        report = {'mode': mode, 'default_fruit': default_fruit, 'files': imported}
        (staged / 'import-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        staged.rename(destination)
    return report
