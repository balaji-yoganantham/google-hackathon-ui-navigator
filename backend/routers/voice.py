"""Voice API stubs (optional): transcribe, synthesize."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/voice", tags=["voice"])


class TranscribeBody(BaseModel):
    audioBase64: str
    language: str = "en"


class SynthesizeBody(BaseModel):
    text: str
    language: str = "en"


@router.post("/transcribe")
async def transcribe_audio(body: TranscribeBody) -> dict:
    """Google Cloud STT - not implemented in this backend."""
    raise HTTPException(501, "Voice transcribe not implemented. Use frontend Web Speech API.")


@router.post("/synthesize")
async def synthesize_speech(body: SynthesizeBody) -> dict:
    """Google Cloud TTS - not implemented in this backend."""
    raise HTTPException(501, "Voice synthesize not implemented. Use frontend Web Speech API.")
