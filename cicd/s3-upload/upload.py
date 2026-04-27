#!/usr/bin/env python3
import argparse
import base64
import logging
import os
import sys
from os import path

import boto3

logger = logging.getLogger(__name__)


def setup_logger(verbose: bool):
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("[%(levelname)-8s] %(message)s")

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(fmt)
    root.addHandler(stderr_handler)                         # Fixed: was logger, should be root

    if verbose:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.addFilter(lambda r: r.levelno < logging.WARNING)
        stdout_handler.setFormatter(fmt)
        root.addHandler(stdout_handler)                     # Fixed: same


def load_env(filepath="../env"):
    if path.isfile(filepath):
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):        # Skip blanks and comments
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key, value)


def read_directory(albumpath) -> list:
    if not path.isdir(albumpath):
        logger.error(f"Path \"{albumpath}\" does not exist or is not a directory.")
        sys.exit(1)
    files = sorted(
        f for f in os.listdir(albumpath)
        if f != "alt.txt" and path.isfile(path.join(albumpath, f))
    )
    logger.info(f"Found {len(files)} files in {albumpath}.")
    return files


def parse_alttext(albumpath: str) -> dict:
    """
    Parses alt.txt in albumpath. Returns dict of filename -> alttext.
    """
    altfile = path.join(albumpath, "alt.txt")
    if not path.isfile(altfile):
        logger.debug("No alt.txt found, skipping.")
        return {}

    alttextdict = {}
    with open(altfile) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split('|', 1)                     # Fixed: was split('\n') on whole file
            if len(parts) != 2:
                logger.warning(f"Line {lineno} in alt.txt has invalid format, skipping.")  # Fixed: warn() is deprecated
                continue
            alttextdict[parts[0]] = parts[1]

    logger.debug(f"Parsed alt texts for {len(alttextdict)} files.")
    return alttextdict


def upload_files(albumname: str, files: list, alttext: dict, bucket: str):
    s3 = boto3.client("s3")
    for filename in files:
        key = f"{albumname}/{filename}"
        filepath = path.join(albumname, filename)
        extra = {}
        if filename in alttext:
            encoded = base64.b64encode(alttext[filename].encode()).decode()
            extra = {"ExtraArgs": {"Metadata": {"alttext": encoded}}}

        logger.info(f"Uploading {filename} → s3://{bucket}/{key}")
        try:
            if extra:
                s3.upload_file(filepath, bucket, key, **extra)
            else:
                s3.upload_file(filepath, bucket, key)
            logger.debug(f"Done.")
        except Exception as e:
            logger.error(f"Failed to upload {filename}: {e}")


def main():
    parser = argparse.ArgumentParser(
        prog="S3 Uploader",
        description="Uploads images to S3 for Personal Blog")
    parser.add_argument('albumname',
                        help="Name of the directory to look into. Resulting album will also be called this.")
    parser.add_argument('-v', '--verbose',
                        action='store_true')
    args = parser.parse_args()
    args.albumname = args.albumname.rstrip("/")

    setup_logger(args.verbose)
    load_env()

    bucket = os.environ.get("AWS_BUCKET")
    if not bucket:
        logger.error("AWS_BUCKET not set.")
        sys.exit(1)

    files = read_directory(args.albumname)
    alttext = parse_alttext(args.albumname)
    upload_files(args.albumname, files, alttext, bucket)
    logger.info("All done.")


if __name__ == "__main__":
    main()
