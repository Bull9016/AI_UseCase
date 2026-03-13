import os
import uuid
import io
import re
import cloudinary
import cloudinary.uploader
import cloudinary.api
from config.config import CLOUDINARY_URL

# Configure Cloudinary if URL is provided
if CLOUDINARY_URL:
    cloudinary.config(url=CLOUDINARY_URL)

def sanitize_filename(filename):
    """Remove special characters from filename for public_id."""
    # Keep alphanumeric, dots, underscores, and hyphens
    return re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

def upload_document_to_cloudinary(file_bytes, filename, resource_type="auto"):
    """
    Upload a file's bytes to Cloudinary.
    Returns the secure URL and the public ID.
    """
    if not CLOUDINARY_URL:
        raise Exception("Cloudinary URL is not configured. Please add CLOUDINARY_URL to your .env file.")

    # Determine resource type: Cloudinary requires 'image' for PDFs to be viewable/transformable
    if filename.lower().endswith(".pdf"):
        resource_type = "image"
    
    # Sanitize and generate unique ID
    clean_name = sanitize_filename(filename)
    public_id = f"neostats_docs/{uuid.uuid4().hex}_{clean_name}"

    try:
        # Wrap bytes in BytesIO for safer stream handling
        file_stream = io.BytesIO(file_bytes)
        
        response = cloudinary.uploader.upload(
            file_stream,
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
