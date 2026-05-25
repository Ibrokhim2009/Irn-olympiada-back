import hashlib
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from django.conf import settings
from django.contrib.auth import get_user_model
from core.models import Olympiad, Registration

User = get_user_model()

class ClickIntegrationTests(APITestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            username="testuser",
            password="testpassword",
            phone="+998991234567"
        )
        
        # Create test olympiad
        self.olympiad = Olympiad.objects.create(
            title_ru="Тестовая Олимпиада",
            price=15000,
            is_free=False
        )
        
        # Create test registration
        self.registration = Registration.objects.create(
            user=self.user,
            olympiad=self.olympiad,
            price=15000
        )
        
        # Setup settings overrides for Click
        settings.CLICK_SERVICE_ID = "103414"
        settings.CLICK_MERCHANT_ID = "21776"
        settings.CLICK_SECRET_KEY = "97aJ6iCk0U"
        settings.CLICK_MERCHANT_USER_ID = "85027"

    def test_get_click_link(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('get-click-link', kwargs={'registration_id': self.registration.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('link', response.data)
        
        link = response.data['link']
        self.assertIn("service_id=103414", link)
        self.assertIn("merchant_id=21776", link)
        self.assertIn("amount=15000.00", link)
        self.assertIn(f"transaction_param={self.registration.id}", link)
        self.assertIn("merchant_user_id=85027", link)

    def test_click_prepare_success(self):
        # Action 0 (Prepare)
        click_trans_id = "99988877"
        service_id = "103414"
        merchant_trans_id = str(self.registration.id)
        amount = "15000.0"
        action = "0"
        error = "0"
        sign_time = "2026-05-25 12:00:00"
        
        secret_key = settings.CLICK_SECRET_KEY
        
        # Calculate sign_string: md5(click_trans_id + service_id + secret_key + merchant_trans_id + amount + action + sign_time)
        raw_sign = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{amount}{action}{sign_time}"
        sign_string = hashlib.md5(raw_sign.encode('utf-8')).hexdigest()
        
        payload = {
            "click_trans_id": click_trans_id,
            "service_id": service_id,
            "click_paydoc_id": "112233",
            "merchant_trans_id": merchant_trans_id,
            "amount": amount,
            "action": action,
            "error": error,
            "error_note": "Success",
            "sign_time": sign_time,
            "sign_string": sign_string
        }
        
        url = reverse('click-callback')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('error'), 0)
        self.assertEqual(response.data.get('merchant_prepare_id'), self.registration.id)

    def test_click_prepare_sign_check_failed(self):
        payload = {
            "click_trans_id": "99988877",
            "service_id": "103414",
            "click_paydoc_id": "112233",
            "merchant_trans_id": str(self.registration.id),
            "amount": "15000.0",
            "action": "0",
            "error": "0",
            "error_note": "Success",
            "sign_time": "2026-05-25 12:00:00",
            "sign_string": "incorrect_hash"
        }
        
        url = reverse('click-callback')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('error'), -1)
        self.assertEqual(response.data.get('error_note'), "SIGN CHECK FAILED")

    def test_click_complete_success(self):
        # Action 1 (Complete)
        click_trans_id = "99988877"
        service_id = "103414"
        merchant_trans_id = str(self.registration.id)
        merchant_prepare_id = str(self.registration.id)
        amount = "15000.0"
        action = "1"
        error = "0"
        sign_time = "2026-05-25 12:00:00"
        
        secret_key = settings.CLICK_SECRET_KEY
        
        # Calculate sign_string: md5(click_trans_id + service_id + secret_key + merchant_trans_id + merchant_prepare_id + amount + action + sign_time)
        raw_sign = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{merchant_prepare_id}{amount}{action}{sign_time}"
        sign_string = hashlib.md5(raw_sign.encode('utf-8')).hexdigest()
        
        payload = {
            "click_trans_id": click_trans_id,
            "service_id": service_id,
            "click_paydoc_id": "112233",
            "merchant_trans_id": merchant_trans_id,
            "merchant_prepare_id": merchant_prepare_id,
            "amount": amount,
            "action": action,
            "error": error,
            "error_note": "Success",
            "sign_time": sign_time,
            "sign_string": sign_string
        }
        
        # Fresh registration state
        self.registration.payment_status = Registration.PaymentStatus.PENDING
        self.registration.save()
        
        url = reverse('click-callback')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('error'), 0)
        
        # Reload registration and verify payment status
        self.registration.refresh_from_db()
        self.assertEqual(self.registration.payment_status, Registration.PaymentStatus.PAID)
        self.assertEqual(self.registration.transaction_id, "CLICK_99988877")
