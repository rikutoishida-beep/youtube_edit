#!/usr/bin/env python3
"""SRT subtitle processing script for YouTube video editing."""

import re
import os

def parse_time(time_str):
    """Parse SRT timecode to milliseconds."""
    time_str = time_str.strip()
    match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_str)
    if not match:
        raise ValueError(f"Invalid time format: {time_str}")
    h, m, s, ms = match.groups()
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)

def format_time(ms):
    """Format milliseconds to SRT timecode."""
    if ms < 0:
        ms = 0
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def parse_srt(filepath):
    """Parse SRT file into list of blocks."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = []
    pattern = r'(\d+)\n話者\s+(\d+)\s+(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\n*$)'

    for match in re.finditer(pattern, content, re.DOTALL):
        idx = int(match.group(1))
        speaker = int(match.group(2))
        start = parse_time(match.group(3))
        end = parse_time(match.group(4))
        text = match.group(5).strip()
        blocks.append({
            'index': idx,
            'speaker': speaker,
            'start': start,
            'end': end,
            'text': text
        })

    return blocks

def group_consecutive_speaker(blocks):
    """Group consecutive blocks by same speaker into segments."""
    if not blocks:
        return []

    segments = []
    current = {
        'speaker': blocks[0]['speaker'],
        'start': blocks[0]['start'],
        'end': blocks[0]['end'],
        'blocks': [blocks[0]]
    }

    for block in blocks[1:]:
        if block['speaker'] == current['speaker']:
            current['end'] = block['end']
            current['blocks'].append(block)
        else:
            segments.append(current)
            current = {
                'speaker': block['speaker'],
                'start': block['start'],
                'end': block['end'],
                'blocks': [block]
            }
    segments.append(current)
    return segments

# Sentence-ending patterns (without trailing punctuation)
SENTENCE_ENDINGS = re.compile(
    r'(ください|ます|です|した|ました|ません|ですね|ますね|ですよ|ますよ'
    r'|ですが|ますが|ですけど|ますけど|ですかね|ますかね'
    r'|だ|んだ|のだ|ものだ|わけだ|よね|かな|だな|ですな'
    r'|る|いる|ている|くる|てくる|ていく|ない|れない'
    r'|た|った|いた|ていた|なかった'
    r'|よ|ね|な|さ|ぞ|わ|かも|けど|から|し|が)$'
)

def smart_merge_blocks(blocks_in_segment):
    """Merge blocks within a segment, detecting sentence boundaries from time gaps."""
    if not blocks_in_segment:
        return []

    # Build sub-sentences based on time gaps
    sub_sentences = []
    current_texts = [blocks_in_segment[0]['text']]
    current_start = blocks_in_segment[0]['start']
    current_end = blocks_in_segment[0]['end']

    for i in range(1, len(blocks_in_segment)):
        prev_block = blocks_in_segment[i - 1]
        curr_block = blocks_in_segment[i]
        gap = curr_block['start'] - prev_block['end']

        # Check if previous text ends at a sentence boundary
        prev_text_so_far = ''.join(current_texts)
        ends_sentence = bool(SENTENCE_ENDINGS.search(prev_text_so_far))

        # If there's a significant gap AND the previous text ends a sentence,
        # treat as separate sentence
        if gap > 300 and ends_sentence and len(prev_text_so_far) > 3:
            # Add period if missing
            merged = ''.join(current_texts)
            if not merged.endswith(('。', '？', '！', '、', '…')):
                merged += '。'
            sub_sentences.append({
                'text': merged,
                'start': current_start,
                'end': current_end
            })
            current_texts = [curr_block['text']]
            current_start = curr_block['start']
            current_end = curr_block['end']
        else:
            current_texts.append(curr_block['text'])
            current_end = curr_block['end']

    # Don't forget the last group
    merged = ''.join(current_texts)
    sub_sentences.append({
        'text': merged,
        'start': current_start,
        'end': current_end
    })

    return sub_sentences

def apply_corrections(text):
    """Apply name corrections."""
    text = text.replace('ゴマスケさん', 'ごますけさん')
    text = text.replace('シリンさん', '白臨さん')
    text = text.replace('しりんさん', '白臨さん')
    text = text.replace('こたさん', 'ことさん')
    text = text.replace('まことさん', 'ことさん')
    return text

def remove_fillers(text):
    """Remove fillers from text."""
    # Remove standalone fillers
    if text.strip() in ('あの、', 'あの', 'あのー', 'あのー、', 'えー', 'えー、', 'えーと', 'えーと、'):
        return ''

    # Remove leading fillers
    text = re.sub(r'^あの、', '', text)
    text = re.sub(r'^あのー、?', '', text)
    text = re.sub(r'^えー、?', '', text)

    # Remove fillers after commas (e.g., "と、あの、" → "と、")
    text = re.sub(r'、あの、', '、', text)
    text = re.sub(r'、あのー、?', '、', text)
    text = re.sub(r'、えー、?', '、', text)

    # Remove fillers after sentence boundaries
    text = re.sub(r'。あの、', '。', text)
    text = re.sub(r'。あのー、?', '。', text)
    text = re.sub(r'。えー、?', '。', text)

    # Remove fillers after ね (e.g., "ですねあの、" → "ですね。")
    text = re.sub(r'ねあの、', 'ね。', text)
    text = re.sub(r'ねあのー、?', 'ね。', text)

    return text

def fix_stutters(text):
    """Fix stuttering/repetitions."""
    text = re.sub(r'二-二-二百', '二百', text)
    return text

def clean_text(text):
    """Clean up whitespace and formatting."""
    # Remove all spaces (AI transcription adds unnecessary spaces)
    text = re.sub(r'\s+', '', text)
    # Re-add space within English words/acronyms where needed
    # (AI text doesn't have meaningful spaces to preserve)
    text = re.sub(r'--', '--', text)
    return text.strip()

def split_text_for_display(text, max_chars=15, hard_max=20):
    """Split text into display-friendly chunks.
    Target max_chars (15), allow up to hard_max (20) to avoid mid-word splits."""
    if len(text) <= max_chars:
        return [text]

    results = []

    # First split at sentence boundaries
    sentences = re.split(r'(?<=[。！？])', text)
    sentences = [s for s in sentences if s.strip()]

    for sentence in sentences:
        if len(sentence) <= max_chars:
            results.append(sentence)
        else:
            # Try splitting at 、
            parts = re.split(r'(?<=、)', sentence)
            parts = [p for p in parts if p.strip()]

            current = ''
            for part in parts:
                if len(current + part) <= max_chars:
                    current += part
                else:
                    if current:
                        results.append(current)
                    if len(part) <= max_chars:
                        current = part
                    elif len(part) <= hard_max:
                        # Allow slightly longer block to avoid bad splits
                        current = part
                    else:
                        sub_parts = split_at_phrases(part, max_chars, hard_max)
                        results.extend(sub_parts[:-1])
                        current = sub_parts[-1] if sub_parts else ''
            if current:
                results.append(current)

    return results if results else [text]

# Patterns that should NOT be split (common multi-char phrases)
UNSPLITTABLE = {
    'と': set('いうえかころっ'),  # という, とか, ところ, とっ
    'も': set('のうら'),  # もの, もう, もら(う)
    'に': set('くつ'),  # にく(い), につ(いて)
    'ん': set('なだでの'),  # そんな, なんだ, なんで, なんの
    'て': set('いおくけしもは'),  # ている, ておく, etc.
    'の': set('にはがでも中'),  # のに, のは, のが, 世の中
    'で': set('すしもき'),  # です, でし(た), でも, でき(る)
    'は': set('な'),  # はな(い)
}

def split_at_phrases(text, max_chars=15, hard_max=20):
    """Split text at natural Japanese phrase boundaries."""
    if len(text) <= max_chars:
        return [text]

    results = []
    remaining = text

    while len(remaining) > max_chars:
        best_pos = -1
        best_quality = 0  # Higher = better split point

        # Search for split points from max_chars down to 4
        search_limit = min(hard_max, len(remaining))
        for i in range(search_limit, 3, -1):
            char = remaining[i-1]
            next_char = remaining[i] if i < len(remaining) else ''

            # Check if this would create an unsplittable pattern
            if char in UNSPLITTABLE and next_char in UNSPLITTABLE.get(char, set()):
                continue

            quality = 0

            # Punctuation: best split point
            if char in '、。！？':
                quality = 100
            # Particles (safe ones)
            elif char in 'をがは' and next_char not in 'っ':
                quality = 80 if i <= max_chars else 60
            elif char == 'ば':  # Conditional form (取れば, etc.)
                quality = 78 if i <= max_chars else 58
            elif char == 'に' and next_char not in UNSPLITTABLE.get('に', set()):
                quality = 75 if i <= max_chars else 55
            elif char == 'で' and next_char not in UNSPLITTABLE.get('で', set()):
                quality = 70 if i <= max_chars else 50
            elif char == 'へ':
                quality = 70 if i <= max_chars else 50
            elif char == 'と' and next_char not in UNSPLITTABLE.get('と', set()):
                quality = 65 if i <= max_chars else 45
            elif char == 'も' and next_char not in UNSPLITTABLE.get('も', set()):
                quality = 65 if i <= max_chars else 45
            elif char == 'て' and next_char not in UNSPLITTABLE.get('て', set()):
                quality = 60 if i <= max_chars else 40
            elif char == 'の' and next_char not in UNSPLITTABLE.get('の', set()):
                quality = 55 if i <= max_chars else 35
            elif char == 'ん' and next_char not in UNSPLITTABLE.get('ん', set()) and i > 4:
                quality = 50 if i <= max_chars else 30

            # Prefer positions closer to max_chars
            if quality > 0 and i <= max_chars:
                quality += 10

            if quality > best_quality:
                best_quality = quality
                best_pos = i

        if best_pos >= 3:
            results.append(remaining[:best_pos])
            remaining = remaining[best_pos:]
        else:
            # Force split at max_chars as last resort
            results.append(remaining[:max_chars])
            remaining = remaining[max_chars:]

    if remaining:
        results.append(remaining)

    return results

def distribute_timecodes(segments_text, total_start, total_end, min_duration=1000):
    """Distribute timecodes proportionally by character count."""
    if not segments_text:
        return []

    total_duration = total_end - total_start
    total_chars = sum(len(t) for t in segments_text)

    if total_chars == 0:
        return [{'text': t, 'start': total_start, 'end': total_end} for t in segments_text]

    result = []
    current_start = total_start

    for i, text in enumerate(segments_text):
        char_ratio = len(text) / total_chars
        duration = int(total_duration * char_ratio)

        if duration < min_duration and len(segments_text) > 1:
            duration = min_duration

        current_end = current_start + duration

        if i == len(segments_text) - 1:
            current_end = total_end
        elif current_end > total_end:
            current_end = total_end

        result.append({
            'text': text,
            'start': current_start,
            'end': current_end
        })
        current_start = current_end

    return result

def process_segments(segments):
    """Process all segments: merge, correct, clean, split into sub-sentences."""
    all_sub_sentences = []

    for seg in segments:
        # Smart merge blocks within segment, detecting sentence boundaries
        sub_sentences = smart_merge_blocks(seg['blocks'])

        for sub in sub_sentences:
            text = sub['text']

            # Apply corrections
            text = apply_corrections(text)
            text = fix_stutters(text)
            text = clean_text(text)
            text = remove_fillers(text)

            # Handle special stutters
            if '守秘義務遵守の、守秘義務遵守のため、' in text:
                text = text.replace('守秘義務遵守の、守秘義務遵守のため、', '守秘義務遵守のため、')
            text = re.sub(r'職場でスト?レス--職場でストレス', '職場でストレス', text)

            if text.strip():
                all_sub_sentences.append({
                    'speaker': seg['speaker'],
                    'start': sub['start'],
                    'end': sub['end'],
                    'text': text.strip()
                })

    return all_sub_sentences

def create_output_blocks(processed_sentences):
    """Create final output blocks with proper splitting and timecodes."""
    all_blocks = {1: [], 2: []}

    for sent in processed_sentences:
        text = sent['text']
        speaker = sent['speaker']

        display_parts = split_text_for_display(text)
        timed_parts = distribute_timecodes(display_parts, sent['start'], sent['end'])

        for part in timed_parts:
            if part['text'].strip():
                all_blocks[speaker].append(part)

    return all_blocks

def merge_short_blocks(blocks, min_duration=1000, max_gap=500):
    """Merge blocks that are too short, only if close together."""
    if not blocks:
        return blocks

    result = [blocks[0]]

    for block in blocks[1:]:
        duration = block['end'] - block['start']
        prev_duration = result[-1]['end'] - result[-1]['start']
        gap = block['start'] - result[-1]['end']
        combined_text = result[-1]['text'] + block['text']

        if gap <= max_gap and len(combined_text) <= 20:
            if duration < min_duration:
                result[-1]['text'] = combined_text
                result[-1]['end'] = block['end']
            elif prev_duration < min_duration:
                result[-1]['text'] = combined_text
                result[-1]['end'] = block['end']
            else:
                result.append(block)
        else:
            result.append(block)

    return result

def write_srt(blocks, filepath):
    """Write blocks to SRT file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        for i, block in enumerate(blocks, 1):
            f.write(f"{i}\n")
            f.write(f"{format_time(block['start'])} --> {format_time(block['end'])}\n")
            f.write(f"{block['text']}\n")
            f.write("\n")

def main():
    input_file = '/home/user/youtube_edit/input_srt/Bパターン_4.srt'
    output_dir = '/home/user/youtube_edit/output_srt'

    print("Parsing SRT file...")
    blocks = parse_srt(input_file)
    print(f"  Parsed {len(blocks)} blocks")

    print("Grouping consecutive speaker blocks...")
    segments = group_consecutive_speaker(blocks)
    print(f"  Created {len(segments)} segments")

    print("Processing segments...")
    processed = process_segments(segments)
    print(f"  Created {len(processed)} sub-sentences")

    print("Creating output blocks...")
    speaker_blocks = create_output_blocks(processed)

    for speaker in [1, 2]:
        speaker_blocks[speaker] = merge_short_blocks(speaker_blocks[speaker])

    print(f"  Speaker 1 (ごますけ): {len(speaker_blocks[1])} blocks")
    print(f"  Speaker 2 (白臨こと): {len(speaker_blocks[2])} blocks")

    output1 = os.path.join(output_dir, '話者1（ごますけ）.srt')
    output2 = os.path.join(output_dir, '話者2（白臨こと）.srt')

    write_srt(speaker_blocks[1], output1)
    write_srt(speaker_blocks[2], output2)

    print(f"\nOutput written to:")
    print(f"  {output1}")
    print(f"  {output2}")

    # Validation
    print("\nValidation:")
    for speaker, name in [(1, 'ごますけ'), (2, '白臨こと')]:
        bks = speaker_blocks[speaker]
        short_blocks = [b for b in bks if b['end'] - b['start'] < 1000]
        long_texts = [b for b in bks if len(b['text']) > 20]
        print(f"  Speaker {speaker} ({name}):")
        print(f"    Total blocks: {len(bks)}")
        print(f"    Blocks < 1 second: {len(short_blocks)}")
        print(f"    Texts > 20 chars: {len(long_texts)}")
        if long_texts:
            for b in long_texts[:5]:
                print(f"      '{b['text']}' ({len(b['text'])} chars)")
        if short_blocks:
            print(f"    Short blocks sample:")
            for b in short_blocks[:3]:
                dur = b['end'] - b['start']
                print(f"      '{b['text']}' ({dur}ms)")

if __name__ == '__main__':
    main()
