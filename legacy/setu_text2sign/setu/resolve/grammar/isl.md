# ISL gloss rules (v1, for review by a Deaf ISL consultant)

These rules drive `setu/resolve/rules.py` and are pasted verbatim into the LLM
prompt when `SETU_RESOLVER=ollama`. Edit this file, not the code, when a rule
is wrong, then ask a developer to update the matching rule in the code.
Every rule marked **[REVIEW]** is an assumption we have not checked yet.

1. **Order:** TIME first, then TOPIC (who/what), then COMMENT (verb). ISL is
   verb-final (subject-object-verb).
   `I went to the bank yesterday` → `YESTERDAY ME BANK GO`
2. **Drop** articles (a, an, the), the copula (is/am/are/was), auxiliaries
   (do, will, can) and most prepositions (to, at, in).
3. **Question words go last** and the eyebrows are **furrowed** for the whole
   question. `What is your name?` → `YOUR NAME WHAT`
4. **Yes/no questions:** keep statement order, **raise the eyebrows** for the
   whole question and tilt the head forward on the last sign.
5. **Negation:** `NOT` comes after the verb, with a **headshake** during it.
   `I don't understand` → `ME UNDERSTAND NOT`
6. **Completed action:** past tense with no time word → add `FINISH` after the
   verb. **[REVIEW]**
7. **Names and unknown words are fingerspelled** (`FS:PRIYA`).
8. **Greetings and social phrases** (HELLO, THANK-YOU, SORRY) come first.
9. **Hindi "kal"** can mean yesterday or tomorrow. Use the verb tense (gaya/tha
   → YESTERDAY, jaunga/hoga → TOMORROW). If the tense doesn't settle it,
   **ask the author**. Never guess.
10. **Commas and sentence ends** close a clause. Words are never moved from one
    clause into another.
11. **Pronouns** are signed by pointing: ME at the chest, YOU forward,
    HE-SHE to the side. **[REVIEW: placement should follow the referent's
    location once it has been set up in space]**
12. **Number incorporation** (e.g. THREE-DAYS) is not implemented yet. Numbers
    are fingerspelled for now. **[TODO]**
