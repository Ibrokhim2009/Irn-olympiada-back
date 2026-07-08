import os
import sys
import time
import random
import requests
import django
import uuid

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.settings')
try:
    django.setup()
except Exception as e:
    print("Failed to boot Django environment. Make sure settings are correct.")
    print("Error:", e)
    sys.exit(1)

from django.core.files.base import ContentFile
from django.db import transaction
from core.models import User, Book, BookOrder

BOT_TOKEN = "7361972097:AAFOiy-yKvejKL_nG4r9b7ecmj6TzJC655A"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# Memory state tracking for multi-step flows
USER_STATES = {}

# Regional groups text
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
        res = requests.post(API_URL + "sendMessage", json=payload)
        return res.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"Error sending message to {chat_id}:", e)
        return None

def delete_message(chat_id, message_id):
    """Delete a message by chat_id and message_id silently."""
    if not message_id:
        return
    try:
        requests.post(API_URL + "deleteMessage", json={"chat_id": chat_id, "message_id": message_id})
    except Exception as e:
        print(f"Error deleting message {message_id} in {chat_id}:", e)

def get_keyboard():
    # Keyboard to request contact & book shop button
    return {
        "keyboard": [
            [
                {
                    "text": "📞 Telefon raqamni yuborish (Parolni tiklash) / Отправить контакт",
                    "request_contact": True
                }
            ],
            [
                {
                    "text": "📚 Kitob do'koni / Магазин книг"
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
        # Link telegram chat ID
        matched_user.telegram_chat_id = str(chat_id)
        # Check password_text. If empty, generate one
        password = matched_user.password_text
        if not password:
            password = str(random.randint(100000, 999999))
            matched_user.set_password(password)
            matched_user.password_text = password
            matched_user.save(update_fields=['password_text', 'password', 'telegram_chat_id'])
        else:
            matched_user.save(update_fields=['telegram_chat_id'])

        credentials_text = (
            f"<b>Sizning profilingiz ma'lumotlari / Данные вашего профиля:</b>\n\n"
            f"👤 F.I.SH / ФИО: {matched_user.first_name} {matched_user.last_name}\n"
            f"🔑 Login (ID): <code>{matched_user.participant_id or matched_user.username}</code>\n"
            f"🔒 Parol / Пароль: <code>{password}</code>\n\n"
            f"Profilingiz muvaffaqiyatli ulandi! Ushbu ma'lumotlar yordamida saytga kirishingiz mumkin.\n"
            f"Ваш профиль успешно привязан! С этими данными вы можете войти на сайт."
        )
        send_message(chat_id, credentials_text, reply_markup=get_keyboard())
    else:
        not_found_text = (
            f"Kechirasiz, ushbu telefon raqamiga (+998 {cleaned_number}) bog'liq profil topilmadi. "
            f"Iltimos, avval ro'yxatdan o'ting.\n\n"
            f"Профиль с номером телефона не найден. Пожалуйста, сначала зарегистрируйтесь."
        )
        send_message(chat_id, not_found_text, reply_markup=get_keyboard())

# List of explicitly allowed Telegram Chat IDs for sending broadcasts
ALLOWED_BROADCAST_CHAT_IDS = ["213943928", "1124326551"]

def process_broadcast(chat_id, message_text):
    # Verify sender is admin or superadmin OR is in the explicitly allowed chat IDs list
    sender = User.objects.filter(telegram_chat_id=str(chat_id)).first()
    is_authorized = (sender and sender.role in ['admin', 'superadmin']) or str(chat_id) in ALLOWED_BROADCAST_CHAT_IDS

    if not is_authorized:
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

def process_books(chat_id):
    # Check if user profile is linked
    user = User.objects.filter(telegram_chat_id=str(chat_id)).first()
    if not user:
        send_message(chat_id, "Iltimos, avval telefon raqamingizni yuborib profilingizni bog'lang. / Пожалуйста, сначала привяжите ваш контакт.", reply_markup=get_keyboard())
        return

    books = Book.objects.filter(is_active=True, book_type='paid')
    if not books.exists():
        send_message(chat_id, "Hozircha sotuvda kitoblar yo'q. / В данный момент книг в продаже нет.", reply_markup=get_keyboard())
        return
        
    send_message(chat_id, "📚 <b>Bizning kitoblarimiz / Наши книги:</b>\nTanlang / Выберите:")
    
    for book in books:
        try:
            title = book.title_uz or book.title_ru or book.title_en or 'Book'
            desc = book.description_uz or book.description_ru or book.description_en or ""
            price_val = book.price or 0
            remaining = book.remaining_stock()
            text = (
                f"📖 <b>{title}</b>\n\n"
                f"📝 {desc}\n\n"
                f"💰 <b>Narxi / Цена:</b> {price_val:,} UZS\n"
                f"📦 <b>Omborda / В наличии:</b> {remaining} ta / шт."
            )

            if remaining > 0:
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": "Sotib olish / Купить", "callback_data": f"buy_book:{book.id}"}]
                    ]
                }
            else:
                text += "\n\n❌ <b>Sotuvda yo'q / Нет в наличии</b>"
                reply_markup = None
            
            sent_photo = False
            if book.cover_image:
                # Method A: Try sending photo via local file upload
                try:
                    img_path = book.cover_image.path
                    if os.path.exists(img_path):
                        with open(img_path, 'rb') as f:
                            payload = {
                                "chat_id": chat_id,
                                "caption": text,
                                "parse_mode": "HTML",
                            }
                            if reply_markup:
                                payload["reply_markup"] = reply_markup
                            files = {"photo": f}
                            res = requests.post(API_URL + "sendPhoto", data=payload, files=files)
                            if res.status_code == 200:
                                sent_photo = True
                except Exception as e:
                    print(f"Failed local path upload for book {book.id}: {e}")
                    
                # Method B: Try sending photo via public URL
                if not sent_photo:
                    try:
                        public_url = "https://x8k2m9f3.irnolympiad.uz" + book.cover_image.url
                        payload = {
                            "chat_id": chat_id,
                            "photo": public_url,
                            "caption": text,
                            "parse_mode": "HTML",
                        }
                        if reply_markup:
                            payload["reply_markup"] = reply_markup
                        res = requests.post(API_URL + "sendPhoto", json=payload)
                        if res.status_code == 200:
                            sent_photo = True
                    except Exception as e:
                        print(f"Failed public URL send for book {book.id}: {e}")
                        
            if sent_photo:
                time.sleep(0.2)
                continue
                
            # Fallback to text message if photo could not be sent or cover_image is missing
            send_message(chat_id, text, reply_markup=reply_markup)
            time.sleep(0.2)
        except Exception as err:
            print(f"Error rendering book {book.id}: {err}")

def process_callback_query(callback_query):
    query_id = callback_query["id"]
    chat_id = callback_query["message"]["chat"]["id"]
    data = callback_query.get("data", "")
    
    # Answer callback query to stop loading spinner
    try:
        requests.post(API_URL + "answerCallbackQuery", json={"callback_query_id": query_id})
    except Exception as e:
        print("Error answering callback query:", e)
        
    if data.startswith("buy_book:"):
        try:
            book_id = int(data.split(":")[1])
            book = Book.objects.filter(id=book_id).first()
            if not book:
                send_message(chat_id, "Kitob topilmadi. / Книга не найдена.")
                return
            
            # Check if user profile is linked
            user = User.objects.filter(telegram_chat_id=str(chat_id)).first()
            if not user:
                send_message(chat_id, "Iltimos, avval telefon raqamingizni yuborib profilingizni bog'lang. / Пожалуйста, сначала привяжите ваш контакт.")
                return
                
            USER_STATES[chat_id] = {
                "state": "SELECT_AMOUNT",
                "book_id": book_id
            }
            
            cancel_markup = {
                "keyboard": [
                    [{"text": "1"}, {"text": "2"}, {"text": "3"}],
                    [{"text": "5"}, {"text": "❌ Bekor qilish / Отмена"}]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            
            send_message(
                chat_id, 
                f"📖 <b>{book.title_uz or book.title_ru}</b>\n"
                f"Narxi / Цена: {book.price:,} UZS\n\n"
                f"Sotib olmoqchi bo'lgan kitoblar sonini tanlang yoki kiriting (masalan: 1, 2, 5):\n\n"
                f"Выберите или введите количество книг, которые хотите купить:",
                reply_markup=cancel_markup
            )
        except Exception as e:
            print("Error in callback query buy_book:", e)

def process_state_message(chat_id, message, state):
    text = message.get("text", "").strip()
    photo = message.get("photo")
    document = message.get("document")
    
    if text == "❌ Bekor qilish / Отмена" or text == "/cancel":
        USER_STATES.pop(chat_id, None)
        send_message(chat_id, "Buyurtma bekor qilindi. / Заказ отменен.", reply_markup=get_keyboard())
        return

    current_state = state["state"]
    
    if current_state == "SELECT_AMOUNT":
        try:
            amount = int(text)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            send_message(chat_id, "Iltimos, to'g'ri son kiriting (masalan: 1, 2, 5). / Пожалуйста, введите целое положительное число.")
            return

        book = Book.objects.filter(id=state["book_id"]).first()
        if not book:
            send_message(chat_id, "Kechirasiz, kitob topilmadi. / Извините, книга не найдена.", reply_markup=get_keyboard())
            USER_STATES.pop(chat_id, None)
            return

        remaining = book.remaining_stock()
        if amount > remaining:
            send_message(
                chat_id,
                f"Kechirasiz, omborda faqat {remaining} ta kitob qoldi. Iltimos, kamroq son kiriting.\n"
                f"Извините, на складе осталось только {remaining} шт. Пожалуйста, введите меньшее количество."
            )
            return

        state["amount"] = amount
        state["state"] = "ENTER_ADDRESS"
        
        cancel_markup = {
            "keyboard": [
                [{"text": "❌ Bekor qilish / Отмена"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
        send_message(
            chat_id,
            "📍 Yetkazib berish manzilini kiriting (shahar/viloyat, tuman, ko'cha, uy raqami):\n\n"
            "Введите адрес доставки (город, область, район, улица, дом):",
            reply_markup=cancel_markup
        )
        
    elif current_state == "ENTER_ADDRESS":
        if not text:
            send_message(chat_id, "Iltimos, manzilni matn ko'rinishida yuboring. / Пожалуйста, введите адрес текстом.")
            return
            
        state["address"] = text
        state["state"] = "WAIT_FOR_RECEIPT"
        
        try:
            book = Book.objects.get(id=state["book_id"])
        except Book.DoesNotExist:
            send_message(chat_id, "Kechirasiz, kitob topilmadi. / Извините, книга не найдена.")
            USER_STATES.pop(chat_id, None)
            return
            
        total_price = book.price * state["amount"]
        state["total_price"] = total_price
        
        checkout_text = (
            f"📋 <b>Buyurtma tasdiqlash / Подтверждение заказа</b>\n\n"
            f"📖 Kitob / Книга: <b>{book.title_uz or book.title_ru}</b>\n"
            f"🔢 Soni / Количество: <b>{state['amount']} ta</b>\n"
            f"💰 Narxi / Общая сумма: <b>{total_price:,} UZS</b>\n"
            f"📍 Manzil / Адрес доставки: <b>{state['address']}</b>\n\n"
            f"💳 <b>To'lov ma'lumotlari / Реквизиты для оплаты:</b>\n"
            f"Karta raqami / Номер карты: <code>8600 1402 1234 5678</code> (Uzcard / Humo)\n"
            f"Karta egasi / Получатель: <b>IRN OLYMPIADS</b>\n\n"
            f"To'lovni amalga oshirgach, iltimos to'lov cheki (kvitansiya, skrinshot) rasmini yoki faylini shu yerga yuboring.\n\n"
            f"После оплаты, пожалуйста, отправьте сюда фото или файл чека."
        )
        
        cancel_markup = {
            "keyboard": [
                [{"text": "❌ Bekor qilish / Отмена"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
        # Save the checkout message_id so we can delete it after receipt is received
        checkout_msg_id = send_message(chat_id, checkout_text, reply_markup=cancel_markup)
        state["checkout_msg_id"] = checkout_msg_id
        
    elif current_state == "WAIT_FOR_RECEIPT":
        file_id = None
        receipt_message_id = message.get("message_id")  # ID of user's receipt photo message
        if photo:
            file_id = photo[-1]["file_id"]
        elif document and document.get("mime_type", "").startswith("image/"):
            file_id = document["file_id"]
            
        if not file_id:
            send_message(chat_id, "Iltimos, to'lov cheki rasmini (kvitansiyani) yuboring. / Пожалуйста, отправьте именно фото или скриншот чека.")
            return
            
        send_message(chat_id, "Chek qabul qilinmoqda, iltimos kuting... / Чек обрабатывается, пожалуйста, подождите...")
        
        file_url_res = requests.get(API_URL + "getFile", params={"file_id": file_id})
        if file_url_res.status_code != 200:
            send_message(chat_id, "Telegram faylni yuklashda xatolik. / Ошибка загрузки файла из Telegram.")
            return
            
        file_path = file_url_res.json().get("result", {}).get("file_path")
        if not file_path:
            send_message(chat_id, "Fayl yo'li aniqlanmadi. / Путь к файлу не найден.")
            return
            
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        img_res = requests.get(download_url)
        if img_res.status_code != 200:
            send_message(chat_id, "Faylni yuklab olishda xatolik. / Ошибка скачивания файла.")
            return
            
        try:
            user = User.objects.filter(telegram_chat_id=str(chat_id)).first()

            with transaction.atomic():
                # Lock the book row so concurrent orders can't oversell the same stock
                book = Book.objects.select_for_update().get(id=state["book_id"])

                if state["amount"] > book.stock:
                    send_message(
                        chat_id,
                        "Kechirasiz, siz kutayotgan vaqtda bu kitob sotilib bo'ldi yoki qoldiq yetarli emas. Buyurtma bekor qilindi.\n"
                        "Извините, пока вы ждали, книга закончилась или остатка недостаточно. Заказ отменен.",
                        reply_markup=get_keyboard()
                    )
                    USER_STATES.pop(chat_id, None)
                    return

                book.stock -= state["amount"]
                book.save(update_fields=["stock"])

                order = BookOrder(
                    user=user,
                    book=book,
                    amount=state["amount"],
                    total_price=state["total_price"],
                    delivery_address=state["address"],
                    status=BookOrder.Status.PENDING
                )
                order.save()

            # Save receipt image (outside the stock-locking transaction — this does network I/O)
            filename = f"receipt_{uuid.uuid4().hex[:10]}.jpg"
            order.receipt_image.save(filename, ContentFile(img_res.content), save=True)
            
            # Delete the checkout details message (card number etc.) for privacy
            checkout_msg_id = state.get("checkout_msg_id")
            USER_STATES.pop(chat_id, None)
            
            # Delete both: the checkout order summary message + the user's receipt photo
            delete_message(chat_id, checkout_msg_id)
            delete_message(chat_id, receipt_message_id)
            
            success_msg = (
                f"✅ <b>Rahmat! Buyurtmangiz qabul qilindi / Спасибо! Ваш заказ принят.</b>\n\n"
                f"📦 Buyurtma ID: #{order.id}\n"
                f"Tez orada administrator to'lovni tekshiradi va sizga xabar yuboradi.\n\n"
                f"Администратор скоро проверит оплату и вам придет уведомление."
            )
            send_message(chat_id, success_msg, reply_markup=get_keyboard())
            
            # Notify admins
            admins = User.objects.filter(role__in=['admin', 'superadmin']).exclude(telegram_chat_id__isnull=True).exclude(telegram_chat_id='')
            admin_msg = (
                f"🔔 <b>Yangi buyurtma! / Новый заказ!</b>\n\n"
                f"📦 Buyurtma ID: #{order.id}\n"
                f"👤 Xaridor / Покупатель: {user.last_name} {user.first_name} (@{user.username or ''})\n"
                f"📞 Tel: {user.phone}\n"
                f"📖 Kitob: {book.title_uz or book.title_ru}\n"
                f"🔢 Soni: {order.amount} ta\n"
                f"💰 Jami: {order.total_price:,} UZS\n"
                f"📍 Manzil: {order.delivery_address}\n\n"
                f"Admin panel orqali tasdiqlashingiz mumkin."
            )
            for admin in admins:
                send_message(admin.telegram_chat_id, admin_msg)
                
        except Exception as e:
            print("Failed to save book order:", e)
            send_message(chat_id, "Tizim xatoligi, buyurtma saqlanmadi. / Системная ошибка, заказ не сохранен.")

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

                # A bug in handling one update should never stop the rest of the
                # batch from being processed (or take down the whole bot).
                try:
                    # Check for callback query
                    callback_query = update.get("callback_query")
                    if callback_query:
                        process_callback_query(callback_query)
                        continue

                    message = update.get("message")
                    if not message:
                        continue

                    chat_id = message["chat"]["id"]
                    text = message.get("text", "")
                    contact = message.get("contact")

                    # If user is in middle of a multi-step order flow
                    if chat_id in USER_STATES:
                        process_state_message(chat_id, message, USER_STATES[chat_id])
                        continue

                    if text.startswith("/start"):
                        parts = text.split(maxsplit=1)
                        payload = parts[1] if len(parts) > 1 else None
                        process_start(chat_id, payload)

                    elif text.startswith("/broadcast"):
                        process_broadcast(chat_id, text)

                    elif text.startswith("/books") or text == "📚 Kitob do'koni / Магазин книг":
                        process_books(chat_id)

                    elif contact:
                        process_contact(chat_id, contact)

                    elif text:
                        help_text = (
                            "Profilingizni bog'lash uchun shaxsiy kabinetdagi havoladan o'ting. "
                            "Parolni tiklash va profilingizni ulash uchun quyidagi 'Telefon raqamni yuborish' tugmasini bosing.\n\n"
                            "Kitoblar xarid qilish uchun <b>📚 Kitob do'koni / Магазин книг</b> tugmasini bosing."
                        )
                        send_message(chat_id, help_text, reply_markup=get_keyboard())
                except Exception as e:
                    print(f"Error processing update {update.get('update_id')}:", e)
                    continue

        except Exception as e:
            print("Bot polling encountered error:", e)
            time.sleep(5)
 
if __name__ == "__main__":
    # main() already never intentionally exits, but this is a last line of
    # defense: if it ever does raise or return, restart it instead of letting
    # the process die (systemd's Restart= is the other layer of this).
    while True:
        try:
            main()
            print("main() returned unexpectedly, restarting in 5s...")
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            print("Fatal error in main(), restarting in 5s:", e)
        time.sleep(5)
