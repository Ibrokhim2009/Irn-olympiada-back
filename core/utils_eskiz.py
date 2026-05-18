import requests
import os
import datetime
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
    
    # Checked and verified endpoints from Postman Documentation:
    # 1. 'user/templates' is the official list endpoint.
    # 2. 'user/template' (fallback)
    # 3. 'template' (fallback)
    # 4. 'message/sms/template' (fallback)
    endpoints = ["user/templates", "user/template", "template", "message/sms/template"]
    headers = { 'Authorization': f'Bearer {token}' }
    
    all_templates = []
    now_iso = datetime.datetime.utcnow().isoformat() + 'Z'
    
    test_templates = [
        {"id": "test_1", "text": "Это тест от Eskiz", "status": "approved", "name": "Test 1 (RU)", "created_at": now_iso},
        {"id": "test_2", "text": "Bu Eskiz dan test", "status": "approved", "name": "Test 2 (UZ)", "created_at": now_iso},
        {"id": "test_3", "text": "This is test from Eskiz", "status": "approved", "name": "Test 3 (EN)", "created_at": now_iso},
    ]
    
    for ep in endpoints:
        try:
            url = f"{ESKIZ_BASE_URL}{ep}"
            response = requests.get(url, headers=headers)
            print(f"Eskiz GET {ep} status code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Eskiz GET {ep} response: {data}")
                
                templates_list = []
                if isinstance(data, list):
                    templates_list = data
                elif isinstance(data, dict):
                    # API returns template lists in either 'result', 'data', or the top-level list
                    templates_list = data.get('result', data.get('data', []))
                
                if isinstance(templates_list, list) and len(templates_list) > 0:
                    for t in templates_list:
                        if isinstance(t, dict):
                            t_id = t.get('id')
                            # 'template' or 'original_text' contains the SMS content
                            t_text = t.get('template') or t.get('original_text') or t.get('text')
                            t_status = t.get('status', 'moderation')
                            
                            # Normalize statuses to: approved, moderation, process, rejected
                            if t_status in ['service', 'reklama', 'approved']:
                                norm_status = 'approved'
                            elif t_status in ['inproccess', 'process']:
                                norm_status = 'process'
                            elif t_status in ['rejected', 'declined']:
                                norm_status = 'rejected'
                            else:
                                norm_status = 'moderation'
                                
                            t_created = t.get('created_at') or t.get('created_date') or t.get('updated_at') or now_iso
                            t_note = t.get('note', '')
                            
                            all_templates.append({
                                'id': t_id,
                                'text': t_text,
                                'status': norm_status,
                                'created_at': t_created,
                                'note': t_note
                            })
                    break # Stop trying other endpoints if we got a valid non-empty list
        except Exception as e:
            print(f"Error fetching from {ep}: {e}")
            continue
            
    # Combine with test templates ensuring no duplicates by text
    unique_texts = set(t['text'] for t in all_templates if t.get('text'))
    for tt in test_templates:
        if tt['text'] not in unique_texts:
            all_templates.append(tt)
            
    return all_templates

def add_template(name, text):
    token = get_eskiz_token()
    if not token:
        return {"status": "error", "message": "No token"}
    
    # Official POST endpoint from Postman documentation: 'user/template'
    url = f"{ESKIZ_BASE_URL}user/template"
    # Payload key MUST be 'template', not 'text' or 'name'
    payload = { 'template': text }
    headers = { 'Authorization': f'Bearer {token}' }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        print(f"Eskiz POST user/template status code: {response.status_code}")
        print(f"Eskiz POST user/template response text: {response.text}")
        
        # Fallback to other endpoints if the main one fails with 404
        if response.status_code == 404:
            url = f"{ESKIZ_BASE_URL}template"
            response = requests.post(url, data={'name': name, 'text': text}, headers=headers)
            
        if response.status_code in [200, 201]:
            try:
                return response.json()
            except Exception:
                return {"status": "success", "message": "Template created successfully"}
        else:
            try:
                data = response.json()
                return {
                    "status": "error",
                    "message": data.get('message', f"Eskiz API Error: {response.status_code}")
                }
            except Exception:
                return {
                    "status": "error",
                    "message": f"Eskiz API Error: {response.status_code}"
                }
    except Exception as e:
        return {"status": "error", "message": str(e)}
