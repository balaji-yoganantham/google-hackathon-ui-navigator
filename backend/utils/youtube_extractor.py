"""Extract transcript from YouTube video URL using youtube-transcript-api."""
import logging
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


def get_video_id(url: str) -> str | None:
    """Extract YouTube video ID from watch URL."""
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
        if "youtu.be" in parsed.netloc:
            return parsed.path.strip("/") or None
        qs = parse_qs(parsed.query)
        return qs.get("v", [None])[0]
    return None


def get_transcript(video_url: str) -> str:
    """Fetch transcript for a YouTube watch URL. Returns empty string on failure."""
    video_id = get_video_id(video_url)
    if not video_id:
        return ""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        if not transcript_list:
            return ""
        return " ".join(item.get("text", "") for item in transcript_list)
    except Exception as e:
        logger.warning("youtube_extractor: failed to get transcript for %s: %s", video_url, e)
        return ""
