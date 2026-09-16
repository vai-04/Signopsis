# ISL gloss rules (v1, for review by a Deaf ISL consultant)

These rules drive `signopsis/resolve/rules.py` and are pasted verbatim into the LLM
prompt when `SIGNOPSIS_RESOLVER=ollama`. Edit this file, not the code, when a rule
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

---

## Reading ISL back into English (sign → text)

These rules are in `signopsis/resolve/sign_to_text.py`. Rules 13 and 14 describe
how the resolver picks between readings, and rules 15 to 24 how it builds the
sentence.

13. **Context picks between look-alike signs** only when the evidence is
    strong: ISL word order, signs that often go together (WANT + WATER), the
    last few sentences, and this user's past answers. If two readings are
    still close, **ask**.
14. **A repair answer is remembered** for this user in the same context, so
    the question is not asked twice.
15. **Time sign** → tense. YESTERDAY or FINISH → past; TOMORROW → future;
    otherwise present. The time word goes first ("Yesterday I went …").
16. **Verb-final → SVO.** `ME BANK GO` → "I go to the bank". GO and COME take
    "to", except before *home*.
17. **Question word last → question word first**, with do-support:
    `YOU WORK WHERE` → "Where do you work?"
18. **Raised brows over the phrase** (face) → yes/no question, even without a
    question sign: `YOU SICK` + raised brows → "Are you sick?"
19. **NOT, or a head shake during a sign** → negation.
20. **No verb** → "is/am/are": `ME HAPPY` → "I am happy";
    `MY NAME FS:PRIYA` → "My name is Priya". **[REVIEW]** PAIN reads as
    "have pain".
21. **A repeated subject pronoun starts a new sentence**:
    `ME PAIN ME MEDICINE NEED` → "I have pain. I need medicine."
22. **PLEASE + verb** → polite request: `PLEASE ME HELP` → "Please help me."
23. **Greetings** become their own sentences.
24. **Hindi output** is SOV with basic agreement and ergative/dative
    subjects (मैंने / मुझे). It is **rough**: it needs review by a native
    speaker, and gender is always masculine singular or respectful plural.
