"""Customer-facing language: English and Bahasa Malaysia.

Every fixed sentence the backend sends (questions, recap, quote messages) lives here, so a Malay
customer never gets a half-English reply. The model is told which language to use for its own
sentences. Detection and switching are deterministic: the customer can ask for a language, or
simply start writing in one.
"""
import re

LANGS = ("en", "ms")

STRINGS = {
    "en": {
        "ask_address": "What is the address of the property?",
        "ask_address_again": "Is the job at the same address as before ({address})? Reply yes, or send the new address.",
        "ask_property_type": "What type of property is it?",
        "ask_customer_name": "What name should we put the quotation under?",
        "ask_phone": "What is the best phone number to reach you on?",
        "ask_email": "What is your email address?",
        "ask_surfaces": "Which surfaces would you like painted?",
        "ask_room_length_m": "How long is the room (in meters)?",
        "ask_room_width_m": "How wide is the room (in meters)?",
        "ask_room_height_m": "How tall is the room (in meters)?",
        "ask_wall_length_m": "How long is the wall (in meters)?",
        "ask_wall_height_m": "How tall is the wall (in meters)?",
        "ask_surface_condition": "What condition are the surfaces in?",
        "ask_paint_tier": "What paint quality would you like: economy, standard or premium?",
        "ask_colour": "What colour would you like?",
        "ask_preferred_datetime": "What date and time would you prefer for the appointment?",
        "label_address": "property address", "label_property_type": "property type",
        "label_surfaces": "surfaces to paint", "label_room_length_m": "room length",
        "label_room_width_m": "room width", "label_room_height_m": "room height",
        "label_surface_condition": "surface condition", "label_paint_tier": "paint quality",
        "label_colour": "colour", "label_preferred_datetime": "preferred time",
        "metres": "{value:g} meters",
        "refusal": "I can only help with your painting job and quotation.",
        "fallback": "Thanks for your message. A member of our team will review your request and get back to you shortly.",
        "inspection_reply": "Thanks for letting us know. That kind of work needs an inspection, so a member of our team will contact you to arrange the next step.",
        "conflict": "Earlier you told me the {label} was {old}, but now it sounds like {new}. Which one is correct?",
        "photo_reply": "Thanks, I've passed your photo to our team to look at.",
        "colour_need_photo": "Send me a photo of the room and I'll suggest a colour that suits it.",
        "colour_suggest": "From your photo, the walls look {current}. These colours would go well: {options}. Which one would you like?",
        "colour_suggest_plain": "Based on your photo, these colours would suit the room: {options}. Which one would you like?",
        "colour_failed": "I couldn't judge a colour from that photo. What colour would you like?",
        "unsupported": "Sorry, I can't open that kind of message. Please type it or send a photo.",
        "voice_off": "Sorry, I can't play voice notes right now. Please type your message.",
        "voice_fail": "Sorry, I couldn't make out that voice note. Could you type it or send it again?",
        "heard": "I heard: \"{text}\".",
        "level_good": "in good condition", "level_minor": "in fairly good condition with minor wear",
        "level_moderate": "showing moderate wear or damage", "level_severe": "in poor condition",
        "photo_line": "Thanks for the photo. It looks like the surface is {level}{issues}. Our team will confirm this when they review your quote.",
        "photo_issues": " (I can see: {issues})",
        "photo_severe": " Damage like this may need an inspection first.",
        "decline": "Thanks for asking! We only do {services} at the moment, so I'll pass this to the team in case they can help.",
        "contact_intro": "That's everything I need about the job, thank you! ",
        "contact_confirm": "Shall I reserve this under {name} and {phone}? Reply yes, or send me the name or number you'd like to use instead.",
        "contact_ask_name": "What name should the booking be under?",
        "contact_ask_phone": "What phone number should we use for the booking?",
        "contact_done": "Perfect, I've noted the booking under {name}, {phone}. We'll prepare your quotation and a team member will confirm your appointment.",
        "owner_line": "{owner}, our {title}, will personally review your job and confirm your quotation and the final date.",
        "wrap_head": "Thank you, I've noted this under {name} ({phone}). {owner_line}",
        "wrap_here": "Here's what I have:",
        "wrap_ok": "Is everything correct?",
        "closing": "Wonderful, thank you! Your quotation will come here once it's confirmed.",
        "recap_address": "Address", "recap_property": "Property", "recap_surfaces": "Surfaces",
        "recap_room": "Room: {l:g} m long, {w:g} m wide, {h:g} m high",
        "recap_wall": "Wall: {l:g} m long, {h:g} m high",
        "recap_estimate": " (your estimate, the team will measure to confirm)",
        "recap_condition": "Condition", "recap_paint": "Paint", "recap_colour": "Colour",
        "recap_time": "Preferred time",
        "faq_price": "I can't quote a price myself: {owner} reviews every job and sends the estimate here once it's confirmed.",
        "faq_services": "At the moment we offer: {services}.",
        "faq_paint": "We can use {tiers} paint, in any colour you like. {owner} will go through the options when confirming.",
        "after_1": "Thanks! {owner} will be in touch here once your quotation is ready.",
        "after_2": "All noted. {owner} is reviewing your job and will message you here.",
        "after_3": "Got it, nothing more needed from you right now. {owner} will follow up on this chat.",
        "after_4": "Thank you! Your details are with {owner}, and you'll hear back here soon.",
        "date_noted": "Noted, I've passed \"{when}\" to {owner} as your preferred time. The final date is confirmed by them after reviewing the job.",
        "date_ask": "{have}Which day and time suits you best? {owner} confirms the final date, so I'll pass your preference on.",
        "date_have": "I have \"{when}\" as your preferred time. ",
        "important": "Noted, I've passed that to {owner} so it's seen before the quotation goes out.",
        "ack_1": "Got it.", "ack_2": "Thanks!", "ack_3": "Noted.", "ack_4": "Perfect.", "ack_5": "Great.",
        "ack_estimate": "Thanks, I'll use the larger figure to be safe.",
        "ack_fixed": "No problem, I've updated the {label} to {value}.",
        "new_job": "Happy to help with another job! ",
        "restart": "No problem, let's start again.",
        "ask_unit": "Are those {a:g} by {b:g} in meters or in feet?",
        "handoff": "Of course, I've asked {owner} to message you here. You can keep telling me about the job in the meantime.",
        "service_retry": "I can quote interior wall and ceiling painting. Which room would you like painted?",
        "declined_again": "I've passed your request to {owner}. If you'd like an interior wall or ceiling painted, tell me which room and I'll start the quote.",
        "foreign": "Sorry, I can only chat in English or Bahasa Malaysia. Could you write to me in one of those?",
        "abuse": "Please keep the chat respectful so I can help you.",
        "location_saved": "Thanks, I've saved the location you shared.",
        "pinned": "Pinned location ({lat:.5f}, {lon:.5f})",
        "welcome_back": "Hi again! If you would like another painting job quoted, just tell me what you want painted.",
        "duration": " We expect the work to take {text}.",
        "booking_ask": "Good news: {owner} can do your job on {when}. We expect {text}. Does that work for you? Reply yes, or tell me which day suits you better.",
        "booking_ok": "Great, you're booked in for {when}. {owner}'s team will see you then!",
        "booking_no": "No problem, I've told {owner} and they'll suggest another time.",
        "booking_remind": "Does {when} work for you? Please reply yes, or tell me a better day.",
        "booking_moved": "Update: your job has moved to {when}. Reply if that does not work for you.",
        "booking_cancelled": "Update: the slot we offered is no longer available. {owner} will suggest a new time.",
        "lang_ms": "Baik, saya akan bercakap dalam Bahasa Malaysia mulai sekarang.",
        "lang_en": "Sure, I'll continue in English.",
        "inspection_message": "This job needs an inspection before we can give a reliable price, so a member of our team will contact you to arrange it.",
        "inspection_wrap": "Thank you, I've passed everything to {owner}. {message}",
        "approved": "Good news from {business}: based on the details you gave us, our estimate is {currency} {total:,.2f} (excluding any applicable tax). This is an estimate only: the final price is confirmed once our team has checked the actual measurements on site.{duration} A team member will contact you to confirm the appointment.",
        "final": "Update from {business}: after checking on site, the final price for your job is {currency} {total:,.2f} (excluding any applicable tax). Thank you for choosing us!",
        "is_yes_words": "",
    },
    "ms": {
        "ask_address": "Apakah alamat hartanah tersebut?",
        "ask_address_again": "Adakah kerja ini di alamat yang sama seperti sebelum ini ({address})? Balas ya, atau hantar alamat baharu.",
        "ask_property_type": "Apakah jenis hartanah tersebut?",
        "ask_customer_name": "Atas nama siapakah sebut harga ini?",
        "ask_phone": "Apakah nombor telefon terbaik untuk menghubungi anda?",
        "ask_email": "Apakah alamat e-mel anda?",
        "ask_surfaces": "Permukaan mana yang anda ingin dicat?",
        "ask_room_length_m": "Berapa panjang bilik itu (dalam meter)?",
        "ask_room_width_m": "Berapa lebar bilik itu (dalam meter)?",
        "ask_room_height_m": "Berapa tinggi bilik itu (dalam meter)?",
        "ask_wall_length_m": "Berapa panjang dinding itu (dalam meter)?",
        "ask_wall_height_m": "Berapa tinggi dinding itu (dalam meter)?",
        "ask_surface_condition": "Bagaimana keadaan permukaan itu?",
        "ask_paint_tier": "Apakah kualiti cat yang anda mahu: ekonomi, standard atau premium?",
        "ask_colour": "Apakah warna yang anda mahu?",
        "ask_preferred_datetime": "Bilakah tarikh dan masa yang anda suka untuk temujanji?",
        "label_address": "alamat", "label_property_type": "jenis hartanah",
        "label_surfaces": "permukaan untuk dicat", "label_room_length_m": "panjang bilik",
        "label_room_width_m": "lebar bilik", "label_room_height_m": "tinggi bilik",
        "label_surface_condition": "keadaan permukaan", "label_paint_tier": "kualiti cat",
        "label_colour": "warna", "label_preferred_datetime": "masa pilihan",
        "metres": "{value:g} meter",
        "refusal": "Saya hanya boleh membantu dengan kerja mengecat dan sebut harga anda.",
        "fallback": "Terima kasih atas mesej anda. Seorang ahli pasukan kami akan menyemak permintaan anda dan menghubungi anda tidak lama lagi.",
        "inspection_reply": "Terima kasih kerana memberitahu kami. Kerja seperti itu memerlukan pemeriksaan, jadi seorang ahli pasukan kami akan menghubungi anda untuk mengatur langkah seterusnya.",
        "conflict": "Tadi anda kata {label} ialah {old}, tetapi sekarang nampaknya {new}. Yang mana satu betul?",
        "photo_reply": "Terima kasih, saya telah menghantar gambar anda kepada pasukan kami untuk disemak.",
        "colour_need_photo": "Hantar gambar bilik itu dan saya akan cadangkan warna yang sesuai.",
        "colour_suggest": "Daripada gambar anda, dinding nampak {current}. Warna ini sesuai: {options}. Yang mana anda mahu?",
        "colour_suggest_plain": "Berdasarkan gambar anda, warna ini sesuai untuk bilik itu: {options}. Yang mana anda mahu?",
        "colour_failed": "Saya tidak dapat menilai warna daripada gambar itu. Apakah warna yang anda mahu?",
        "unsupported": "Maaf, saya tidak dapat membuka jenis mesej itu. Sila taip atau hantar gambar.",
        "voice_off": "Maaf, saya tidak dapat mendengar nota suara sekarang. Sila taipkan mesej anda.",
        "voice_fail": "Maaf, saya tidak dapat memahami nota suara itu. Boleh anda taip atau hantar semula?",
        "heard": "Saya dengar: \"{text}\".",
        "level_good": "dalam keadaan baik", "level_minor": "dalam keadaan agak baik dengan sedikit haus",
        "level_moderate": "menunjukkan haus atau kerosakan sederhana", "level_severe": "dalam keadaan teruk",
        "photo_line": "Terima kasih untuk gambar itu. Nampaknya permukaan itu {level}{issues}. Pasukan kami akan mengesahkannya semasa menyemak sebut harga anda.",
        "photo_issues": " (saya nampak: {issues})",
        "photo_severe": " Kerosakan seperti ini mungkin memerlukan pemeriksaan dahulu.",
        "decline": "Terima kasih bertanya! Buat masa ini kami hanya menawarkan {services}, jadi saya akan serahkan perkara ini kepada pasukan kami jika mereka boleh membantu.",
        "contact_intro": "Itu sahaja maklumat yang saya perlukan tentang kerja itu, terima kasih! ",
        "contact_confirm": "Boleh saya tempah atas nama {name} dan {phone}? Balas ya, atau hantar nama atau nombor lain yang anda mahu guna.",
        "contact_ask_name": "Tempahan ini atas nama siapa?",
        "contact_ask_phone": "Nombor telefon mana yang patut kami guna untuk tempahan ini?",
        "contact_done": "Baik, saya telah catat tempahan atas nama {name}, {phone}. Kami akan menyediakan sebut harga anda dan seorang ahli pasukan akan mengesahkan temujanji anda.",
        "owner_line": "{owner}, {title} kami, akan menyemak sendiri kerja anda dan mengesahkan sebut harga serta tarikh akhir.",
        "wrap_head": "Terima kasih, saya telah catat ini atas nama {name} ({phone}). {owner_line}",
        "wrap_here": "Ini maklumat yang saya ada:",
        "wrap_ok": "Adakah semuanya betul?",
        "closing": "Bagus, terima kasih! Sebut harga anda akan dihantar di sini selepas disahkan.",
        "recap_address": "Alamat", "recap_property": "Hartanah", "recap_surfaces": "Permukaan",
        "recap_room": "Bilik: panjang {l:g} m, lebar {w:g} m, tinggi {h:g} m",
        "recap_wall": "Dinding: panjang {l:g} m, tinggi {h:g} m",
        "recap_estimate": " (anggaran anda, pasukan kami akan mengukur untuk mengesahkan)",
        "recap_condition": "Keadaan", "recap_paint": "Cat", "recap_colour": "Warna",
        "recap_time": "Masa pilihan",
        "faq_price": "Saya tidak boleh memberi harga sendiri: {owner} menyemak setiap kerja dan akan menghantar anggaran di sini selepas disahkan.",
        "faq_services": "Buat masa ini kami menawarkan: {services}.",
        "faq_paint": "Kami boleh guna cat {tiers}, dalam apa jua warna yang anda suka. {owner} akan menerangkan pilihan semasa mengesahkan.",
        "after_1": "Terima kasih! {owner} akan menghubungi anda di sini apabila sebut harga siap.",
        "after_2": "Baik, dicatat. {owner} sedang menyemak kerja anda dan akan mesej anda di sini.",
        "after_3": "Faham, tiada apa lagi yang diperlukan daripada anda sekarang. {owner} akan menyusul di sini.",
        "after_4": "Terima kasih! Maklumat anda ada pada {owner}, dan anda akan mendapat jawapan di sini tidak lama lagi.",
        "date_noted": "Dicatat, saya telah sampaikan \"{when}\" kepada {owner} sebagai masa pilihan anda. Tarikh akhir disahkan oleh mereka selepas menyemak kerja itu.",
        "date_ask": "{have}Hari dan masa mana yang sesuai untuk anda? {owner} mengesahkan tarikh akhir, jadi saya akan sampaikan pilihan anda.",
        "date_have": "Saya ada \"{when}\" sebagai masa pilihan anda. ",
        "important": "Dicatat, saya telah sampaikan itu kepada {owner} supaya dilihat sebelum sebut harga dihantar.",
        "ack_1": "Faham.", "ack_2": "Terima kasih!", "ack_3": "Dicatat.", "ack_4": "Bagus.", "ack_5": "Baik.",
        "ack_estimate": "Terima kasih, saya akan guna angka yang lebih besar untuk selamat.",
        "ack_fixed": "Tiada masalah, saya telah kemas kini {label} kepada {value}.",
        "new_job": "Dengan senang hati saya bantu untuk kerja lain! ",
        "restart": "Tiada masalah, kita mulakan semula.",
        "ask_unit": "Adakah {a:g} kali {b:g} itu dalam meter atau kaki?",
        "handoff": "Baik, saya telah minta {owner} mesej anda di sini. Anda boleh terus beritahu saya tentang kerja itu sementara menunggu.",
        "service_retry": "Saya boleh sebut harga untuk mengecat dinding dan siling dalaman. Bilik mana yang anda mahu cat?",
        "declined_again": "Saya telah serahkan permintaan anda kepada {owner}. Jika anda mahu dinding atau siling dalaman dicat, beritahu bilik mana dan saya akan mulakan sebut harga.",
        "foreign": "Maaf, saya hanya boleh berbual dalam bahasa Inggeris atau Bahasa Malaysia. Boleh anda tulis dalam salah satu bahasa itu?",
        "abuse": "Sila jaga kesopanan dalam sembang ini supaya saya dapat membantu anda.",
        "location_saved": "Terima kasih, saya telah simpan lokasi yang anda kongsi.",
        "pinned": "Lokasi dikongsi ({lat:.5f}, {lon:.5f})",
        "welcome_back": "Hai lagi! Jika anda mahu sebut harga untuk kerja mengecat yang lain, beritahu saya apa yang anda mahu cat.",
        "duration": " Kami menjangka kerja ini mengambil masa {text}.",
        "booking_ask": "Berita baik: {owner} boleh melakukan kerja anda pada {when}. Kami menjangka {text}. Adakah itu sesuai untuk anda? Balas ya, atau beritahu hari mana yang lebih sesuai.",
        "booking_ok": "Baik, anda telah ditempah pada {when}. Pasukan {owner} akan datang pada masa itu!",
        "booking_no": "Tiada masalah, saya telah beritahu {owner} dan mereka akan mencadangkan masa lain.",
        "booking_remind": "Adakah {when} sesuai untuk anda? Sila balas ya, atau beritahu hari yang lebih baik.",
        "booking_moved": "Makluman: kerja anda telah dialihkan ke {when}. Balas jika itu tidak sesuai untuk anda.",
        "booking_cancelled": "Makluman: slot yang kami tawarkan tidak lagi tersedia. {owner} akan mencadangkan masa baharu.",
        "lang_ms": "Baik, saya akan bercakap dalam Bahasa Malaysia mulai sekarang.",
        "lang_en": "Sure, I'll continue in English.",
        "inspection_message": "Kerja ini memerlukan pemeriksaan sebelum kami boleh beri harga yang tepat, jadi seorang ahli pasukan kami akan menghubungi anda untuk mengaturnya.",
        "inspection_wrap": "Terima kasih, saya telah serahkan semuanya kepada {owner}. {message}",
        "approved": "Berita baik daripada {business}: berdasarkan maklumat yang anda beri, anggaran kami ialah {currency} {total:,.2f} (tidak termasuk cukai jika berkenaan). Ini hanyalah anggaran: harga akhir disahkan selepas pasukan kami menyemak ukuran sebenar di tapak.{duration} Seorang ahli pasukan akan menghubungi anda untuk mengesahkan temujanji.",
        "final": "Maklumat daripada {business}: selepas semakan di tapak, harga akhir untuk kerja anda ialah {currency} {total:,.2f} (tidak termasuk cukai jika berkenaan). Terima kasih kerana memilih kami!",
        "is_yes_words": "",
    },
}


def t(key, lang="en", **kwargs):
    text = STRINGS.get(lang, STRINGS["en"]).get(key) or STRINGS["en"][key]
    return text.format(**kwargs) if kwargs else text


_SPELLING = [(re.compile(r"\bmetres\b"), "meters"), (re.compile(r"\bmetre\b"), "meter"),
             (re.compile(r"\bMetres\b"), "Meters"), (re.compile(r"\bMetre\b"), "Meter"),
             (re.compile(r"\bcentimetres\b"), "centimeters"), (re.compile(r"\bcentimetre\b"), "centimeter")]


def us_spelling(text):
    """English replies say "meters", including the ones the model writes itself."""
    for pattern, replacement in _SPELLING:
        text = pattern.sub(replacement, text)
    return text


def metres(value, lang="en"):
    return t("metres", lang, value=value)


# --- word lists (Malay) ---------------------------------------------------------------------
MALAY_WORDS = {
    "saya", "aku", "nak", "hendak", "mahu", "ingin", "tak", "tidak", "boleh", "bilik", "dinding", "siling",
    "cat", "mengecat", "rumah", "alamat", "tolong", "terima", "kasih", "berapa", "harga", "bila", "esok",
    "lusa", "hari", "minggu", "depan", "bulan", "pagi", "petang", "malam", "betul", "okey", "apa", "ini",
    "itu", "dan", "dengan", "untuk", "yang", "sahaja", "saja", "lagi", "sudah", "belum", "ada", "tiada",
    "kos", "warna", "kualiti", "panjang", "lebar", "tinggi", "meter", "kaki", "selamat", "hai", "helo",
    "macam", "mana", "kat", "sikit", "banyak", "tapi", "atau", "kalau", "tolonglah", "sila", "awak", "anda",
    "kami", "kita", "dia", "mereka", "sebut", "perkhidmatan", "pejabat", "dapur", "ruang", "tamu", "kamu",
    "ya", "ye", "baik", "setuju", "bukan", "salah", "sebenarnya", "maaf", "sekarang", "nanti", "dalam",
}
# words that are Malay-only enough to count double
MALAY_STRONG = {"saya", "nak", "hendak", "mahu", "tak", "tidak", "bilik", "dinding", "siling", "rumah",
                "berapa", "harga", "esok", "boleh", "awak", "kami", "terima", "kasih", "tolong", "cat"}
ENGLISH_WORDS = {
    "i", "my", "the", "is", "are", "want", "would", "like", "please", "you", "your", "what", "how", "when",
    "where", "can", "could", "do", "does", "and", "for", "with", "this", "that", "it", "to", "of", "in",
    "on", "a", "an", "need", "paint", "room", "wall", "hello", "hi", "thanks", "thank", "yes", "no", "me",
    "we", "have", "will", "just", "about", "also", "tomorrow", "today", "ok", "okay", "so", "but",
}

_ASK_MS = re.compile(
    r"\b(malay|melayu|bahasa malaysia|bahasa melayu|bm)\b", re.I)
_ASK_EN = re.compile(r"\b(english|eng|inggeris|bahasa inggeris|bi)\b", re.I)
_ASK_VERB = re.compile(
    r"\b(speak|talk|reply|answer|switch|change|use|say|write|please|pls|plz|can you|could you|back to|go back|"
    r"cakap|bercakap|guna|gunakan|tukar|balas|boleh|cuba|sila|tulis|balik)\b", re.I)


def requested_language(message):
    """The language the customer explicitly asks for ("speak Malay", "cakap English"), or None."""
    if not _ASK_VERB.search(message):
        return None
    wants_ms, wants_en = bool(_ASK_MS.search(message)), bool(_ASK_EN.search(message))
    if wants_ms and not wants_en:
        return "ms"
    if wants_en and not wants_ms:
        return "en"
    return None


def detect(message, current="en"):
    """The language to answer in: an explicit request wins, then a clear switch in how the customer writes.
    Short or mixed messages (Manglish) keep the current language, so it never flips on one word."""
    asked = requested_language(message)
    if asked:
        return asked
    words = re.findall(r"[a-z']+", message.lower())
    malay = sum(w in MALAY_WORDS for w in words)
    strong = sum(w in MALAY_STRONG for w in words)
    english = sum(w in ENGLISH_WORDS for w in words)
    if current != "ms" and (strong >= 1 and malay >= 2 and malay > english or malay >= 3 and malay > english):
        return "ms"
    if current == "ms" and english >= 3 and malay == 0:
        return "en"
    return current


def language_problem(reply, lang):
    """A model reply in the wrong language (it follows the history, not the customer), or None."""
    words = re.findall(r"[a-z']+", reply.lower())
    malay = sum(w in MALAY_WORDS for w in words)
    english = sum(w in ENGLISH_WORDS for w in words)
    if lang == "en" and malay >= 2 and malay > english:
        return "reply is in Malay but the customer is writing English; reply in English"
    if lang == "ms" and english >= 4 and malay == 0:
        return "reply is in English but the customer is writing Bahasa Malaysia; reply in Bahasa Malaysia"
    return None


# --- surface / tier vocabulary ----------------------------------------------------------------
SURFACE_WORDS = {"dinding": "walls", "siling": "ceiling"}
TIER_WORDS = {"ekonomi": "economy", "economy": "economy", "eco": "economy", "cheap": "economy",
              "budget": "economy", "basic": "economy", "murah": "economy", "standard": "standard",
              "premium": "premium"}
COLOUR_WORDS = {"white", "black", "grey", "gray", "blue", "green", "red", "yellow", "cream", "beige", "brown",
                "pink", "purple", "orange", "silver", "gold", "navy", "teal", "ivory", "putih", "hitam", "kelabu",
                "biru", "hijau", "merah", "kuning", "krim", "coklat", "ungu", "oren"}
COLOUR_MS = {"white": "putih", "ivory": "ivori", "cream": "krim", "beige": "beige", "grey": "kelabu", "blue": "biru",
             "navy": "biru tua", "teal": "teal", "green": "hijau", "yellow": "kuning", "pink": "merah jambu",
             "brown": "coklat"}
ISSUE_MS = {"peeling": "cat mengelupas", "flaking": "cat tertanggal", "cracks": "retak", "stains": "kesan kotoran",
            "bubbling": "cat menggelembung", "holes": "lubang", "damp": "lembap", "mould": "kulat",
            "water_damage": "kerosakan air"}
