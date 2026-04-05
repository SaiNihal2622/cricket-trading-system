#!/usr/bin/env python3
"""
Download IPL ball-by-ball data from Cricsheet.org

Usage:
    python scripts/download_data.py                    # Download to default location
    python scripts/download_data.py --output data/     # Custom output directory
    python scripts/download_data.py --format csv       # CSV format (default)
"""
import argparse
import io
import logging
import os
import sys
import zipfile

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Cricsheet download URLs
CRICSHEET_URLS = {
    "ipl_csv": "https://cricsheet.org/downloads/ipl_csv2.zip",
    "ipl_json": "https://cricsheet.org/downloads/ipl_json.zip",
    "t20i_csv": "https://cricsheet.org/downloads/t20s_csv2.zip",
}

DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def download_and_extract(url: str, output_dir: str) -> list[str]:
    """Download ZIP from URL and extract to output directory"""
    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"Downloading from {url}...")
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()

    logger.info(f"Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

    # Extract ZIP
    extracted_files = []
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # Extract CSV files
            if info.filename.endswith((".csv", ".json")):
                target = os.path.join(output_dir, os.path.basename(info.filename))
                with open(target, "wb") as f:
                    f.write(zf.read(info.filename))
                extracted_files.append(target)

    logger.info(f"Extracted {len(extracted_files)} files to {output_dir}")
    return extracted_files


def merge_csvs(csv_files: list[str], output_path: str):
    """Merge multiple per-match CSVs into a single file"""
    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas not installed — skipping CSV merge")
        return

    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f)
            # Extract match_id from filename if not present
            if "match_id" not in df.columns:
                match_id = os.path.splitext(os.path.basename(f))[0]
                df["match_id"] = match_id
            dfs.append(df)
        except Exception as e:
            logger.warning(f"Skipping {f}: {e}")

    if dfs:
        merged = pd.concat(dfs, ignore_index=True)
        merged.to_csv(output_path, index=False)
        logger.info(f"Merged {len(dfs)} files → {output_path} ({len(merged)} rows)")
        return merged
    return None


def download_ipl_data(output_dir: str, merge: bool = True) -> str:
    """Download and prepare IPL ball-by-ball data"""
    url = CRICSHEET_URLS["ipl_csv"]

    logger.info("=" * 50)
    logger.info("  IPL DATA DOWNLOADER (Cricsheet.org)")
    logger.info("=" * 50)
    logger.info(f"Source: {url}")
    logger.info(f"Output: {output_dir}")

    files = download_and_extract(url, output_dir)

    csv_files = [f for f in files if f.endswith(".csv")]
    logger.info(f"Found {len(csv_files)} CSV match files")

    if merge and csv_files:
        merged_path = os.path.join(output_dir, "ipl_all_matches.csv")
        merge_csvs(csv_files, merged_path)
        logger.info(f"\n✅ Merged dataset ready: {merged_path}")
        logger.info(f"Use with: python scripts/train_model.py --data {merged_path}")
        return merged_path

    return output_dir


def main():
    parser = argparse.ArgumentParser(description="Download IPL ball-by-ball data")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT, help="Output directory")
    parser.add_argument("--dataset", type=str, default="ipl_csv",
                        choices=list(CRICSHEET_URLS.keys()),
                        help="Dataset to download")
    parser.add_argument("--no-merge", action="store_true", help="Don't merge CSVs")
    args = parser.parse_args()

    if args.dataset == "ipl_csv":
        download_ipl_data(args.output, merge=not args.no_merge)
    else:
        url = CRICSHEET_URLS[args.dataset]
        download_and_extract(url, args.output)

    logger.info("\n✅ Download complete!")


if __name__ == "__main__":
    main()
