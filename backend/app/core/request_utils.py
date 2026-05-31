"""Request utilities for safe upload handling."""

from fastapi import HTTPException, UploadFile


async def read_upload_file_limited(upload_file: UploadFile, max_bytes: int) -> bytes:
    """Read upload file with byte limit enforcement.

    Reads file in chunks and raises HTTPException(413) if limit exceeded.

    Args:
        upload_file: The uploaded file to read
        max_bytes: Maximum bytes allowed

    Returns:
        File contents as bytes

    Raises:
        HTTPException: 413 if file exceeds max_bytes
    """
    total_bytes = 0
    chunks = []

    # Read in 64KB chunks
    chunk_size = 64 * 1024

    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break

        chunk_len = len(chunk)
        total_bytes += chunk_len

        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "File too large",
                    "max_size_bytes": max_bytes,
                    "limit_type": "upload_file",
                },
            )

        chunks.append(chunk)

    # Reset file position for potential downstream use
    await upload_file.seek(0)

    return b"".join(chunks)
