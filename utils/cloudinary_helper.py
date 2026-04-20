"""
Upload base64-encoded images to Cloudinary.
"""

import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


def upload_base64_image(
    b64_string: str,
    folder: str = "garage-attendance",
) -> str:
    """
    Upload a base64 image to Cloudinary.
    Returns the secure URL of the uploaded image.
    """
    if "," not in b64_string:
        b64_string = f"data:image/jpeg;base64,{b64_string}"

    result = cloudinary.uploader.upload(
        b64_string,
        folder=folder,
        resource_type="image",
        transformation=[
            {"width": 400, "height": 400, "crop": "fill", "gravity": "face"}
        ],
    )
    return result["secure_url"]
