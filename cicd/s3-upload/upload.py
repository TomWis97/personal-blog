#!/usr/bin/env python3
import argparse
import logging
import sys
from os import path

logger = logging.getLogger(__name__)

def setup_logger(verbose: bool) -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # Let handlers filter levels

    # WARNING+ → stderr, always
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)

    fmt = logging.Formatter("[%(levelname)-8s] %(message)s")
    stderr_handler.setFormatter(fmt)

    # DEBUG/INFO → stdout, only if -v
    if verbose:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.addFilter(lambda r: r.levelno < logging.WARNING)  # Don't duplicate warnings
        stdout_handler.setFormatter(fmt)
        logger.addHandler(stdout_handler)

    logger.addHandler(stderr_handler)
    return logger

def load_env(filepath="../env"):
    if os.path.isfile(filepath):
        with open(filepath) as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                os.environ.setdefault(key, value)

def read_directory(albumpath):
    if not path.isdir(albumpath):
        logger.error("Path \"{}\" does not exist or is not a directory.".format(albumpath))
        sys.exit(1)

def parse_alttext(file: str) -> dict:
    """
    Parses alttext file. Returns dictionary of key=filename, value=alttext.
    """
    alttextdict = {}
    for line in file.split('\n'):
        parts = line.split('|')
        if len(parts) != 2:
            logger.warn("Line in alt text file has more or less than 2 fields!")
        alttextdict[parts[0]] = parts[1]
    return alttextdict

def main():
    parser = argparse.ArgumentParser(
            prog="S3 Uploader",
            description="Uploads images to S3 for Personal Blog")
    parser.add_argument('albumname',
                        help="Name of the directory to look into. Resulting album will also be called this.")
    parser.add_argument('-v', '--verbose',
                        action='store_true')
    args = parser.parse_args()
    logger = setup_logger(args.verbose)

    load_env()
    
    read_directory(args.albumname)
    
if __name__ == "__main__":
    main()
