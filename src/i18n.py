"""Customer-facing language: English and Bahasa Malaysia.

Every fixed sentence the backend sends (questions, recap, quote messages) lives here, so a Malay
customer never gets a half-English reply. The model is told which language to use for its own
sentences. Detection and switching are deterministic: the customer can ask for a language, or
simply start writing in one.
"""
import re
from datetime import date

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
        "ask_surface_condition": "What condition are the surfaces in? For example good, peeling, cracks or damp.",
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
        "consent_notice": "Under Malaysia's PDPA 2010, do you consent to {business} (using Gesir.AI) processing your job details, photos, voice notes and phone number to prepare this quote? Only {owner} sees them, we keep them only for this job, and you can withdraw any time by typing STOP, which erases them. (Reply 1 to agree, 2 to decline)",
        "consent_again": "To prepare your quote I need your consent under Malaysia's PDPA 2010 to process your job details, photos and voice notes. Reply 1 to agree, 2 to decline.",
        "consent_objection": "Understood, I will not record or use anything more from you. Reply STOP and I will erase everything held about you, or reply 1 if you would like to carry on with your quote.",
        "consent_thanks": "Thank you, your consent is recorded. You can withdraw it any time by typing STOP.",
        "consent_declined": "No problem, I won't process your details. If you change your mind, reply 1 and we can continue. You can also contact {owner} directly.",
        "consent_withdrawn": "Done. Your messages, photos, bookings and details have been erased and I won't contact you again. Message us any time to start fresh.",
        "photo_not_surface": "Thanks, but that photo doesn't show a wall or ceiling, so I can't use it for your quote. Could you send a photo of the wall or ceiling you'd like painted?",
        "faq_private": "I can't share personal details or other customers' information, but {owner} will message you here once your quote is ready.",
        "faq_prep": "{owner} will go through any preparation, like moving furniture or access to the home, when confirming your quote.",
        "faq_other": "Good question. {owner} can help with that when confirming your quote.",
        "st_ok_1": "No rush.", "st_ok_2": "Take your time.", "st_ok_3": "Whenever you're ready.",
        "contact_another": "Happy to quote another room too. First, let's finish this booking.",
        "recap_intro": "Here's what I have so far:",
        "faq_bot": "I'm the virtual assistant for {business}, so not a person, but {owner} reviews every quote personally.",
        "cancel_noted": "No problem, I've let {owner} know you'd like to cancel. If you change your mind or want a new quote, just message me.",
        "st_welcome": "You're welcome!",
        "wrap_another": "Happy to quote another room as well. Let's confirm this one first: if everything above is right, reply yes, then tell me about the next room.",
        "faq_discount": "{owner} sets the final price, so any discount can be discussed when your quote is confirmed.",
        "faq_time": "How long it takes depends on the size of the rooms. {owner} will confirm the schedule and duration with your quote.",
        "faq_avail": "{owner} confirms availability once I have your details. You can tell me your preferred date and time as we go.",
        "faq_where": "I'll take down your address so {owner} can confirm we cover your area.",
        "faq_pay": "{owner} will share the payment details when your quote is confirmed.",
        "faq_warranty": "{owner} can tell you about any warranty when your quote is confirmed.",
        "faq_coats": "{owner} will go through the details of the work, such as the number of coats, when confirming your quote.",
        "faq_wallpaper": "I can only quote the painting itself. {owner} can tell you whether preparation work like removing wallpaper is possible.",
        "faq_materials": "You choose the paint quality (economy, standard or premium) and {owner} confirms exactly what the quote includes.",
        "faq_compare": "Economy is the most affordable, premium is the highest quality, and standard sits in between. {owner} can go through the options when confirming.",
        "faq_whyaddress": "The address lets {owner} check the location and plan the visit.",
        "faq_whyquestions": "A few details help {owner} prepare an accurate quote. I'll keep it quick.",
        "faq_offtopic": "That's a bit outside what I can help with. I'm here for painting quotes.",
        "st_hello": "Yes, I'm here! Which room would you like painted?",
        "st_thanks": "You're welcome! Message me any time you'd like a painting quote.",
        "st_bye": "Thanks for stopping by! Message me any time you need a painting quote.",
        "st_okay": "Sure! Which room would you like painted?",
        "st_confused": "Sorry, I didn't catch that. Which room would you like painted?",
        "date_past": "That day has already passed. Which day would work for you?",
        "date_past_year": "That date has already passed this year. Which day would work for you? If you mean next year, please include the year, for example 20 Oct {year}.",
        "date_need_day": "I'll need a specific day to book. Which date would suit you, for example Saturday morning?",
        "date_ask_again": "Which day and time would suit you? For example, Saturday 10am, or just \"anytime\".",
        "condition_ask_again": "Are the surfaces in good condition, or is there peeling, cracks, damp or stains?",
        "colour_ideas": "Popular choices are white, cream or light grey. Send me a photo of the room and I can suggest colours that suit it. Which colour would you like?",
        "colour_ask_again": "Which colour would you like? For example white, cream, grey, or say \"no preference\".",
        "address_ask_again": "What is the full address of the property, for example 12 Jalan Bunga, Taman Melati?",
        "wrap_nochange": "No problem. Is there anything you'd like to change? If everything above is right, reply yes.",
        "photo_wait": "One moment, I'm looking at the photo you sent.",
        "est_head": "Good news from {business}! Here is your estimate:",
        "est_total": "Estimate: {currency} {total:,.2f} (excluding any applicable tax)",
        "est_room": "{name}: {size}", "est_room_name": "Room {n}",
        "est_surfaces": "Surfaces: {value}", "est_paint": "Paint: {value}", "est_colour": "Colour: {value}",
        "est_time": "Time needed: {value}", "est_date": "Preferred date: {value}",
        "est_note": "This is an estimate only: the final price is confirmed once our team has checked the measurements on site. A team member will contact you to confirm the appointment.",
        "est_pdf": "Your estimate is attached as a PDF.",
        "final_head": "Update from {business}: here is your final price after the site visit.",
        "final_total": "Final price: {currency} {total:,.2f} (excluding any applicable tax)",
        "final_note": "Thank you for choosing us!",
        "job_updated": "Got it, I've updated your job ({changes}). {owner} will send you the updated estimate shortly.",
        "job_noted": "Got it, I've noted that ({changes}) and let {owner} know.",
        "estimate_updated_intro": "Your estimate has been updated with the changes you asked for.",
        "change_rooms": "rooms", "change_sizes": "room size",
        "colour_not_yet": "I haven't received the photo yet. It can take a moment to arrive, and I'll tell you as soon as I see it.",
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
        "recap_room_n": "Room {n}{name}: {l:g} m long, {w:g} m wide, {h:g} m high",
        "recap_wall_n": "Wall {n}{name}: {l:g} m long, {h:g} m high",
        "rooms_noted": "Noted, that is {count} rooms so far.",
        "room_height_shared": "I'll use the same height for the other rooms unless you tell me otherwise.",
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
        "ask_surface_condition": "Bagaimana keadaan permukaan itu? Contohnya baik, cat mengelupas, retak atau lembap.",
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
        "consent_notice": "Di bawah PDPA Malaysia 2010, adakah anda bersetuju {business} (menggunakan Gesir.AI) memproses butiran kerja, gambar, nota suara dan nombor telefon anda untuk menyediakan sebut harga ini? Hanya {owner} dapat melihatnya, kami menyimpannya hanya untuk kerja ini, dan anda boleh menarik balik bila-bila masa dengan menaip STOP, yang akan memadamkannya. (Balas 1 untuk setuju, 2 untuk tidak)",
        "consent_again": "Untuk menyediakan sebut harga, saya perlukan persetujuan anda di bawah PDPA Malaysia 2010 untuk memproses butiran kerja, gambar dan nota suara anda. Balas 1 untuk setuju, 2 untuk tidak.",
        "consent_objection": "Faham, saya tidak akan merekod atau menggunakan apa-apa lagi daripada anda. Balas STOP dan saya akan memadam semua yang disimpan tentang anda, atau balas 1 jika anda mahu meneruskan sebut harga.",
        "consent_thanks": "Terima kasih, persetujuan anda telah direkodkan. Anda boleh menarik balik bila-bila masa dengan menaip STOP.",
        "consent_declined": "Tiada masalah, saya tidak akan memproses butiran anda. Jika anda berubah fikiran, balas 1 dan kita boleh teruskan. Anda juga boleh hubungi {owner} terus.",
        "consent_withdrawn": "Selesai. Mesej, gambar, tempahan dan butiran anda telah dipadam dan saya tidak akan menghubungi anda lagi. Mesej kami bila-bila masa untuk bermula semula.",
        "photo_not_surface": "Terima kasih, tetapi gambar itu tidak menunjukkan dinding atau siling, jadi saya tidak dapat menggunakannya untuk sebut harga anda. Boleh hantar gambar dinding atau siling yang ingin dicat?",
        "faq_private": "Saya tidak boleh berkongsi maklumat peribadi atau maklumat pelanggan lain, tetapi {owner} akan menghubungi anda di sini selepas sebut harga siap.",
        "faq_prep": "{owner} akan terangkan persediaan, seperti mengalih perabot atau akses ke rumah, semasa mengesahkan sebut harga.",
        "faq_other": "Soalan yang baik. {owner} boleh membantu perkara itu semasa mengesahkan sebut harga anda.",
        "st_ok_1": "Tak apa.", "st_ok_2": "Ambil masa anda.", "st_ok_3": "Bila-bila anda sedia.",
        "contact_another": "Boleh, saya juga boleh sebut harga bilik lain. Mari siapkan tempahan ini dahulu.",
        "recap_intro": "Ini yang saya ada setakat ini:",
        "faq_bot": "Saya pembantu maya {business}, bukan manusia, tetapi {owner} menyemak setiap sebut harga sendiri.",
        "cancel_noted": "Baik, saya telah beritahu {owner} bahawa anda mahu batalkan. Jika anda berubah fikiran atau mahu sebut harga baharu, mesej saya sahaja.",
        "st_welcome": "Sama-sama!",
        "wrap_another": "Boleh, saya juga boleh sebut harga bilik lain. Mari sahkan yang ini dahulu: jika semuanya betul, balas ya, kemudian ceritakan tentang bilik seterusnya.",
        "faq_discount": "{owner} menetapkan harga akhir, jadi diskaun boleh dibincangkan semasa sebut harga disahkan.",
        "faq_time": "Tempohnya bergantung pada saiz bilik. {owner} akan mengesahkan jadual dan tempoh bersama sebut harga anda.",
        "faq_avail": "{owner} akan mengesahkan ketersediaan selepas saya ada maklumat anda. Anda boleh beritahu tarikh dan masa pilihan anda nanti.",
        "faq_where": "Saya akan catat alamat anda supaya {owner} boleh mengesahkan kawasan anda dalam liputan kami.",
        "faq_pay": "{owner} akan berkongsi butiran bayaran apabila sebut harga disahkan.",
        "faq_warranty": "{owner} boleh beritahu tentang waranti apabila sebut harga disahkan.",
        "faq_coats": "{owner} akan terangkan butiran kerja, seperti bilangan lapisan cat, semasa mengesahkan sebut harga.",
        "faq_wallpaper": "Saya hanya boleh sebut harga untuk kerja mengecat. {owner} boleh beritahu sama ada kerja persediaan seperti membuang kertas dinding boleh dibuat.",
        "faq_materials": "Anda pilih kualiti cat (ekonomi, standard atau premium) dan {owner} akan mengesahkan apa yang termasuk dalam sebut harga.",
        "faq_compare": "Ekonomi paling berpatutan, premium berkualiti tertinggi, dan standard di antara keduanya. {owner} boleh terangkan pilihan semasa mengesahkan.",
        "faq_whyaddress": "Alamat membolehkan {owner} menyemak lokasi dan merancang lawatan.",
        "faq_whyquestions": "Beberapa maklumat membantu {owner} menyediakan sebut harga yang tepat. Saya akan cepatkan.",
        "faq_offtopic": "Itu di luar bidang saya. Saya di sini untuk sebut harga mengecat.",
        "st_hello": "Ya, saya di sini! Bilik mana yang anda mahu cat?",
        "st_thanks": "Sama-sama! Mesej saya bila-bila masa anda mahu sebut harga mengecat.",
        "st_bye": "Terima kasih singgah! Mesej saya bila-bila masa anda perlukan sebut harga mengecat.",
        "st_okay": "Baik! Bilik mana yang anda mahu cat?",
        "st_confused": "Maaf, saya tidak faham. Bilik mana yang anda mahu cat?",
        "date_past": "Hari itu sudah berlalu. Hari mana yang sesuai untuk anda?",
        "date_past_year": "Tarikh itu sudah berlalu tahun ini. Hari mana yang sesuai untuk anda? Jika maksud anda tahun depan, sila nyatakan tahun, contohnya 20 Okt {year}.",
        "date_need_day": "Saya perlukan hari yang tepat untuk tempahan. Tarikh mana yang sesuai, contohnya Sabtu pagi?",
        "date_ask_again": "Hari dan masa mana yang sesuai? Contohnya Sabtu 10 pagi, atau \"bila-bila masa\".",
        "condition_ask_again": "Adakah permukaan dalam keadaan baik, atau ada cat mengelupas, retak, lembap atau kesan kotoran?",
        "colour_ideas": "Pilihan popular ialah putih, krim atau kelabu cerah. Hantar gambar bilik dan saya boleh cadangkan warna yang sesuai. Warna apa yang anda mahu?",
        "colour_ask_again": "Warna apa yang anda mahu? Contohnya putih, krim, kelabu, atau cakap \"tiada pilihan\".",
        "address_ask_again": "Apakah alamat penuh hartanah itu, contohnya 12 Jalan Bunga, Taman Melati?",
        "wrap_nochange": "Baik. Ada apa-apa yang anda mahu ubah? Jika semuanya betul, balas ya.",
        "photo_wait": "Sekejap ya, saya sedang melihat gambar yang anda hantar.",
        "est_head": "Berita baik daripada {business}! Ini anggaran anda:",
        "est_total": "Anggaran: {currency} {total:,.2f} (tidak termasuk cukai jika berkenaan)",
        "est_room": "{name}: {size}", "est_room_name": "Bilik {n}",
        "est_surfaces": "Permukaan: {value}", "est_paint": "Cat: {value}", "est_colour": "Warna: {value}",
        "est_time": "Tempoh kerja: {value}", "est_date": "Tarikh pilihan: {value}",
        "est_note": "Ini hanyalah anggaran: harga akhir disahkan selepas pasukan kami menyemak ukuran sebenar di tapak. Seorang ahli pasukan akan menghubungi anda untuk mengesahkan temujanji.",
        "est_pdf": "Anggaran anda dilampirkan sebagai PDF.",
        "final_head": "Maklumat daripada {business}: ini harga akhir anda selepas lawatan tapak.",
        "final_total": "Harga akhir: {currency} {total:,.2f} (tidak termasuk cukai jika berkenaan)",
        "final_note": "Terima kasih kerana memilih kami!",
        "job_updated": "Baik, saya telah kemas kini kerja anda ({changes}). {owner} akan menghantar anggaran baharu tidak lama lagi.",
        "job_noted": "Baik, saya telah catat ({changes}) dan beritahu {owner}.",
        "estimate_updated_intro": "Anggaran anda telah dikemas kini mengikut perubahan yang anda minta.",
        "change_rooms": "bilik", "change_sizes": "saiz bilik",
        "colour_not_yet": "Saya belum terima gambar itu. Ia mungkin mengambil sedikit masa, dan saya akan beritahu sebaik sahaja saya nampak.",
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
        "recap_room_n": "Bilik {n}{name}: panjang {l:g} m, lebar {w:g} m, tinggi {h:g} m",
        "recap_wall_n": "Dinding {n}{name}: panjang {l:g} m, tinggi {h:g} m",
        "rooms_noted": "Baik, setakat ini {count} bilik.",
        "room_height_shared": "Saya akan guna ketinggian yang sama untuk bilik lain kecuali anda beritahu sebaliknya.",
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


_SENTENCE_START = re.compile(r"(^|[.!?]\s+)([a-z])")


def t(key, lang="en", **kwargs):
    text = STRINGS.get(lang, STRINGS["en"]).get(key) or STRINGS["en"][key]
    if "{year}" in text:
        kwargs.setdefault("year", date.today().year + 1)      # "20 Oct 2027": next year, whenever this runs
    text = text.format(**kwargs) if kwargs else text
    if "owner" in kwargs:           # "{owner} will confirm" with no owner's name is "Our team will confirm"
        text = _SENTENCE_START.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    return text


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
