#!/usr/bin/env python3
"""
stitchandasciify.py
"""

from __future__ import annotations

import argparse
import concurrent.futures
import re
import sys
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Dependency check first, with a friendly message instead of a raw traceback.
# This is the very first thing that can go wrong for a non-programmer running
# this by double-click, so it gets a dedicated, actionable error.
# ---------------------------------------------------------------------------
try:
    import numpy as np
    from PIL import Image, ImageEnhance
except ImportError as exc:
    print("=" * 70)
    print("Missing required package:", exc.name if hasattr(exc, "name") else exc)
    print()
    print("This script needs Pillow and numpy. Install them with:")
    print()
    print("    pip install pillow numpy")
    print()
    print("Then run this script again.")
    print("=" * 70)
    input("Press Enter to exit...")
    sys.exit(1)

# Pillow renamed Image.LANCZOS -> Image.Resampling.LANCZOS in v9.1. Support both
# so this works whether the user has an old or new Pillow on Python 3.12/3.14.
RESAMPLE_FILTER = getattr(getattr(Image, "Resampling", Image), "LANCZOS")

# ---------------------------------------------------------------------------
# Constants (H1: no unexplained magic numbers/strings below this point)
# ---------------------------------------------------------------------------

# Filename pattern used by the ZeldaDungeon tile pyramid: "{col}_{row}.jpg"
TILE_FILENAME_RE = re.compile(r"^(\d+)_(\d+)\.(jpg|jpeg|png)$", re.IGNORECASE)

DEFAULT_TILE_RESOLUTION = 100  # ASCII characters sampled per tile edge
DEFAULT_OUTPUT_NAME = "BOTW-ASCII.txt"

# Simple 10-level ramp (fast, low detail).
RAMP_SIMPLE = " .:-=+*#%@"

# Classic 70-level Paul Bourke density ramp (slow to eyeball, great detail).
# Ordered sparse -> dense.
RAMP_DETAILED = (
    " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
)

RAMPS = {"simple": RAMP_SIMPLE, "detailed": RAMP_DETAILED}

# Above this many total ASCII characters we ask for confirmation before
# grinding through the conversion (protects a curious double-click user from
# accidentally generating a multi-hundred-MB text file and wondering why
# their PC fans spun up).
CONFIRMATION_THRESHOLD_CHARS = 9_000_000  # ~ a 3000x3000 grid

# A neutral mid-gray used for placeholder tiles that are missing from the set.
PLACEHOLDER_GRAY_VALUE = 128


class TileGridError(RuntimeError):
    """Raised for problems with the tile directory that the user must fix."""


def resolve_tile_directory(argv: list[str]) -> Path:
    """
    Figure out which folder holds the tiles, supporting several ways a
    real person actually invokes this script:

      1. Dragging a single folder onto the .py file      -> argv = [folder]
      2. Dragging one or more loose tile files onto it    -> argv = [file, file, ...]
      3. Passing a path explicitly on the command line    -> argv = [path]
      4. Double-clicking with no arguments at all          -> argv = []

    Never silently guesses across ambiguous input; falls back to an
    interactive prompt only when nothing else worked.
    """
    if argv:
        paths = [Path(p) for p in argv]
        existing = [p for p in paths if p.exists()]
        if not existing:
            raise TileGridError(
                f"None of the path(s) you provided exist:\n"
                + "\n".join(f"  {p}" for p in paths)
            )
        first = existing[0]
        if first.is_dir():
            return first.resolve()
        # One or more files were dragged in directly -> use their common parent.
        return first.parent.resolve()

    # No arguments: look for common relative locations next to the script
    # or the current working directory before bothering the user.
    script_dir = Path(__file__).resolve().parent
    candidates = [
        Path.cwd() / "tiles" / "5",
        Path.cwd() / "5",
        script_dir / "tiles" / "5",
        script_dir / "5",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    print("No tile folder was given.")
    print("Drag the tile folder onto this script, or type its path below.")
    typed = input("Path to tile folder: ").strip().strip('"')
    if not typed:
        raise TileGridError("No path entered.")
    path = Path(typed)
    if not path.is_dir():
        raise TileGridError(f"Not a folder: {path}")
    return path.resolve()


def discover_tiles(tile_dir: Path) -> tuple[dict[tuple[int, int], Path], int, int]:
    """
    Scan tile_dir for files matching "{col}_{row}.ext" and return:
      - a dict mapping (col, row) -> file path
      - the number of columns (max col + 1)
      - the number of rows    (max row + 1)

    Grid size is inferred from the filenames themselves (A4: never assume a
    fixed 32x32 -- a different zoom level or a partial download would silently
    produce a wrong/cropped result if we hardcoded it).
    """
    tiles: dict[tuple[int, int], Path] = {}
    for entry in tile_dir.iterdir():
        if not entry.is_file():
            continue
        match = TILE_FILENAME_RE.match(entry.name)
        if not match:
            continue
        col, row = int(match.group(1)), int(match.group(2))
        tiles[(col, row)] = entry

    if not tiles:
        raise TileGridError(
            f"No tile files matching NUMBER_NUMBER.jpg were found in:\n  {tile_dir}\n"
            "Make sure this is the folder that directly contains files like "
            "'0_0.jpg', '0_1.jpg', etc."
        )

    max_col = max(col for col, _ in tiles)
    max_row = max(row for _, row in tiles)
    cols, rows = max_col + 1, max_row + 1
    return tiles, cols, rows


def get_reference_tile_size(tiles: dict[tuple[int, int], Path]) -> tuple[int, int]:
    """Open the first available tile to learn the source pixel dimensions."""
    any_path = next(iter(tiles.values()))
    with Image.open(any_path) as img:
        return img.size  # (width, height)


def build_ascii_ramp(name: str, custom: Optional[str]) -> str:
    if custom:
        if len(custom) < 2:
            raise TileGridError("--charset must contain at least 2 characters.")
        return custom
    if name not in RAMPS:
        raise TileGridError(f"Unknown ramp '{name}'. Choose from: {', '.join(RAMPS)}")
    return RAMPS[name]


def tile_to_ascii_block(
    tile_path: Optional[Path],
    tile_res: int,
    ramp: np.ndarray,
    invert: bool,
    contrast: float,
    brightness: float,
    reference_size: tuple[int, int],
) -> np.ndarray:
    """
    Convert a single tile image (or a gray placeholder, if tile_path is None
    because that tile is missing from the set) into a (tile_res, tile_res)
    array of single characters.
    """
    if tile_path is None:
        # A4: don't assume every tile exists -- fill gaps with a flat gray
        # placeholder so one missing file can't crash the whole stitch.
        gray = np.full((tile_res, tile_res), PLACEHOLDER_GRAY_VALUE, dtype=np.float64)
    else:
        with Image.open(tile_path) as img:
            img = img.convert("L")  # grayscale luminance
            if img.size != reference_size:
                # Tiles are supposed to be uniform; if one is a stray odd
                # size (partial edge tile), normalize it instead of letting
                # it desync the grid.
                img = img.resize(reference_size, RESAMPLE_FILTER)
            if contrast != 1.0:
                img = ImageEnhance.Contrast(img).enhance(contrast)
            if brightness != 1.0:
                img = ImageEnhance.Brightness(img).enhance(brightness)
            img = img.resize((tile_res, tile_res), RESAMPLE_FILTER)
            gray = np.asarray(img, dtype=np.float64)

    normalized = gray / 255.0
    if invert:
        # "Classic" ink-on-paper mapping: dark pixel -> dense character.
        normalized = 1.0 - normalized

    ramp_len = len(ramp)
    indices = np.clip((normalized * (ramp_len - 1)).round().astype(np.int64), 0, ramp_len - 1)
    return ramp[indices]


def render_progress(done: int, total: int, start_time: float) -> None:
    """Single-line progress indicator; avoids a tqdm dependency."""
    pct = done / total if total else 1.0
    elapsed = time.perf_counter() - start_time
    eta = (elapsed / done * (total - done)) if done else 0.0
    bar_width = 30
    filled = int(bar_width * pct)
    bar = "#" * filled + "-" * (bar_width - filled)
    sys.stdout.write(
        f"\r  [{bar}] {done}/{total} tiles ({pct*100:5.1f}%)  ETA {eta:5.1f}s"
    )
    sys.stdout.flush()
    if done == total:
        sys.stdout.write("\n")


def stitch_and_asciify(
    tile_dir: Path,
    output_path: Path,
    tile_res: int,
    ramp_str: str,
    invert: bool,
    contrast: float,
    brightness: float,
    workers: int,
    assume_yes: bool,
) -> None:
    print(f"Scanning tiles in: {tile_dir}")
    tiles, cols, rows = discover_tiles(tile_dir)
    expected_total = cols * rows
    missing = expected_total - len(tiles)

    print(f"Detected a {cols} x {rows} tile grid ({expected_total} tiles expected).")
    if missing:
        print(f"  Note: {missing} tile(s) are missing and will be filled with gray.")

    reference_size = get_reference_tile_size(tiles)
    print(f"Reference tile size: {reference_size[0]}x{reference_size[1]} px")

    ascii_width = cols * tile_res
    ascii_height = rows * tile_res
    total_chars = ascii_width * ascii_height
    print(
        f"Output ASCII grid: {ascii_width} x {ascii_height} characters "
        f"({total_chars:,} total)."
    )

    if total_chars > CONFIRMATION_THRESHOLD_CHARS and not assume_yes:
        approx_mb = total_chars / (1024 * 1024)
        answer = input(
            f"That's a large output (~{approx_mb:.0f} MB as text). Continue? [y/N] "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return

    ramp_array = np.array(list(ramp_str))

    # Pre-allocate the full character grid. Each tile writes into its own,
    # non-overlapping slice, so doing this from multiple threads is safe
    # without a lock (B5: shared mutable state is fine here specifically
    # because no two tasks ever touch the same memory region).
    full_grid = np.empty((ascii_height, ascii_width), dtype="<U1")

    tasks = [(col, row) for row in range(rows) for col in range(cols)]
    start_time = time.perf_counter()
    done_count = 0
    lock_free_progress_step = max(1, len(tasks) // 200)  # don't spam stdout

    def process_one(col: int, row: int) -> None:
        path = tiles.get((col, row))
        block = tile_to_ascii_block(
            path, tile_res, ramp_array, invert, contrast, brightness, reference_size
        )
        row_start, row_end = row * tile_res, (row + 1) * tile_res
        col_start, col_end = col * tile_res, (col + 1) * tile_res
        full_grid[row_start:row_end, col_start:col_end] = block

    print("Converting tiles to ASCII...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_one, col, row): (col, row) for col, row in tasks}
        for future in concurrent.futures.as_completed(futures):
            col, row = futures[future]
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001 - log-and-continue is the
                # intentional recovery strategy here: one bad tile shouldn't
                # abort a run that's minutes into a 1000+ tile job. The tile
                # keeps whatever was written into full_grid (still zeros/
                # empty at worst) and we tell the user which one failed.
                print(f"\n  Warning: tile ({col},{row}) failed: {exc}")
            done_count += 1
            if done_count % lock_free_progress_step == 0 or done_count == len(tasks):
                render_progress(done_count, len(tasks), start_time)

    print("Writing output file...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        for row_index in range(ascii_height):
            handle.write("".join(full_grid[row_index]))
            handle.write("\n")

    elapsed = time.perf_counter() - start_time
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Done in {elapsed:.1f}s. Wrote {size_mb:.1f} MB to:\n  {output_path}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stitch map tiles into one big ASCII-art text file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Tile folder (or file(s) dragged from it). If omitted, the "
        "script looks near itself or asks interactively.",
    )
    parser.add_argument(
        "-r",
        "--tile-res",
        type=int,
        default=DEFAULT_TILE_RESOLUTION,
        help=f"ASCII characters sampled per tile edge (default: {DEFAULT_TILE_RESOLUTION}).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help=f"Output file path (default: '{DEFAULT_OUTPUT_NAME}' next to the tile folder).",
    )
    parser.add_argument(
        "--ramp",
        choices=list(RAMPS.keys()),
        default="detailed",
        help="Built-in character density ramp to use (default: detailed).",
    )
    parser.add_argument(
        "--charset",
        type=str,
        default=None,
        help="Custom character ramp, ordered sparse->dense, overrides --ramp.",
    )
    parser.add_argument(
        "--classic",
        action="store_true",
        help="Use ink-on-paper mapping (dark pixel = dense char). Default "
        "maps bright pixel = dense char, which looks correct on the dark "
        "themed HTML viewer.",
    )
    parser.add_argument(
        "--contrast", type=float, default=1.15, help="Contrast multiplier (default: 1.15)."
    )
    parser.add_argument(
        "--brightness", type=float, default=1.0, help="Brightness multiplier (default: 1.0)."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Parallel worker threads (default: CPU count).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Don't ask for confirmation on very large outputs, and don't "
        "pause for Enter at the end.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    pause_at_exit = not args.yes

    try:
        tile_dir = resolve_tile_directory(args.paths)
        output_path = (
            Path(args.output).resolve() if args.output else tile_dir / DEFAULT_OUTPUT_NAME
        )
        ramp_str = build_ascii_ramp(args.ramp, args.charset)
        workers = args.workers if args.workers and args.workers > 0 else None

        if args.tile_res <= 0:
            raise TileGridError("--tile-res must be a positive integer.")

        stitch_and_asciify(
            tile_dir=tile_dir,
            output_path=output_path,
            tile_res=args.tile_res,
            ramp_str=ramp_str,
            invert=args.classic,
            contrast=args.contrast,
            brightness=args.brightness,
            workers=workers,
            assume_yes=args.yes,
        )
        return 0

    except TileGridError as exc:
        print(f"\nError: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        return 130
    finally:
        if pause_at_exit:
            # Keep the console window open when launched by double-click /
            # drag-and-drop so the user can actually read the summary or any
            # error before it vanishes.
            try:
                input("\nPress Enter to exit...")
            except (EOFError, OSError):
                pass


if __name__ == "__main__":
    sys.exit(main())
