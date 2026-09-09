"""Streaming checksums for the immutable raw vault.

SHA-256 is the canonical Kemirix artifact hash. MD5 exists only to verify
official upstream publication checksums where a provider publishes one (for
example the RxNorm full release); it is never an integrity authority for
Kemirix. S3 ETags (multipart or otherwise) are never treated as SHA-256.
"""

import hashlib

CHUNK_SIZE = 1024 * 1024


def _stream(path, digest):
    with open(path, "rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest


def sha256_file(path):
    """Streaming SHA-256 of a fully written, closed local file (lowercase hex)."""
    return _stream(path, hashlib.sha256()).hexdigest()


def md5_file(path):
    """Streaming MD5 of a closed local file, for upstream checksum verification only."""
    return _stream(path, hashlib.md5()).hexdigest()


def sha256_stream(stream, chunk_size=CHUNK_SIZE):
    """Streaming SHA-256 of a binary stream (remote object verification)."""
    digest = hashlib.sha256()
    while chunk := stream.read(chunk_size):
        digest.update(chunk)
    return digest.hexdigest()
