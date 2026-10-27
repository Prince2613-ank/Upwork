"""Read-only report inventory; never accepts a filesystem path from the browser."""
import hashlib
from pathlib import Path

from server.config import PROJECT_ROOT


def inventory(settings):
    roots = [(settings.data_dir / 'reports', True, 'Reports')]
    if settings.data_dir.resolve() == (PROJECT_ROOT / 'output/server').resolve():
        roots.extend([(PROJECT_ROOT / 'output', False, 'Local exports'),
                      (PROJECT_ROOT / 'output/reports', True, 'Local exports')])
    seen, entries = set(), []
    for root, recursive, source in roots:
        if not root.is_dir():
            continue
        for candidate in (root.rglob('*.html') if recursive else root.glob('*.html')):
            path = candidate.resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file() or path in seen:
                continue
            seen.add(path)
            stat = path.stat()
            relative = path.relative_to(root.resolve()).as_posix()
            entries.append({'id': hashlib.sha256((str(root.resolve()) + '/' + relative).encode()).hexdigest(),
                            'name': path.name, 'size': stat.st_size, 'updated_at': stat.st_mtime,
                            'source': source, 'path': path, 'relative': relative})
    return sorted(entries, key=lambda entry: entry['updated_at'], reverse=True)
