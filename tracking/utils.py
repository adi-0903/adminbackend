import re
from urllib.parse import urlparse


def parse_user_agent(user_agent_string):
    """
    Parse user agent string and extract device information
    """
    try:
        ua_lower = user_agent_string.lower()
        
        # Determine device type and platform
        device_type = 'web'
        platform = 'unknown'
        
        # Check for mobile devices
        if any(x in ua_lower for x in ['mobile', 'android', 'iphone', 'ipod', 'blackberry', 'windows phone']):
            device_type = 'mobile'
        
        # Check for tablets
        elif any(x in ua_lower for x in ['ipad', 'tablet', 'kindle', 'playbook', 'nexus 7', 'nexus 10']):
            device_type = 'tablet'
        
        # Determine platform
        if 'iphone' in ua_lower or 'ipad' in ua_lower or 'ipod' in ua_lower:
            platform = 'ios'
        elif 'android' in ua_lower:
            platform = 'android'
        elif 'windows' in ua_lower:
            platform = 'windows'
        elif 'mac' in ua_lower:
            platform = 'macos'
        elif 'linux' in ua_lower:
            platform = 'linux'
        elif 'x11' in ua_lower:
            platform = 'linux'
        else:
            platform = 'web'
        
        # Extract device model
        device_model = extract_device_model(user_agent_string, platform)
        
        # Extract OS version
        os_version = extract_os_version(user_agent_string, platform)
        
        return {
            'device_type': device_type,
            'platform': platform,
            'device_model': device_model,
            'os_version': os_version,
            'user_agent': user_agent_string,
        }
    except Exception as e:
        print(f"Error parsing user agent: {e}")
        return {
            'device_type': 'unknown',
            'platform': 'unknown',
            'device_model': 'Unknown',
            'os_version': 'Unknown',
            'user_agent': user_agent_string,
        }


def extract_device_model(user_agent_string, platform):
    """
    Extract device model from user agent string
    """
    ua_lower = user_agent_string.lower()
    
    # iPhone models
    if 'iphone' in ua_lower:
        if 'iphone 15' in ua_lower:
            return 'iPhone 15'
        elif 'iphone 14' in ua_lower:
            return 'iPhone 14'
        elif 'iphone 13' in ua_lower:
            return 'iPhone 13'
        elif 'iphone 12' in ua_lower:
            return 'iPhone 12'
        else:
            return 'iPhone'
    
    # iPad models
    elif 'ipad' in ua_lower:
        if 'ipad pro' in ua_lower:
            return 'iPad Pro'
        elif 'ipad air' in ua_lower:
            return 'iPad Air'
        elif 'ipad mini' in ua_lower:
            return 'iPad Mini'
        else:
            return 'iPad'
    
    # Android devices
    elif 'android' in ua_lower:
        # Samsung
        if 'samsung' in ua_lower:
            if 'galaxy s' in ua_lower:
                match = re.search(r'galaxy s(\d+)', ua_lower)
                if match:
                    return f'Samsung Galaxy S{match.group(1)}'
            return 'Samsung Galaxy'
        # Google Pixel
        elif 'pixel' in ua_lower:
            match = re.search(r'pixel (\d+)', ua_lower)
            if match:
                return f'Google Pixel {match.group(1)}'
            return 'Google Pixel'
        else:
            return 'Android Device'
    
    # Windows devices
    elif 'windows' in ua_lower:
        if 'surface' in ua_lower:
            return 'Microsoft Surface'
        else:
            return 'Windows PC'
    
    # Mac devices
    elif 'mac' in ua_lower:
        if 'macbook' in ua_lower:
            if 'pro' in ua_lower:
                return 'MacBook Pro'
            elif 'air' in ua_lower:
                return 'MacBook Air'
            else:
                return 'MacBook'
        else:
            return 'Mac'
    
    return 'Unknown'


def extract_os_version(user_agent_string, platform):
    """
    Extract OS version from user agent string
    """
    ua_lower = user_agent_string.lower()
    
    if platform == 'ios':
        # Extract iOS version
        match = re.search(r'os (\d+_\d+)', ua_lower)
        if match:
            version = match.group(1).replace('_', '.')
            return f'iOS {version}'
        return 'iOS Unknown'
    
    elif platform == 'android':
        # Extract Android version
        match = re.search(r'android (\d+\.?\d*)', ua_lower)
        if match:
            return f'Android {match.group(1)}'
        return 'Android Unknown'
    
    elif platform == 'windows':
        # Extract Windows version
        if 'windows nt 10.0' in ua_lower:
            return 'Windows 10'
        elif 'windows nt 6.3' in ua_lower:
            return 'Windows 8.1'
        elif 'windows nt 6.2' in ua_lower:
            return 'Windows 8'
        else:
            return 'Windows Unknown'
    
    elif platform == 'macos':
        # Extract macOS version
        match = re.search(r'mac os x (\d+[._]\d+)', ua_lower)
        if match:
            version = match.group(1).replace('_', '.')
            return f'macOS {version}'
        return 'macOS Unknown'
    
    elif platform == 'linux':
        return 'Linux'
    
    return 'Unknown'


def get_client_ip(request):
    """
    Get client IP address from request
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
