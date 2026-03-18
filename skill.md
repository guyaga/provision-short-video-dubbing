---
name: provision-short-video-dubbing
description: "Quick dubbing for short Provision ISR product videos (30s-2min) with natural translations and burned-in subtitles. Uses Gemini 3.1 Pro for translation refinement and ElevenLabs for expressive TTS. Produces videos with dubbed audio and styled subtitles. Use for: short video dubbing, product clip translation, social media video localization. Triggers: provision short video, dub short video, provision clip, short dubbing, product video translation"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Provision Short Video Dubbing

Quick dubbing pipeline for short Provision ISR product videos (30 seconds to 2 minutes). Designed for product clips, social media videos, and short promotional content. Produces a final video with dubbed audio and burned-in styled subtitles.

## Quick Overview

This skill handles the complete dubbing workflow for SHORT videos (under 2 minutes):

1. **Transcribe** the video using Gemini 3.1 Pro, or use an existing SRT file
2. **Translate** to the target language with a two-step Gemini refinement process that makes translations sound natural for spoken narration (not written text)
3. **Generate TTS** audio segments using ElevenLabs with expressive voice settings
4. **Create styled ASS subtitles** with customizable fonts, colors, outlines, and shadows
5. **Combine** everything with FFmpeg: original video + dubbed audio + burned-in subtitles

## Prerequisites

- **Python 3.10+**
- **FFmpeg** installed and available on PATH
- **Google Gemini API key** (for transcription and translation refinement)
- **ElevenLabs API key** (for TTS generation)
- Python packages: `google-genai`, `elevenlabs`, `pydub`

Install dependencies:
```bash
pip install google-genai elevenlabs pydub
```

Set environment variables:
```bash
export GEMINI_API_KEY="your-gemini-api-key"
export ELEVENLABS_API_KEY="your-elevenlabs-api-key"
```

## Project Structure

```
project_dir/
  input/
    video.mp4              # Source short video
    captions.srt           # Optional existing SRT captions
  output/
    transcript.json        # Transcribed segments
    translation.json       # Draft translation
    refined_translation.json  # Refined natural-sounding translation
    dubbed_audio.mp3       # Combined TTS audio
    subtitles.ass          # Styled ASS subtitle file
    final_video.mp4        # Final dubbed video with subtitles
  config.json              # Configuration file
```

## Complete Workflow

### Step 1: Prepare the project

Create the project directory and place your short video in `input/`. Optionally include an SRT file if captions already exist.

### Step 2: Configure settings

Edit `config.json` to set:
- Target language (e.g., "es-419" for Latin American Spanish, "it" for Italian)
- ElevenLabs voice ID
- Subtitle styling preferences
- Output settings

### Step 3: Run the all-in-one script

```bash
python create_dubbed_video.py --config config.json
```

This runs the full pipeline: transcribe/parse SRT, translate, refine, TTS, subtitle, combine.

### Step 4: Review output

The final video is saved to `output/final_video.mp4`.

## Translation Refinement Approach

The translation uses a two-step process with Gemini 3.1 Pro:

1. **Draft translation**: Gemini translates the English transcript to the target language
2. **Refinement**: A second Gemini call takes both the English original and the draft translation, then refines it specifically for spoken narration:
   - Makes phrases sound natural when spoken aloud, not like written text
   - Keeps the same duration/pacing as the original segments
   - Uses conversational tone appropriate for product videos
   - Avoids overly formal or literary language
   - Preserves technical product terms where appropriate

The refinement prompt instructs Gemini to think about how a native speaker would naturally describe the product in casual, confident speech.

## ASS Subtitle Styling Options

The subtitle system uses Advanced SubStation Alpha (ASS) format for rich styling:

- **Font**: Default is "Arial" (widely available). Use "Rubik" or "Open Sans" for a modern look.
- **Size**: Default 20px. Scale based on video resolution.
- **Primary color**: White (`&H00FFFFFF`) for readability.
- **Outline color**: Black (`&H00000000`) for contrast.
- **Outline width**: 2px default. Increase for busy backgrounds.
- **Shadow**: 1px offset with semi-transparent black.
- **Background**: Optional semi-transparent box behind text.
- **Position**: Bottom center (default). Can adjust vertical margin.
- **Alignment**: Center (2). Use 1 for left, 3 for right.
- **RTL support**: For Hebrew/Arabic, alignment and Unicode markers are handled automatically.

Example style line:
```
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,30,1
```

## Voice Selection Tips

Choose ElevenLabs voices based on the target language and content type:

- **Spanish (Latin American)**: Look for voices with warm, conversational tone. Male voices work well for security product narration.
- **Italian**: Choose voices with clear enunciation. Avoid overly dramatic voices for product content.
- **French**: Select voices with neutral accent (not strongly regional).
- **German**: Choose professional, clear voices. German TTS quality varies, so test carefully.
- **Portuguese (Brazilian)**: Warm, engaging voices work best for product demos.
- **Hebrew**: Limited native voice options. Test thoroughly for natural rhythm.
- **Arabic**: Modern Standard Arabic voices for broad reach, or dialect-specific for regional content.

General tips:
- Always test a short segment before running the full pipeline
- Use "expressive" or "multilingual" voice models when available
- Match the energy level of the original narration
- For product videos, prefer confident, clear voices over dramatic ones

## Configuration

All settings are controlled via `config.json`. Key parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `source_video` | Path to input video | `input/video.mp4` |
| `source_srt` | Path to existing SRT (optional) | `null` |
| `target_language` | Target language code | `"es-419"` |
| `target_language_name` | Human-readable language name | `"Latin American Spanish"` |
| `elevenlabs_voice_id` | ElevenLabs voice ID | `"pNInz6obpgDQGcFmaJgB"` |
| `elevenlabs_model` | ElevenLabs model | `"eleven_multilingual_v2"` |
| `gemini_model` | Gemini model for translation | `"gemini-3.1-pro"` |
| `subtitle_font` | ASS subtitle font name | `"Arial"` |
| `subtitle_size` | Font size in pixels | `20` |
| `subtitle_primary_color` | Text color (ASS hex) | `"&H00FFFFFF"` |
| `subtitle_outline_color` | Outline color (ASS hex) | `"&H00000000"` |
| `subtitle_outline_width` | Outline thickness | `2` |
| `subtitle_shadow_offset` | Shadow distance | `1` |
| `subtitle_margin_v` | Vertical margin from bottom | `30` |
| `output_dir` | Output directory | `"output"` |
