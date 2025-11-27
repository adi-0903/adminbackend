import requests
import logging
from django.conf import settings

logger = logging.getLogger('user')

def send_otp(phone_number: str) -> dict:
    url = f"https://cpaas.messagecentral.com/verification/v3/send?countryCode=91&customerId={settings.OTP_CUSTOMER_ID}&flowType=SMS&mobileNumber={phone_number}"
    
    headers = {
        'authToken': settings.OTP_AUTH_TOKEN
    }
    
    try:
        response = requests.post(url, headers=headers, timeout=30)
        response.raise_for_status()  # Raise exception for non-200 status codes
        
        logger.info(f"OTP sent successfully to {phone_number}")
        return response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error when sending OTP to {phone_number}")
        return {"error": "Request timed out. Please try again."}
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error when sending OTP to {phone_number}")
        return {"error": "Connection error. Please check your internet connection."}
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error when sending OTP to {phone_number}: {str(e)}")
        return {"error": f"Server error: {e.response.status_code}. Please try again later."}
    except (requests.RequestException, ValueError) as e:
        logger.error(f"Error sending OTP to {phone_number}: {str(e)}")
        return {"error": "Failed to send OTP. Please try again later."}

def verify_otp(phone_number: str, verification_id: str, otp: str) -> dict:
    url = f"https://cpaas.messagecentral.com/verification/v3/validateOtp?countryCode=91&mobileNumber={phone_number}&verificationId={verification_id}&customerId={settings.OTP_CUSTOMER_ID}&code={otp}"
    
    headers = {
        'authToken': settings.OTP_AUTH_TOKEN    
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()  # Raise exception for non-200 status codes
        
        logger.info(f"OTP verification successful for {phone_number}")
        return response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error when verifying OTP for {phone_number}")
        return {"error": "Request timed out. Please try again."}
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error when verifying OTP for {phone_number}")
        return {"error": "Connection error. Please check your internet connection."}
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error when verifying OTP for {phone_number}: {str(e)}")
        return {"error": f"Server error: {e.response.status_code}. Please try again later."}
    except (requests.RequestException, ValueError) as e:
        logger.error(f"Error verifying OTP for {phone_number}: {str(e)}")
        return {"error": "Failed to verify OTP. Please try again."}



