# Probe: Amazon charges outside physical Orders

One-off prompt for Claude in Chrome. Steven pastes everything under "Prompt" into the side panel, in a Chrome window logged in to Amazon. It answers grilling question Q12: which non-physical Amazon charges can a scrape read reliably?

---

## Prompt

You are checking what Amazon shows on a few pages. You are a reader, not a recorder.

### Hard rules

- **Read only.** Do not save any file, do not click buy, cancel, return, or change anything, and do not write to Google Sheets.
- **Do not sign in anywhere.** If a page asks for a sign-in, stop on that page and report it.
- **Never guess.** If something is not shown, say "not shown".
- **Do not copy full card numbers or addresses.** The last four digits of a card are fine.

### Places to check (last 90 days)

1. **Digital Orders**: `https://www.amazon.com/gp/css/order-history` → the "Digital Orders" tab (Kindle, Prime Video, apps).
2. **Memberships & Subscriptions**: `https://www.amazon.com/mc` or "Your Account" → "Memberships & Subscriptions" (Prime fee, Grocery Subscription, others).
3. **Audible**: `https://www.audible.com/account/purchase-history`.
4. **Whole Foods Orders**: open one Whole Foods Order's details page.

### For each place, answer

- Can you reach it without signing in again? (yes / no, and what it asked for)
- How many charges does it show in the last 90 days?
- For each charge, is each of these shown? Answer "shown", "not shown", or "only on another page (which one)":
  - date charged
  - amount charged
  - card last four
  - an order number or other ID
  - what was bought (title or plan name)
- Does the page show charges older than 90 days, or only the current plan or next charge?
- Give **one** example charge as it appears, with the card masked to its last four.

For **Whole Foods** also answer:
- Is a delivery tip shown on the Order? If yes, is it inside the Order total or listed separately?
- Is there a shipped or delivered date?
- Are gift card or points shown as payment?

### Report

End with a short table: place, reachable (yes/no), "complete per charge" (yes/no), and what is missing. Then list anything confusing.
