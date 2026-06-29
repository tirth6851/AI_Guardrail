# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Purpose

**AI Guardrail** is a multi-phase Python project that combines content safety filtering with AI integration. It validates user prompts against a banned-word list, then sends safe prompts to the Groq AI API (`llama-3.3-70b-versatile` model) for processing.

---

## Architecture & Data Flow

```
User Input (stdin)
    ↓
tokenization() → Splits input into words, applies lowercase + casefold
    ↓
promtVerification() → Checks tokenized words against banned.txt
    ↓
    ├─ If banned word found → Return False (FLAGGED)
    └─ If all words safe → Return True (ALLOWED)
    ↓ (if True)
LLMrequest() → Sends **original prompt string** to Groq API
    ↓
Extract response via `.choices[0].message.content`
    ↓
Display to user
```

---

## Key Design Decisions

1. **Dual Prompt Storage:** The script maintains TWO versions of user input:
   - `user_input` (string): Original prompt for the Groq API
   - `TokenizedPromt` (list): Tokenized words for banned-word checking
   
   This separation is critical—Groq's API expects a string in the `content` field, not a list.

2. **Global Variable for State:** `user_input` is declared as a global variable and populated by `tokenization()`. This allows `LLMrequest()` to access it without being a return value.

3. **Early Exit in Loop:** The `promtVerification()` loop returns immediately on the first banned word (returns False) and after confirming all words are safe (returns True outside the loop).

4. **Environment-Based Secrets:** The Groq API key is loaded from the `.env` file via `dotenv` and `os.getenv()`, never hardcoded.

---

## Running the Script

```bash
python safety_guard.py
```

The script will prompt for user input. If the input contains no banned words, it sends the prompt to Groq and displays the AI's response.

---

## Files & Responsibilities

- **safety_guard.py**: Main application. Contains tokenization, safety checking, and Groq API integration.
- **banned.txt**: External list of prohibited words/phrases (one per line). Loaded at runtime.
- **.env**: Environment variables file (not committed to git). Must contain `GROQ_API_KEY=<your_key>`.
- **.gitignore**: Excludes `.env` and other sensitive/temporary files.

---

## Dependencies

Install via:
```bash
pip install groq python-dotenv
```

- **groq**: Official Groq Python client for API calls.
- **python-dotenv**: Loads environment variables from `.env` file.

---

## Phase-by-Phase Status

- **Phase 1 ✓ COMPLETE**: Local safety filter with file I/O and text processing.
- **Phase 2 ✓ COMPLETE**: Groq AI integration, API authentication, JSON response parsing.
- **Phase 3 (PLANNED)**: Response filtering—process and validate AI outputs before returning to users.

---

## Known Issues & TODO

- `promtVerification()` currently returns on the first word check. Should check **all** words before returning, but logic is adequate for Phase 2.
- Global `user_input` variable works for single-threaded scripts but should be refactored into function parameters for production code.
- `.env` file and banned words list must be manually created/updated—no initialization automation yet.

---

## When Modifying This Code

- **Adding features to safety checks**: Extend `promtVerification()` or `tokenization()`.
- **Changing the AI model**: Update the `model` parameter in `LLMrequest()` (currently `llama-3.3-70b-versatile`).
- **Integrating Phase 3 response filtering**: Add a new function to process the AI response before printing; call it within or after `LLMrequest()`.
- **Testing API integration**: Make sure `GROQ_API_KEY` is set in `.env` before running.

---

## Tutor Context

This project is being built incrementally with an educational, hands-on approach. The developer is learning:
- Python package management and libraries
- API authentication and environment variables
- HTTP client abstractions and JSON response parsing
- Multi-step debugging and problem-solving

Code style follows pragmatic, learning-focused patterns—not enterprise standards. Prioritize clarity for education over performance optimizations.