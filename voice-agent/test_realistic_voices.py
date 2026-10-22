import asyncio
import edge_tts
from pathlib import Path

sample_en = "Hello! Noted, 4 by 5 metres. How is the condition of the walls? Any peeling paint, mould, or cracks?"
sample_ms = "Helo! Baik, saiz 4 by 5 metres dicatat. Bagaimana pula dengan keadaan dinding? Ada cat mengelupas atau retak halus?"

out_dir = Path(__file__).resolve().parent / "data" / "audio_cache"
out_dir.mkdir(parents=True, exist_ok=True)

# Comparison of top tier neural voices
VOICES = {
    "Ava_Multilingual_Female": "en-US-AvaMultilingualNeural",
    "Andrew_Multilingual_Male": "en-US-AndrewMultilingualNeural",
    "Emma_Multilingual_Female": "en-US-EmmaMultilingualNeural",
    "Brian_Multilingual_Male": "en-US-BrianMultilingualNeural",
    "Yasmin_Malay_Female": "ms-MY-YasminNeural",
    "Osman_Malay_Male": "ms-MY-OsmanNeural"
}

async def generate():
    for name, v in VOICES.items():
        text = sample_ms if "Malay" in name else sample_en
        # Natural speech rate & slight volume boost for clarity
        comm = edge_tts.Communicate(text, v, rate="+1%", pitch="+0Hz")
        out_file = out_dir / f"sample_{name}.mp3"
        await comm.save(str(out_file))
        print(f"Generated {out_file.name} ({out_file.stat().st_size} bytes)")

if __name__ == "__main__":
    asyncio.run(generate())
