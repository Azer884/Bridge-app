"""
Transcript Manager for Orbyte Voice Agent
Persists and manages conversation transcripts per conversation_id.
Format:
- conversation_id
- speaker: 'customer' or 'agent'
- text: spoken dialogue
- timestamp: ISO 8601 string
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

TRANSCRIPTS_DIR = Path(__file__).resolve().parent / "data" / "transcripts"
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

class TranscriptManager:
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or TRANSCRIPTS_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, conversation_id: str) -> Path:
        safe_id = "".join(c for c in conversation_id if c.isalnum() or c in ("-", "_"))
        return self.storage_dir / f"{safe_id}.json"

    def record_turn(self, conversation_id: str, speaker: str, text: str) -> Dict[str, Any]:
        """Record a single dialogue turn into the conversation transcript file."""
        entry = {
            "conversation_id": conversation_id,
            "speaker": speaker.lower(),
            "text": text.strip(),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        file_path = self._get_file_path(conversation_id)
        transcript = self.get_transcript(conversation_id)
        transcript.append(entry)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(transcript, f, indent=2, ensure_ascii=False)

        return entry

    def get_transcript(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Retrieve full transcript list for a given conversation ID."""
        file_path = self._get_file_path(conversation_id)
        if not file_path.exists():
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def export_for_extract(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Format the transcript as expected by POST /extract."""
        raw_list = self.get_transcript(conversation_id)
        return [
            {
                "conversation_id": entry.get("conversation_id", conversation_id),
                "speaker": entry.get("speaker", "customer"),
                "text": entry.get("text", ""),
                "timestamp": entry.get("timestamp", "")
            }
            for entry in raw_list
        ]
