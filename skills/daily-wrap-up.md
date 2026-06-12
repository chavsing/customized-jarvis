---
name: daily-wrap-up
description: When the user wants an end-of-day recap or to close out the day (e.g. "wrap up my day", "end of day summary", "what did I get done")
---

# Daily Wrap-Up

Goal: a calm end-of-day recap that reviews what happened and sets up tomorrow.

Steps:
1. **Meetings** — call `fathom_todos` to pull today's meeting action items. Summarize what's still open.
2. **Calendar** — call `calendar_brief` to check what's coming up tomorrow so the user knows what to prepare for.
3. **Loose ends** — briefly ask if there's anything they want you to remember for tomorrow; if they give you something durable (a task, a reminder, a decision), save it with `save_memory` (category: notes or projects).
4. **Close** — give a short, encouraging one-line sign-off.

Tone: relaxed and concise — it's the end of the day. Speak it naturally, don't recite lists mechanically. Keep the whole thing under ~6 spoken sentences.
