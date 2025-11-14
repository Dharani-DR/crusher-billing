"""
Messaging Service Module
Supports SMS and WhatsApp via multiple providers:
- Twilio (SMS & WhatsApp)
- MSG91 (SMS)
- Generic HTTP API
"""
import os
import requests
from typing import Optional, Dict, Any
from flask import url_for, request as flask_request


def format_template(template: str, variables: Dict[str, Any]) -> str:
    """Format message template with variables"""
    if not template:
        return ""
    
    try:
        return template.format(**variables)
    except KeyError as e:
        print(f"⚠️ Missing template variable: {e}")
        return template


def send_sms_twilio(api_key: str, api_secret: str, from_number: str, to_number: str, message: str) -> Dict[str, Any]:
    """Send SMS via Twilio"""
    try:
        from twilio.rest import Client
        
        client = Client(api_key, api_secret)
        message_obj = client.messages.create(
            body=message,
            from_=from_number,
            to=to_number
        )
        return {
            "success": True,
            "message_id": message_obj.sid,
            "status": message_obj.status,
            "provider": "twilio"
        }
    except ImportError:
        return {"success": False, "error": "Twilio library not installed. Run: pip install twilio"}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "twilio"}


def send_sms_msg91(api_key: str, sender_id: str, to_number: str, message: str) -> Dict[str, Any]:
    """Send SMS via MSG91"""
    try:
        url = "https://control.msg91.com/api/v5/flow/"
        headers = {
            "accept": "application/json",
            "authkey": api_key,
            "content-type": "application/json"
        }
        
        # MSG91 API format
        payload = {
            "template_id": "",  # Template ID if using template
            "sender": sender_id,
            "short_url": "0",
            "mobiles": to_number,
            "message": message
        }
        
        # Alternative: Use sendotp API
        url = "https://control.msg91.com/api/sendotp.php"
        params = {
            "authkey": api_key,
            "message": message,
            "sender": sender_id,
            "mobile": to_number,
            "otp": ""  # Not needed for regular SMS
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            return {
                "success": True,
                "message_id": response.text,
                "status": "sent",
                "provider": "msg91"
            }
        else:
            return {
                "success": False,
                "error": f"MSG91 API error: {response.status_code} - {response.text}",
                "provider": "msg91"
            }
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "msg91"}


def send_sms_generic(api_url: str, api_key: str, sender_id: str, to_number: str, message: str, 
                     method: str = "GET", headers: Optional[Dict] = None, 
                     params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict[str, Any]:
    """Send SMS via generic HTTP API"""
    try:
        if not api_url:
            return {"success": False, "error": "API URL not configured"}
        
        # Default headers
        if not headers:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}" if api_key else None
            }
            headers = {k: v for k, v in headers.items() if v}
        
        # Default params/data
        if not params and not data:
            params = {
                "apikey": api_key,
                "sender": sender_id,
                "to": to_number,
                "message": message
            }
        
        if method.upper() == "POST":
            response = requests.post(api_url, json=data or params, headers=headers, timeout=10)
        else:
            response = requests.get(api_url, params=params or data, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            return {
                "success": True,
                "message_id": response.text[:100],
                "status": "sent",
                "provider": "generic"
            }
        else:
            return {
                "success": False,
                "error": f"API error: {response.status_code} - {response.text[:200]}",
                "provider": "generic"
            }
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "generic"}


def send_whatsapp_twilio(account_sid: str, auth_token: str, from_number: str, to_number: str, message: str) -> Dict[str, Any]:
    """Send WhatsApp via Twilio"""
    try:
        from twilio.rest import Client
        
        client = Client(account_sid, auth_token)
        
        # Twilio WhatsApp format: whatsapp:+1234567890
        from_whatsapp = f"whatsapp:{from_number}" if not from_number.startswith("whatsapp:") else from_number
        to_whatsapp = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number
        
        message_obj = client.messages.create(
            body=message,
            from_=from_whatsapp,
            to=to_whatsapp
        )
        return {
            "success": True,
            "message_id": message_obj.sid,
            "status": message_obj.status,
            "provider": "twilio"
        }
    except ImportError:
        return {"success": False, "error": "Twilio library not installed. Run: pip install twilio"}
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "twilio"}


def send_whatsapp_generic(api_url: str, api_key: str, from_number: str, to_number: str, message: str,
                          method: str = "POST", headers: Optional[Dict] = None,
                          params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict[str, Any]:
    """Send WhatsApp via generic HTTP API (e.g., WhatsApp Business API, etc.)"""
    try:
        if not api_url:
            return {"success": False, "error": "API URL not configured"}
        
        # Default headers
        if not headers:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}" if api_key else None
            }
            headers = {k: v for k, v in headers.items() if v}
        
        # Default payload
        if not data and not params:
            data = {
                "to": to_number,
                "from": from_number,
                "message": message
            }
        
        if method.upper() == "GET":
            response = requests.get(api_url, params=params or data, headers=headers, timeout=10)
        else:
            response = requests.post(api_url, json=data or params, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            return {
                "success": True,
                "message_id": response.text[:100],
                "status": "sent",
                "provider": "generic"
            }
        else:
            return {
                "success": False,
                "error": f"API error: {response.status_code} - {response.text[:200]}",
                "provider": "generic"
            }
    except Exception as e:
        return {"success": False, "error": str(e), "provider": "generic"}


def send_sms(settings, to_number: str, message: str) -> Dict[str, Any]:
    """
    Send SMS using configured provider
    
    Args:
        settings: Settings model instance
        to_number: Recipient phone number (format: +91XXXXXXXXXX)
        message: Message text
    
    Returns:
        Dict with success status and details
    """
    if not settings.sms_api_key:
        return {"success": False, "error": "SMS API key not configured"}
    
    provider = getattr(settings, 'sms_provider', 'twilio') or 'twilio'
    
    # Normalize phone number
    if not to_number.startswith('+'):
        if to_number.startswith('91'):
            to_number = '+' + to_number
        elif to_number.startswith('0'):
            to_number = '+91' + to_number[1:]
        else:
            to_number = '+91' + to_number
    
    if provider == 'twilio':
        # For Twilio, API key is Account SID, API secret is Auth Token
        api_secret = getattr(settings, 'sms_api_secret', None) or settings.sms_api_key
        from_number = getattr(settings, 'sms_sender_id', None) or settings.sms_sender_id
        if not from_number:
            return {"success": False, "error": "SMS sender number not configured"}
        return send_sms_twilio(settings.sms_api_key, api_secret, from_number, to_number, message)
    
    elif provider == 'msg91':
        return send_sms_msg91(settings.sms_api_key, settings.sms_sender_id or "SENDER", to_number, message)
    
    elif provider == 'generic':
        api_url = getattr(settings, 'sms_api_url', '') or ''
        return send_sms_generic(api_url, settings.sms_api_key, settings.sms_sender_id or "", to_number, message)
    
    else:
        return {"success": False, "error": f"Unknown SMS provider: {provider}"}


def send_whatsapp(settings, to_number: str, message: str) -> Dict[str, Any]:
    """
    Send WhatsApp message using configured provider
    
    Args:
        settings: Settings model instance
        to_number: Recipient phone number (format: +91XXXXXXXXXX)
        message: Message text
    
    Returns:
        Dict with success status and details
    """
    if not settings.whatsapp_sender_number:
        return {"success": False, "error": "WhatsApp sender number not configured"}
    
    provider = getattr(settings, 'whatsapp_provider', 'twilio') or 'twilio'
    
    # Normalize phone number
    if not to_number.startswith('+'):
        if to_number.startswith('91'):
            to_number = '+' + to_number
        elif to_number.startswith('0'):
            to_number = '+91' + to_number[1:]
        else:
            to_number = '+91' + to_number
    
    if provider == 'twilio':
        # For Twilio WhatsApp, use SMS API credentials (Account SID and Auth Token)
        api_secret = getattr(settings, 'sms_api_secret', None) or settings.sms_api_key
        from_number = settings.whatsapp_sender_number
        if not from_number:
            return {"success": False, "error": "WhatsApp sender number not configured"}
        return send_whatsapp_twilio(settings.sms_api_key, api_secret, from_number, to_number, message)
    
    elif provider == 'generic':
        api_url = getattr(settings, 'whatsapp_api_url', '') or ''
        api_key = getattr(settings, 'whatsapp_api_key', settings.sms_api_key) or settings.sms_api_key
        return send_whatsapp_generic(api_url, api_key, settings.whatsapp_sender_number, to_number, message)
    
    else:
        return {"success": False, "error": f"Unknown WhatsApp provider: {provider}"}


def send_invoice_notification(settings, invoice, base_url: str = None) -> Dict[str, Any]:
    """
    Send invoice notification via SMS and/or WhatsApp
    
    Args:
        settings: Settings model instance
        invoice: Invoice model instance
        base_url: Base URL for PDF link generation
    
    Returns:
        Dict with results for SMS and WhatsApp
    """
    results = {"sms": None, "whatsapp": None}
    
    # Get customer phone number
    customer = invoice.customer
    if not customer or not customer.phone:
        return {"sms": {"success": False, "error": "Customer phone number not available"},
                "whatsapp": {"success": False, "error": "Customer phone number not available"}}
    
    # Generate PDF link
    if base_url:
        pdf_link = f"{base_url}/invoice/{invoice.id}/pdf"
    else:
        # Try to generate URL from request context
        try:
            pdf_link = url_for('invoice_pdf', invoice_id=invoice.id, _external=True)
        except:
            pdf_link = f"/invoice/{invoice.id}/pdf"
    
    # Prepare template variables
    variables = {
        "customer": customer.name,
        "amount": f"₹{invoice.grand_total:.2f}",
        "bill_no": invoice.bill_no,
        "date": invoice.date.strftime("%d-%m-%Y"),
        "pdf_link": pdf_link
    }
    
    # Send SMS if configured
    if settings.sms_api_key and settings.sms_template:
        sms_message = format_template(settings.sms_template, variables)
        results["sms"] = send_sms(settings, customer.phone, sms_message)
    
    # Send WhatsApp if configured
    if settings.whatsapp_sender_number and settings.whatsapp_template:
        whatsapp_message = format_template(settings.whatsapp_template, variables)
        results["whatsapp"] = send_whatsapp(settings, customer.phone, whatsapp_message)
    
    return results

