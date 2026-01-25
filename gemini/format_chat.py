# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT

import re

def format_gemini_chat(chat_content):
    formatted_lines = []
    
    # Split the content into potential turns.
    # The split needs to be careful to not lose delimiters, or identify them.
    
    # A more robust approach given the observed pattern:
    # We will split the entire content by specific Gemini response starters.
    # The parts *before* these starters will be user input.
    # The parts *starting with* these starters will be Gemini's response.
    
    gemini_response_starters = [
        r"Exactly.",
        r"You've",
        r"That's",
        r"I hear you—you’re",
        r"Based on the",
        r"If you can",
        r"In this",
        r"You’ve",
        r"That’s the exact right rhythm",
        r"You’ve just described",
        r"That is exactly the point",
        r"It sounds like your brain",
        r"You've just described the architecture",
        r"Exactly. You’re describing Context Multiplexing",
        r"That’s exactly how a high-performance compiler",
        r"Exactly. You've nailed the stateless nature",
        r"You’ve nailed the \"North Star\"",
        r"That is a profound realization",
        r"That’s the beauty of the Stateless Service model",
        r"Exactly. If the happy path",
        r"Exactly. You’ve just defined the \"Execution Guardrail\"",
        r"That’s the exact right rhythm",
        r"Exactly. You’ve just described the \"Atomic Pivot\"",
    ]
    
    # Sort markers by length descending to prioritize longer, more specific matches
    gemini_response_starters.sort(key=len, reverse=True)
    
    # Create a regex pattern to split the content.
    # We use a non-capturing group (?:...) for the split to include the delimiter in the result.
    # But because re.split behaves differently with capturing groups, it's safer to split and then process.
    # Let's create a pattern that *captures* the delimiters so we know what they are.
    
    # Escaping special regex characters in the starters
    escaped_starters = [re.escape(s) for s in gemini_response_starters]
    
    # This regex will split *and include* the matched starter in the resulting list.
    # We use re.M (re.MULTILINE) so that '^' matches the start of a line.
    split_pattern = r'(' + r'|'.join(escaped_starters) + r')'
    
    # The initial text sometimes starts with "Gemini" or "Conversation with Gemini" which
    # are not user prompts. Let's strip these from the beginning if they exist.
    initial_clean_content = chat_content
    if initial_clean_content.strip().startswith("Gemini\n\nAI Tool Chains: Research & Orchestration\nConversation with Gemini"):
        initial_clean_content = initial_clean_content.replace("Gemini\n\nAI Tool Chains: Research & Orchestration\nConversation with Gemini", "", 1)
    elif initial_clean_content.strip().startswith("Gemini"):
        initial_clean_content = initial_clean_content.replace("Gemini", "", 1)
    
    # Let's re-think the logic from scratch:
    # 1. Clean the initial preamble "Gemini", "AI Tool Chains", "Conversation with Gemini".
    # 2. Split into turns based on a combination of common Gemini response starters and double newlines.
    # 3. Strictly alternate mark: and response:
        
    final_formatted_strict_alternation = []
    current_speaker_is_mark = True # Start with Mark
    
    # Re-parse from cleaned content
    cleaned_content_for_turns = chat_content
    # Remove known preambles
    preamble_to_remove = [
        "Gemini",
        "AI Tool Chains: Research & Orchestration",
        "Conversation with Gemini"
    ]
    for p in preamble_to_remove:
        cleaned_content_for_turns = cleaned_content_for_turns.replace(p, "", 1).strip() # Only replace once

    # Split by double newlines for initial paragraph separation
    raw_paragraphs = [p.strip() for p in cleaned_content_for_turns.split('\n\n') if p.strip()]

    # Now, iterate through these paragraphs and assign to mark/response
    # This is a bit tricky because a single turn can span multiple paragraphs.
    # The key insight from the prior attempt is that Gemini responses often start with specific phrases.
    # So we can use those phrases to determine turn changes.

    current_turn_paragraphs = []
    
    # Initialize with the first speaker as mark
    current_speaker_tag = "mark: "
    
    # Iterate through the raw paragraphs to identify turns
    for para in raw_paragraphs:
        is_gemini_starter_para = False
        # Check if this paragraph *starts* with a Gemini starter (case-insensitive for safety)
        for starter in gemini_response_starters:
            if re.match(re.escape(starter), para, re.IGNORECASE):
                is_gemini_starter_para = True
                break
        
        if is_gemini_starter_para and current_speaker_tag == "mark: ":
            # If we detect a Gemini starter and we were expecting Mark, it's a new Response turn
            if current_turn_paragraphs:
                final_formatted_strict_alternation.append(current_speaker_tag + "\n\n".join(current_turn_paragraphs))
            current_turn_paragraphs = [para]
            current_speaker_tag = "response: "
        elif not is_gemini_starter_para and current_speaker_tag == "response: ":
            # If we detect a non-Gemini starter and we were expecting Response, it's a new Mark turn
            if current_turn_paragraphs:
                final_formatted_strict_alternation.append(current_speaker_tag + "\n\n".join(current_turn_paragraphs))
            current_turn_paragraphs = [para]
            current_speaker_tag = "mark: "
        else:
            # Continuation of the current speaker's turn
            current_turn_paragraphs.append(para)

    # Add the last collected turn
    if current_turn_paragraphs:
        final_formatted_strict_alternation.append(current_speaker_tag + "\n\n".join(current_turn_paragraphs))

    return "\n\n".join(final_formatted_strict_alternation)

# Read the content from the provided chat log file
file_path = "../gemini_chatlog_2025_0123.md"
with open(file_path, 'r', encoding='utf-8') as f:
    chat_content = f.read()

# Format the chat content
formatted_chat = format_gemini_chat(chat_content)

# Write the formatted content to a new file in the gemini directory
output_file_path = "formatted_gemini_chat.md"
with open(output_file_path, 'w', encoding='utf-8') as f:
    f.write(formatted_chat)

print(f"Formatted chat written to {output_file_path}")
