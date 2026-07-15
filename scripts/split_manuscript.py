#!/usr/bin/env python3
"""
split_manuscript.py - Standalone utility to segment a monolithic manuscript file into individual chapter files.
"""

import argparse
import re
import sys
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("SplitManuscript")


def split_manuscript(manuscript_path: Path, output_dir: Path) -> None:
    """Read a monolithic manuscript file, segment it by chapter boundaries, and save individual files."""
    if not manuscript_path.exists():
        logger.error(f"Manuscript file not found: {manuscript_path}")
        sys.exit(1)

    logger.info(f"Reading manuscript from {manuscript_path}")
    with open(manuscript_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Regex to capture various chapter headers, e.g., "Chapter 1", "CHAPTER II", "Chapter One", "### Chapter X", "Ch. 5"
    header_pattern = re.compile(
        r"(?:\r?\n|^)"                    # Line start or document start
        r"(?:###\s*)?"                    # Optional markdown headers
        r"(?:Chapter|CHAPTER|Ch\.)"       # Chapter keyword
        r"\s+"                            # Whitespace
        r"(?:[0-9]+|[IVXLCDM]+|[A-Za-z]+)" # Chapter number/word
        r"(?:[^\r\n]*)"                   # Rest of header line
        r"(?:\r?\n|$)"                    # Line end
    )

    matches = list(header_pattern.finditer(content))
    
    if not matches:
        logger.warning("No chapter boundaries detected. Saving entire content as chapter_01.txt.")
        chapters = [content.strip()]
    else:
        chapters = []
        for i in range(len(matches)):
            start = matches[i].start()
            end = matches[i+1].start() if i + 1 < len(matches) else len(content)
            chapter_text = content[start:end].strip()
            if chapter_text:
                chapters.append(chapter_text)

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Splitting into {len(chapters)} chapters...")

    for idx, chapter in enumerate(chapters, start=1):
        word_count = len(chapter.split())
        filename = f"chapter_{idx:02d}.txt"
        dest_path = output_dir / filename
        
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(chapter)
            
        logger.info(f"Saved {filename} ({word_count} words)")

    logger.info(f"Successfully processed manuscript. Chapters saved in {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Bulk Manuscript Splitter Utility")
    parser.add_argument(
        "--manuscript",
        "--input",
        type=str,
        required=True,
        help="Path to the monolithic manuscript .txt file.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/chapters",
        help="Directory to save the zero-padded chapter files (default: data/chapters).",
    )
    args = parser.parse_args()

    split_manuscript(Path(args.manuscript), Path(args.output_dir))


if __name__ == "__main__":
    main()
