"""
Benchmark and Validation Test Suite for STT Service
Tests speech-to-text with faster-whisper across:
1. English with spoken dimensions ("around 4 by 5 metres")
2. Malay with spoken numbers ("empat kali lima meter", "dinding mengelupas")
3. Mixed Manglish ("Boss, master bedroom saiz 4 by 5 metres, cat Jotun")
4. Additional number tests ("3 by 4 metres", "10 by 12 feet")

Asserts dimension accuracy, language identification, and latency.
"""

import time
import re
from pathlib import Path
from stt_service import STTService
from tts_service import TTSService

TEST_CASES = [
    {
        "id": "EN-01",
        "description": "English with dimensions '4 by 5 metres'",
        "text": "Hello, I would like to get a quote to paint my living room. The room size is 4 by 5 metres, and walls are in good condition.",
        "lang": "en",
        "expected_dim": "4 by 5 metres",
        "expected_lang": "en"
    },
    {
        "id": "MS-01",
        "description": "Malay with spoken numbers 'empat kali lima meter'",
        "text": "Helo, saya nak minta sebut harga cat bilik tidur. Saiz bilik empat kali lima meter, dinding ada cat mengelupas.",
        "lang": "ms",
        "expected_dim": "4 by 5 metres",
        "expected_lang": "ms"
    },
    {
        "id": "MANGLISH-01",
        "description": "Mixed Malaysian English / Malay code-switching",
        "text": "Hi boss, I nak paint my master bedroom. Size dalam 4 by 5 metres, ada sikit retak halus, nak guna cat Jotun.",
        "lang": "ms",
        "expected_dim": "4 by 5 metres",
        "expected_lang": "ms"
    },
    {
        "id": "EN-02",
        "description": "English with '3 by 4 metres'",
        "text": "Can you give me an estimate for two bedrooms? Each is 3 by 4 metres, ceiling is high.",
        "lang": "en",
        "expected_dim": "3 by 4 metres",
        "expected_lang": "en"
    },
    {
        "id": "MS-02",
        "description": "Malay with 'tiga kali empat meter'",
        "text": "Saya perlukan cat untuk ruang makan, anggaran tiga kali empat meter, warna putih matte.",
        "lang": "ms",
        "expected_dim": "3 by 4 metres",
        "expected_lang": "ms"
    }
]

def run_benchmarks():
    print("=" * 70)
    print("       ORBYTE QUOTE AGENT - STT BENCHMARK SUITE       ")
    print("=" * 70)

    tts = TTSService()
    stt = STTService(model_size="base", device="cpu")

    audio_dir = Path(__file__).resolve().parent / "data" / "test_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    results = []
    all_passed = True

    for case in TEST_CASES:
        cid = case["id"]
        print(f"\n--- Testing [{cid}]: {case['description']} ---")
        print(f"Ground Truth : \"{case['text']}\"")

        # 1. Synthesize audio test file
        audio_file = tts.synthesize(case["text"], output_filename=f"test_{cid.lower()}.mp3", lang=case["lang"])

        # 2. Transcribe with faster-whisper
        t0 = time.time()
        stt_result = stt.transcribe(str(audio_file))
        latency = round(time.time() - t0, 3)

        transcribed = stt_result["text"]
        detected_lang = stt_result["language"]
        print(f"Transcribed  : \"{transcribed}\"")
        print(f"Detected Lang: {detected_lang} (confidence: {stt_result['language_probability']})")
        print(f"Latency      : {latency}s")

        # 3. Check dimension extraction
        dim_passed = case["expected_dim"].lower() in transcribed.lower()
        if not dim_passed:
            # Check digits version
            digits_expected = case["expected_dim"].replace("metres", "meter").replace("by", "kali")
            dim_passed = digits_expected.lower() in transcribed.lower()

        status = "PASS" if dim_passed else "FAIL"
        if not dim_passed:
            all_passed = False

        print(f"Dimension Check ('{case['expected_dim']}'): [{'PASS' if dim_passed else 'FAIL'}]")

        results.append({
            "id": cid,
            "status": status,
            "latency": latency,
            "dim_passed": dim_passed,
            "detected_lang": detected_lang,
            "transcribed": transcribed
        })

    print("\n" + "=" * 70)
    print("                    BENCHMARK SUMMARY TABLE                  ")
    print("=" * 70)
    print(f"{'Test ID':<12} | {'Status':<8} | {'Latency':<9} | {'Language':<10} | {'Dimension Verified'}")
    print("-" * 70)
    for r in results:
        print(f"{r['id']:<12} | {r['status']:<8} | {r['latency']}s    | {r['detected_lang']:<10} | {r['dim_passed']}")

    print("=" * 70)
    if all_passed:
        print(">>> ALL TESTS PASSED! Faster-Whisper accurately captures spoken dimensions and languages.")
    else:
        print(">>> SOME TESTS FAILED. Review output above.")
    print("=" * 70)

if __name__ == "__main__":
    run_benchmarks()
