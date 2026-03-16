"""Voice API: transcribe audio to URL + goal via Vertex AI Gemini."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gemini.client import GeminiClient

router = APIRouter(prefix="/api/voice", tags=["voice"])

_gemini_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client


class TranscribeBody(BaseModel):
    audioBase64: str
    mimeType: str = "audio/webm"
    language: str = "en"


class SynthesizeBody(BaseModel):
    text: str
    language: str = "en"


@router.post("/transcribe")
async def transcribe_audio(body: TranscribeBody) -> dict:
    """Send raw audio to Vertex AI Gemini; return {url, goal} for the agent."""
    if not body.audioBase64 or len(body.audioBase64) < 500:
        raise HTTPException(400, "AUDIO_TOO_SHORT")
    try:
        client = get_gemini_client()
        result = await client.parse_audio_command(body.audioBase64, body.mimeType)
        return {"url": result["url"], "goal": result["goal"]}
    except ValueError as e:
        if str(e) == "AUDIO_TOO_SHORT":
            raise HTTPException(400, "AUDIO_TOO_SHORT") from e
        raise HTTPException(422, str(e)) from e


@router.post("/synthesize")
async def synthesize_speech(body: SynthesizeBody) -> dict:
    """Google Cloud TTS - not implemented in this backend."""
    raise HTTPException(501, "Voice synthesize not implemented. Use frontend Web Speech API.")
