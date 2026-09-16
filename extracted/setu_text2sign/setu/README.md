# SETU · text → sign (pipeline D) with a 2D pixel test avatar

Type English, Hindi or Hinglish. SETU turns it into ISL gloss, animates a pixel
avatar, reads its own signing back with a recognizer, and decides whether to
**emit** the signing, **ask** the author (repair) or **hold**.

```bash
pip install -r requirements.txt
pytest -q                                              # all green = the pipeline works
uvicorn setu.serve.main:app --reload                   # open http://localhost:8000
python -m setu.cli "Do you want water?" --gif water.gif
python -m setu.cli "mujhe kal bank jaana hai"          # shows a repair prompt
python -m setu.cli "mujhe kal bank jaana hai" --resolve 1=TOMORROW
```

`dist/setu_text2sign_demo.html` opens by double-click with no server. It is
limited to the 12 example sentences.

Try these in the viewer:

| Input | What it tests |
|---|---|
| `I went to the bank yesterday.` | time first, verb last → `YESTERDAY ME BANK GO` |
| `What is your name?` | wh-word last, furrowed brows, head tilt |
| `Do you want water?` | round-trip gate catches a confusable sign and fingerspells it |
| `mujhe kal bank jaana hai` | "kal" = yesterday or tomorrow → the author must choose |
| `main kal ghar gaya tha` | the past tense settles "kal" with no question asked |
| `Where is the toilet?` | word with no sign → fingerspelling |
| `I have pain, I need medicine.` | high-stakes banner, stricter threshold |

Tick **landmarks** to see the 21-point MediaPipe-format skeleton the recognizer
sees. See `ARCHITECTURE.md` for the design, the UI contract and the swap-in plan.

> The sign motions are placeholders, not validated ISL. Replace them with
> reference data and review them with Deaf signers before any real use.
