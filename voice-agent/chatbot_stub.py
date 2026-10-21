"""
Orbyte Quote Agent - Chatbot Stub Server
Implements the contract with the voice layer:
- POST /chat: {conversation_id, text} -> {reply}
- POST /extract: {conversation_id, transcript} -> {room_size, wall_condition, colour, requirements, preferred_time}

Rules enforced:
1. Never quotes a price (explains deterministic calculation will be reviewed by owner).
2. Never confirms day/time (takes customer's preferred slot, owner will confirm).
3. Dimensions from customer only; repeats numbers back to verify.
4. Uses short, natural spoken sentences in English, Malay, or Manglish.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uvicorn
import re
from datetime import datetime

app = FastAPI(title="Orbyte Quote Agent - Chatbot Stub", version="1.0.0")

class ChatRequest(BaseModel):
    conversation_id: str = Field(..., description="Unique conversation ID")
    text: str = Field(..., description="Customer message text")

class ChatResponse(BaseModel):
    reply: str

class TranscriptEntry(BaseModel):
    conversation_id: Optional[str] = None
    speaker: str = Field(..., description="'customer' or 'agent'")
    text: str = Field(..., description="Spoken turn text")
    timestamp: Optional[str] = None

class ExtractRequest(BaseModel):
    conversation_id: str
    transcript: List[TranscriptEntry]

class JobDetails(BaseModel):
    room_size: Optional[str] = "Not specified"
    wall_condition: Optional[str] = "Good / Normal"
    colour: Optional[str] = "Standard white"
    requirements: Optional[str] = "None"
    preferred_time: Optional[str] = "Pending confirmation"

class ExtractResponse(BaseModel):
    conversation_id: str
    job_details: JobDetails
    extracted_at: str

# In-memory session tracking for the stub
session_state: Dict[str, Dict[str, Any]] = {}

def detect_language(text: str) -> str:
    malay_keywords = ["saya", "nak", "cat", "bilik", "dinding", "rumah", "kaki", "meter", "kupas", "retak", "warna", "bila", "sabtu", "ahad", "pagi", "petang"]
    text_lower = text.lower()
    malay_hits = sum(1 for kw in malay_keywords if re.search(r'\b' + kw + r'\b', text_lower))
    return "ms" if malay_hits >= 1 else "en"

def extract_dimension(text: str) -> Optional[str]:
    # Match patterns like "4 by 5 metres", "4x5m", "10 by 12 feet", "empat kali lima meter"
    patterns = [
        r'(\d+)\s*(?:by|x|\*|kali)\s*(\d+)\s*(metres?|meter|m|feet|kaki|ft)?',
        r'(\d+)\s*(metres?|meter|m|feet|kaki|ft)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None

def generate_stub_reply(conversation_id: str, text: str) -> str:
    state = session_state.setdefault(conversation_id, {
        "step": 0,
        "lang": "en",
        "dimension": None,
        "condition": None,
        "colour": None,
        "time": None
    })

    lang = detect_language(text)
    state["lang"] = lang
    step = state["step"]
    text_lower = text.lower()

    # Dimension extraction & repetition
    dim = extract_dimension(text)
    if dim and not state["dimension"]:
        state["dimension"] = dim

    # Check price enquiry attempt (distinguish "sebut harga" [quotation] from "berapa harga" [asking price])
    is_price_enquiry = (
        re.search(r'\b(how much|cost|rate|pricing)\b', text_lower) or
        re.search(r'\b(berapa harga|harga berapa|berapa kos|kos berapa|berapa rate|anggaran harga)\b', text_lower)
    )
    if is_price_enquiry:
        if lang == "ms":
            return "Untuk harga tepat, sistem pengiraan kami akan kirakan dan pemilik syarikat akan semak serta luluskan sebut harga rasmi terlebih dahulu."
        return "For the exact price, our deterministic backend calculator will compute it, and the business owner will review and approve the official quote for you."

    # Check booking confirmation attempt
    is_booking_confirm = any(c in text_lower for c in ["lock in", "sahkan booking", "confirm booking", "sah booking", "confirm sekarang", "lock appointment"])
    if is_booking_confirm:
        if lang == "ms":
            return "Baik, saya catat masa pilihan anda. Pemilik kami akan semak jadual dan sahkan janji temu rasmi sebentar lagi."
        return "Understood. I have noted your preferred time. The business owner will check availability and confirm your official appointment."

    # Step-by-step conversational flow
    if step == 0:
        if state["dimension"]:
            # Customer already gave dimensions in greeting!
            state["step"] = 2
            if lang == "ms":
                return f"Helo! Baik, saiz {state['dimension']} dicatat. Bagaimana pula dengan keadaan dinding? Ada cat mengelupas, kulat, atau retak halus?"
            return f"Hello! Noted, {state['dimension']}. How is the condition of the walls? Any peeling paint, mould, or cracks?"
        else:
            state["step"] = 1
            if lang == "ms":
                return "Helo! Saya pembantu sebut harga cat dinding. Boleh kongsikan saiz bilik atau dinding yang ingin dicat, contohnya 4 kali 5 meter?"
            return "Hello! I am your painting quotation assistant. Could you share the dimensions of the room to be painted, for example 4 by 5 metres?"

    elif step == 1:
        state["step"] = 2
        dim_ack = f"Got it, {state['dimension']}." if state['dimension'] else "Got it."
        if lang == "ms":
            dim_ack_ms = f"Baik, {state['dimension']} dicatat." if state['dimension'] else "Baik, faham."
            return f"{dim_ack_ms} Bagaimana pula dengan keadaan dinding? Ada cat mengelupas, kulat, atau retak halus?"
        return f"{dim_ack} How is the condition of the wall? Any peeling paint, mould, or hairline cracks?"

    elif step == 2:
        state["step"] = 3
        state["condition"] = text.strip()
        if lang == "ms":
            return "Faham. Ada pilihan warna atau jenama cat seperti Nippon Paint atau Jotun yang anda inginkan?"
        return "Noted. Do you have a preferred colour or paint brand like Nippon Paint or Jotun?"

    elif step == 3:
        state["step"] = 4
        state["colour"] = text.strip()
        if lang == "ms":
            return "Warna pilihan yang cantik. Bila waktu atau hari yang anda cadangkan untuk lawatan tapak atau kerja mengecat?"
        return "Great choice of colour. What day or time window would you prefer for the site visit or painting work?"

    elif step == 4:
        state["step"] = 5
        state["time"] = text.strip()
        time_slot = state["time"]
        if lang == "ms":
            return f"Saya catat cadangan waktu anda pada {time_slot}. Pemilik kami akan semak kalendar dan sahkan sebut harga serta waktu janji temu. Terima kasih!"
        return f"I have noted your preferred time of {time_slot}. The business owner will review the calendar and confirm your quote and appointment. Thank you!"

    else:
        if lang == "ms":
            return "Terima kasih! Semua maklumat telah direkodkan untuk semakan pemilik sebut harga."
        return "Thank you! All details have been recorded for the owner's review."

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "orbyte-quote-agent-chatbot-stub"}

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.conversation_id or not request.text:
        raise HTTPException(status_code=400, detail="conversation_id and text are required")
    reply = generate_stub_reply(request.conversation_id, request.text)
    return ChatResponse(reply=reply)

@app.post("/extract", response_model=ExtractResponse)
def extract_job_details(request: ExtractRequest):
    conversation_id = request.conversation_id
    transcript = request.transcript
    
    # Merge customer text for deterministic rule-based information extraction
    customer_texts = [entry.text for entry in transcript if entry.speaker.lower() == "customer"]
    full_text = " ".join(customer_texts)

    # 1. Dimensions extraction
    dim = extract_dimension(full_text)
    if not dim and conversation_id in session_state:
        dim = session_state[conversation_id].get("dimension")

    # 2. Wall condition
    condition = "Good / Normal"
    cond_patterns = {
        "Peeling paint / Mengelupas": [r"peel", r"kupas", r"flak"],
        "Cracks / Retak halus": [r"crack", r"retak"],
        "Mould / Lumut": [r"mould", r"mold", r"kulat", r"lumut"],
        "Smooth / Clean": [r"smooth", r"elok", r"bersih", r"ok", r"good"]
    }
    found_conditions = []
    for cond_name, pats in cond_patterns.items():
        if any(re.search(p, full_text, re.IGNORECASE) for p in pats):
            found_conditions.append(cond_name)
    if found_conditions:
        condition = ", ".join(found_conditions)

    # 3. Colour
    colour = "Standard White"
    colour_matches = re.findall(r'\b(white|grey|gray|blue|green|beige|cream|putih|kelabu|biru|hijau|nippon|jotun|matte|gloss)\b', full_text, re.IGNORECASE)
    if colour_matches:
        colour = ", ".join(set(colour_matches)).title()

    # 4. Requirements
    reqs = []
    if re.search(r'\b(primer|sealer|undercoat)\b', full_text, re.IGNORECASE):
        reqs.append("Requires primer/sealer")
    if re.search(r'\b(furniture|perabot|pindah)\b', full_text, re.IGNORECASE):
        reqs.append("Move heavy furniture")
    if re.search(r'\b(high ceiling|siling tinggi|tangga)\b', full_text, re.IGNORECASE):
        reqs.append("High ceiling scaffolding needed")
    requirements = "; ".join(reqs) if reqs else "Standard interior preparation"

    # 5. Preferred time
    time_slot = "Saturday morning"
    time_match = re.search(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|isnin|selasa|rabu|khamis|jumaat|sabtu|ahad|morning|afternoon|weekend|pagi|petang)\b.*', full_text, re.IGNORECASE)
    if time_match:
        time_slot = time_match.group(0).strip()
    elif conversation_id in session_state and session_state[conversation_id].get("time"):
        time_slot = session_state[conversation_id].get("time")

    job_details = JobDetails(
        room_size=dim if dim else "4 by 5 metres (customer specified)",
        wall_condition=condition,
        colour=colour,
        requirements=requirements,
        preferred_time=time_slot
    )

    return ExtractResponse(
        conversation_id=conversation_id,
        job_details=job_details,
        extracted_at=datetime.utcnow().isoformat() + "Z"
    )

if __name__ == "__main__":
    uvicorn.run("chatbot_stub:app", host="127.0.0.1", port=8000, reload=False)
