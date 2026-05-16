import requests
import os
from django.core.cache import cache
from environs import Env

env = Env()
env.read_env()

ESKIZ_EMAIL = env.str("ESKIZ_EMAIL", "")
ESKIZ_PASSWORD = env.str("ESKIZ_PASSWORD", "")
ESKIZ_BASE_URL = "https://notify.eskiz.uz/api/"

def get_eskiz_token():
    token = cache.get("eskiz_token")
    if token:
        return token
    
    url = f"{ESKIZ_BASE_URL}auth/login"
    payload = {
        'email': ESKIZ_EMAIL,
        'password': ESKIZ_PASSWORD
    }
    try:
        response = requests.post(url, data=payload)
        data = response.json()
        if response.status_code == 200:
            token = data.get('data', {}).get('token')
            # Token is valid for 30 days, we cache it for 29 days
            cache.set("eskiz_token", token, 60 * 60 * 24 * 29)
            return token
    except Exception as e:
        print(f"Eskiz login error: {e}")
    return None

def send_sms(mobile_phone, message, from_name="4546"):
    token = get_eskiz_token()
    if not token:
        return {"status": "error", "message": "Failed to get token"}
    
    url = f"{ESKIZ_BASE_URL}message/sms/send"
    # Ensure phone number is in correct format (998XXXXXXXXX)
    phone = str(mobile_phone).replace("+", "").replace(" ", "")
    
    payload = {
        'mobile_phone': phone,
        'message': message,
        'from': from_name,
    }
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        print(f"Eskiz send SMS response to {phone}: {response.text}")
        return response.json()
    except Exception as e:
        print(f"Eskiz send SMS error: {e}")
        return {"status": "error", "message": str(e)}

def get_templates():
    token = get_eskiz_token()
    if not token:
        return []
    
    # 1. Try standard endpoint
    # 2. Try 'message/sms/template'
    # 3. Try 'user/template'
    endpoints = ["template", "message/sms/template", "user/template"]
    headers = { 'Authorization': f'Bearer {token}' }
    
    all_templates = []
    
    # Always include the 3 Test Templates if in test status
    test_templates = [
        {"id": "test_1", "text": "Это тест от Eskiz", "status": "approved", "name": "Test 1 (RU)"},
        {"id": "test_2", "text": "Bu Eskiz dan test", "status": "approved", "name": "Test 2 (UZ)"},
        {"id": "test_3", "text": "This is test from Eskiz", "status": "approved", "name": "Test 3 (EN)"},
    ]
    
    for ep in endpoints:
        try:
            url = f"{ESKIZ_BASE_URL}{ep}"
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                templates = data if isinstance(data, list) else data.get('data', [])
                if isinstance(templates, list) and len(templates) > 0:
                    all_templates.extend(templates)
                    break # Found them!
        except Exception:
            continue
            
    # Combine with test templates (remove duplicates if any)
    unique_texts = set(t['text'] for t in all_templates)
    for tt in test_templates:
        if tt['text'] not in unique_texts:
            all_templates.append(tt)
            
    return all_templates

def add_template(name, text):
    token = get_eskiz_token()
    if not token:
        return {"status": "error", "message": "No token"}
    
    url = f"{ESKIZ_BASE_URL}template"
    payload = { 'name': name, 'text': text }
    headers = { 'Authorization': f'Bearer {token}' }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        # If /template fails, try /message/sms/template
        if response.status_code == 404:
            url = f"{ESKIZ_BASE_URL}message/sms/template"
            response = requests.post(url, data=payload, headers=headers)
            
        try:
            return response.json()
        except Exception:
            return {"status": "error", "message": f"Eskiz API Error: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
