"""
Provision Short Video Dubbing - Translation Refinement
=======================================================
Standalone template for the Gemini translation refinement step.
Takes English transcript + draft translation and refines it for
natural spoken narration using Gemini 3.1 Pro.

The refinement focuses on making translations sound like natural speech,
not written text. It preserves timing/pacing constraints so TTS output
will fit within the original segment durations.

Usage:
    from refine_translation import refine_translation_with_gemini

    refined = refine_translation_with_gemini(
        translated_segments,
        "Latin American Spanish",
        "gemini-3.1-pro"
    )
"""

import json
import os
import re
import sys
import time

try:
    from google import genai
except ImportError:
    print("ERROR: google-genai package not installed. Run: pip install google-genai")
    sys.exit(1)


def refine_translation_with_gemini(
    translated_segments: list[dict],
    target_language_name: str,
    gemini_model: str = "gemini-3.1-pro",
) -> list[dict]:
    """
    Refine draft translations for natural spoken narration.

    Takes segments with 'original_text' and 'translated_text' fields,
    sends them to Gemini with a detailed prompt for spoken narration
    refinement, and returns segments with an added 'refined_text' field.

    Args:
        translated_segments: List of dicts with keys:
            - start (float): Start time in seconds
            - end (float): End time in seconds
            - original_text (str): Original English text
            - translated_text (str): Draft translation
        target_language_name: Human-readable name of target language
            (e.g., "Latin American Spanish", "Italian", "Brazilian Portuguese")
        gemini_model: Gemini model to use (default: "gemini-3.1-pro")

    Returns:
        List of dicts with original fields plus 'refined_text'.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Build the segment data for the prompt
    segments_text = []
    for i, seg in enumerate(translated_segments):
        duration = seg["end"] - seg["start"]
        segments_text.append(
            f"Segment {i + 1} [{seg['start']:.2f}s - {seg['end']:.2f}s] "
            f"(duration: {duration:.1f}s):\n"
            f"  English: {seg['original_text']}\n"
            f"  Draft {target_language_name}: {seg['translated_text']}"
        )
    segments_block = "\n\n".join(segments_text)

    prompt = f"""You are a professional voice-over translator and localization expert
specializing in {target_language_name}.

I have a product video with English narration that has been draft-translated into
{target_language_name}. Your job is to REFINE the draft translation so it sounds
completely natural for SPOKEN narration -- not written text.

Key requirements:
1. NATURAL SPEECH: The refined text must sound like how a native {target_language_name}
   speaker would naturally describe this product in casual, confident speech. Avoid
   overly formal, literary, or stiff phrasing.
2. PACING: Each segment must fit within the same time duration as the original.
   If the draft translation is too long for the segment duration, shorten it while
   keeping the meaning. If it is too short, you can slightly expand it.
   Approximate speaking rate: ~3-4 words per second for most languages.
3. SPOKEN RHYTHM: Use contractions, natural pauses, and conversational connectors
   where appropriate. The text will be read aloud by a TTS voice.
4. PRODUCT TERMS: Keep technical product names and model numbers in their original
   form (e.g., "Provision ISR", "4K", "IP camera"). Do not translate brand names.
5. TONE: Professional but approachable -- this is a product demo, not a formal
   presentation. Think: confident salesperson showing off a product.
6. FLOW: Ensure smooth transitions between segments. Each segment should sound
   natural on its own but also flow well into the next.

Here are the segments to refine:

{segments_block}

Return ONLY a JSON array with objects containing:
- "start": same start time (float)
- "end": same end time (float)
- "original_text": the original English text
- "translated_text": the draft translation (unchanged)
- "refined_text": your refined {target_language_name} version for spoken narration

Return raw JSON only, no markdown fences, no explanation."""

    print(f"  Sending {len(translated_segments)} segments to Gemini for refinement...")

    response = client.models.generate_content(
        model=gemini_model,
        contents=prompt,
    )

    response_text = response.text.strip()

    # Remove markdown code fences if present
    if response_text.startswith("```"):
        response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
        response_text = re.sub(r"\s*```$", "", response_text)

    refined_segments = json.loads(response_text)
    print(f"  Refined {len(refined_segments)} segments for natural spoken narration.")

    return refined_segments


def refine_from_files(
    english_transcript_path: str,
    draft_translation_path: str,
    target_language_name: str,
    output_path: str,
    gemini_model: str = "gemini-3.1-pro",
) -> list[dict]:
    """
    Convenience function: load segments from JSON files, refine, and save.

    Args:
        english_transcript_path: Path to JSON with English transcript segments
        draft_translation_path: Path to JSON with draft translated segments
        target_language_name: Target language name
        output_path: Where to save refined segments JSON
        gemini_model: Gemini model to use

    Returns:
        List of refined segment dicts.
    """
    with open(draft_translation_path, "r", encoding="utf-8") as f:
        translated_segments = json.load(f)

    # If translated segments don't have original_text, merge from transcript
    if translated_segments and "original_text" not in translated_segments[0]:
        with open(english_transcript_path, "r", encoding="utf-8") as f:
            english_segments = json.load(f)

        for trans_seg, eng_seg in zip(translated_segments, english_segments):
            trans_seg["original_text"] = eng_seg.get("text", "")

    refined = refine_translation_with_gemini(
        translated_segments, target_language_name, gemini_model
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(refined, f, indent=2, ensure_ascii=False)

    print(f"  Refined translation saved to: {output_path}")
    return refined


# ===========================================================================
# CLI Entry Point (standalone usage)
# ===========================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Refine draft translation for natural spoken narration"
    )
    parser.add_argument(
        "--transcript", type=str, required=True,
        help="Path to English transcript JSON",
    )
    parser.add_argument(
        "--translation", type=str, required=True,
        help="Path to draft translation JSON",
    )
    parser.add_argument(
        "--language", type=str, required=True,
        help="Target language name (e.g., 'Latin American Spanish')",
    )
    parser.add_argument(
        "--output", type=str, required=True,
        help="Output path for refined translation JSON",
    )
    parser.add_argument(
        "--model", type=str, default="gemini-3.1-pro",
        help="Gemini model to use (default: gemini-3.1-pro)",
    )
    args = parser.parse_args()

    refine_from_files(
        args.transcript,
        args.translation,
        args.language,
        args.output,
        args.model,
    )
