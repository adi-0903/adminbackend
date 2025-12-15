import re
from user_agents import parse

def detect_device_type(user_agent_string):
    """
    Detect device type from User-Agent string
    Returns: 'Mobile', 'Tablet', 'Web', or 'Unknown'
    """
    if not user_agent_string:
        return 'Unknown'
    
    try:
        user_agent = parse(user_agent_string)
        
        if user_agent.is_mobile:
            return 'Mobile'
        elif user_agent.is_tablet:
            return 'Tablet'
        elif user_agent.is_pc:
            return 'Web'
        else:
            return 'Unknown'
    except:
        return 'Unknown'

def extract_device_info(user_agent_string):
    """
    Extract detailed device information from User-Agent
    """
    if not user_agent_string:
        return {
            'device_type': 'Unknown',
            'platform': 'Unknown',
            'os_version': 'Unknown',
            'app_version': 'Unknown',
            'device_model': 'Unknown'
        }
    
    try:
        user_agent = parse(user_agent_string)
        
        return {
            'device_type': detect_device_type(user_agent_string),
            'platform': str(user_agent.os.family) if user_agent.os else 'Unknown',
            'os_version': str(user_agent.os.version_string) if user_agent.os else 'Unknown',
            'app_version': str(user_agent.browser.version_string) if user_agent.browser else 'Unknown',
            'device_model': str(user_agent.device.model) if user_agent.device else 'Unknown'
        }
    except:
        return {
            'device_type': 'Unknown',
            'platform': 'Unknown',
            'os_version': 'Unknown',
            'app_version': 'Unknown',
            'device_model': 'Unknown'
        }
