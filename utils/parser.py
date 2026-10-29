import re
from typing import Optional

def extract_episode_number(text: Optional[str]) -> Optional[int]:
    """
    Video caption yoki fayl nomidan epizod raqamini aniqlaydi.
    Masalan:
      "1-qism" -> 1
      "Naruto 25 - qism" -> 25
      "Episode 12" -> 12
      "14 ep" -> 14
      "ep. 03" -> 3
      "5-epizod" -> 5
      "Qora Klever 170" -> 170
    """
    if not text:
        return None

    cleaned = text.strip()

    # Pattern 1: Raqam + qism / ep / epizod / seriya (e.g. "12-qism", "12 qism", "12ep", "12 seriya")
    match = re.search(r'(\d+)\s*(?:-?\s*(?:qism|ep|epizod|seriya|серия|выпуск))\b', cleaned, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass

    # Pattern 2: qism / ep / epizod / seriya + Raqam (e.g. "Episode 12", "qism 12", "ep. 12", "#12")
    match = re.search(r'(?:qism|ep|epizod|episode|серия|#)\s*[:.-]?\s*(\d+)\b', cleaned, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass

    # Pattern 3: "12 / 170" yoki "12/170"
    match = re.search(r'\b(\d+)\s*/\s*\d+\b', cleaned)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass

    # Pattern 4: Qator oxiridagi yoki alohida ajralgan raqam (e.g. "Qora Klever 05")
    numbers = re.findall(r'\b(\d+)\b', cleaned)
    if numbers:
        # Eng oxirgi mos keladigan raqamni olish (odatda oxirida qism bo'ladi, masalan: "Naruto Shippuden 2007 15" -> 15)
        # Agar raqam 1900-2099 oralig'ida bo'lsa va undan boshqa raqam bo'lsa, yil deb hisoblab o'tkazib yuboramiz
        for num_str in reversed(numbers):
            val = int(num_str)
            if 1950 <= val <= 2050 and len(numbers) > 1:
                continue
            return val

    return None

