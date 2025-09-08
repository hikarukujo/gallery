# Deletion Control Feature

The Smart Gallery now includes comprehensive deletion control functionality that allows administrators to:

1. **Enable/Disable Deletion Globally**: Completely prevent file and folder deletion for all users
2. **IP-Based Access Control**: Allow deletion only from specific IP addresses or IP ranges (CIDR blocks)

## Configuration

Add the following settings to your `config.py` file:

```python
# Deletion Control Settings
ENABLE_DELETION = True  # Set to False to disable deletion completely
DELETION_ALLOWED_IPS = ['192.168.1.100', '10.0.0.0/8']  # List of allowed IPs/CIDR blocks
```

## Environment Variables

You can also configure these settings using environment variables:

```bash
export GALLERY_ENABLE_DELETION=true
export GALLERY_DELETION_ALLOWED_IPS="192.168.1.100,10.0.0.0/8,172.16.0.0/12"
```

## Configuration Examples

### Example 1: Disable Deletion Completely
```python
ENABLE_DELETION = False
DELETION_ALLOWED_IPS = []
```

### Example 2: Allow Deletion from Any IP (Default)
```python
ENABLE_DELETION = True
DELETION_ALLOWED_IPS = []  # Empty list allows any IP
```

### Example 3: Specific IP Addresses Only
```python
ENABLE_DELETION = True
DELETION_ALLOWED_IPS = [
    '192.168.1.100',  # Admin workstation
    '10.0.0.50',      # Management server
    '127.0.0.1'       # Localhost
]
```

### Example 4: IP Ranges (CIDR Blocks)
```python
ENABLE_DELETION = True
DELETION_ALLOWED_IPS = [
    '192.168.1.0/24',    # Local network
    '10.0.0.0/8',        # Private network range
    '172.16.0.0/12'      # Another private range
]
```

### Example 5: Mixed Configuration
```python
ENABLE_DELETION = True
DELETION_ALLOWED_IPS = [
    '192.168.1.100',     # Specific admin IP
    '192.168.1.0/24',    # Local network range
    '10.0.0.0/8'         # Corporate network
]
```

## How It Works

### IP Detection
The system automatically detects the client's real IP address, even when behind proxies or load balancers by checking:
1. `X-Forwarded-For` header (takes first IP if multiple)
2. `X-Real-IP` header
3. `request.remote_addr` as fallback

### Permission Checking
When a deletion request is made, the system:
1. Checks if `ENABLE_DELETION` is `True`
2. If IP restrictions are configured, validates the client IP against the allowed list
3. Supports both individual IP addresses and CIDR network blocks
4. Returns appropriate error messages when access is denied

### Frontend Integration
- Delete buttons are hidden/shown based on permissions
- JavaScript can check permissions via `/galleryout/check_deletion_permission` endpoint
- Error messages clearly indicate why deletion was denied

## Security Notes

- **CIDR Notation**: Use standard CIDR notation (e.g., `192.168.1.0/24`) for IP ranges
- **Proxy Headers**: The system respects `X-Forwarded-For` and `X-Real-IP` headers for proper IP detection behind proxies
- **Invalid IPs**: Invalid IP addresses or CIDR blocks in configuration are ignored (logged for debugging)
- **Default Behavior**: When no IP restrictions are set, deletion is allowed from any IP (if `ENABLE_DELETION` is `True`)

## Testing

You can test the deletion permissions by:

1. **Checking current status**: Visit `/galleryout/check_deletion_permission` to see your current IP and permission status
2. **Trying deletion**: Attempt to delete a file - you'll get a clear error message if not permitted
3. **Environment variables**: Use environment variables for temporary testing without modifying config files

## Docker/Container Deployment

For containerized deployments:

```yaml
environment:
  - GALLERY_ENABLE_DELETION=true
  - GALLERY_DELETION_ALLOWED_IPS=192.168.1.0/24,10.0.0.100
```

This feature provides robust control over deletion operations while maintaining ease of use for authorized users.