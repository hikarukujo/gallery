# Example Smart Gallery Configuration
# Copy this file to config.py and modify according to your needs

import os

# Basic Configuration
BASE_OUTPUT_PATH = os.environ.get('GALLERY_BASE_OUTPUT_PATH', '/path/to/your/comfyui/output')
BASE_INPUT_PATH = os.environ.get('GALLERY_BASE_INPUT_PATH', '/path/to/your/comfyui/input')
FFPROBE_MANUAL_PATH = os.environ.get('GALLERY_FFPROBE_MANUAL_PATH', "/usr/bin/ffprobe")
SERVER_PORT = int(os.environ.get('GALLERY_SERVER_PORT', '8189'))
THUMBNAIL_WIDTH = int(os.environ.get('GALLERY_THUMBNAIL_WIDTH', '300'))
WEBP_ANIMATED_FPS = float(os.environ.get('GALLERY_WEBP_ANIMATED_FPS', '16.0'))
PAGE_SIZE = int(os.environ.get('GALLERY_PAGE_SIZE', '100'))

_special_folders_env = os.environ.get('GALLERY_SPECIAL_FOLDERS', 'video,audio')
SPECIAL_FOLDERS = [folder.strip() for folder in _special_folders_env.split(',') if folder.strip()]

# Deletion Control Examples:

# Example 1: Completely disable deletion for everyone
# ENABLE_DELETION = False
# DELETION_ALLOWED_IPS = []

# Example 2: Allow deletion from any IP (default behavior)
ENABLE_DELETION = True
DELETION_ALLOWED_IPS = []

# Example 3: Only allow deletion from specific IP addresses
# ENABLE_DELETION = True
# DELETION_ALLOWED_IPS = ['192.168.1.100', '10.0.0.50']

# Example 4: Allow deletion from specific IP ranges (CIDR blocks)
# ENABLE_DELETION = True  
# DELETION_ALLOWED_IPS = ['192.168.1.0/24', '10.0.0.0/8']

# Example 5: Mixed IP addresses and CIDR blocks
# ENABLE_DELETION = True
# DELETION_ALLOWED_IPS = ['192.168.1.100', '10.0.0.0/8', '172.16.0.0/12', '127.0.0.1']

# Current settings (using environment variables with fallbacks)
ENABLE_DELETION = os.environ.get('GALLERY_ENABLE_DELETION', 'true').lower() == 'true'
_deletion_allowed_ips_env = os.environ.get('GALLERY_DELETION_ALLOWED_IPS', '')
DELETION_ALLOWED_IPS = [ip.strip() for ip in _deletion_allowed_ips_env.split(',') if ip.strip()]