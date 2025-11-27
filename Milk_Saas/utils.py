from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.utils import IntegrityError
from rest_framework.exceptions import ValidationError as DRFValidationError
import logging

logger = logging.getLogger('django')

def custom_exception_handler(exc, context):
    """Custom exception handler for REST framework that handles additional Django exceptions."""
    
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    # If response is already handled by DRF, return it
    if response is not None:
        return format_error_response(response, exc)

    # Handle Django validation errors
    if isinstance(exc, DjangoValidationError):
        data = {
            'error': 'Validation Error',
            'detail': exc.message if hasattr(exc, 'message') else str(exc)
        }
        return Response(data, status=status.HTTP_400_BAD_REQUEST)

    # Handle database integrity errors
    if isinstance(exc, IntegrityError):
        data = {
            'error': 'Database Error',
            'detail': 'Database integrity error occurred.'
        }
        return Response(data, status=status.HTTP_400_BAD_REQUEST)

    # Log unhandled exceptions
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    # Return generic error for unhandled exceptions
    data = {
        'error': 'Server Error',
        'detail': 'An unexpected error occurred.'
    }
    return Response(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def format_error_response(response, exc):
    """Format error response to maintain consistent error structure."""
    
    if isinstance(exc, DRFValidationError):
        response.data = {
            'error': 'Validation Error',
            'detail': response.data
        }
    elif hasattr(response, 'data') and isinstance(response.data, dict):
        if 'detail' in response.data:
            response.data = {
                'error': exc.__class__.__name__,
                'detail': response.data['detail']
            }
    
    return response