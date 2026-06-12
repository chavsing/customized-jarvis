---
name: email-triage
description: When the user wants to sort, prioritize, or get on top of their emails (e.g. "help me with my inbox", "what emails need attention", "triage my email")
---

# Email Triage

Goal: give the user a fast, prioritized read on their inbox and surface only what matters.

Steps:
1. Call `gmail_brief` to fetch recent unread emails.
2. Mentally group them into three buckets:
   - **Urgent / needs a reply** — from real people, questions, deadlines, anything time-sensitive.
   - **Important but not urgent** — updates, receipts, things to read later.
   - **Noise** — newsletters, marketing, automated notifications.
3. Speak a SHORT summary: how many total, then read out ONLY the urgent bucket by sender + subject (max 5). Mention the count of the other buckets without listing them.
4. If the user asks you to reply to one, draft a concise, professional reply and read it back before sending (use `send_message` only if they confirm).

Keep it conversational and brief — this is spoken aloud. Never read every email; the point is to filter.
