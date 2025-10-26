"""File management endpoints."""

import base64
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi import File as FastAPIFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import config
from app.database import get_db
from app.dependencies import get_current_user
from app.models import File, FileImage, User
from app.schemas import (
    FileImageInfo,
    FileImagesResponse,
    FileListItem,
    FileListResponse,
    FileStatusResponse,
    FileUploadResponse,
)
from app.services.file_handler import (
    FileProcessingError,
    compress_image,
    convert_docx_ppt_to_images,
    get_file_type_from_mime,
    validate_file_size,
    validate_mime_type,
)

router = APIRouter(prefix="/api/files", tags=["File Management"])


def process_document_background(file_id: int, file_data: bytes, file_type: str, db_url: str):
    """Convert a document into images and persist the results.

    Args:
        file_id: Identifier of the uploaded file record.
        file_data: Raw binary content of the document.
        file_type: Logical file type (`"docx"` or `"ppt"`).
        db_url: Database URL used to create a separate background session.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Background tasks require their own database connection.
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # Mark the file as processing.
        file = db.query(File).filter(File.id == file_id).first()
        if file:
            file.processing_status = "processing"
            db.commit()

        # Convert the document into images.
        try:
            images = convert_docx_ppt_to_images(file_data, file_type)

            # Store generated images.
            for page_num, (image_data, width, height) in enumerate(images, start=1):
                file_image = FileImage(
                    file_id=file_id,
                    page_number=page_num,
                    image_data=image_data,
                    width=width,
                    height=height,
                    file_size=len(image_data),
                )
                db.add(file_image)

            # Flag completion.
            if file:
                file.processing_status = "completed"
                db.commit()

        except FileProcessingError as e:
            # Capture failures.
            if file:
                file.processing_status = "failed"
                file.error_message = str(e)
                db.commit()

    finally:
        db.close()


@router.post("/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = FastAPIFile(...),
    images: Optional[List[UploadFile]] = FastAPIFile(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Handle file uploads and persist metadata plus derived assets.

    Args:
        background_tasks: FastAPI background task manager for async processing.
        file: Primary uploaded file.
        images: Optional pre-rendered images (used when uploading PDFs).
        user: Authenticated user who owns the file.
        db: Database session injected by FastAPI.

    Returns:
        FileUploadResponse: Details about the stored file and derivative count.

    Raises:
        HTTPException: When the file is too large, the MIME type is missing or
        unsupported, or PDF uploads lack rendered images.
    """
    # Read the raw payload.
    file_data = await file.read()
    file_size = len(file_data)

    # Validate file size.
    if not validate_file_size(file_size):
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {config.MAX_FILE_SIZE / 1024 / 1024:.1f} MB",
        )

    # Validate MIME type.
    mime_type = file.content_type
    if not mime_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to determine file type")

    if not validate_mime_type(mime_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type: {mime_type}")

    # Map MIME type to logical file type.
    file_type = get_file_type_from_mime(mime_type)

    # Persist metadata and binary payload.
    new_file = File(
        user_id=user.id,
        filename=file.filename,
        file_type=file_type,
        mime_type=mime_type,
        file_data=file_data,
        file_size=file_size,
        processing_status="pending",
    )

    db.add(new_file)
    db.commit()
    db.refresh(new_file)

    image_count = 0

    # Branch by file type.
    if file_type == "image":
        # Images compress inline.
        try:
            compressed_data, width, height = compress_image(file_data, config.IMAGE_MAX_DIMENSION)

            file_image = FileImage(
                file_id=new_file.id,
                page_number=1,
                image_data=compressed_data,
                width=width,
                height=height,
                file_size=len(compressed_data),
            )
            db.add(file_image)

            new_file.processing_status = "completed"
            db.commit()
            image_count = 1

        except FileProcessingError as e:
            new_file.processing_status = "failed"
            new_file.error_message = str(e)
            db.commit()

    elif file_type == "pdf":
        # PDFs reuse pre-rendered images from the client.
        if images:
            try:
                for idx, img_file in enumerate(images, start=1):
                    img_data = await img_file.read()
                    compressed_data, width, height = compress_image(img_data, config.IMAGE_MAX_DIMENSION)

                    file_image = FileImage(
                        file_id=new_file.id,
                        page_number=idx,
                        image_data=compressed_data,
                        width=width,
                        height=height,
                        file_size=len(compressed_data),
                    )
                    db.add(file_image)

                new_file.processing_status = "completed"
                db.commit()
                image_count = len(images)

            except FileProcessingError as e:
                new_file.processing_status = "failed"
                new_file.error_message = str(e)
                db.commit()
        else:
            # Reject PDFs without associated renders.
            new_file.processing_status = "failed"
            new_file.error_message = "Missing image data in PDF file"
            db.commit()

    elif file_type in ["docx", "ppt"]:
        # Word/PowerPoint files convert asynchronously.
        from app.config import config as app_config

        background_tasks.add_task(
            process_document_background, new_file.id, file_data, file_type, app_config.DATABASE_URL
        )

    return FileUploadResponse(
        file_id=new_file.id,
        filename=new_file.filename,
        file_type=file_type,
        processing_status=new_file.processing_status,
        image_count=image_count if image_count > 0 else None,
    )


@router.get("/{file_id}/status", response_model=FileStatusResponse)
def get_file_status(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return processing status for a specific file.

    Args:
        file_id: Identifier for the file to inspect.
        user: Authenticated user, used to verify ownership.
        db: Database session injected by FastAPI.

    Returns:
        FileStatusResponse: Current status, generated image count, and any
        error message.

    Raises:
        HTTPException: When the file does not exist or does not belong to the
        requesting user.
    """
    file = db.query(File).filter(File.id == file_id, File.user_id == user.id).first()

    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Count generated images, if any.
    image_count = db.query(FileImage).filter(FileImage.file_id == file_id).count()

    return FileStatusResponse(
        file_id=file.id,
        processing_status=file.processing_status,
        image_count=image_count if image_count > 0 else None,
        error_message=file.error_message,
    )


@router.get("/{file_id}/images", response_model=FileImagesResponse)
def get_file_images(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return all image derivatives for a file as base64 strings.

    Args:
        file_id: Identifier of the original file.
        user: Authenticated user, used to verify ownership.
        db: Database session injected by FastAPI.

    Returns:
        FileImagesResponse: Ordered list of image metadata and base64 payloads.

    Raises:
        HTTPException: When the file is not found or not owned by the user.
    """
    file = db.query(File).filter(File.id == file_id, File.user_id == user.id).first()

    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Fetch ordered images.
    images = db.query(FileImage).filter(FileImage.file_id == file_id).order_by(FileImage.page_number).all()

    image_infos = []
    for img in images:
        # Embed base64 payloads for transport.
        image_base64 = base64.b64encode(img.image_data).decode("utf-8")

        image_infos.append(
            FileImageInfo(
                page=img.page_number,
                image_id=img.id,
                width=img.width,
                height=img.height,
                image_data_base64=image_base64,
            )
        )

    return FileImagesResponse(file_id=file_id, images=image_infos)


@router.get("/{file_id}/images/{page_number}")
def get_file_image(
    file_id: int, page_number: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Return a single page image derived from a document.

    Args:
        file_id: Identifier of the parent file.
        page_number: Page index to retrieve.
        user: Authenticated user, used to verify ownership.
        db: Database session injected by FastAPI.

    Returns:
        Response: Raw WebP image bytes.

    Raises:
        HTTPException: When the file or derived image does not exist or the
        user lacks access.
    """
    # Verify ownership.
    file = db.query(File).filter(File.id == file_id, File.user_id == user.id).first()

    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Fetch the requested page.
    image = db.query(FileImage).filter(FileImage.file_id == file_id, FileImage.page_number == page_number).first()

    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    return Response(content=image.image_data, media_type="image/webp")


@router.get("/{file_id}")
def download_file(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Download the original uploaded file.

    Args:
        file_id: Identifier of the file to download.
        user: Authenticated user, used to verify ownership.
        db: Database session injected by FastAPI.

    Returns:
        Response: Raw file bytes with appropriate headers.

    Raises:
        HTTPException: When the file cannot be located or is not owned by the
        user.
    """
    file = db.query(File).filter(File.id == file_id, File.user_id == user.id).first()

    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    return Response(
        content=file.file_data,
        media_type=file.mime_type,
        headers={"Content-Disposition": f"attachment; filename={file.filename}"},
    )


@router.get("", response_model=FileListResponse)
def list_files(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List files owned by the current user.

    Args:
        user: Authenticated user whose files are requested.
        db: Database session injected by FastAPI.

    Returns:
        FileListResponse: Collection of the user's files in reverse
        chronological order.
    """
    files = db.query(File).filter(File.user_id == user.id).order_by(File.created_at.desc()).all()

    file_items = [FileListItem.model_validate(f) for f in files]

    return FileListResponse(files=file_items)


@router.delete("/{file_id}", response_model=dict)
def delete_file(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete a file and any derived images.

    Args:
        file_id: Identifier of the file to delete.
        user: Authenticated user, used to verify ownership.
        db: Database session injected by FastAPI.

    Returns:
        dict: Confirmation message.

    Raises:
        HTTPException: When the file cannot be located or does not belong to
        the requesting user.
    """
    file = db.query(File).filter(File.id == file_id, File.user_id == user.id).first()

    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    db.delete(file)
    db.commit()

    return {"message": "File deleted"}
