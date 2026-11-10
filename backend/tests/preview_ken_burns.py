"""
backend/tests/preview_ken_burns.py — Visual preview script for render_ken_burns().

Not a pytest test. Renders real Ken-Burns clips to disk so you can watch the
zoom/pan motion and confirm timing looks right, instead of asserting on pixels.

Usage:
    python backend/tests/preview_ken_burns.py path/to/image.png
    python backend/tests/preview_ken_burns.py path/to/image.png --duration 3 --intensity 0.25
    python backend/tests/preview_ken_burns.py path/to/image.png --out-dir /tmp/kb_preview

Renders one clip per direction (zoom_in, zoom_out, pan_left, pan_right) at the
given duration/intensity, then opens the output folder (macOS) so you can play
them.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ken_burns import render_ken_burns

DIRECTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Path to a source image (png/jpg)")
    parser.add_argument("--duration", type=float, default=4.0, help="Clip duration in seconds (default: 4.0)")
    parser.add_argument("--intensity", type=float, default=0.2, help="Zoom/pan intensity, 0.1-0.3 (default: 0.2)")
    parser.add_argument("--width", type=int, default=960, help="Output width (default: 960)")
    parser.add_argument("--height", type=int, default=540, help="Output height (default: 540)")
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/ken_burns_preview"), help="Output directory")
    parser.add_argument("--direction", choices=DIRECTIONS, help="Render only this one direction")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open the output folder")
    args = parser.parse_args()

    if not args.image.exists():
        parser.error(f"Image not found: {args.image}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    directions = [args.direction] if args.direction else DIRECTIONS

    print(f"Source image: {args.image}")
    print(f"Duration: {args.duration}s  Intensity: {args.intensity}  Size: {args.width}x{args.height}")
    print(f"Output dir: {args.out_dir}\n")

    for direction in directions:
        out_path = args.out_dir / f"{direction}_d{args.duration}_i{args.intensity}.mp4"
        print(f"Rendering {direction} -> {out_path.name} ...")
        render_ken_burns(
            args.image,
            out_path,
            direction,
            intensity=args.intensity,
            duration_seconds=args.duration,
            width=args.width,
            height=args.height,
        )
        print(f"  done ({out_path.stat().st_size} bytes)")

    print("\nAll clips rendered.")
    if not args.no_open and sys.platform == "darwin":
        subprocess.run(["open", str(args.out_dir)])


if __name__ == "__main__":
    main()
