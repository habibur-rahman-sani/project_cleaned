"""
ইউজারের নিজের API key ডাটাবেজে প্লেইন টেক্সটে রাখা হয় না — Fernet (symmetric
encryption) দিয়ে এনক্রিপ্ট করে রাখা হয়। FERNET_KEY .env-এ না দিলে সার্ভিস
স্টার্টআপেই এরর দিয়ে থেমে যাবে (ভুলে প্লেইন key ডাটাবেজে যাওয়া ঠেকাতে)।
"""
from cryptography.fernet import Fernet
from .config import settings

if settings.fernet_key.startswith("CHANGE_ME"):
    raise RuntimeError(
        "FERNET_KEY সেট করা হয়নি। চালাও: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
        "তারপর ফলাফলটা .env-এর FERNET_KEY-তে বসাও।"
    )

_f = Fernet(settings.fernet_key.encode())


def encrypt(plain: str) -> str:
    return _f.encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    return _f.decrypt(token.encode()).decode()
