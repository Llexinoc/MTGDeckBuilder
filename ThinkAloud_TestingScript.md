# ManaForge Think-Aloud Testing: Complete Assessment Materials

**Student Name:** [Your Name]  
**Assignment:** Think-Aloud User Testing  
**Application:** ManaForge — Themed MTG Deckbuilder  
**Date Prepared:** July 21, 2026

---

## TABLE OF CONTENTS
1. Intro Script (with Consent & Think-Aloud Process)
2. App Overview & Use Cases
3. Preliminary Questions
4. Task List
5. Scenarios & Instructions
6. Testing Notes & Observation Prompts
7. Session Timeline

---

## 1. INTRO SCRIPT

### Recording Permission & Consent
*[Read verbatim to participant]*

"Hi [Participant Name], thank you for volunteering to test this application today. Before we begin, I want to explain what we're doing and get your permission for something important.

**I will be recording this session** using [Zoom/OBS/other recording software]. The recording includes video and audio of the interface and our conversation. This recording will be used only to help me analyze how people interact with the app so I can improve it. 

Your name and personal information will not be shared. This recording is confidential and will only be reviewed by me and my instructors as part of a class project.

**Is it okay with you if I record this session?** You can ask me to stop at any time, and you can ask me to delete the recording afterward if you change your mind."

*[Pause for explicit yes/no. Do not proceed without clear consent.]*

---

### Think-Aloud Process Explanation
*[Read verbatim to participant]*

"Great, thank you. Now let me explain the **Think-Aloud process**.

Throughout this session, I'd like you to **narrate what you're thinking and doing out loud**. This might feel a little awkward at first, but it's very helpful for me.

For example:
- 'I'm looking at this box and I'm not sure what it means...'
- 'I think I need to click the Build button...'
- 'I expected to see something different here...'
- 'This is confusing because...'

You don't need perfect sentences — just tell me what's going on in your head as you interact with the app.

**Important:** This is NOT a test of you. There are no right or wrong answers. If you can't figure something out, that's actually really valuable information — it tells me the app needs to be clearer. So please don't feel bad if you get stuck.

I might ask you questions while you're working, like:
- 'What are you thinking right now?'
- 'What do you see on the screen?'
- 'What were you expecting?'

But mostly I'll just listen and observe. Does this make sense? Do you have any questions about the process?"

*[Answer any questions. Reassure them that thinking out loud is okay and encouraged.]*

---

### Preliminary Background Questions
*[Conversational tone — listen actively]*

"Before we dive into the app, I'd like to ask you a few questions about your experience with Magic and deckbuilding. This helps me understand where you're coming from:

1. **Have you played Magic: The Gathering before?** If yes, roughly how long? If no, is this your first time hearing about it?

2. **Have you ever built a Magic deck yourself?** If yes, what format(s)? Was it fun? Difficult?

3. **When you think about building a deck, what's usually the hardest part?** For example: picking cards, figuring out mana, knowing if cards are good, building a curve, etc.

4. **Have you used any online deckbuilding tools before?** Like Moxfield, Archidekt, or others? What was your experience?"

*[Listen and take mental notes about their baseline knowledge. This frames how you interpret their interactions.]*

---

### Transition to Testing
"Okay, thank you for sharing that. Now I'm going to present you with a few scenarios — basically, I'll describe a situation and a goal you're trying to accomplish. Your job is to use ManaForge to achieve that goal.

You have the app open on the screen. Feel free to explore it, click things, type things — just like you would normally use any website. I won't give you step-by-step instructions, but I'm here to observe and listen to your thoughts.

Ready to get started?"

*[Wait for confirmation. Begin recording if not already.]*

---

## 2. APP OVERVIEW & USE CASES
*[Read aloud to participant after intro questions]*

"Let me give you a quick overview of what ManaForge does.

**ManaForge** is an AI-assisted Magic: The Gathering deckbuilder. Here's the basic idea: instead of spending 30 minutes searching through thousands of cards and trying to figure out if they work together, you can just describe your deck idea in plain English and ManaForge builds it for you.

For example:
- Type 'Blue control deck with card draw' → get a full, legal Commander deck
- Type 'Red aggressive dragons' → get a different deck focused on that theme
- Type 'Green creatures budget' → get a casual/jank-themed deck

**Key features:**
- You describe the theme, the app builds it
- You can choose deck format (Commander = 100 cards, or Standard = 60 cards)
- You can adjust the 'power level' — from ultra-casual jank to competitive
- You can add reference cards you want to include
- You see the reasoning behind why it built the deck that way
- All decks are legal and generated by deckbuilding logic (not copied)

Think of it like: theme description → deckbuilding math → finished deck with reasoning.

The goal is to make deckbuilding faster and more accessible whether you're brand new or experienced.

Any questions before we start the scenarios?"

---

## 3. PRELIMINARY QUESTIONS
*[Already integrated into Intro Script, but listed here for reference]*

- Experience with Magic: The Gathering?
- Have you built a deck? Format(s)?
- Hardest part of deckbuilding for you?
- Used other online deckbuilding tools?

---

## 4. TASK LIST
*[Do NOT show these to the participant. These are your notes.]*

### Core Tasks the App Supports:

1. **Build a themed deck from a natural language description**
   - User inputs a theme (e.g., "dragons", "blue control", "lifegain")
   - App generates a complete deck
   - User views the completed deck and its stats

2. **Customize deck format (Commander vs. Standard)**
   - User selects deck format from dropdown
   - App builds deck in correct format (100 vs. 60 cards)
   - User understands the format difference

3. **Adjust power level/bracket**
   - User sets a bracket/power level (casual to competitive)
   - App builds a deck appropriate to that level
   - User can see the difference between power levels

4. **Add reference cards to influence building**
   - User inputs optional card names or deck URLs
   - App incorporates references into building logic
   - User sees if/how references appeared in final deck

5. **Understand deck reasoning and composition**
   - User reads the "How this deck was built" section
   - User views card type distribution, mana curve, card roles (creatures, removal, ramp, etc.)
   - User can explain the deck strategy back to you

6. **Compare different deck variations**
   - User builds the same theme with different constraints
   - User compares versions (casual vs. competitive, different formats, with/without reference cards)
   - User notices differences in card count, mana curve, strategy

---

## 5. SCENARIOS & PARTICIPANT INSTRUCTIONS

### SCENARIO 1: Build Your First Themed Deck

**[Hand participant this card with the scenario. Read it aloud. Then say: "Go ahead and try to build this deck. Think out loud as you go."]**

---

**SCENARIO 1: Dragon Enthusiast**

"You're relatively new to Magic. You've always thought dragons were cool, and your friend told you that you could build a dragon-themed Commander deck, but you have no idea where to start. There are 30,000+ Magic cards and you don't know which dragons are good or how to balance them.

You decide to try ManaForge to see if it can help you build a dragon deck quickly, without having to learn all the card rules first."

**Your Goal:** Use ManaForge to build a dragon-themed Commander deck. Once the deck is generated, spend a moment looking at what it created. Tell me: does it make sense? Do you see mostly dragon creatures?

---

**[After participant finishes: "What did you think? Was that what you expected?"]*

---

### SCENARIO 2: You Want a More Casual Deck

**[Hand participant this card. Read it aloud. Then say: "Try to make that adjustment in the app. Think out loud."]**

---

**SCENARIO 2: Fun Over Winning**

"The dragon deck you just built looks strong and competitive. But you remember your friend mentioning there's a way to adjust how serious a deck is. You want to build a dragon deck that's more casual and fun — the kind where goofy plays and theme matter more than winning, because you're playing with friends just for laughs."

**Your Goal:** Using ManaForge, build a dragon deck again, but this time adjust it to be more casual. Can you spot a difference between this casual version and the competitive one you built before?

---

**[After participant finishes: "What changed? How is this deck different?"]*

---

### SCENARIO 3: Add Your Favorite Card

**[Hand participant this card. Read it aloud. Then say: "Try building with a reference card. Think out loud."]**

---

**SCENARIO 3: Including a Card You Love**

"You have a card you absolutely love — maybe it's a rare card you just pulled, or a card that means something to you. You want to make sure it's in your new deck. You've heard that some deckbuilding apps let you say 'I want this card in my deck' before building.

You want to build a blue control deck, and you want to make sure it includes [suggestion: Counterspell, or let them pick a card they know]."

**Your Goal:** Build a blue control deck while adding a reference card. See if the app incorporates your preference into the final deck. Do you think your reference card ended up in the deck?

---

**[After participant finishes: "Do you see your card in the deck? How would you know?"]*

---

### SCENARIO 4: Understand the Deck Strategy

**[Hand participant this card. Read it aloud. Then say: "Explore the deck and tell me what you think it's doing."]**

---

**SCENARIO 4: Learning How Decks Work**

"You've built a few decks now and they look interesting, but you're curious — why did ManaForge choose these specific cards? What's the strategy? Why are there so many creatures vs. spells? Why these lands?

You want to understand the reasoning so you can learn how deckbuilding actually works."

**Your Goal:** Look at the deck details, the reasoning section, and the stats. Then explain back to me: What is this deck trying to do? Why does it have the cards it does? Don't worry if you don't understand everything — just share what you see.

---

**[After participant finishes: "So in your own words, what's the strategy of this deck?"]*

---

### SCENARIO 5: Switch Formats

**[Hand participant this card. Read it aloud. Then say: "Build a dragon deck in the other format. Notice what's different."]**

---

**SCENARIO 5: Smaller Format, Faster Games**

"Your usual playgroup plays Commander (100-card singleton), but next week you're going to a local game store's Friday Night Magic event, which uses Standard format (60-card constructed). The decks play faster and meaner.

You want to quickly adapt your dragon concept to work in this smaller, faster format."

**Your Goal:** Build a dragon deck in Standard format instead of Commander. What's different about this deck? Why do you think it's different?

---

**[After participant finishes: "How does this deck feel different from the Commander dragon deck?"]*

---

## 6. TESTING NOTES & OBSERVATION PROMPTS

### If Participant Gets Stuck or Quiet:

Use these prompts to encourage think-aloud (do NOT give instructions):

- "What are you looking for right now?"
- "What do you see on the screen?"
- "What were you expecting to see?"
- "What are you thinking right now?"
- "Why did you click on that?"
- "Do you have any questions about what you're seeing?"
- "What would you try next?"

### DO NOT:
- Point them to a button or menu
- Explain how to use the app
- Suggest the "right" way to do something
- Interrupt their problem-solving

### Things to Observe & Note:

**Confusion Points:**
- Where does the participant look first?
- What terminology confuses them? (deck format, archetype, power level, bracket)
- Do they understand what "reference cards" means?
- Can they tell the difference between Commander and Standard?

**Smooth Interactions:**
- Do they naturally find the text input box?
- Do they understand they need to click "Build"?
- Can they find and read the deck reasoning?
- Do they notice the deck stats and mana curve?

**Engagement Signals:**
- Do they ask questions about the deck?
- Do they comment on the card choices?
- Do they seem interested in trying another build?
- Do they explore the interface voluntarily?

---

## 7. SESSION TIMELINE

| Time | Activity | Duration |
|------|----------|----------|
| 0:00-1:00 | Welcome, recording consent | 1 min |
| 1:00-2:00 | Think-aloud explanation | 1 min |
| 2:00-3:00 | App overview | 1 min |
| 3:00-5:00 | Preliminary questions | 2 min |
| 5:00-11:00 | Scenarios 1-5 (think-aloud) | 6 min |
| 11:00-12:00 | Wrap-up & thank you | 1 min |
| **Total** | | **~12 min** |

---

## RECORDING & TECHNICAL SETUP

### Before You Start Recording:

- [ ] Recording software (Zoom, OBS, etc.) is open
- [ ] Microphone is working and positioned well
- [ ] Screen shows the entire app interface
- [ ] You can see/hear the participant clearly
- [ ] Backup audio recording is active (optional but recommended)
- [ ] All notifications are silenced
- [ ] Phone is on silent

### After Recording:

- [ ] Stop recording
- [ ] Export as .mp4 (unedited)
- [ ] Name: `Tester1_ManaForge_ThinkAloud.mp4` and `Tester2_ManaForge_ThinkAloud.mp4`
- [ ] Verify both audio tracks are clear
- [ ] Save both recordings for submission

---

## DEBRIEF (End of Session)

**[After all scenarios, while still recording:]**

"That was really helpful, thank you. Before we wrap up, a couple quick final questions:

1. **Overall, what was your first impression of ManaForge?** Did it do what you expected?

2. **Was there anything confusing or frustrating about using it?**

3. **If you were going to suggest one thing to improve, what would it be?**

4. **Would you use this tool again to build decks?**"

*[Listen to their responses. Thank them genuinely.]*

"Thank you so much for your time and thoughtfulness. This feedback is really valuable and will help me improve the app. I really appreciate it!"

---

## SUBMISSION CHECKLIST

- [ ] This document (intro script + tasks + scenarios) formatted as PDF
- [ ] Filename: `[LastName]_[FirstName]_Week#_ThinkAloudTesting.pdf`
- [ ] Recording 1: `Tester1_ManaForge_ThinkAloud.mp4` (unedited)
- [ ] Recording 2: `Tester2_ManaForge_ThinkAloud.mp4` (unedited)
- [ ] Both files uploaded to assignment submission
- [ ] Both recordings are clear (video and audio)
- [ ] Both testers are identifiable by voice
- [ ] No sensitive personal information in recordings

---

## NOTES FOR TEST ANALYSIS (Post-Testing)

After completing both sessions, look for:

1. **Common confusion points** — Did both testers struggle with the same feature?
2. **Terminology issues** — What words did testers misunderstand?
3. **Smooth interactions** — What worked intuitively?
4. **Engagement** — Did testers seem interested and invested?
5. **Feature requests** — What did they want that wasn't there?
6. **Accessibility** — Was the interface readable? Easy to navigate?
7. **Validity** — Did scenarios feel realistic? Did they understand their goal?

---

**End of Testing Materials**
