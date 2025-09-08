# This file contains all user-configurable settings for the Smart Gallery.
# Adjust the parameters in this file to customize the gallery behavior.
#
# Configuration values can be overridden using environment variables:
# - GALLERY_BASE_OUTPUT_PATH
# - GALLERY_BASE_INPUT_PATH
# - GALLERY_FFPROBE_MANUAL_PATH
# - GALLERY_SERVER_PORT
# - GALLERY_THUMBNAIL_WIDTH
# - GALLERY_WEBP_ANIMATED_FPS
# - GALLERY_PAGE_SIZE
# - GALLERY_SPECIAL_FOLDERS (comma-separated list)
# - GALLERY_ENABLE_DELETION (true/false)
# - GALLERY_DELETION_ALLOWED_IPS (comma-separated list of IPs and CIDR blocks)
#
# IMPORTANT:
# - Even on Windows, always use forward slashes ( / ) in paths, 
#   not backslashes ( \ ), to ensure compatibility.
# - It is strongly recommended to have ffmpeg installed, 
#   since some features depend on it.

import os

# Path to the ComfyUI 'output' folder.
BASE_OUTPUT_PATH = os.environ.get('GALLERY_BASE_OUTPUT_PATH', 'output')

# Path to the ComfyUI 'input' folder (used for locating .json workflows).
BASE_INPUT_PATH = os.environ.get('GALLERY_BASE_INPUT_PATH', 'input')

# Path to the ffmpeg utility "ffprobe.exe" (Windows). 
# On Linux, adjust the filename accordingly. 
# This is required for extracting workflows from .mp4 files.  
# NOTE: Having a full ffmpeg installation is highly recommended.
FFPROBE_MANUAL_PATH = os.environ.get('GALLERY_FFPROBE_MANUAL_PATH', "C:/omgp10/ffmpeg2/bin/ffprobe.exe")

# Port on which the gallery web server will run. 
# Must be different from the ComfyUI port.  
# Note: the gallery does not require ComfyUI to be running; it works independently.
SERVER_PORT = int(os.environ.get('GALLERY_SERVER_PORT', '8189'))

# Width (in pixels) of the generated thumbnails.
THUMBNAIL_WIDTH = int(os.environ.get('GALLERY_THUMBNAIL_WIDTH', '300'))

# Assumed frame rate for animated WebP files.  
# Many tools, including ComfyUI, generate WebP animations at ~16 FPS.  
# Adjust this value if your WebPs use a different frame rate,  
# so that animation durations are calculated correctly.
WEBP_ANIMATED_FPS = float(os.environ.get('GALLERY_WEBP_ANIMATED_FPS', '16.0'))

# Maximum number of files to load initially before showing a "Load more" button.  
# Use a very large number (e.g., 9999999) for "infinite" loading.
PAGE_SIZE = int(os.environ.get('GALLERY_PAGE_SIZE', '100'))

# Names of special folders (e.g., 'video', 'audio').
# These folders will appear in the menu only if they exist inside BASE_OUTPUT_PATH.
# Leave as-is if unsure.
_special_folders_env = os.environ.get('GALLERY_SPECIAL_FOLDERS', 'video,audio')
SPECIAL_FOLDERS = [folder.strip() for folder in _special_folders_env.split(',') if folder.strip()]

# Deletion Control Settings
# Set to False to completely disable file/folder deletion for all users
# Set to True to enable deletion (subject to IP restrictions if configured)
ENABLE_DELETION = os.environ.get('GALLERY_ENABLE_DELETION', 'true').lower() == 'true'

# Comma-separated list of IP addresses and CIDR blocks that are allowed to delete files
# when ENABLE_DELETION is True. Examples: '192.168.1.100,10.0.0.0/8,172.16.0.0/12'
# Leave empty to allow deletion from any IP (when ENABLE_DELETION is True)
# Only takes effect when ENABLE_DELETION is True
_deletion_allowed_ips_env = os.environ.get('GALLERY_DELETION_ALLOWED_IPS', '192.168.1.100,10.0.0.0/8,172.16.0.0/12')
DELETION_ALLOWED_IPS = [ip.strip() for ip in _deletion_allowed_ips_env.split(',') if ip.strip()]