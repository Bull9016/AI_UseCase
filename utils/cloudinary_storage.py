import os
import uuid
import cloudinary
import cloudinary.uploader
import cloudinary.api
from config.config import CLOUDINARY_URL

# Configure Cloudinary if URL is provided
if CLOUDINARY_URL:
    cloudinary.config(url=CLOUDINARY_URL)

def upload_document_to_cloudinary(file_bytes, filename, resource_type="auto"):
    """
    Upload a file's bytes to Cloudinary.
    Returns the secure URL and the public ID.
    Raises exception if Cloudinary is not configured or upload fails.
    """
    if not CLOUDINARY_URL:
        raise Exception("Cloudinary URL is not configured. Please add CLOUDINARY_URL to your .env file.")

    # Generate a unique public ID to avoid overwrites
    public_id = f"neostats_docs/{uuid.uuid4().hex}_{filename}"

    try:
        response = cloudinary.uploader.upload(
            file_bytes,
            public_id=public_id,
            resource_type=resource_type,
            use_filename=True,
            unique_filename=False,
            overwrite=True
        )
        return response.get("secure_url"), response.get("public_id")
    except Exception as e:
        print(f"[CLOUDINARY ERROR] {e}")
        raise
