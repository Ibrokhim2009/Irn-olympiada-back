import os
import sys
import time
import random
import requests
import django

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
try:
    django.setup()
except Exception as e:
    print("Failed to boot Django environment. Make sure settings are correct.")
    print("Error:", e)
    sys.exit(1)

from core.models import User

BOT_TOKEN = "7361972097:AAFOiy-yKvejKL_nG4r9b7ecmj6TzJC655A"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# regional groups text
CHANNELS_TEXT = (
    "Hurmatli ishtirokchilar!\n\n"
    "Olimpiada o‘tkazilish sanasi tez orada e’lon qilinadi. "
    "Sanalarni o‘tkazib yubormaslik uchun hozircha o‘z hududingiz bo‘yicha quyidagi guruhlarga obuna bo‘lib qo‘ying:\n\n"
    "📍 Toshkent va Sirdaryo:\nhttps://t.me/Olympiads_Tashkent\n\n"
    "📍 Xorazm va Qoraqalpog‘iston:\nhttps://t.me/Khorezm_Karakalpakstan\n\n"
    "📍 Surxondaryo va Qashqadaryo:\nhttps://t.me/IRN_Surkhandarya_Kashkadarya\n\n"
    "📍 Jizzax va Samarqand:\nhttps://t.me/IRNJizzakh_Samarkand\n\n"
    "📍 Navoiy va Buxoro:\nhttps://t.me/IRN_Navoi_Bukhara\n\n"
    "Barcha yangiliklar va olimpiada sanalari ushbu guruhlarda e’lon qilinadi."
)

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(API_URL + "sendMessage", json=payload)
    except Exception as e:
        print(f"Error sending message to {chat_id}:", e)

def get_keyboard():
    # Keyboard to request contact
    return {
        "keyboard": [
            [
                {
                    "text": "📞 Telefon raqamni yuborish (Parolni tiklash) / Отправить контакт",
                    "request_contact": True
                }
            ]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def clean_phone(phone_str):
    if not phone_str:
        return ""
    digits = "".join(filter(str.isdigit, str(phone_str)))
    return digits[-9:] if len(digits) >= 9 else digits

def process_start(chat_id, payload):
    # Try to link user if start has payload
    user = None
    if payload:
        payload = payload.strip()
        print(f"Start payload received: {payload}")
        if payload.startswith("USR-"):
            user = User.objects.filter(participant_id=payload).first()
        else:
            try:
                user = User.objects.filter(id=int(payload)).first()
            except ValueError:
                pass
    
    welcome_text = "Xush kelibsiz! / Добро пожаловать!"
    if user:
        user.telegram_chat_id = str(chat_id)
        user.save(update_fields=['telegram_chat_id'])
        welcome_text = (
            f"<b>{user.first_name} {user.last_name}</b>, profilingiz muvaffaqiyatli bog'landi! "
            f"Endi saytdan foydalanishni davom ettirishingiz mumkin.\n\n"
            f"Ваш профиль успешно привязан! Вы можете продолжать работу с сайтом."
        )
    
    send_message(chat_id, welcome_text, reply_markup=get_keyboard())
    time.sleep(0.5)
    send_message(chat_id, CHANNELS_TEXT)

def process_contact(chat_id, contact):
    phone_number = contact.get("phone_number")
    if not phone_number:
        send_message(chat_id, "Telefon raqami aniqlanmadi. / Номер телефона не определен.")
        return

    cleaned_number = clean_phone(phone_number)
    print(f"Received contact. Cleaned phone: {cleaned_number}")

    # Search for user matching cleaned phone number (last 9 digits)
    users = User.objects.all()
    matched_user = None
    for u in users:
        if clean_phone(u.phone) == cleaned_number:
            matched_user = u
            break

    if matched_user:
        # Check password_text. If empty, generate one
        password = matched_user.password_text
        if not password:
            password = str(random.randint(100000, 999999))
            matched_user.set_password(password)
            matched_user.password_text = password
            matched_user.save(update_fields=['password_text', 'password'])

        credentials_text = (
            f"<b>Sizning profilingiz ma'lumotlari / Данные вашего профиля:</b>\n\n"
            f"👤 F.I.SH / ФИО: {matched_user.first_name} {matched_user.last_name}\n"
            f"🔑 Login (ID): <code>{matched_user.participant_id or matched_user.username}</code>\n"
            f"🔒 Parol / Пароль: <code>{password}</code>\n\n"
            f"Ushbu ma'lumotlar yordamida saytga kirishingiz mumkin."
        )
        send_message(chat_id, credentials_text)
    else:
        not_found_text = (
            f"Kechirasiz, ushbu telefon raqamiga (+998 {cleaned_number}) bog'liq profil topilmadi. "
            f"Iltimos, avval ro'yxatdan o'ting.\n\n"
            f"Профиль с номером телефона не найден. Пожалуйста, сначала зарегистрируйтесь."
        )
        send_message(chat_id, not_found_text)

def process_broadcast(chat_id, message_text):
    # Verify sender is admin or superadmin
    sender = User.objects.filter(telegram_chat_id=str(chat_id)).first()
    if not sender or sender.role not in ['admin', 'superadmin']:
        send_message(chat_id, "Sizda broadcast yuborish huquqi yo'q. / У вас нет прав для рассылки.")
        return

    # Extract clean broadcast text
    broadcast_msg = message_text.replace("/broadcast", "").strip()
    if not broadcast_msg:
        send_message(chat_id, "Broadcast xabar matnini yuboring. Masalan: <code>/broadcast Xabar matni</code>")
        return

    # Get all users with telegram_chat_id
    recipients = User.objects.filter(telegram_chat_id__isnull=False).exclude(telegram_chat_id="")
    total = recipients.count()
    success_count = 0

    send_message(chat_id, f"Broadcast boshlandi. Jami qabul qiluvchilar: {total}...")

    for r in recipients:
        try:
            send_message(r.telegram_chat_id, broadcast_msg)
            success_count += 1
            time.sleep(0.05) # Rate limit protection
        except Exception as e:
            print(f"Error sending broadcast to {r.telegram_chat_id}: {e}")

    send_message(chat_id, f"Broadcast yakunlandi!\n✅ Muvaffaqiyatli: {success_count}/{total}")

def main():
    print("Telegram Bot daemon started polling...")
    offset = 0
    while True:
        try:
            res = requests.get(API_URL + "getUpdates", params={"offset": offset, "timeout": 30})
            if res.status_code != 200:
                print("Error from Telegram API status:", res.status_code)
                time.sleep(5)
                continue

            updates = res.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message")
                if not message:
                    continue

                chat_id = message["chat"]["id"]
                text = message.get("text", "")
                contact = message.get("contact")

                if text.startswith("/start"):
                    parts = text.split(maxsplit=1)
                    payload = parts[1] if len(parts) > 1 else None
                    process_start(chat_id, payload)

                elif text.startswith("/broadcast"):
                    process_broadcast(chat_id, text)

                elif contact:
                    process_contact(chat_id, contact)

                elif text:
                    # Echo standard message with instructions
                    help_text = (
                        "Profilingizni bog'lash uchun shaxsiy kabinetdagi havoladan o'ting. "
                        "Parolni tiklash uchun quyidagi 'Telefon raqamni yuborish' tugmasini bosing."
                    )
                    send_message(chat_id, help_text, reply_markup=get_keyboard())

        except Exception as e:
            print("Bot polling encountered error:", e)
            time.sleep(5)

if __name__ == "__main__":
    main()
