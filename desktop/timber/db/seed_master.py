"""Client's master data — suppliers, factories and bank accounts.

Bundled with the app so a FRESH install comes up ready to trade: no typing
in 120 names by hand. Transcribed from the client's own lists.

Every name is stored in BOTH languages: ``(english, urdu)``. The app shows
whichever matches the user's language (see ``BilingualName``). The English
factory spellings follow the client's own (from the party list); supplier
and account English names are transliterations — review and correct freely
in the Master Data / Bank Accounts pages.

Safety: :func:`ensure_master_data` only seeds a table that is completely
empty. It never re-adds a party or account the client has deliberately
deleted, and never creates duplicates.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from timber.db.models import BankAccount, Party
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

# --- suppliers: (english, urdu) -------------------------------------
SUPPLIERS: list[tuple[str, str]] = [
    ("Khalid Hussain Lashari", "خالد حسین لاشاری"),
    ("M Alam Gharo", "ایم عالم گھارو"),
    ("Khizar Hayat", "خضر حیات"),
    ("Maqbool Ahmed Khanpur", "مقبول احمد خانپور"),
    ("Tanveer Ahmed Bhatta", "تنویر احمد بھٹہ"),
    ("Salman Tando Adam", "سلمان ٹنڈو آدم"),
    ("Rana Younus", "رانا یونس"),
    ("Sangar Khan Lashari", "سینگار خان لاشاری"),
    ("Hamid Raza", "حامد رضا"),
    ("Abdul Qadir Noorpur", "عبدالقادر نور پور"),
    ("Aqib Aslam Tando Allahyar", "عاقب اسلم ٹنڈوالہیار"),
    ("Sahib Khan 90 Mor", "صاحب خان 90موڑ"),
    ("Nasrullah Khan", "نصراللہ خان"),
    ("Raheem Bakhsh", "رحیم بخش"),
    ("Ali Dost Khan", "علی دوست خان"),
    ("Barat Khan Lasbela", "بارات خان لسبیلہ"),
    ("Bahadur Khan Tando Adam", "بہادر خان ٹنڈو آدم"),
    ("Abdul Quddus", "عبدالقدس"),
    ("Amin Khan Ahmedpur", "امین خان احمد پور"),
    ("Saleem Shah Tando", "سلیم شاہ ٹنڈو"),
    ("Jan Muhammad Tando Allahyar", "جان محمد ٹنڈو الہیار"),
    ("M Jaman Khan", "ایم جمن خان"),
    ("Khadim Hussain", "خادم حسین"),
    ("Asghar Hyderabad", "اصغر حیدرآباد"),
    ("Jameel Nooriabad", "جمیل نوری آباد"),
    ("Rehan Jahan Khan", "ریحان جہان خان"),
    ("Ijaz Cheema", "اعجاز چیمہ"),
    ("Shahid Mirpur Khas", "شاہد میر پور خاص"),
    ("Akhtar Ali Jutt", "اختر علی جٹ"),
    ("Imran Tando Allahyar", "عمران ٹنڈو الہیار"),
    ("Shafqat Joiya", "شفقت جوئیہ"),
    ("Kashif Raza Jandanwala", "کاشف رضا جنڈانوالہ"),
    ("Ustad Shafi Sardar Garh", "استاد شفیع سردار گڑھ"),
    ("Hafiz Adeel", "حافظ عدیل"),
    ("Shah Nawaz Tando Adam", "شاہ نواز ٹنڈو آدم"),
    ("Malik Yaseen", "ملک یٰسین"),
    ("Inayatullah Nooriabad", "عنایت اللہ نوری آباد"),
    ("Sher Khan", "شیر خان"),
    ("Alam Sher Mianwali", "عالم شیر میانوالی"),
    ("Yasir Faisalabad", "یاسر فیصل آباد"),
    ("M Danish", "ایم دانش"),
    ("Mubashir Ali Tando Adam", "مبشرعلی ٹنڈو آدم"),
    ("Usman Gambir Adda", "عثمان گیمبر اڈا"),
    ("Asif Baloch Tando Jam", "آصف بلوچ ٹنڈو جام"),
    ("Ehsanullah Danish", "احسان اللہ دانش"),
    ("M Qaiser Jal Magsi", "ایم قیصر جل مگسی"),
    ("Ghulam Muhammad Nooriabad", "غلام محمد نوری آباد"),
    ("Mukhtiar Tando Allahyar", "مختیار ٹنڈو الہیار"),
    ("Nazir Ahmed Tando Jam", "نذیر احمد ٹنڈو جام"),
    ("M Saleh Tando Allahyar", "ایم صالح ٹنڈو الہیار"),
    ("Samar Abbas Magsi", "ثمر عباس مگسی"),
    ("Gulab Khan", "گلاب خان"),
    ("Fayyaz Jamaldin", "فیاض جمال دین"),
    ("Karim Nawaz", "کریم نواز"),
    ("Naeem Hussain Chhang", "نعیم حسین چھانگ"),
    ("Usman Ali Jamt", "عثمان علی جمٹ"),
    ("Mehboob Jamt", "محبوب جمٹ"),
    ("Sharif Pattoki", "شریف پتوکی"),
    ("Ayaz Khan Darya Khan", "ایاز خان دریا خان"),
    ("Mudassar Saleem (Saifullah)", "مدثر سلیم (سیف اللہ)"),
    ("Faisal Shahzad", "فیصل شہزاد"),
    ("Amir Khan Chhang", "امیر خان چھانگ"),
    ("Rasheed Ahmed Akhtar", "رشید احمد اختر"),
    ("Sheraz Faris", "شیراز فارس"),
    ("Shafiq Ahmed Khanpur", "شفیق احمد خانپور"),
    ("Munawar Hyderabad", "منور حیدر آباد"),
    ("Liaquat Hayat Chhang", "لیاقت حیات چھانگ"),
    ("Nasir Mahmood Matli", "ناصر محمود ماتلی"),
    ("Akmal Khan", "اکمل خان"),
    ("Ubaidullah Bhatti", "عبیداللہ بھٹی"),
    ("M Naeem Roda", "ایم نعیم روڈا"),
    ("Umar Farooq Jamt", "عمر فاروق جمٹ"),
    ("Malik Liaquat", "ملک لیاقت"),
    ("Abdul Raheem Khanpur", "عبدالرحیم خانپور"),
    ("Rafiullah Khan", "رفیع اللہ خان"),
    ("Zafar Iqbal Faisalabad", "ظفر اقبال فیصل آباد"),
    ("Haji Sabir Tando Adam", "حاجی صابر ٹنڈو آدم"),
]

# --- factories: (english, urdu) -------------------------------------
FACTORIES: list[tuple[str, str]] = [
    ("Best Board Nooriabad", "بیسٹ بورڈ نوری آباد"),
    ("Khawaja Azhar Butt", "خواجہ اظہر بٹ"),
    ("Pak Tex", "پاک ٹیکس"),
    ("Asia Board Nooriabad", "ایشیاء بورڈ نوری آباد"),
    ("Bilal Ashraf Mills", "بلال اشرف ملز"),
    ("Sadaqat Tactile Mills", "صداقت ٹیکٹائل ملز"),
    ("Ali Traders", "علی ٹریڈرز"),
    ("Kashmir Board Chiniot", "کشمیر بورڈ چنیوٹ"),
    ("Abdullah Zia Ashraf", "عبداللہ ضیاء اشرف"),
    ("Frontier Mill", "فرنٹیئر مل"),
    ("Al Noor MDF Moro Karachi (Sattar Ahmed)", "النور MDF مورو کراچی (ستار احمد)"),
    ("National Silk Mills", "نیشنل سلک ملز"),
    ("Kashmir Board Adda Fazil", "کشمیر بورڈ اڈا فاضل"),
    ("MA Processing Mills", "ایم اے پروسیسنگ ملز"),
    ("Magna Textile Mills 2", "میگنا ٹیکسٹائل ملز 2"),
    ("Al Noor MDF Moro Karachi (Naveed Sattar)", "النور MDF مورو کراچی (نوید ستار)"),
]

# --- bank accounts: (english, urdu) ---------------------------------
# "Cash" is intentionally absent: the app creates and manages that account
# itself (bank_service.cash_account).
BANK_ACCOUNTS: list[tuple[str, str]] = [
    ("Habib Metro W", "حبیب میٹرو W"),
    ("UBL 2464", "یو بی ایل 2464"),
    ("Al Habib ASWS", "الحبیب ASWS"),
    ("Meezan NT", "میزان NT"),
    ("Meezan Abu Bakr", "میزان ابو بکر"),
    ("Faisal 3220", "فیصل 3220"),
    ("UBL-133", "یو بی ایل-133"),
    ("Alfalah 1951", "الفلاح 1951"),
    ("Alfalah CWS", "الفلاح CWS"),
    ("Habib Metro Kashif", "حبیب میٹرو کاشف"),
    ("Meezan (Kashif)", "میزان (Kashif)"),
    ("Meezan (Naveed)", "میزان (Naveed)"),
    ("Meezan 229", "میزان 229"),
    ("Al Habib CWS", "الحبیب CWS"),
    ("UBL (CWS)", "یو بی ایل (CWS)"),
    ("UBL NT", "یو بی ایل NT"),
    ("Meezan 3050", "میزان 3050"),
    ("Cheque", "چیک"),
    ("Naveed Sattar HBL", "نوید ستار HBL"),
    ("Bank Islami (W)", "بنک اسلامی(W)"),
    ("Abu Bakr HBL", "ابو بکر HBL"),
    ("Waqar Tayyab", "وقار طیب"),
    ("UBL (Ibtisam Sattar)", "UBL (ابتسام ستار)"),
    ("Bank Islami (St)", "بنک اسلامی(St)"),
    ("Bank Islami Ibtisam", "بنک اسلامی ابتسام"),
    ("Meezan 3936", "میزان 3936"),
    ("Meezan Ibtisam", "میزان ابتسام"),
]


# Placeholder parties for a truck whose supplier/factory isn't known yet.
# The trade is booked against these, then edited to the real party once it's
# claimed. Always present (re-created if deleted).
UNKNOWN_SUPPLIER = ("Unknown supplier", "نامعلوم بیوپاری")
UNKNOWN_FACTORY = ("Unknown factory", "نامعلوم فیکٹری")


def ensure_unknown_parties(session: Session) -> None:
    """Guarantee the 'Unknown supplier' and 'Unknown factory' placeholders
    exist. Called every startup so they can't be permanently removed."""
    from timber.core import admin_service

    for (en, ur), ptype in (
        (UNKNOWN_SUPPLIER, PARTY_BAPARI),
        (UNKNOWN_FACTORY, PARTY_FACTORY),
    ):
        found = session.scalar(
            select(Party).where(
                or_(Party.name_en == en, Party.name_ur == ur, Party._name.in_((en, ur))),
                Party.party_type == ptype,
            )
        )
        if found is None:
            admin_service.create_party(
                session, name_en=en, name_ur=ur, party_type=ptype
            )


def ensure_master_data(session: Session, force: bool = False) -> dict[str, int]:
    """Ensure the database is usable, and OPTIONALLY seed the client's
    supplier/factory/account master data.

    Always: get-or-creates the app's own "Cash" account (the app needs it).

    Master data (suppliers/factories/bank accounts) is loaded ONLY when
    ``force`` is True or ``config.SEED_MASTER_DATA`` is on — and even then only
    into empty tables (never duplicates, never resurrects deleted rows). It is
    OFF by default now that the live data lives in the shared cloud database, so
    a new PC/exe connects to that instead of loading its own copy. Run
    ``python -m timber.db.seed_master`` once to seed a brand-new cloud DB.
    """
    from timber.core import admin_service, bank_service
    from timber import config

    created = {"suppliers": 0, "factories": 0, "accounts": 0}

    # The Cash account is required for cash payments — always ensure it.
    cash = bank_service.cash_account(session)  # get-or-create "Cash"

    if not (force or config.SEED_MASTER_DATA):
        session.flush()
        return created  # clean install: no client master data auto-loaded

    # Parties: seed only when there is not a single party yet.
    if session.scalar(select(func.count(Party.id))) == 0:
        for en, ur in SUPPLIERS:
            admin_service.create_party(
                session, name_en=en, name_ur=ur, party_type=PARTY_BAPARI
            )
            created["suppliers"] += 1
        for en, ur in FACTORIES:
            admin_service.create_party(
                session, name_en=en, name_ur=ur, party_type=PARTY_FACTORY
            )
            created["factories"] += 1

    # Bank accounts: seed only when nothing but the app's own Cash exists.
    others = session.scalar(
        select(func.count(BankAccount.id)).where(BankAccount.id != cash.id)
    )
    if others == 0:
        for en, ur in BANK_ACCOUNTS:
            bank_service.create_account(
                session, name_en=en, name_ur=ur, opening_balance=0
            )
            created["accounts"] += 1

    session.flush()
    return created


if __name__ == "__main__":
    # One-time seed of the client's master data into the CURRENT database
    # (e.g. a brand-new Supabase project). Idempotent: safe to re-run.
    from timber.db.engine import SessionLocal

    with SessionLocal() as _s:
        _created = ensure_master_data(_s, force=True)
        ensure_unknown_parties(_s)
        _s.commit()
    print("Seeded master data:", _created)
