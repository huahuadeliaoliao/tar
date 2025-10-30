"""File utilities for compression and document conversion."""

import io
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from pdf2image import convert_from_bytes, convert_from_path
from PIL import Image

from app.config import config


class FileProcessingError(Exception):
    """Raised when file processing fails."""


def compress_image(image_data: bytes, max_dimension: Optional[int] = None) -> Tuple[bytes, int, int]:
    """Compress an image into WebP format.

    Args:
        image_data: Raw image bytes.
        max_dimension: Optional maximum dimension in pixels for width/height.

    Returns:
        Tuple[bytes, int, int]: Compressed WebP bytes plus resulting width and
        height.

    Raises:
        FileProcessingError: When the image cannot be processed.
    """
    try:
        # Open the image payload.
        img = Image.open(io.BytesIO(image_data))

        # Convert to RGB because WebP requires it.
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Enforce max dimensions if requested.
        if max_dimension:
            if img.width > max_dimension or img.height > max_dimension:
                ratio = min(max_dimension / img.width, max_dimension / img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Export as WebP.
        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=config.IMAGE_COMPRESSION_QUALITY)
        compressed_data = buffer.getvalue()

        return compressed_data, img.width, img.height

    except Exception as e:
        raise FileProcessingError(f"Image compression failed: {str(e)}") from e


def convert_docx_ppt_to_images(
    file_data: bytes, file_type: str, timeout: Optional[int] = None
) -> List[Tuple[bytes, int, int]]:
    """Convert DOCX or PPT files into WebP images via LibreOffice and pdf2image.

    Args:
        file_data: Raw DOCX or PPT binary.
        file_type: Logical file type (`"docx"` or `"ppt"`).
        timeout: Optional timeout for the LibreOffice conversion.

    Returns:
        List[Tuple[bytes, int, int]]: Sequence of WebP bytes with dimensions for
        each converted page.

    Raises:
        FileProcessingError: When conversion fails at any stage.
    """
    if timeout is None:
        timeout = config.LIBREOFFICE_TIMEOUT

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # 1. Persist the incoming file.
            input_ext = ".docx" if file_type == "docx" else ".pptx"
            input_file = Path(tmpdir) / f"input{input_ext}"
            input_file.write_bytes(file_data)

            # 2. Convert to PDF via LibreOffice.
            try:
                # Force LibreOffice to use a temporary profile directory.
                user_install_dir = Path(tmpdir) / "libreoffice_profile"
                user_install_dir.mkdir(exist_ok=True)

                # Provide a temporary HOME so LibreOffice initializes cleanly.
                env = os.environ.copy()
                env["HOME"] = tmpdir

                result = subprocess.run(
                    [
                        config.LIBREOFFICE_PATH,
                        "--headless",
                        "--nofirststartwizard",
                        "--norestore",
                        "--nolockcheck",
                        f"-env:UserInstallation=file://{user_install_dir}",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        tmpdir,
                        str(input_file),
                    ],
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                    check=True,
                    env=env,
                )

                # Ensure the PDF exists.
                pdf_file = Path(tmpdir) / "input.pdf"
                if not pdf_file.exists():
                    raise FileProcessingError(f"LibreOffice conversion failed: {result.stderr}")

            except subprocess.TimeoutExpired as e:
                raise FileProcessingError(f"LibreOffice conversion timed out (> {timeout} seconds)") from e
            except subprocess.CalledProcessError as e:
                raise FileProcessingError(f"LibreOffice conversion error: {e.stderr}") from e

            # 3. Convert PDF pages into images.
            try:
                images = convert_from_path(str(pdf_file), dpi=config.PDF_TO_IMAGE_DPI, fmt="png")
            except Exception as e:
                raise FileProcessingError(f"Failed to convert PDF to images: {str(e)}") from e

            # 4. Downscale each image if needed and encode as WebP.
            webp_images = []
            for img in images:
                # Honor max dimensions.
                if img.width > config.IMAGE_MAX_DIMENSION or img.height > config.IMAGE_MAX_DIMENSION:
                    ratio = min(config.IMAGE_MAX_DIMENSION / img.width, config.IMAGE_MAX_DIMENSION / img.height)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)

                # Encode as WebP.
                buffer = io.BytesIO()
                img.save(buffer, format="WEBP", quality=config.IMAGE_COMPRESSION_QUALITY)
                webp_images.append((buffer.getvalue(), img.width, img.height))

            return webp_images

        except FileProcessingError:
            raise
        except Exception as e:
            raise FileProcessingError(f"Document conversion failed: {str(e)}") from e


def convert_pdf_to_images(pdf_data: bytes) -> List[Tuple[bytes, int, int]]:
    """Convert a PDF binary payload into WebP images.

    Args:
        pdf_data: Raw PDF bytes.

    Returns:
        List[Tuple[bytes, int, int]]: Sequence of WebP bytes with dimensions.

    Raises:
        FileProcessingError: When conversion fails.
    """
    try:
        images = convert_from_bytes(pdf_data, dpi=config.PDF_TO_IMAGE_DPI, fmt="png")
    except Exception as e:  # pragma: no cover - pdf2image behaviour is environment-specific
        raise FileProcessingError(f"Failed to convert PDF to images: {str(e)}") from e

    webp_images: List[Tuple[bytes, int, int]] = []
    for img in images:
        if img.width > config.IMAGE_MAX_DIMENSION or img.height > config.IMAGE_MAX_DIMENSION:
            ratio = min(config.IMAGE_MAX_DIMENSION / img.width, config.IMAGE_MAX_DIMENSION / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img = img.convert("RGB")
        img.save(buffer, format="WEBP", quality=config.IMAGE_COMPRESSION_QUALITY)
        webp_images.append((buffer.getvalue(), img.width, img.height))

    return webp_images


def get_file_type_from_mime(mime_type: str) -> str:
    """Map a MIME string to one of the supported logical file types.

    Args:
        mime_type: MIME type string supplied by the client.

    Returns:
        str: Logical file type key such as `"image"` or `"pdf"`.

    Raises:
        ValueError: When the MIME type is not supported.
    """
    for file_type, mime_types in config.ALLOWED_FILE_TYPES.items():
        if mime_type in mime_types:
            return file_type

    raise ValueError(f"Unsupported file type: {mime_type}")


def validate_file_size(file_size: int) -> bool:
    """Check whether the file size is within the configured limit.

    Args:
        file_size: Size of the uploaded file in bytes.

    Returns:
        bool: True when the file size is below the configured maximum.
    """
    return file_size <= config.MAX_FILE_SIZE


def validate_mime_type(mime_type: str) -> bool:
    """Check whether a MIME type is allowed.

    Args:
        mime_type: MIME type string supplied by the client.

    Returns:
        bool: True when the MIME type is supported.
    """
    try:
        get_file_type_from_mime(mime_type)
        return True
    except ValueError:
        return False
