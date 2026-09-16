"""Word -> gloss vocabulary for the rule resolver.

Each gloss has a grammatical category the ISL reorder rules use.
The *motion* for each gloss lives in signopsis/generate/signs.py; a gloss that is
in this file but not in signs.py is automatically fingerspelled.
"""
from __future__ import annotations

# gloss -> category
CATEGORY: dict[str, str] = {
    # pronouns / people
    "ME": "PRON", "YOU": "PRON", "HE-SHE": "PRON", "WE": "PRON", "THEY": "PRON",
    "MY": "PRON", "YOUR": "PRON",
    "MOTHER": "NOUN", "FATHER": "NOUN", "FRIEND": "NOUN", "DOCTOR": "NOUN",
    # time
    "YESTERDAY": "TIME", "TODAY": "TIME", "TOMORROW": "TIME", "NOW": "TIME",
    "MORNING": "TIME", "NIGHT": "TIME", "FINISH": "ASPECT",
    # question words
    "WHAT": "WH", "WHERE": "WH", "WHEN": "WH", "WHO": "WH", "WHY": "WH", "HOW": "WH",
    "HOW-MANY": "WH",
    # negation / affirmation
    "NOT": "NEG", "NO": "NEG", "YES": "AFFIRM",
    # verbs
    "GO": "VERB", "COME": "VERB", "EAT": "VERB", "DRINK": "VERB", "HELP": "VERB",
    "WANT": "VERB", "UNDERSTAND": "VERB", "WORK": "VERB", "KNOW": "VERB",
    "LIKE": "VERB", "NEED": "VERB", "SIGN": "VERB",
    # nouns
    "WATER": "NOUN", "FOOD": "NOUN", "HOME": "NOUN", "SCHOOL": "NOUN",
    "HOSPITAL": "NOUN", "BANK": "NOUN", "MONEY": "NOUN", "MEDICINE": "NOUN",
    "PAIN": "NOUN", "TIME": "NOUN", "BOOK": "NOUN", "NAME": "NOUN", "RIVER": "NOUN",
    "TOILET": "NOUN",
    # adjectives / states
    "GOOD": "ADJ", "BAD": "ADJ", "HAPPY": "ADJ", "SAD": "ADJ", "SICK": "ADJ",
    # social phrases
    "HELLO": "PHRASE", "THANK-YOU": "PHRASE", "PLEASE": "PHRASE", "SORRY": "PHRASE",
    "WELCOME": "PHRASE",
}

# multi-word phrases, matched before single words (lowercased, space-joined)
PHRASES_EN: dict[str, list[str]] = {
    "thank you": ["THANK-YOU"],
    "thanks": ["THANK-YOU"],
    "good morning": ["GOOD", "MORNING"],
    "good night": ["GOOD", "NIGHT"],
    "how many": ["HOW-MANY"],
    "how much": ["HOW-MANY"],
    "you're welcome": ["WELCOME"],
    "right now": ["NOW"],
    "sign language": ["SIGN"],
}

EN: dict[str, str] = {
    "i": "ME", "me": "ME", "myself": "ME", "my": "MY", "mine": "MY",
    "you": "YOU", "your": "YOUR", "yours": "YOUR",
    "he": "HE-SHE", "she": "HE-SHE", "him": "HE-SHE", "her": "HE-SHE", "his": "HE-SHE",
    "we": "WE", "us": "WE", "our": "WE", "they": "THEY", "them": "THEY", "their": "THEY",
    "mother": "MOTHER", "mom": "MOTHER", "mum": "MOTHER",
    "father": "FATHER", "dad": "FATHER",
    "friend": "FRIEND", "friends": "FRIEND",
    "doctor": "DOCTOR", "doctors": "DOCTOR",
    "yesterday": "YESTERDAY", "today": "TODAY", "tomorrow": "TOMORROW",
    "now": "NOW", "morning": "MORNING", "night": "NIGHT", "tonight": "NIGHT",
    "what": "WHAT", "where": "WHERE", "when": "WHEN", "who": "WHO", "whom": "WHO",
    "why": "WHY", "how": "HOW",
    "not": "NOT", "no": "NO", "never": "NOT", "yes": "YES", "yeah": "YES",
    "go": "GO", "goes": "GO", "going": "GO", "went": "GO", "gone": "GO",
    "come": "COME", "comes": "COME", "coming": "COME", "came": "COME",
    "eat": "EAT", "eats": "EAT", "eating": "EAT", "ate": "EAT", "eaten": "EAT",
    "drink": "DRINK", "drinks": "DRINK", "drinking": "DRINK", "drank": "DRINK",
    "help": "HELP", "helps": "HELP", "helping": "HELP", "helped": "HELP",
    "want": "WANT", "wants": "WANT", "wanted": "WANT",
    "understand": "UNDERSTAND", "understood": "UNDERSTAND",
    "work": "WORK", "works": "WORK", "working": "WORK", "worked": "WORK", "job": "WORK",
    "know": "KNOW", "knows": "KNOW", "knew": "KNOW",
    "like": "LIKE", "likes": "LIKE", "liked": "LIKE", "love": "LIKE",
    "need": "NEED", "needs": "NEED", "needed": "NEED",
    "water": "WATER", "food": "FOOD", "meal": "FOOD",
    "home": "HOME", "house": "HOME", "school": "SCHOOL",
    "hospital": "HOSPITAL", "clinic": "HOSPITAL",
    "bank": "BANK", "money": "MONEY", "cash": "MONEY",
    "medicine": "MEDICINE", "medicines": "MEDICINE", "tablet": "MEDICINE",
    "pain": "PAIN", "hurts": "PAIN", "hurt": "PAIN", "ache": "PAIN",
    "time": "TIME", "book": "BOOK", "books": "BOOK", "name": "NAME",
    "river": "RIVER", "toilet": "TOILET", "bathroom": "TOILET", "washroom": "TOILET",
    "good": "GOOD", "fine": "GOOD", "great": "GOOD", "bad": "BAD",
    "happy": "HAPPY", "sad": "SAD", "sick": "SICK", "ill": "SICK", "unwell": "SICK",
    "hello": "HELLO", "hi": "HELLO", "hey": "HELLO",
    "please": "PLEASE", "sorry": "SORRY", "welcome": "WELCOME",
}

PAST_FORMS = {"went", "gone", "came", "ate", "eaten", "drank", "helped", "wanted",
              "understood", "worked", "knew", "liked", "needed", "did", "was", "were"}
FUTURE_MARKERS = {"will", "shall", "gonna"}

# function words ISL drops (articles, copula, auxiliaries, most prepositions)
STOP_EN = {
    "a", "an", "the", "is", "am", "are", "was", "were", "be", "been", "being",
    "to", "do", "does", "did", "of", "at", "in", "on", "for", "with", "will",
    "shall", "would", "can", "could", "should", "may", "might", "must", "gonna",
    "and", "so", "very", "really", "just", "some", "any", "this", "that", "it",
    "there", "have", "has", "had", "much", "lot", "lots", "too", "also", "from", "by", "about", "into", "please?",
}

# ---------------------------------------------------------------- Hindi / Hinglish
# romanized + Devanagari. "kal" is deliberately ambiguous (yesterday/tomorrow):
# the resolver must use tense or ask.
HI: dict[str, str] = {
    "main": "ME", "mai": "ME", "mujhe": "ME", "mujhko": "ME", "mera": "MY", "meri": "MY", "mere": "MY",
    "tum": "YOU", "aap": "YOU", "tu": "YOU", "tumhara": "YOUR", "aapka": "YOUR", "aapki": "YOUR",
    "tumhari": "YOUR", "woh": "HE-SHE", "vo": "HE-SHE", "hum": "WE", "humara": "WE",
    "maa": "MOTHER", "mummy": "MOTHER", "papa": "FATHER", "pita": "FATHER", "dost": "FRIEND",
    "aaj": "TODAY", "abhi": "NOW", "subah": "MORNING", "raat": "NIGHT",
    "kya": "WHAT", "kahan": "WHERE", "kahaan": "WHERE", "kab": "WHEN", "kaun": "WHO",
    "kyun": "WHY", "kyon": "WHY", "kaise": "HOW", "kitna": "HOW-MANY", "kitne": "HOW-MANY",
    "nahi": "NOT", "nahin": "NOT", "mat": "NOT", "haan": "YES", "ha": "YES",
    "jaana": "GO", "jana": "GO", "gaya": "GO", "gayi": "GO", "gaye": "GO", "jaunga": "GO",
    "jaungi": "GO", "jaa": "GO", "ja": "GO", "jaata": "GO", "jaati": "GO",
    "aana": "COME", "aaya": "COME", "aayi": "COME", "aaunga": "COME", "aao": "COME",
    "khana": "FOOD", "khaya": "EAT", "khaana": "FOOD", "khaunga": "EAT", "kha": "EAT",
    "peena": "DRINK", "piya": "DRINK", "piyo": "DRINK", "pani": "WATER", "paani": "WATER",
    "madad": "HELP", "chahiye": "WANT", "chahta": "WANT", "chahti": "WANT",
    "samajh": "UNDERSTAND", "samjha": "UNDERSTAND", "samjhi": "UNDERSTAND",
    "kaam": "WORK", "pata": "KNOW", "pasand": "LIKE", "zaroorat": "NEED",
    "ghar": "HOME", "school": "SCHOOL", "aspatal": "HOSPITAL", "hospital": "HOSPITAL",
    "bank": "BANK", "paisa": "MONEY", "paise": "MONEY", "dawai": "MEDICINE", "dawa": "MEDICINE",
    "dard": "PAIN", "samay": "TIME", "waqt": "TIME", "kitab": "BOOK", "naam": "NAME",
    "nadi": "RIVER", "accha": "GOOD", "achha": "GOOD", "theek": "GOOD", "bura": "BAD",
    "khush": "HAPPY", "dukhi": "SAD", "beemar": "SICK", "bimar": "SICK",
    "namaste": "HELLO", "dhanyavaad": "THANK-YOU", "dhanyawad": "THANK-YOU",
    "shukriya": "THANK-YOU", "maaf": "SORRY", "kripya": "PLEASE", "doctor": "DOCTOR",
    # Devanagari
    "मैं": "ME", "मुझे": "ME", "मेरा": "MY", "मेरी": "MY", "तुम": "YOU", "आप": "YOU",
    "आपका": "YOUR", "आज": "TODAY", "अभी": "NOW", "क्या": "WHAT", "कहाँ": "WHERE",
    "कहां": "WHERE", "कब": "WHEN", "कौन": "WHO", "क्यों": "WHY", "कैसे": "HOW",
    "नहीं": "NOT", "हाँ": "YES", "गया": "GO", "गई": "GO", "जाऊँगा": "GO", "जाना": "GO",
    "आया": "COME", "खाना": "FOOD", "पानी": "WATER", "मदद": "HELP", "चाहिए": "WANT",
    "घर": "HOME", "अस्पताल": "HOSPITAL", "बैंक": "BANK", "पैसे": "MONEY", "दवाई": "MEDICINE",
    "दर्द": "PAIN", "नाम": "NAME", "अच्छा": "GOOD", "नमस्ते": "HELLO", "धन्यवाद": "THANK-YOU",
    "डॉक्टर": "DOCTOR", "समझ": "UNDERSTAND",
}
HI_AMBIGUOUS: dict[str, list[str]] = {"kal": ["YESTERDAY", "TOMORROW"], "कल": ["YESTERDAY", "TOMORROW"]}
HI_PAST = {"gaya", "gayi", "gaye", "tha", "thi", "the", "aaya", "aayi", "khaya", "piya",
           "samjha", "samjhi", "गया", "गई", "था", "थी", "आया", "kiya", "hua"}
HI_FUTURE = {"jaunga", "jaungi", "aaunga", "khaunga", "karunga", "karungi", "hoga", "hogi",
             "जाऊँगा", "जाऊंगा", "आऊँगा", "होगा", "ga", "gi"}
STOP_HI = {"hai", "hain", "hoon", "hu", "ho", "tha", "thi", "the", "ko", "se", "ka", "ki",
           "ke", "mein", "me", "par", "pe", "bhi", "toh", "to", "ne", "raha", "rahi", "rahe",
           "kar", "karo", "karna", "karunga", "karungi", "kiya", "hua", "hoga", "hogi", "ek",
           "है", "हैं", "हूँ", "हूं", "था", "थी", "को", "से", "का", "की", "के", "में", "पर",
           "भी", "तो", "ने", "रहा", "रही", "करना", "ga", "gi"}

# Words that signal a high-stakes context (raises thresholds, shows banner)
HIGH_STAKES = {"HOSPITAL", "DOCTOR", "MEDICINE", "PAIN", "SICK"}
HIGH_STAKES_WORDS = {"police", "court", "lawyer", "surgery", "emergency", "allergy",
                     "allergic", "dose", "prescription", "consent", "blood", "ambulance"}

# English back-gloss for the author preview
BACK_GLOSS: dict[str, str] = {
    "ME": "I", "MY": "my", "YOU": "you", "YOUR": "your", "HE-SHE": "he/she", "WE": "we",
    "THEY": "they", "THANK-YOU": "thank you", "HOW-MANY": "how many", "FINISH": "(done)",
    "NOT": "not", "NO": "no",
}
