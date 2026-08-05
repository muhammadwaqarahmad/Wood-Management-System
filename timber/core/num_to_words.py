"""Number → words in English and Urdu, using the South-Asian
lakh/crore system (for amounts on bills and as a typing hint).
"""

from __future__ import annotations

from decimal import Decimal

_EN_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_EN_TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
]

# Urdu words 0..99 (irregular, so a full table).
_UR = [
    "صفر", "ایک", "دو", "تین", "چار", "پانچ", "چھ", "سات", "آٹھ", "نو",
    "دس", "گیارہ", "بارہ", "تیرہ", "چودہ", "پندرہ", "سولہ", "سترہ", "اٹھارہ", "انیس",
    "بیس", "اکیس", "بائیس", "تئیس", "چوبیس", "پچیس", "چھببیس", "ستائیس", "اٹھائیس", "انتیس",
    "تیس", "اکتیس", "بتیس", "تینتیس", "چونتیس", "پینتیس", "چھتیس", "سینتیس", "اڑتیس", "انتالیس",
    "چالیس", "اکتالیس", "بیالیس", "تینتالیس", "چوالیس", "پینتالیس", "چھیالیس", "سینتالیس", "اڑتالیس", "انچاس",
    "پچاس", "اکیاون", "باون", "تریپن", "چون", "پچپن", "چھپن", "ستاون", "اٹھاون", "انسٹھ",
    "ساٹھ", "اکسٹھ", "باسٹھ", "ترسٹھ", "چوسٹھ", "پینسٹھ", "چھیاسٹھ", "سڑسٹھ", "اڑسٹھ", "انہتر",
    "ستر", "اکہتر", "بہتر", "تہتر", "چوہتر", "پچہتر", "چھہتر", "ستہتر", "اٹھہتر", "اناسی",
    "اسی", "اکیاسی", "بیاسی", "تراسی", "چوراسی", "پچاسی", "چھیاسی", "ستاسی", "اٹھاسی", "نواسی",
    "نوے", "اکیانوے", "بانوے", "ترانوے", "چورانوے", "پچانوے", "چھیانوے", "ستانوے", "اٹھانوے", "ننانوے",
]


def _english_int(n: int) -> str:
    if n < 20:
        return _EN_ONES[n]
    if n < 100:
        return _EN_TENS[n // 10] + (f"-{_EN_ONES[n % 10]}" if n % 10 else "")
    if n < 1000:
        return _EN_ONES[n // 100] + " hundred" + (f" {_english_int(n % 100)}" if n % 100 else "")
    if n < 10**5:
        return _english_int(n // 1000) + " thousand" + (f" {_english_int(n % 1000)}" if n % 1000 else "")
    if n < 10**7:
        return _english_int(n // 10**5) + " lakh" + (f" {_english_int(n % 10**5)}" if n % 10**5 else "")
    return _english_int(n // 10**7) + " crore" + (f" {_english_int(n % 10**7)}" if n % 10**7 else "")


def _urdu_int(n: int) -> str:
    if n < 100:
        return _UR[n]
    if n < 1000:
        return _UR[n // 100] + " سو" + (f" {_urdu_int(n % 100)}" if n % 100 else "")
    if n < 10**5:
        return _urdu_int(n // 1000) + " ہزار" + (f" {_urdu_int(n % 1000)}" if n % 1000 else "")
    if n < 10**7:
        return _urdu_int(n // 10**5) + " لاکھ" + (f" {_urdu_int(n % 10**5)}" if n % 10**5 else "")
    return _urdu_int(n // 10**7) + " کروڑ" + (f" {_urdu_int(n % 10**7)}" if n % 10**7 else "")


def to_words(amount, lang: str | None = None) -> str:
    """Money amount → words, e.g. '1,20,000.50' →
    'One lakh twenty thousand rupees and fifty paisa'."""
    if lang is None:
        from timber import i18n

        lang = i18n.get_language()

    value = Decimal(str(amount or 0))
    sign = "-" if value < 0 else ""
    value = abs(value)
    rupees = int(value)
    paisa = int((value - rupees) * 100)

    if lang == "ur":
        words = _urdu_int(rupees) + " روپے"
        if paisa:
            words += f" اور {_urdu_int(paisa)} پیسے"
        return (("منفی " if sign else "") + words)

    words = _english_int(rupees) + " rupees"
    if paisa:
        words += f" and {_english_int(paisa)} paisa"
    words = words[0].upper() + words[1:]
    return (("Minus " if sign else "") + words)
