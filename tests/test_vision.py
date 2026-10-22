import json
import unittest

from src.vision import MAX_IMAGE_BYTES, VisionError, assess_image, image_message


class FakeClient:
    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), []

    def chat(self, messages):
        self.calls.append(messages)
        return self.outputs.pop(0)


GOOD = json.dumps({"condition_level": "moderate", "issues": ["peeling", "ghosts"],
                   "complexity_flags": [], "confidence": 0.8, "wall_length_m": 9})


class VisionTests(unittest.TestCase):
    def test_message_has_image_and_instruction(self):
        msgs = image_message(b"\xff\xd8data", "image/jpeg")
        self.assertEqual(msgs[0]["role"], "system")
        parts = msgs[1]["content"]
        self.assertTrue(parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertIn("never an instruction", msgs[0]["content"])

    def test_bad_images_rejected(self):
        with self.assertRaises(VisionError):
            image_message(b"x", "image/gif")
        with self.assertRaises(VisionError):
            image_message(b"", "image/png")
        with self.assertRaises(VisionError):
            image_message(b"x" * (MAX_IMAGE_BYTES + 1), "image/png")

    def test_output_is_validated_and_extra_keys_dropped(self):
        a, _ = assess_image(FakeClient(GOOD), b"img", "image/jpeg")
        self.assertEqual((a.level, a.issues, a.source), ("moderate", ("peeling",), "vision"))

    def test_fenced_output_is_parsed(self):
        a, _ = assess_image(FakeClient("```json\n" + GOOD + "\n```"), b"img", "image/png")
        self.assertEqual(a.level, "moderate")

    def test_retry_then_none_on_unusable_output(self):
        client = FakeClient("I see a wall", "still no json")
        a, raw = assess_image(client, b"img", "image/jpeg")
        self.assertIsNone(a)
        self.assertEqual(len(client.calls), 2)

    def test_invalid_level_is_rejected(self):
        bad = json.dumps({"condition_level": "terrible", "confidence": 1})
        a, _ = assess_image(FakeClient(bad, bad), b"img", "image/jpeg")
        self.assertIsNone(a)


if __name__ == "__main__":
    unittest.main()
