"""Voice notes -> text. Gemini (native API, accepts Telegram's OGG/Opus directly) first, Groq Whisper as fallback.

Gemini is asked for Roman Urdu so the transcript reads like the drivers' typed messages; Whisper may return Urdu
script, which the LLM agent still understands. Both are free tiers; voice length is capped by the channel.
"""
import base64
import json
import os
import urllib.request
import uuid

PROMPT = ("Transcribe this voice note from a Pakistani fleet driver or manager exactly as spoken. Write Urdu and "
          "Punjabi speech in Roman Urdu (Latin script); keep English words in English; write vehicle numbers like "
          "LEA-22-2030 and numbers as digits. Output only the transcript, nothing else. If there is no speech, "
          "output nothing.")


class SpeechUnavailable(Exception):
    pass


def _post(url, data, headers, timeout=30):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class Gemini:
    name = "gemini"

    def __init__(self, api_key, model, transport=None):
        self.api_key, self.model = api_key, model
        self.transport = transport or _post

    def transcribe(self, audio, mime):
        payload = {"contents": [{"parts": [{"text": PROMPT},
                                           {"inline_data": {"mime_type": mime,
                                                            "data": base64.b64encode(audio).decode()}}]}],
                   "generationConfig": {"temperature": 0}}
        body = self.transport(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            json.dumps(payload).encode(), {"Content-Type": "application/json", "x-goog-api-key": self.api_key})
        try:
            parts = body["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            raise SpeechUnavailable("gemini: unexpected response") from None
        return "".join(p.get("text", "") for p in parts).strip()


class GroqWhisper:
    name = "groq"

    def __init__(self, api_key, model, transport=None):
        self.api_key, self.model = api_key, model
        self.transport = transport or _post

    def transcribe(self, audio, mime):
        boundary = uuid.uuid4().hex
        ext = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/wav": "wav"}.get(mime, "ogg")
        fields = [("model", self.model), ("response_format", "json"), ("temperature", "0")]
        body = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                        for k, v in fields)
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="voice.{ext}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n").encode() + audio + f"\r\n--{boundary}--\r\n".encode()
        out = self.transport("https://api.groq.com/openai/v1/audio/transcriptions", body,
                             {"Content-Type": f"multipart/form-data; boundary={boundary}",
                              "Authorization": f"Bearer {self.api_key}", "User-Agent": "fleetlog-ai/1.0"})
        if not isinstance(out, dict) or "text" not in out:
            raise SpeechUnavailable("groq: unexpected response")
        return out["text"].strip()


class Transcriber:
    def __init__(self, engines):
        self.engines = list(engines)
        self.last_used = None

    def __bool__(self):
        return bool(self.engines)

    def transcribe(self, audio, mime="audio/ogg"):
        errors = []
        for e in self.engines:
            try:
                text = e.transcribe(audio, mime)
                if text:
                    self.last_used = e.name
                    return text
                errors.append(f"{e.name}: empty")
            except Exception as ex:  # quota, network, bad key: try the next engine
                errors.append(f"{e.name}: {type(ex).__name__}")
        raise SpeechUnavailable("; ".join(errors) or "no speech engine configured")


def from_env():
    env = os.environ.get
    engines = []
    if env("GEMINI_API_KEY") or env("GOOGLE_API_KEY"):
        from .llm import models
        for m in models(env("OPS_GEMINI_STT_MODEL") or env("OPS_GEMINI_MODEL", "gemini-3.8-flash,gemini-3.5-flash")):
            engines.append(Gemini(env("GEMINI_API_KEY") or env("GOOGLE_API_KEY"), m))
    if env("GROQ_API_KEY"):
        engines.append(GroqWhisper(env("GROQ_API_KEY"), env("OPS_GROQ_STT_MODEL", "whisper-large-v3-turbo")))
    return Transcriber(engines)
