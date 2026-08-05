"""
One-off import of the IRN Republic Olympiad 2026 Math test questions
(grades 1-11) for a given SubOlympiad, transcribed from the supplied PDFs.

The source PDFs turned out to share a single 100-question bank: each grade's
20-question paper is a sliding window of that bank (10 questions carried over
from the previous grade + 10 new ones), advancing by 10 per grade from grade 1
through grade 9. The grade "10-11" PDF is byte-for-byte identical in content to
grade 9's paper (same 20 questions) -- there was no separate grade 10 or grade
11 paper supplied, so both the grade-10 and grade-11 sessions are imported with
that same shared set. Flag this to the client if a distinct paper exists that
wasn't provided.

Some questions are pure grammar/word problems that appear in only ONE
language line in the PDF and are otherwise identical across uz/en/ru; most
carry all three languages explicitly and are stored in text_uz/text_en/text_ru
respectively (unlike the English-subject import, this content is genuinely
trilingual). Several questions are unanswerable as plain text (diagrams,
figures, stacked equations) -- those carry an image (see _math_images_data.py)
attached to the Question.image field. correct_option is left blank for every
question -- fill it in via the admin Test Manager after import.

Usage:
    python manage.py import_math_questions --list
    python manage.py import_math_questions --sub-olympiad-id=<id> --dry-run
    python manage.py import_math_questions --sub-olympiad-id=<id>
"""
import base64
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from core.models import SubOlympiad, SubOlympiadGrade, Test, Question
from .._math_images_data import MATH_IMAGES


def _q(uz, en, ru, options, image=None):
    return {'uz': uz, 'en': en, 'ru': ru, 'options': options, 'image': image}


# The shared 100-question bank, in bank order. Grade N's paper is
# QUESTION_POOL[(N-1)*10 : (N-1)*10 + 20] for N in 1..9; grades 10 and 11 both
# reuse the same window as grade 9 (see module docstring).
QUESTION_POOL = [
    _q("Yig'indini toping: 387+128", "Find the sum: 387+128", "Найдите сумму: 387+128",
       [('A', '515'), ('B', '514'), ('C', '415'), ('D', '525')]),
    _q("Ayirmani toping: 100-63", "Find the difference: 100-63", "Найдите разность: 100-63",
       [('A', '27'), ('B', '37'), ('C', '47'), ('D', '17')]),
    _q("Ketma-ketlikdagi keyingi sonni toping? 7 12 17 22 27 ____",
       "Find the next number in sequence? 7 12 17 22 27 ____",
       "Найдите следующее число в последовательности? 7 12 17 22 27 ____",
       [('A', '30'), ('B', '31'), ('C', '32'), ('D', '42')]),
    _q("N ning qiymatini toping?", "Find the value of N?", "Найдите значение N?",
       [('A', '30'), ('B', '32'), ('C', '20'), ('D', '24')], image='elephant_n'),
    _q("Hisoblang: 1+2+3+4+5+6+7+8+9+10+11+12", "Calculate: 1+2+3+4+5+6+7+8+9+10+11+12",
       "Вычислите: 1+2+3+4+5+6+7+8+9+10+11+12",
       [('A', '65'), ('B', '74'), ('C', '76'), ('D', '78')]),
    _q("8 va 15 ning ko'paytmasini toping?", "Find the product of 8 and 15?",
       "Найдите произведение чисел 8 и 15?",
       [('A', '23'), ('B', '120'), ('C', '60'), ('D', '80')]),
    _q("Hisoblang: 124+362-24-62", "Calculate: 124+362-24-62", "Вычислите: 124+362-24-62",
       [('A', '400'), ('B', '390'), ('C', '420'), ('D', '415')]),
    _q("Fermada 17 ta quyonlar bor. Ularning jami panjalari sonini toping?",
       "There are 17 rabbits in the farm. Find the total number of their legs?",
       "На ферме 17 кроликов. Найдите общее количество лапы?",
       [('A', '34'), ('B', '68'), ('C', '72'), ('D', '38')]),
    _q("Ifodaning qiymatini toping? (12+16):4-1", "Find the value of expression? (12+16):4-1",
       "Найдите значение выражения? (12+16):4-1",
       [('A', '7'), ('B', '6'), ('C', '8'), ('D', '5')]),
    _q("Ertaga haftaning Payshanba kuni bo'lsa, kecha haftaning qaysi kuni bo'lgan?",
       "If tomorrow is Thursday, what day of the week was yesterday?",
       "Если завтра Четверг, какой день недели был вчера?",
       [('A', 'Dushanba-Monday-Понедельник'), ('B', 'Seshanba-Tuesday-Вторник'),
        ('C', 'Chorshanba-Wednesday-Среда'), ('D', 'Yakshanba-Sunday-Воскресенье')]),
    # 11-20
    _q("Ayirmani hisoblang: 1000-499", "Calculate the difference: 1000-499",
       "Найдите разность: 1000-499",
       [('A', '401'), ('B', '701'), ('C', '601'), ('D', '501')]),
    _q("Do'konda 7 ta quti bor. Har bir qutida 15 tadan olma bo'lsa, jami olmalar sonini toping?",
       "There are 7 boxes in the shop. If there are 15 apples in each box, find the number of total apples?",
       "В магазине 7 коробок. В каждой коробке по 15 яблок. Найдите общее количество яблок?",
       [('A', '105'), ('B', '22'), ('C', '100'), ('D', '95')]),
    _q("Yulduzcha amalining natijasini toping? 6 ⭐ 2 = ?",
       "Find the result of the star operation? 6 ⭐ 2 = ?",
       "Найдите результат операции со звездой? 6 ⭐ 2 = ?",
       [('A', '84'), ('B', '12'), ('C', '86'), ('D', '48')], image='star_table'),
    _q("4, 0, 5, 1 raqamlaridan foydalangan holda qanday eng kichik 3 xonali sonni hosil qilish mumkin?",
       "By using digits 4, 0, 5, 1 which smallest 3-digit number is it possible to create?",
       "Используя цифры 4, 0, 5, 1 какое наименьшее 3-х значное число можно составить?",
       [('A', '401'), ('B', '405'), ('C', '014'), ('D', '104')]),
    _q("Sinfda 25 nafar o'quvchi bor edi. O'quv yili boshida 6 nafar yangi o'quvchi kelib qo'shildi, o'quv yili oxirida 4 nafar o'quvchi ketdi. Sinfda necha nafar o'quvchi qoldi?",
       "There were 25 students in the class. At the beginning of the school year 6 new students joined, at the end of the school year 4 students left. How many students are left in the class?",
       "В классе были 25 учеников. В начале учебного года добавились 6 учеников, в конце учебного года покинули 4 ученика. Сколько учеников осталось в классе?",
       [('A', '27'), ('B', '28'), ('C', '29'), ('D', '26')]),
    _q("To'g'ri to'rtburchakning tomonlari 5 sm va 7 sm bo'lsa, uning perimetrini toping?",
       "If sides of a rectangle are 5 cm and 7 cm, find it's perimeter?",
       "Стороны прямоугольника 5 см и 7 см. Найдите периметр прямоугольника?",
       [('A', '12'), ('B', '24'), ('C', '22'), ('D', '26')]),
    _q("X ning qiymatini toping? 30 26 22 X 14", "Find the value of X? 30 26 22 X 14",
       "Найдите значение X? 30 26 22 X 14",
       [('A', '20'), ('B', '19'), ('C', '18'), ('D', '16')]),
    _q("24 quyidagi sonlardan qaysiga qoldiqsiz bo'linadi?",
       "24 is divisible by which of these numbers without remainder?",
       "На какое из данных чисел без остатка делится число 24?",
       [('A', '3'), ('B', '5'), ('C', '7'), ('D', '9')]),
    _q("Yig'indini toping? 32+47+6+8+3", "Find the sum? 32+47+6+8+3", "Найдите сумму? 32+47+6+8+3",
       [('A', '86'), ('B', '96'), ('C', '99'), ('D', '86')]),
    _q("Javobi 10 ga teng bo'lgan misolni belgilang.", "Choose the expression with the result of 10.",
       "Ответ какого выражения равен 10?",
       [('A', '25+5'), ('B', '39-28'), ('C', '44-34'), ('D', '19-11')]),
    # 21-30
    _q("Ketma-ketlikdagi keyingi sonni toping? 204 100 48 22 ___",
       "Find the next number in this sequence? 204 100 48 22 ___",
       "Найдите следующее число в последовательности? 204 100 48 22 ___",
       [('A', '11'), ('B', '9'), ('C', '7'), ('D', '14')]),
    _q("Yig'indini toping? 10+11+12+13+14+15+16+17+18+19+20",
       "Find the sum? 10+11+12+13+14+15+16+17+18+19+20",
       "Найдите сумму? 10+11+12+13+14+15+16+17+18+19+20",
       [('A', '150'), ('B', '170'), ('C', '145'), ('D', '165')]),
    _q("Ayirmani toping? 10000-2994", "Find the difference? 10000-2994", "Найдите разность? 10000-2994",
       [('A', '8006'), ('B', '8996'), ('C', '7006'), ('D', '6006')]),
    _q("Eng katta uch xonali juft sonni toping?", "Find the biggest three-digit even number?",
       "Найдите наибольшее трехзначное четное число?",
       [('A', '999'), ('B', '998'), ('C', '100'), ('D', '102')]),
    _q("Uchburchakning tomonlari 6, 8 va A ga teng. Agar uning perimetri 25 bo'lsa, A ning qiymatini toping?",
       "Sides of the triangle are 6, 8 and A. If the perimeter is 25, find the value of A?",
       "Стороны треугольника 6, 8 и А. Периметр равен 25. Найдите значение А?",
       [('A', '10'), ('B', '11'), ('C', '9'), ('D', '12')]),
    _q("To'g'ri to'rtburchakning tomonlari 15 va 16 ga teng. Uning perimetri yarmini toping?",
       "Sides of rectangle are 15 and 16. Find half of the perimeter?",
       "Стороны прямоугольника 15 и 16. Найдите половину периметра?",
       [('A', '31'), ('B', '62'), ('C', '30'), ('D', '64')]),
    _q("E ning qiymatini toping?", "Find the value of E?", "Найдите значение Е?",
       [('A', '8'), ('B', '4'), ('C', '12'), ('D', '10')], image='elephant_e_chain'),
    _q("Eng katta toq sonni tanlang?", "Choose the biggest odd number?",
       "Выберите наибольшее нечетное число?",
       [('A', '94'), ('B', '91'), ('C', '88'), ('D', '89')]),
    _q("Yulduzchaning qiymatini toping?", "Find the value of the star?", "Найдите значение звезды?",
       [('A', '5'), ('B', '4'), ('C', '8'), ('D', '7')], image='triangle_diamond_star'),
    _q("Qoldiqni toping? 1397:5", "Find the remainder? 1397:5", "Найдите остаток? 1397:5",
       [('A', '2'), ('B', '7'), ('C', '3'), ('D', '4')]),
    # 31-40
    _q("Yig'indini toping? 1+2+3+…+22+23+24", "Find the sum? 1+2+3+…+22+23+24",
       "Найдите сумму? 1+2+3+…+22+23+24",
       [('A', '300'), ('B', '600'), ('C', '75'), ('D', '225')]),
    _q("25 ning natural bo'luvchilari sonini toping?", "Find the number of natural divisors of 25?",
       "Найдите количество натуральных делителей числа 25?",
       [('A', '4'), ('B', '5'), ('C', '3'), ('D', '6')]),
    _q("100 ga eng yaqin sonni belgilang?", "Choose the closest number to 100?",
       "Найдите ближайшее число к 100?",
       [('A', '124'), ('B', '77'), ('C', '94'), ('D', '105')]),
    _q("Maktabda 1025 nafar o'quvchi bor. Teatrga o'quvchilarning 5 dan 2 qismi chipta sotib oldi. Jami nechta chipta sotilgan?",
       "There are 1025 students at school. Two fifths of all students bought tickets for the theatre. How many tickets were sold in total?",
       "В школе 1025 учеников. Два пятых учеников купили билеты в театр. Сколько билетов было продано?",
       [('A', '410'), ('B', '205'), ('C', '815'), ('D', '102')]),
    _q("Ketma-ketlikdagi keyingi 2 ta son yig'indisini toping? 105 100 95 90 85 ___ ____",
       "Find the sum of the next 2 numbers in this sequence? 105 100 95 90 85 ___ ____",
       "Найдите сумму следующих 2 чисел в последовательности? 105 100 95 90 85 ___ ____",
       [('A', '165'), ('B', '170'), ('C', '155'), ('D', '150')]),
    _q("124 ning eng katta natural bo'luvchisini toping?", "Find the biggest natural divisor of 124?",
       "Найдите наибольший натуральный делитель числа 124?",
       [('A', '4'), ('B', '124'), ('C', '62'), ('D', '24')]),
    _q("1 m 24 sm = ? mm", "1 m 24 cm = ? mm", "1 м 24 см = ? мм",
       [('A', '1240'), ('B', '124'), ('C', '1024'), ('D', '1204')]),
    _q("Toshkent shahridan Samarqandga 2 xil yo'l bilan, Samarqanddan Buxoroga 4 xil yo'l bilan borish mumkin. Toshkentdan Buxoro shahriga Samarqand orqali necha xil yo'llar bilan borish mumkin?",
       "There are 2 different routes from Tashkent to Samarkand, and 4 different routes from Samarkand to Bukhara. How many different routes are there from Tashkent to Bukhara through Samarkand?",
       "Из Ташкента до Самарканда 2 разные дороги. Из Самарканда до Бухары 4 разные дороги. Сколькими разными путями можно добраться из Ташкента до Бухары через Самарканд?",
       [('A', '6'), ('B', '4'), ('C', '8'), ('D', '2')]),
    _q("122 va 11 ning ko'paytmasini toping?", "Find the product of 122 and 11?",
       "Найдите произведение чисел 122 и 11?",
       [('A', '1342'), ('B', '121'), ('C', '1320'), ('D', '1240')]),
    _q("Kvadratning tomonlari 7 ga teng bo'lsa, uning yuzasini toping?",
       "If the side of a square is 7, find it's area?",
       "Если сторона квадрата равна 7, найдите его площадь?",
       [('A', '28'), ('B', '49'), ('C', '14'), ('D', '24')]),
    # 41-50
    _q("Hisoblang: 580-579+578-577+…+4-3+2-1", "Calculate: 580-579+578-577+…+4-3+2-1",
       "Вычислите: 580-579+578-577+…+4-3+2-1",
       [('A', '300'), ('B', '290'), ('C', '280'), ('D', '270')]),
    _q("Ketma-ketlikning 99-hadini toping? 4 7 10 13 ….", "Find the 99th term of the given sequence? 4 7 10 13 ….",
       "Найдите 99-е число в последовательности? 4 7 10 13 ….",
       [('A', '304'), ('B', '301'), ('C', '124'), ('D', '298')]),
    _q("9-qatordagi sonlar yig'indisini toping?", "Find the sum of numbers in the 9th row?",
       "Найдите сумму всех чисел в 9-м ряду?",
       [('A', '90'), ('B', '81'), ('C', '55'), ('D', '100')], image='pascal_triangle'),
    _q("196 va 324 sonlarining o'rta arifmetik qiymatini toping?", "Find the average of 196 and 324?",
       "Найдите среднее арифметическое чисел 196 и 324?",
       [('A', '260'), ('B', '250'), ('C', '360'), ('D', '224')]),
    _q("141 va 999 sonlar orasida nechta butun son bor?", "How many whole numbers are there between 141 and 999?",
       "Найдите количество целых чисел между 141 и 999?",
       [('A', '858'), ('B', '857'), ('C', '859'), ('D', '860')]),
    _q("Kvadratning yuzasi 256 ga teng bo'lsa, uning tomonini toping?",
       "If the area of a square is 256, find it's side?",
       "Если площадь квадрата 256, найдите его сторону?",
       [('A', '6'), ('B', '26'), ('C', '128'), ('D', '16')]),
    _q("3, 0, 7, 8, 9 raqamlaridan foydalangan holda nechta turli 3 xonali sonlarni hosil qilish mumkin? (Raqamlardan takroran foydalanish mumkin emas)",
       "By using digits 3, 0, 7, 8, 9 how many different 3-digit numbers is it possible to make? (Digits cannot be used repeatedly)",
       "Используя цифры 3, 0, 7, 8, 9 сколько разных трехзначных чисел можно составить? (Цифры повторно использовать нельзя)",
       [('A', '12'), ('B', '48'), ('C', '36'), ('D', '24')]),
    _q("Oxirgi raqamni toping? 2³⁷", "Find the last digit? 2³⁷", "Найдите последнюю цифру? 2³⁷",
       [('A', '2'), ('B', '4'), ('C', '8'), ('D', '6')], image='two_37'),
    _q("Ayirmani toping: 10000-2999", "Find the difference: 10000-2999", "Найдите разность: 10000-2999",
       [('A', '7001'), ('B', '8001'), ('C', '7901'), ('D', '6001')]),
    _q("To'g'ri to'rtburchakning yuzasi 56 ga, bo'yi 7 ga teng. Uning enini toping?",
       "The area of the rectangle is 56, the height is 7. Find it's length?",
       "Площадь прямоугольника 56, высота 7. Найдите его ширину?",
       [('A', '21'), ('B', '8'), ('C', '5'), ('D', '4')]),
    # 51-60
    _q("Qanday sonning 30% i 36 ning 25% iga teng?", "What number's 30% is equal to 25% of 36?",
       "30% какого числа равно 25% от числа 36?",
       [('A', '30'), ('B', '90'), ('C', '18'), ('D', '45')]),
    _q("N ning qiymatini toping?", "Find the value of N?", "Найдите значение N?",
       [('A', '18'), ('B', '8'), ('C', '13'), ('D', '7')], image='cloud_chain_n'),
    _q("Hisoblang: 1²+2²+3²+…+20²", "Calculate: 1²+2²+3²+…+20²",
       "Вычислите: 1²+2²+3²+…+20²",
       [('A', '210'), ('B', '44100'), ('C', '986'), ('D', '2870')], image='sum_of_squares'),
    _q("1200 ning natural bo'luvchilari sonini toping?", "Find the number of natural divisors of 1200?",
       "Найдите количество натуральных делителей числа 1200?",
       [('A', '14'), ('B', '30'), ('C', '24'), ('D', '8')]),
    _q("Yig'indini hisoblang? 1+2+3+4+…+798+799+800", "Calculate the sum? 1+2+3+4+…+798+799+800",
       "Найдите сумму? 1+2+3+4+…+798+799+800",
       [('A', '320400'), ('B', '124500'), ('C', '640800'), ('D', '1240')]),
    _q("Bugun haftaning Dushanba kuni bo'lsa, 999999 kundan keyin haftaning qaysi kuni bo'ladi?",
       "If today is Monday, what day of the week will it be after 999999 days?",
       "Если сегодня Понедельник, какой день недели будет через 999999 дней?",
       [('A', 'Dushanba-Monday-Понедельник'), ('B', 'Seshanba-Tuesday-Вторник'),
        ('C', 'Chorshanba-Wednesday-Среда'), ('D', 'Payshanba-Thursday-Четверг')]),
    _q("ABC 3-xonali sonni toping?", "Find the value of the 3-digit number ABC?",
       "Найдите значение трехзначного числа ABC?",
       [('A', '123'), ('B', '129'), ('C', '149'), ('D', '238')], image='aaa_bbb_ccc'),
    _q("Ketma-ketlikdagi keyingi sonni toping? 7 15 31 63 ____",
       "Find the next number in the given sequence? 7 15 31 63 ____",
       "Найдите следующее число в последовательности? 7 15 31 63 ____",
       [('A', '96'), ('B', '120'), ('C', '126'), ('D', '127')]),
    _q("Ko'paytmani toping? 38/45 × 55/95", "Find the product? 38/45 × 55/95",
       "Найдите произведение? 38/45 × 55/95",
       [('A', '2090/45'), ('B', '22/45'), ('C', '22/14'), ('D', '55/45')], image='fraction_mult'),
    _q("Noma'lum sonni toping? (3X+10):2-126= -103", "Find the unknown number? (3X+10):2-126= -103",
       "Найдите неизвестное число? (3X+10):2-126= -103",
       [('A', '-11'), ('B', '11'), ('C', '12'), ('D', '36')]),
    # 61-70
    _q("Shaklning yuzasini toping?", "Find the area of the given shape?", "Найдите площадь фигуры?",
       [('A', '260'), ('B', '300'), ('C', '320'), ('D', '90')], image='area_shape'),
    _q("180 ning natural bo'luvchilari yig'indisini toping?", "Find the sum of natural divisors of 180?",
       "Найдите сумму натуральных делителей числа 180?",
       [('A', '546'), ('B', '0'), ('C', '181'), ('D', '76')]),
    _q("5, 0, 7, 8, 4, 2 raqamlaridan foydalangan holda jami nechta turli 3-xonali sonlarni hosil qilish mumkin? (raqamlardan takroran foydalanish mumkin)",
       "By using digits 5, 0, 7, 8, 4, 2 in total how many different 3-digit numbers is it possible to make? (Digits can be used repeatedly)",
       "Используя цифры 5, 0, 7, 8, 4, 2 сколько разных трехзначных чисел можно составить? (Цифры можно использовать повторно)",
       [('A', '170'), ('B', '100'), ('C', '24'), ('D', '180')]),
    _q("Sonlarning eng kichik umumiy karralisini toping: 14; 24; 46; 90?",
       "Find the least common multiple of the numbers: 14; 24; 46; 90?",
       "Найдите наименьшее общее кратное чисел: 14; 24; 46; 90?",
       [('A', '31080'), ('B', '57960'), ('C', '920'), ('D', '1080')]),
    _q("Ifodaning qiymatini toping?", "Find the value of the expression?", "Найдите значение выражения?",
       [('A', '147/85'), ('B', '-294/170'), ('C', '1'), ('D', '-3')], image='fraction_division'),
    _q("20-qatorda o'rtada qaysi son joylashgan?", "What number will be in the middle of the 20th row?",
       "Какое число будет в середине 20-го ряда?",
       [('A', '369'), ('B', '180'), ('C', '381'), ('D', '124')], image='spiral_numbers'),
    _q("Kubning hajmi 1331 ga teng bo'lsa, uning balandligini toping?",
       "If the volume of the cube is 1331, find it's height?",
       "Если объем куба 1331, найдите его высоту?",
       [('A', '12'), ('B', '21'), ('C', '11'), ('D', '7')]),
    _q("To'g'ri burchakli uchburchakning katetlari 8 sm va 12 sm bo'lsa, uning yuzasini toping?",
       "If the legs of a right-angled triangle are 8 cm and 12 cm, find it's area?",
       "Если катеты прямоугольного треугольника равны 8 см и 12 см, найдите его площадь?",
       [('A', '48'), ('B', '96'), ('C', '64'), ('D', '20')]),
    _q("Sam 12 yoshda, akasi undan 3 yosh katta. 10 yildan so'ng ularning yoshlari orasidagi farq nechaga teng bo'ladi?",
       "Sam is 12 years old, his brother is 3 years older than him. After 10 years, what will the difference between their ages be?",
       "Саму 12 лет, брат старше его на 3 года. Через 10 лет разница между их возрастами будет составлять сколько лет?",
       [('A', '13'), ('B', '6'), ('C', '3'), ('D', '12')]),
    _q("Hisoblang: 10+20+30+40+……+1990+2000", "Calculate: 10+20+30+40+……+1990+2000",
       "Вычислите: 10+20+30+40+……+1990+2000",
       [('A', '201000'), ('B', '20100'), ('C', '21000'), ('D', '40100')]),
    # 71-80
    _q("Oxirgi raqamni toping?", "Find the last digit?", "Найдите последнюю цифру?",
       [('A', '8'), ('B', '4'), ('C', '2'), ('D', '6')], image='num_1028_9999'),
    _q("4 nafar xodim ishni 7 kunda yakunlaydi. 14 nafar xodim shu ishni necha kunda yakunlaydi?",
       "4 workers finish the job in 7 days. How many days does it take 14 workers to finish the same job?",
       "4 сотрудника выполняют работу за 7 дней. За сколько дней 14 сотрудников закончат ту же работу?",
       [('A', '3'), ('B', '2'), ('C', '4'), ('D', '1')]),
    _q("3003 ning barcha natural bo'luvchilari sonini toping?", "Find the number of all natural divisors of 3003?",
       "Найдите количество всех натуральных делителей числа 3003?",
       [('A', '8'), ('B', '10'), ('C', '12'), ('D', '16')]),
    _q("Hisoblang:", "Calculate:", "Вычислите:",
       [('A', '64'), ('B', '4'), ('C', '16'), ('D', '256')], image='expr_4_3_2_over_16'),
    _q("1 dan 500 gacha bo'lgan ketma-ket natural sonlar ko'paytmasi nechta 0 bilan tugaydi?",
       "With how many 0s does the product of all consecutive natural numbers from 1 to 500 end?",
       "Сколькими нулями заканчивается произведение последовательных чисел от 1 до 500?",
       [('A', '20'), ('B', '50'), ('C', '124'), ('D', '48')]),
    _q("X ning eng katta qiymatini toping? (X+5)(12-2X)(X-4)=0", "Find the biggest value of X? (X+5)(12-2X)(X-4)=0",
       "Найдите наибольшее значение Х? (X+5)(12-2X)(X-4)=0",
       [('A', '6'), ('B', '4'), ('C', '12'), ('D', '5')]),
    _q("Do'konda ruchkalar bor edi. Birinchi kuni ruchkalarning yarmi va yana 2 ta ruchka, ikkinchi kuni qolgan ruchkalarning yarmi va yana 1 ta ruchka, uchinchi kuni qolgan ruchkalarning 4 dan 1 qismi sotildi. Natijada do'konda 21 ta ruchka qoldi. Do'konda jami nechta ruchka bo'lgan?",
       "There were pens in the shop. On the first day half of all pens and 2 more pens were sold, on the second day half of the remaining pens and 1 more pen were sold, on the third day one fourth of the remaining pens were sold. 21 pens were then left in the shop. How many pens were in the shop at the beginning?",
       "В магазине были ручки. В первый день продали половину ручек и ещё 2 ручки. Во второй день продали половину оставшихся ручек и ещё 1 ручку. В третий день продали одну четвертую часть оставшихся ручек. В результате в магазине осталась 21 ручка. Сколько всего ручек было в магазине?",
       [('A', '80'), ('B', '100'), ('C', '120'), ('D', '140')]),
    _q("Soddalashtiring:", "Simplify:", "Упростите:",
       [('A', '2a'), ('B', '3a+1'), ('C', '4'), ('D', '4/a')], image='simplify_expr'),
    _q("1000-shaklda nechta kvadrat mavjud?", "How many squares are there in the 1000th shape?",
       "Найдите количество квадратов в 1000-й фигуре?",
       [('A', '1002'), ('B', '5050'), ('C', '50050'), ('D', '500500')], image='figure_squares'),
    _q("Kvadrat tenglamani yeching? x²-3x+2=0", "Solve the quadratic equation? x²-3x+2=0",
       "Решите квадратное уравнение? x²-3x+2=0",
       [('A', '1;2'), ('B', '-1;2'), ('C', '-1;-2'), ('D', '3;1')], image='quadratic_eq'),
    # 81-90
    _q("Doiraning yuzasi 176,625 bo'lsa, uning diametri uzunligini toping?",
       "If the area of a circle is 176.625, find it's diameter?",
       "Если площадь круга равна 176,625, найдите его диаметр?",
       [('A', '8.5'), ('B', '7.5'), ('C', '15'), ('D', '6.5')]),
    _q("Teng tomonli uchburchakning tomoni 4 ga teng bo'lsa, uning yuzasini toping?",
       "If the side of an equilateral triangle is 4, find it's area?",
       "Сторона равностороннего треугольника равна 4, найдите его площадь?",
       [('A', '16'), ('B', '12'), ('C', '4√3'), ('D', '2√3')]),
    _q("A ning birlar xonasidagi raqamni toping? A = 1·7·13·...·43·49",
       "Find the unit's digit of A? A = 1·7·13·...·43·49",
       "Найдите цифру единиц числа А? A = 1·7·13·...·43·49",
       [('A', '1'), ('B', '5'), ('C', '3'), ('D', '7')], image='A_product_seq'),
    _q("2026 ning natural bo'luvchilari yig'indisini toping?", "Find the sum of natural divisors of 2026?",
       "Найдите сумму натуральных делителей числа 2026?",
       [('A', '2027'), ('B', '3042'), ('C', '3041'), ('D', '2988')]),
    _q("Teng tomonli oktagonning tashqi burchagini toping?", "Find the exterior angle of a regular octagon?",
       "Найдите внешний угол правильного восьмиугольника?",
       [('A', '135'), ('B', '225'), ('C', '45'), ('D', '35')]),
    _q("y ni toping?", "Find y?", "Найдите y?",
       [('A', '6'), ('B', '4'), ('C', '2'), ('D', '-3')], image='system_2x_y'),
    _q("X ni toping?", "Find X?", "Найдите Х?",
       [('A', '48'), ('B', '18'), ('C', '44'), ('D', '13')], image='angle_52_2x12'),
    _q("Har bir qator, ustun va diagonallar yig'indisi teng bo'lsa, x ni toping?",
       "If the sum of numbers in each row, column and diagonal is the same, find x?",
       "Если сумма чисел в каждом ряду, столбце и диагонали одинакова, найдите значение х?",
       [('A', '2'), ('B', '3'), ('C', '4'), ('D', '5')], image='magic_square'),
    _q("Hisoblang:", "Calculate:", "Вычислите:",
       [('A', '1'), ('B', '32'), ('C', '261'), ('D', '271')], image='big_fraction_expr'),
    _q("Eng katta uch xonali tub sonni belgilang:", "Choose the biggest three-digit prime number:",
       "Выберите наибольшее трехзначное простое число:",
       [('A', '997'), ('B', '991'), ('C', '999'), ('D', '897')]),
    # 91-100
    _q("Y=4X+12 funksiya grafigining koordinata o'qlari bilan kesishish nuqtalarini toping?",
       "Find the coordinates of the intersection points of the graph of Y=4X+12 with the coordinate axes?",
       "Найдите координаты точек пересечения графика функции Y=4X+12 с осями координат?",
       [('A', '(12;0); (-3;0)'), ('B', '(7;9)'), ('C', '(0;12); (-3;0)'), ('D', '(0;12); (0;-3)')]),
    _q("X ning mumkin bo'lgan eng kichik butun qiymatini toping?",
       "Find the smallest possible whole value of X?",
       "Найдите наименьшее возможное целое значение числа Х?",
       [('A', '-2'), ('B', '-1'), ('C', '0'), ('D', '1')], image='inequality_3x'),
    _q("1 dan 2026 gacha bo'lgan ketma-ket natural sonlar ko'paytmasi nechta 0 bilan tugaydi?",
       "How many 0s are there at the end of the product of consecutive natural numbers from 1 to 2026?",
       "Сколькими нулями заканчивается произведение последовательных чисел от 1 до 2026?",
       [('A', '404'), ('B', '504'), ('C', '505'), ('D', '55')]),
    _q("A ni toping?", "Find A?", "Найдите A?",
       [('A', '2009'), ('B', '1005'), ('C', '1004'), ('D', '1001')], image='alternating_sum'),
    _q("N ni toping? 1+2+3+4+…+N=499500", "Find N? 1+2+3+4+…+N=499500", "Найдите N? 1+2+3+4+…+N=499500",
       [('A', '800'), ('B', '720'), ('C', '999'), ('D', '1999')]),
    _q("Hisoblang:", "Calculate:", "Вычислите:",
       [('A', '99'), ('B', '100'), ('C', '2476'), ('D', '2475')], image='nested_fraction_sum'),
    _q("To'g'ri to'rtburchakning yuzasi (xy+3x-2y-6), bo'yi (y+3) bo'lsa, uning enini toping?",
       "If the area of a rectangle is (xy+3x-2y-6), and the height is (y+3), find it's length?",
       "Площадь прямоугольника (xy+3x-2y-6), высота (y+3), найдите его ширину?",
       [('A', 'X-2'), ('B', 'X+2'), ('C', '2X-1'), ('D', '2-X')]),
    _q("Hisoblang:", "Calculate:", "Вычислите:",
       [('A', '8'), ('B', '-7'), ('C', '7'), ('D', '7.125')], image='exponent_expr_49'),
    _q("To'g'ri burchakli uchburchakning gipotenuzasi 13 ga, kateti 5 ga teng bo'lsa, uning yuzasini toping?",
       "If the hypotenuse of a right-angled triangle is 13, and a leg is 5, find the area of the triangle?",
       "Гипотенуза прямоугольного треугольника равна 13, катет равен 5. Найдите площадь треугольника?",
       [('A', '65'), ('B', '30'), ('C', '60'), ('D', '12')]),
    _q("X ni toping?", "Find X?", "Найдите Х?",
       [('A', '9'), ('B', '7'), ('C', '6'), ('D', '4')], image='three_var_system'),
]

assert len(QUESTION_POOL) == 100, f"expected 100 pool questions, got {len(QUESTION_POOL)}"

# grade -> list of 20 QUESTION_POOL items (0-indexed slice)
GRADE_WINDOWS = {}
for grade in range(1, 10):
    start = (grade - 1) * 10
    GRADE_WINDOWS[grade] = QUESTION_POOL[start:start + 20]
# No separate grade 10/11 paper was supplied -- the "Grade 10-11" PDF is
# identical in content to grade 9's paper, so both sessions get that window.
GRADE_WINDOWS[10] = GRADE_WINDOWS[9]
GRADE_WINDOWS[11] = GRADE_WINDOWS[9]


class Command(BaseCommand):
    help = (
        "One-off import of the IRN Republic Olympiad 2026 Math test questions "
        "(grades 1-11) for a given SubOlympiad. Correct answers are left blank -- "
        "fill them in via the admin Test Manager after import."
    )

    def add_arguments(self, parser):
        parser.add_argument('--sub-olympiad-id', type=int, default=None,
                             help='SubOlympiad id to import into (e.g. the "МОСК математика" subject).')
        parser.add_argument('--list', action='store_true',
                             help='List candidate SubOlympiads (title containing math-like keywords) and exit.')
        parser.add_argument('--overwrite', action='store_true',
                             help="Delete a grade's existing questions before importing (default: skip grades that already have questions).")
        parser.add_argument('--dry-run', action='store_true',
                             help='Preview what would be created without writing to the database.')

    def handle(self, *args, **options):
        if options['list']:
            subs = SubOlympiad.objects.filter(
                Q(title_ru__icontains='матем') | Q(title_en__icontains='math') | Q(title_uz__icontains='matematik')
            ).select_related('olympiad')
            if not subs:
                self.stdout.write('No matching SubOlympiad found.')
                return
            for s in subs:
                self.stdout.write(f"id={s.id}  \"{s.title_ru or s.title_en or s.title_uz}\"  (olympiad: {s.olympiad.title_ru}, id={s.olympiad_id})")
            return

        sub_id = options.get('sub_olympiad_id')
        if not sub_id:
            raise CommandError('Pass --sub-olympiad-id=<id> (use --list to find it first).')

        try:
            sub = SubOlympiad.objects.get(id=sub_id)
        except SubOlympiad.DoesNotExist:
            raise CommandError(f'No SubOlympiad with id={sub_id}')

        dry = options['dry_run']
        overwrite = options['overwrite']

        for grade in range(1, 12):
            questions = GRADE_WINDOWS[grade]
            try:
                gs = SubOlympiadGrade.objects.get(sub_olympiad=sub, grade=str(grade))
            except SubOlympiadGrade.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'Grade {grade}: no SubOlympiadGrade session found for this subject, skipping.'))
                continue

            try:
                test = gs.test
            except Test.DoesNotExist:
                test = None

            if test and test.questions.exists():
                if not overwrite:
                    self.stdout.write(self.style.WARNING(
                        f'Grade {grade}: test already has {test.questions.count()} questions, skipping (pass --overwrite to replace).'
                    ))
                    continue
                if not dry:
                    test.questions.all().delete()

            if dry:
                verb = 'replace' if (test and overwrite) else 'create'
                self.stdout.write(f'Grade {grade}: would {verb} test and import {len(questions)} questions.')
                continue

            if not test:
                test = Test.objects.create(sub_olympiad_grade=gs, title=f"{sub.title_ru or sub.title_en} ({grade} кл.)")

            created = 0
            for q in questions:
                question = Question(
                    test=test,
                    text_uz=q['uz'], text_en=q['en'], text_ru=q['ru'],
                    options=[{'id': opt_id, 'text': opt_text} for opt_id, opt_text in q['options']],
                    correct_option='',
                )
                if q['image']:
                    ext, b64 = MATH_IMAGES[q['image']]
                    question.image.save(f"{q['image']}.{ext}", ContentFile(base64.b64decode(b64)), save=False)
                question.save()
                created += 1
            self.stdout.write(self.style.SUCCESS(f'Grade {grade}: imported {created} questions (test id={test.id}).'))
