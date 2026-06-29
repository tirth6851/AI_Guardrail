# AI_Guardrail

## Overview
A multi-phase Python project that combines content safety filtering with AI integration. The guardrail validates user prompts against banned words, then sends safe prompts to the Groq AI API for processing.

---

## Phase 1: Local Safety Filter ✓ COMPLETE
Implemented content validation using local file I/O and text processing.

* **Step 1:** File I/O – Reading from an external `banned.txt` file instead of hardcoding lists in your script.
* **Step 2:** Text Standardization – Making the user's text lowercase and removing punctuation so no one can bypass the filter using capitalization (e.g. "HACK").
* **Step 3:** Tokenization – Splitting the user's sentence into individual words to check against the banned list efficiently.

---

## Phase 2: Groq AI Integration ✓ COMPLETE
Connected the local safety guardrail to the Groq AI API for automated response generation.

* **Step 1:** Package Management – Installed `groq` library via pip and understood how Python package managers work.
* **Step 2:** API Authentication – Loaded `GROQ_API_KEY` from environment variables using `python-dotenv`, avoiding hardcoded secrets.
* **Step 3:** Network Requests & Groq Client – Instantiated the Groq client with authentication and learned how API client libraries abstract HTTP complexity.
* **Step 4:** JSON Parsing – Extracted the AI's text response from nested JSON response objects using dictionary navigation (`response.choices[0].message.content`).

**Key Features Implemented:**
- Safe prompts bypass the safety filter and are sent to Groq
- Integration with `llama-3.3-70b-versatile` model
- Original prompt text preserved for API calls while tokenized version used for banned-word checking
- Environment-based credential management for security

---

## Phase 3: Enhanced Safety & Response Filtering (PLANNED)
Future work to process and filter AI responses before returning to users.

---

## Architecture Overview
```
User Input
    ↓
Tokenization + Banned Word Check
    ↓ (if safe)
Groq API Call (original text)
    ↓
Extract AI Response
    ↓
Return to User
```

---

## Environment Setup
1. Create a `.env` file in the project root:
   ```
   GROQ_API_KEY=your_groq_api_key_here
   ```
2. Install dependencies:
   ```
   pip install groq python-dotenv
   ```
3. Add or update `banned.txt` with prohibited words/phrases

---

## Running the Script
```bash
python safety_guard.py
```
Follow the prompt to enter your text, and the script will determine if it's safe to send to the AI.