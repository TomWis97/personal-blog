#!/usr/bin/env python3
import argparse
import base64
import logging
import os
import re
import sys
from io import BytesIO
from os import path
from pathlib import Path

import boto3
from PIL import Image

logger = logging.getLogger(__name__)

MAX_WIDTH = 1920
MAX_HEIGHT = 1080

ALBUM_RE = re.compile(r"^!Album\[([^\]]+)\]$", re.MULTILINE)
ALBUM_FILES_RE = re.compile(r"^!AlbumFiles\[([^\]]+)\]$", re.MULTILINE)


def setup_logger(verbose: bool):
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("[%(levelname)-8s] %(message)s")

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(fmt)
    root.addHandler(stderr_handler)

    if verbose:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.addFilter(lambda r: r.levelno < logging.WARNING)
        stdout_handler.setFormatter(fmt)
        root.addHandler(stdout_handler)


def load_env(filepath="../env"):
    if path.isfile(filepath):
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key, value)


def find_markdown_files(content_path: str) -> list:
    md_files = sorted(Path(content_path).rglob("*.md"))
    logger.info(f"Found {len(md_files)} Markdown file(s) under {content_path}.")
    return md_files


def list_album_objects(s3, bucket: str, albumname: str) -> list:
    """
    Returns a list of dicts with 'key', 'filename', and 'alttext' for every
    object in the album prefix. Alt text is decoded from the base64-encoded
    x-amz-meta-alttext object metadata, if present.
    """
    prefix = f"{albumname}/"
    paginator = s3.get_paginator("list_objects_v2")
    objects = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = key[len(prefix):]
            if not filename:                                # Skip the directory placeholder object, if any
                continue

            head = s3.head_object(Bucket=bucket, Key=key)
            raw_alttext = head.get("Metadata", {}).get("alttext", "")
            alttext = ""
            if raw_alttext:
                try:
                    alttext = base64.b64decode(raw_alttext.encode()).decode()
                except Exception:
                    logger.warning(f"Could not decode alt text for {key}, skipping.")

            objects.append({"key": key, "filename": filename, "alttext": alttext})

    logger.info(f"Found {len(objects)} object(s) in album '{albumname}'.")
    return objects


def stem_to_jpg(filename: str) -> str:
    """Returns the filename with a .jpg extension."""
    return Path(filename).stem + ".jpg"


def download_and_resize(s3, bucket: str, obj: dict, dest_dir: str) -> str:
    """
    Downloads an S3 object, resizes it to fit within MAX_WIDTH × MAX_HEIGHT,
    converts it to JPEG, and writes it to dest_dir.
    Returns the output filename (with .jpg extension).
    """
    key = obj["key"]
    out_filename = stem_to_jpg(obj["filename"])
    out_path = path.join(dest_dir, out_filename)

    logger.info(f"Downloading s3://{bucket}/{key}")
    buffer = BytesIO()
    s3.download_fileobj(bucket, key, buffer)
    buffer.seek(0)

    image = Image.open(buffer)
    image = image.convert("RGB")                            # Ensures JPEG compatibility (drops alpha, etc.)
    image.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.LANCZOS)

    image.save(out_path, "JPEG", quality=85, optimize=True)
    logger.debug(f"Saved resized image to {out_path} ({image.width}×{image.height}).")
    return out_filename


def render_album(s3, bucket: str, albumname: str, md_dir: str) -> str:
    """
    Processes an !Album[albumname] reference:
    - Downloads and resizes all images in the album.
    - Returns the Markdown replacement string.
    """
    objects = list_album_objects(s3, bucket, albumname)
    if not objects:
        logger.warning(f"Album '{albumname}' is empty or does not exist.")
        return ""

    lines = []
    for obj in objects:
        out_filename = download_and_resize(s3, bucket, obj, md_dir)
        alttext = obj["alttext"] or out_filename
        lines.append(f"![{alttext}]({out_filename})")

    return "\n".join(lines)


def render_album_files(s3, bucket: str, albumname: str, cloudfront_base: str) -> str:
    """
    Processes an !AlbumFiles[albumname] reference:
    - Lists all images in the album.
    - Returns a Markdown unordered list linking to the CloudFront URLs of the originals.
    """
    objects = list_album_objects(s3, bucket, albumname)
    if not objects:
        logger.warning(f"Album '{albumname}' is empty or does not exist.")
        return ""

    base = cloudfront_base.rstrip("/")
    lines = []
    for obj in objects:
        url = f"{base}/{obj['key']}"
        label = obj["alttext"] or obj["filename"]
        lines.append(f"- [{label}]({url})")

    return "\n".join(lines)


def process_markdown_file(md_path: Path, s3, bucket: str, cloudfront_base: str):
    """Reads a Markdown file, replaces album references in-place."""
    logger.info(f"Processing {md_path}")
    content = md_path.read_text(encoding="utf-8")
    md_dir = str(md_path.parent)
    changed = False

    def replace_album(match):
        nonlocal changed
        albumname = match.group(1)
        logger.debug(f"Replacing !Album[{albumname}] in {md_path}")
        replacement = render_album(s3, bucket, albumname, md_dir)
        changed = True
        return replacement

    def replace_album_files(match):
        nonlocal changed
        albumname = match.group(1)
        logger.debug(f"Replacing !AlbumFiles[{albumname}] in {md_path}")
        replacement = render_album_files(s3, bucket, albumname, cloudfront_base)
        changed = True
        return replacement

    content = ALBUM_RE.sub(replace_album, content)
    content = ALBUM_FILES_RE.sub(replace_album_files, content)

    if changed:
        md_path.write_text(content, encoding="utf-8")
        logger.info(f"Updated {md_path}.")
    else:
        logger.debug(f"No album references found in {md_path}, skipping.")


def main():
    parser = argparse.ArgumentParser(
        prog="S3 Prepare",
        description="Downloads and resizes images from S3 and prepares Markdown files for container image build.")
    parser.add_argument("content_path",
                        help="Path to the content directory to search for Markdown files.")
    parser.add_argument("-v", "--verbose",
                        action="store_true")
    args = parser.parse_args()
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)

    setup_logger(args.verbose)
    load_env()

    bucket = os.environ.get("AWS_BUCKET")
    if not bucket:
        logger.error("AWS_BUCKET not set.")
        sys.exit(1)

    cloudfront_base = os.environ.get("CLOUDFRONT_BASE_URL", "")
    if not cloudfront_base:
        logger.error("CLOUDFRONT_BASE_URL not set.")
        sys.exit(1)

    if not path.isdir(args.content_path):
        logger.error(f"Path \"{args.content_path}\" does not exist or is not a directory.")
        sys.exit(1)

    s3 = boto3.client("s3")
    md_files = find_markdown_files(args.content_path)

    for md_path in md_files:
        process_markdown_file(md_path, s3, bucket, cloudfront_base)

    logger.info("All done.")


if __name__ == "__main__":
    main()
