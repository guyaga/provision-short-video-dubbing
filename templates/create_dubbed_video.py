"""
Provision Short Video Dubbing - All-in-One Pipeline
====================================================
Complete pipeline for dubbing short product videos (30s-2min):
1. Transcribe video OR parse existing SRT
2. Translate with Gemini refinement for natural spoken narration
3. Generate TTS audio with ElevenLabs
4. Create styled ASS subtitles
5. Combine: original video + dubbed audio + burned-in subtitles

Usage:
    python create_dubbed_video.py --config config.json
    python create_dubbed_video.py --video input/video.mp4 --language es-419
    python create_dubbed_video.py --video input/video.mp4 --srt input/captions.srt --language it
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Project directory: all paths are relative to this script's parent
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "templates"))

from refine_translation import refine_translation_with_gemini
from create_subtitles import create_ass_subtitles

# ---------------------------------------------------------------------------
# Optional imports -- fail gracefully with clear messages
# ---------------------------------------------------------------------------
try:
    from google import genai
except ImportError:
    print("ERROR: google-genai package not installed. Run: pip install google-genai")
    sys.exit(1)

try:
    from elevenlabs import ElevenLabs
except ImportError:
    print("ERROR: elevenlabs package not installed. Run: pip install elevenlabs")
    sys.exit(1)

try:
    from pydub import AudioSegment
except ImportError:
    print("ERROR: pydub package not installed. Run: pip install pydub")
    sys.exit(1)


# ===========================================================================
# SRT Parsing
# ===========================================================================

def parse_srt(srt_path: str) -> list[dict]:
    """Parse an SRT file into a list of segments with start, end, text."""
    segments = []
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n\s*\n", content.strip())
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        # Line 0: index number
        # Line 1: timecodes
        # Lines 2+: text
        timecode_line = lines[1]
        text = " ".join(lines[2:]).replace("\n", " ").strip()

        match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            timecode_line,
        )
        if not match:
            continue

        start_str = match.group(1).replace(",", ".")
        end_str = match.group(2).replace(",", ".")

        segments.append({
            "start": _timecode_to_seconds(start_str),
            "end": _timecode_to_seconds(end_str),
            "text": text,
        })

    return segments


def _timecode_to_seconds(tc: str) -> float:
    """Convert HH:MM:SS.mmm to seconds."""
    parts = tc.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


# ===========================================================================
# Transcription with Gemini
# ===========================================================================

def transcribe_video_with_gemini(video_path: str, gemini_model: str) -> list[dict]:
    """
    Transcribe a short video using Gemini 3.1 Pro.
    Returns a list of segments: [{start, end, text}, ...]
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print(f"  Uploading video for transcription: {video_path}")
    uploaded_file = client.files.upload(file=video_path)

    # Wait for file processing
    while uploaded_file.state.name == "PROCESSING":
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)

    if uploaded_file.state.name == "FAILED":
        print(f"ERROR: Video upload failed: {uploaded_file.state.name}")
        sys.exit(1)

    prompt = """Transcribe this video into segments with timestamps.
Return ONLY a JSON array with objects containing:
- "start": start time in seconds (float)
- "end": end time in seconds (float)
- "text": the spoken text for that segment

Keep segments short (1-2 sentences each). Be accurate with timestamps.
Return raw JSON only, no markdown fences."""

    response = client.models.generate_content(
        model=gemini_model,
        contents=[uploaded_file, prompt],
    )

    # Parse response JSON
    response_text = response.text.strip()
    # Remove markdown code fences if present
    if response_text.startswith("```"):
        response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
        response_text = re.sub(r"\s*```$", "", response_text)

    segments = json.loads(response_text)
    print(f"  Transcribed {len(segments)} segments.")
    return segments


# ===========================================================================
# Translation with Gemini (Draft)
# ===========================================================================

def translate_segments(
    segments: list[dict],
    target_language_name: str,
    gemini_model: str,
) -> list[dict]:
    """
    Draft-translate segments to the target language using Gemini.
    Returns segments with added 'translated_text' field.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Build transcript text for context
    transcript_lines = []
    for i, seg in enumerate(segments):
        transcript_lines.append(
            f"[{seg['start']:.2f} - {seg['end']:.2f}] {seg['text']}"
        )
    transcript_text = "\n".join(transcript_lines)

    prompt = f"""Translate the following English video transcript segments into {target_language_name}.
This is for a product video narration, so keep the tone professional yet conversational.

Transcript:
{transcript_text}

Return ONLY a JSON array with objects containing:
- "start": same start time as original (float)
- "end": same end time as original (float)
- "original_text": the original English text
- "translated_text": the translated text in {target_language_name}

Preserve all timestamps exactly as given. Return raw JSON only, no markdown fences."""

    response = client.models.generate_content(
        model=gemini_model,
        contents=prompt,
    )

    response_text = response.text.strip()
    if response_text.startswith("```"):
        response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
        response_text = re.sub(r"\s*```$", "", response_text)

    translated = json.loads(response_text)
    print(f"  Draft-translated {len(translated)} segments to {target_language_name}.")
    return translated


# ===========================================================================
# TTS Generation with ElevenLabs
# ===========================================================================

def generate_tts_segments(
    segments: list[dict],
    voice_id: str,
    model_id: str,
    output_dir: str,
) -> list[str]:
    """
    Generate TTS audio for each translated segment using ElevenLabs.
    Returns list of paths to individual audio segment files.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("ERROR: ELEVENLABS_API_KEY environment variable not set.")
        sys.exit(1)

    client = ElevenLabs(api_key=api_key)
    segment_paths = []

    os.makedirs(output_dir, exist_ok=True)

    for i, seg in enumerate(segments):
        text = seg.get("refined_text") or seg.get("translated_text", "")
        if not text.strip():
            continue

        print(f"  Generating TTS for segment {i + 1}/{len(segments)}...")

        # Generate audio with ElevenLabs
        audio_generator = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=model_id,
            output_format="mp3_44100_128",
        )

        # Write audio bytes to file
        segment_path = os.path.join(output_dir, f"segment_{i:03d}.mp3")
        with open(segment_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)

        segment_paths.append(segment_path)

    print(f"  Generated {len(segment_paths)} TTS audio segments.")
    return segment_paths


def combine_tts_segments(
    segments: list[dict],
    segment_paths: list[str],
    total_duration_ms: int,
    output_path: str,
) -> str:
    """
    Combine individual TTS segments into a single audio track,
    placing each segment at its correct timestamp position.
    Returns path to combined audio file.
    """
    # Create silent base track matching video duration
    combined = AudioSegment.silent(duration=total_duration_ms)

    path_idx = 0
    for seg in segments:
        text = seg.get("refined_text") or seg.get("translated_text", "")
        if not text.strip():
            continue
        if path_idx >= len(segment_paths):
            break

        segment_audio = AudioSegment.from_mp3(segment_paths[path_idx])
        start_ms = int(seg["start"] * 1000)

        # Overlay the TTS segment at the correct position
        combined = combined.overlay(segment_audio, position=start_ms)
        path_idx += 1

    combined.export(output_path, format="mp3")
    print(f"  Combined audio saved to: {output_path}")
    return output_path


# ===========================================================================
# FFmpeg: Get video duration
# ===========================================================================

def get_video_duration_ms(video_path: str) -> int:
    """Get video duration in milliseconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    info = json.loads(result.stdout)
    duration_s = float(info["format"]["duration"])
    return int(duration_s * 1000)


# ===========================================================================
# FFmpeg: Combine video + dubbed audio + subtitles
# ===========================================================================

def combine_video(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_path: str,
) -> str:
    """
    Combine original video (no audio) + dubbed audio + burned-in ASS subtitles.
    Returns path to final output video.
    """
    # Use FFmpeg to:
    #   - Take video stream from original
    #   - Replace audio with dubbed track
    #   - Burn in ASS subtitles using the ass filter
    #
    # NOTE: On Windows, the subtitle path colons and backslashes need escaping
    # for the FFmpeg filter. We convert to forward slashes and escape colons.
    sub_path_escaped = subtitle_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",       # video from original
        "-map", "1:a:0",       # audio from dubbed track
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-vf", f"ass='{sub_path_escaped}'",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    print(f"  Running FFmpeg to combine video...")
    print(f"  Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  FFmpeg stderr:\n{result.stderr}")
        print("ERROR: FFmpeg failed. Check the command output above.")
        sys.exit(1)

    print(f"  Final video saved to: {output_path}")
    return output_path


# ===========================================================================
# Main Pipeline
# ===========================================================================

def load_config(config_path: str) -> dict:
    """Load configuration from JSON file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_pipeline(config: dict):
    """Run the complete dubbing pipeline."""
    # Resolve paths relative to PROJECT_DIR
    source_video = str(PROJECT_DIR / config["source_video"])
    source_srt = config.get("source_srt")
    if source_srt:
        source_srt = str(PROJECT_DIR / source_srt)
    output_dir = str(PROJECT_DIR / config.get("output_dir", "output"))
    os.makedirs(output_dir, exist_ok=True)

    target_language = config.get("target_language", "es-419")
    target_language_name = config.get("target_language_name", "Latin American Spanish")
    gemini_model = config.get("gemini_model", "gemini-3.1-pro")

    # TODO: Replace with your ElevenLabs voice ID
    # Recommended voices:
    #   - "pNInz6obpgDQGcFmaJgB" (Adam - English, deep male)
    #   - "ErXwobaYiN019PkySvjV" (Antoni - warm male)
    #   - "EXAVITQu4vr4xnSDxMaL" (Bella - young female)
    #   - For multilingual: use "eleven_multilingual_v2" model with any voice
    voice_id = config.get("elevenlabs_voice_id", "pNInz6obpgDQGcFmaJgB")
    elevenlabs_model = config.get("elevenlabs_model", "eleven_multilingual_v2")

    # Subtitle styling
    subtitle_config = {
        "font": config.get("subtitle_font", "Arial"),
        "size": config.get("subtitle_size", 20),
        "primary_color": config.get("subtitle_primary_color", "&H00FFFFFF"),
        "outline_color": config.get("subtitle_outline_color", "&H00000000"),
        "outline_width": config.get("subtitle_outline_width", 2),
        "shadow_offset": config.get("subtitle_shadow_offset", 1),
        "margin_v": config.get("subtitle_margin_v", 30),
        "margin_l": config.get("subtitle_margin_l", 10),
        "margin_r": config.get("subtitle_margin_r", 10),
        "alignment": config.get("subtitle_alignment", 2),
        "video_width": config.get("video_width", 1920),
        "video_height": config.get("video_height", 1080),
        "rtl": config.get("rtl", False),
    }

    # -----------------------------------------------------------------------
    # Step 1: Transcribe or parse SRT
    # -----------------------------------------------------------------------
    print("\n=== Step 1: Transcription ===")
    if source_srt and os.path.exists(source_srt):
        print(f"  Using existing SRT: {source_srt}")
        segments = parse_srt(source_srt)
    else:
        print(f"  Transcribing video with Gemini ({gemini_model})...")
        segments = transcribe_video_with_gemini(source_video, gemini_model)

    # Save transcript
    transcript_path = os.path.join(output_dir, "transcript.json")
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, indent=2, ensure_ascii=False)
    print(f"  Transcript saved to: {transcript_path}")

    # -----------------------------------------------------------------------
    # Step 2: Translate (draft)
    # -----------------------------------------------------------------------
    print("\n=== Step 2: Draft Translation ===")
    translated_segments = translate_segments(
        segments, target_language_name, gemini_model
    )

    translation_path = os.path.join(output_dir, "translation.json")
    with open(translation_path, "w", encoding="utf-8") as f:
        json.dump(translated_segments, f, indent=2, ensure_ascii=False)
    print(f"  Draft translation saved to: {translation_path}")

    # -----------------------------------------------------------------------
    # Step 3: Refine translation for spoken narration
    # -----------------------------------------------------------------------
    print("\n=== Step 3: Translation Refinement ===")
    refined_segments = refine_translation_with_gemini(
        translated_segments, target_language_name, gemini_model
    )

    refined_path = os.path.join(output_dir, "refined_translation.json")
    with open(refined_path, "w", encoding="utf-8") as f:
        json.dump(refined_segments, f, indent=2, ensure_ascii=False)
    print(f"  Refined translation saved to: {refined_path}")

    # -----------------------------------------------------------------------
    # Step 4: Generate TTS audio
    # -----------------------------------------------------------------------
    print("\n=== Step 4: TTS Generation ===")
    tts_dir = os.path.join(output_dir, "tts_segments")
    segment_paths = generate_tts_segments(
        refined_segments, voice_id, elevenlabs_model, tts_dir
    )

    # Get video duration and combine segments into single audio track
    video_duration_ms = get_video_duration_ms(source_video)
    dubbed_audio_path = os.path.join(output_dir, "dubbed_audio.mp3")
    combine_tts_segments(
        refined_segments, segment_paths, video_duration_ms, dubbed_audio_path
    )

    # -----------------------------------------------------------------------
    # Step 5: Create styled ASS subtitles
    # -----------------------------------------------------------------------
    print("\n=== Step 5: Subtitle Generation ===")
    subtitle_path = os.path.join(output_dir, "subtitles.ass")

    # Prepare subtitle segments (use refined text for subtitle display)
    subtitle_segments = []
    for seg in refined_segments:
        subtitle_segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg.get("refined_text") or seg.get("translated_text", ""),
        })

    create_ass_subtitles(subtitle_segments, subtitle_path, subtitle_config)
    print(f"  Subtitles saved to: {subtitle_path}")

    # -----------------------------------------------------------------------
    # Step 6: Combine everything with FFmpeg
    # -----------------------------------------------------------------------
    print("\n=== Step 6: Final Video Assembly ===")
    output_video_path = os.path.join(output_dir, "final_video.mp4")
    combine_video(source_video, dubbed_audio_path, subtitle_path, output_video_path)

    print("\n=== Pipeline Complete ===")
    print(f"  Final video: {output_video_path}")
    return output_video_path


# ===========================================================================
# CLI Entry Point
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Provision Short Video Dubbing Pipeline"
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to config.json file",
    )
    parser.add_argument(
        "--video", type=str, default=None,
        help="Path to source video (overrides config)",
    )
    parser.add_argument(
        "--srt", type=str, default=None,
        help="Path to existing SRT captions (optional, overrides config)",
    )
    parser.add_argument(
        "--language", type=str, default=None,
        help="Target language code, e.g. es-419 (overrides config)",
    )
    parser.add_argument(
        "--language-name", type=str, default=None,
        help="Target language name, e.g. 'Latin American Spanish' (overrides config)",
    )
    args = parser.parse_args()

    # Load config from file or use defaults
    if args.config:
        config_path = str(PROJECT_DIR / args.config) if not os.path.isabs(args.config) else args.config
        config = load_config(config_path)
    else:
        config = {}

    # CLI overrides
    if args.video:
        config["source_video"] = args.video
    if args.srt:
        config["source_srt"] = args.srt
    if args.language:
        config["target_language"] = args.language
    if args.language_name:
        config["target_language_name"] = args.language_name

    # Validate required fields
    if "source_video" not in config:
        print("ERROR: No source video specified. Use --video or set source_video in config.json")
        sys.exit(1)

    run_pipeline(config)


if __name__ == "__main__":
    main()
