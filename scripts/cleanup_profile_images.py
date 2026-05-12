"""Cleanup orphaned profile image derivative sets.

Features:
- Detect base original images (pattern: student_<id>_*.jpg) in uploads/profile_pics
- Identify derivative siblings: _512.jpg/_256.jpg/_128.jpg and .webp
- Cross-check database User.profile_pic (normalized via get_profile_pic_path) to see if base file still referenced.
- If not referenced by any user (and not current for any), delete derivative set.
- Supports dry-run (default) and --apply to actually delete.
- Optional --days N to only consider files older than N days (default 2).

Usage (dry run):
  python scripts/cleanup_profile_images.py
Apply deletions:
  python scripts/cleanup_profile_images.py --apply
Cron example (daily at 02:30):
  30 2 * * * /path/to/venv/bin/python /srv/app/scripts/cleanup_profile_images.py --apply >> /var/log/piyuguide/cleanup.log 2>&1
"""
from __future__ import annotations
import os, re, argparse, sys, time, datetime
from typing import Dict, List, Set

# Ensure app import path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import create_app  # type: ignore
from app.extensions import db  # type: ignore
from app.models import User  # type: ignore

PROFILE_DIR = os.path.join(BASE_DIR, 'static', 'uploads', 'profile_pics')
BASE_PATTERN = re.compile(r'^(student_\d+_\d+)\.jpg$', re.IGNORECASE)

DERIVATIVE_SUFFIXES = ['_512.jpg', '_256.jpg', '_128.jpg', '.webp']


def list_current_profile_bases() -> Set[str]:
    bases: Set[str] = set()
    for user in User.query.filter(User.profile_pic.isnot(None)).all():
        rel = user.get_profile_pic_path()  # e.g., uploads/profile_pics/student_1_123456789.jpg
        if not rel:
            continue
        filename = rel.split('/')[-1]
        m = BASE_PATTERN.match(filename)
        if m:
            bases.add(m.group(1))
    return bases


def find_orphan_bases(current_bases: Set[str], min_mtime: float) -> Dict[str, List[str]]:
    orphans: Dict[str, List[str]] = {}
    if not os.path.isdir(PROFILE_DIR):
        return orphans
    for fname in os.listdir(PROFILE_DIR):
        m = BASE_PATTERN.match(fname)
        if not m:
            continue
        base_id = m.group(1)
        abs_base = os.path.join(PROFILE_DIR, fname)
        try:
            st = os.stat(abs_base)
        except OSError:
            continue
        if st.st_mtime > min_mtime:
            continue  # too new
        if base_id in current_bases:
            continue  # still referenced
        # Collect derivatives
        group_files = [abs_base]
        for suf in DERIVATIVE_SUFFIXES:
            cand = os.path.join(PROFILE_DIR, base_id + suf)
            if os.path.exists(cand):
                group_files.append(cand)
        orphans[base_id] = group_files
    return orphans


def human_size(num: int) -> str:
    for unit in ['B','KB','MB','GB']:
        if num < 1024.0:
            return f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}TB"


def total_bytes(files: List[str]) -> int:
    total = 0
    for f in files:
        try:
            total += os.path.getsize(f)
        except OSError:
            pass
    return total


def main():
    parser = argparse.ArgumentParser(description='Cleanup orphaned profile images')
    parser.add_argument('--apply', action='store_true', help='Perform deletions (otherwise dry-run)')
    parser.add_argument('--days', type=int, default=2, help='Only remove sets older than N days (default 2)')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        current_bases = list_current_profile_bases()
        cutoff = time.time() - args.days * 86400
        orphans = find_orphan_bases(current_bases, cutoff)
        if not orphans:
            print('No orphaned profile image sets found.')
            return 0
        grand = 0
        print(f"Found {len(orphans)} orphan base sets (older than {args.days} days). Dry-run={not args.apply}")
        for base, files in sorted(orphans.items()):
            size = total_bytes(files)
            grand += size
            print(f"- {base}: {len(files)} files, {human_size(size)}")
            for f in files:
                print(f"   {'DEL' if args.apply else 'KEEP'} {os.path.relpath(f, BASE_DIR)}")
                if args.apply:
                    try:
                        os.remove(f)
                    except OSError as e:
                        print(f"     (error removing {f}: {e})")
        print(f"Total potential reclaimed: {human_size(grand)}")
        if not args.apply:
            print('Re-run with --apply to delete.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
