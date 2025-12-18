import requests
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
from io import BytesIO
import os
import logging
import hashlib
import tempfile
import subprocess

logger = logging.getLogger(__name__)

def get_image(image_url):
    response = requests.get(image_url)
    img = None
    if 200 <= response.status_code < 300 or response.status_code == 304:
        img = Image.open(BytesIO(response.content))
    else:
        logger.error(f"Received non-200 response from {image_url}: status_code: {response.status_code}")
    return img

def change_orientation(image, orientation, inverted=False):
    if orientation == 'horizontal':
        angle = 0
    elif orientation == 'vertical':
        angle = 90

    if inverted:
        angle = (angle + 180) % 360

    return image.rotate(angle, expand=1)

def resize_image(image, desired_size, image_settings=[]):
    img_width, img_height = image.size
    desired_width, desired_height = desired_size
    desired_width, desired_height = int(desired_width), int(desired_height)

    img_ratio = img_width / img_height
    desired_ratio = desired_width / desired_height

    keep_width = "keep-width" in image_settings

    x_offset, y_offset = 0,0
    new_width, new_height = img_width,img_height
    # Step 1: Determine crop dimensions
    desired_ratio = desired_width / desired_height
    if img_ratio > desired_ratio:
        # Image is wider than desired aspect ratio
        new_width = int(img_height * desired_ratio)
        if not keep_width:
            x_offset = (img_width - new_width) // 2
    else:
        # Image is taller than desired aspect ratio
        new_height = int(img_width / desired_ratio)
        if not keep_width:
            y_offset = (img_height - new_height) // 2

    # Step 2: Crop the image
    image = image.crop((x_offset, y_offset, x_offset + new_width, y_offset + new_height))

    # Step 3: Resize to the exact desired dimensions (if necessary)
    return image.resize((desired_width, desired_height), Image.LANCZOS)

def apply_image_enhancement(img, image_settings={}):
    # Convert image to RGB mode if necessary for enhancement operations
    # ImageEnhance requires RGB mode for operations like blend
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
        

    # Apply Brightness
    img = ImageEnhance.Brightness(img).enhance(image_settings.get("brightness", 1.0))

    # Apply Contrast
    img = ImageEnhance.Contrast(img).enhance(image_settings.get("contrast", 1.0))

    # Apply Saturation (Color)
    img = ImageEnhance.Color(img).enhance(image_settings.get("saturation", 1.0))

    # Apply Sharpness
    img = ImageEnhance.Sharpness(img).enhance(image_settings.get("sharpness", 1.0))

    return img

def compute_image_hash(image):
    """Compute SHA-256 hash of an image."""
    image = image.convert("RGB")
    img_bytes = image.tobytes()
    return hashlib.sha256(img_bytes).hexdigest()

def take_screenshot_html(html_str, dimensions, timeout_ms=None):
    image = None
    # Default timeout of 15 seconds for pages with external resources (like CDN scripts)
    if timeout_ms is None:
        timeout_ms = 15000

    try:
        # Create a temporary HTML file
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as html_file:
            html_file.write(html_str.encode("utf-8"))
            html_file_path = html_file.name

        image = take_screenshot(html_file_path, dimensions, timeout_ms)

        # Remove html file
        os.remove(html_file_path)

    except Exception as e:
        logger.error(f"Failed to take screenshot: {str(e)}")

    return image

def take_screenshot(target, dimensions, timeout_ms=None):
    image = None
    img_file_path = None
    try:
        # Create a temporary output file for the screenshot
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as img_file:
            img_file_path = img_file.name

        # Default timeout of 10 seconds if not specified
        if timeout_ms is None:
            timeout_ms = 10000

        command = [
            "chromium-headless-shell",
            target,
            "--headless",
            f"--screenshot={img_file_path}",
            f"--window-size={dimensions[0]},{dimensions[1]}",
            f"--timeout={timeout_ms}",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--use-gl=swiftshader",
            "--hide-scrollbars",
            "--in-process-gpu",
            "--js-flags=--jitless",
            "--disable-zero-copy",
            "--disable-gpu-memory-buffer-compositor-resources",
            "--disable-extensions",
            "--disable-plugins",
            "--mute-audio",
            "--no-sandbox",
            "--virtual-time-budget=10000"
        ]

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Check if the process failed
        if result.returncode != 0:
            logger.error("Chromium process failed:")
            logger.error(result.stderr.decode('utf-8'))
            if result.stdout:
                logger.error(result.stdout.decode('utf-8'))
            return None

        # Check if the output file exists
        if not os.path.exists(img_file_path):
            logger.error(f"Screenshot file was not created: {img_file_path}")
            return None

        # Check if the file has content
        file_size = os.path.getsize(img_file_path)
        if file_size == 0:
            logger.error(f"Screenshot file is empty (0 bytes): {img_file_path}")
            return None

        # Try to load the image using PIL
        try:
            with Image.open(img_file_path) as img:
                image = img.copy()
        except Exception as img_error:
            logger.error(f"Failed to open screenshot file as image (file size: {file_size} bytes): {str(img_error)}")
            # Log first few bytes for debugging
            with open(img_file_path, 'rb') as f:
                header = f.read(min(100, file_size))
                logger.error(f"File header (first {len(header)} bytes): {header[:50]}")
            return None

        # Remove image files
        os.remove(img_file_path)

    except Exception as e:
        logger.error(f"Failed to take screenshot: {str(e)}")
        # Clean up temp file if it exists
        if img_file_path and os.path.exists(img_file_path):
            try:
                os.remove(img_file_path)
            except:
                pass

    return image

def pad_image_blur(img: Image, dimensions: tuple[int, int]) -> Image:
    bkg = ImageOps.fit(img, dimensions)
    bkg = bkg.filter(ImageFilter.BoxBlur(8))
    img = ImageOps.contain(img, dimensions)

    img_size = img.size
    bkg.paste(img, ((dimensions[0] - img_size[0]) // 2, (dimensions[1] - img_size[1]) // 2))
    return bkg
