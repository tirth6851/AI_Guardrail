# AI Guardrail - Development Plan

## Overall Vision

Build a multi-layered AI safety system that:
1. **Phase 1**: Validates user input against a local banned-word list
2. **Phase 2**: Integrates with Groq AI to process safe prompts
3. **Phase 3**: Validates AI responses before returning them to the user

---

## Phase 1: Local Safety Filter ✅ COMPLETE

### Objectives
Implement content validation using local file I/O and text processing without external API calls.

### Completed Steps
- ✅ **File I/O**: Read banned words from external `banned.txt` file
- ✅ **Text Standardization**: Normalize user input (lowercase, remove punctuation via `casefold()`)
- ✅ **Tokenization**: Split input into individual words for efficient matching

### Key Functions
- `tokenization()`: Accepts user input, applies `.strip().casefold()`, splits on word boundaries using regex
- `promtVerification()`: Checks tokenized words against banned list, returns boolean

### Known Limitations
- Only checks for exact word matches (phrase-level detection not implemented)
- Case-folding handles ASCII but not Unicode variants
- No context awareness (e.g., "bad" in "badminton" still flags)

---

## Phase 2: Groq AI Integration ✅ COMPLETE

### Objectives
Connect the local safety filter to the Groq AI API for automated response generation on safe prompts.

### Completed Steps
- ✅ **Package Management**: Installed `groq` library via pip
- ✅ **API Authentication**: Loaded `GROQ_API_KEY` from `.env` using `python-dotenv`
- ✅ **Groq Client**: Instantiated `Groq(api_key=key)` for API calls
- ✅ **JSON Response Parsing**: Extracted AI text via `response.choices[0].message.content`
- ✅ **Integration**: Safe prompts automatically sent to Groq for processing

### Key Functions
- `LLMrequest()`: Makes API call to Groq with the original user prompt, extracts and displays response

### Architecture Decision
- **Dual Prompt Storage**: 
  - Original prompt (string) → sent to Groq
  - Tokenized prompt (list) → used for banned-word checking
  - This prevents information loss and maintains API compatibility

### Current Behavior
```
Safe Prompt → Groq API → AI Response → Display
Banned Prompt → Rejected with "FLAGGED" message
```

### Known Limitations
- No response filtering (AI output not validated)
- No error handling for API failures (timeouts, rate limits, network errors)
- No logging of interactions
- Uses global variable for state (`user_input`)

---

## Phase 3: Response Validation & Filtering ✅ COMPLETE (via local classifiers)

> **Superseded design note:** the step-by-step banned-word/regex plan below was
> the *original* Phase-3 sketch. It was replaced by self-owned TF-IDF+LR
> classifiers (`judge_input`/`judge_output`, trained on `wildguardmix`) plus a
> hardening pass (normalization, weapons backstop, injection heuristics, PII
> redaction, eval harness). See `CLAUDE.md`, `ROADMAP.md`, and `HANDOFF.md`. The
> text below is kept as history, not as the current plan.

### Objectives
Validate and filter AI responses to ensure they meet safety standards before returning to the user.

### Proposed Steps

#### Step 1: Response Extraction & Analysis
- [ ] Implement `analyze_response()` function to examine AI output
- [ ] Identify response structure: full text, confidence scores, tokens used
- [ ] Log response metadata (model used, tokens, timestamp)

#### Step 2: Response-Level Filtering
- [ ] Check AI response for banned/harmful content using same banned-word list
- [ ] Implement regex-based pattern matching for common unsafe outputs (URLs, personal info patterns, etc.)
- [ ] Add severity levels: "warn", "block", "redact"

#### Step 3: Context-Aware Safety
- [ ] Build a mapping of prompt intent to expected response type
- [ ] Flag responses that don't match expected intent (e.g., prompt asks for code, response is poetry)
- [ ] Detect prompt injection attempts in the AI's response

#### Step 4: User Feedback & Logging
- [ ] Log all interactions (prompt, AI response, filter decisions) to a local file or database
- [ ] Provide meaningful error messages when responses are filtered
- [ ] Add optional "why was this filtered?" explanations

#### Step 5: Refinement & Testing
- [ ] Create test suite with known safe/unsafe AI responses
- [ ] Tune filtering sensitivity to balance safety vs. usability
- [ ] Document filter behavior and limitations

### Proposed Functions
```python
def analyze_response(response_object):
    """Extract and structure AI response data."""
    
def filter_response(text, banned_list):
    """Check response text against banned words and patterns."""
    
def log_interaction(prompt, response, filter_result):
    """Record interaction to audit trail."""
```

### Architectural Changes
- Create a response handler module (separate from safety checks)
- Add a logging/audit module for tracking all interactions
- Consider database storage for logs (SQLite to start)

### Error Handling to Implement
- Groq API timeouts → retry with backoff
- Rate limiting → queue requests
- Network errors → graceful degradation
- Malformed responses → fallback to default message

---

## Phase 4+: Advanced Features (Future Consideration)

- [ ] Multi-model support (rotate between different Groq models)
- [ ] Customizable banned-word lists per user/context
- [ ] Machine learning-based content classification
- [ ] Conversation history & context awareness
- [ ] Web UI for easier interaction
- [ ] API server mode (Flask/FastAPI)
- [ ] Performance metrics & monitoring

---

## Testing Strategy

### Phase 1 & 2 (Current)
- Manual testing with various inputs
- Test with empty banned.txt, single word, multiple words
- Verify API key loading and error handling

### Phase 3 (When implemented)
- Create `test_responses.py` with:
  - Safe AI responses (should pass)
  - Unsafe AI responses (should be flagged)
  - Edge cases (empty response, truncated text)
- Unit tests for each filter function
- Integration tests for full pipeline

---

## Development Guidelines

### Code Style
- Keep functions small and focused
- Use descriptive variable names (e.g., `banned_list` not `bl`)
- Add inline comments for non-obvious logic

### Before Moving to Next Phase
- [ ] Manual testing complete
- [ ] No unhandled exceptions
- [ ] README updated with new features
- [ ] Changes committed to git

### Tutoring Context
Development is intentionally hands-on and incremental. Focus on:
- Understanding WHY each step matters
- Learning underlying concepts before implementation
- Building confidence with small, working pieces
- Refactoring/improving code after learning new concepts

---

## Milestones & Timeline

| Phase | Status | Est. Completion |
|-------|--------|-----------------|
| Phase 1 | ✅ Complete | Done |
| Phase 2 | ✅ Complete | Done |
| Phase 3 | 🔄 Planned | Next |
| Phase 4+ | ⏸️ On Hold | Future |

---

## Notes for Future Development

- Groq models available: Check Groq docs for latest models (currently using `llama-3.3-70b-versatile`)
- Banned list can be extended with regex patterns for more sophisticated matching
- Consider cost optimization: Groq has free tier limits—monitor token usage
- Response filtering may need tuning based on real-world usage patterns