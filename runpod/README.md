# RunPod endpoints

Gesir has no custom RunPod handler: the three endpoints run ready-made RunPod serverless workers, and the backend calls them
from `src/runpod_client.py` (chat and photos) and `src/transcribe.py` (voice notes).

| Endpoint | Worker | Model | GPU | Used for |
| -------- | ------ | ----- | --- | -------- |
| `RUNPOD_ENDPOINT_ID` (`ose8agxpb9p1mr`) | vLLM | `Qwen/Qwen2.5-7B-Instruct` | 24 GB | reading what the customer writes, writing replies |
| `RUNPOD_VISION_ENDPOINT_ID` (`m3a8r7m8ebibba`) | vLLM | `Qwen/Qwen2.5-VL-7B-Instruct` | 24 GB | reading photos of walls and aircon units |
| `STT_RUNPOD_ENDPOINT_ID` (`nvnrh39cdxgymr`) | Faster Whisper | `small` | 24 GB | voice-note transcription |

All three scale to zero when idle, so the first request after a quiet period waits 2 to 5 minutes for a worker. Set Min Workers
to 1 before a live demo. Test one with:

```bash
curl -X POST https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input": {"messages": [{"role": "user", "content": "Hello"}], "sampling_params": {"max_tokens": 50}}}'
```

Proof of use: [`../submission/SDC2026_HRISSA_Runpod_POU.pdf`](../submission/SDC2026_HRISSA_Runpod_POU.pdf)
