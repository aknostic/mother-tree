---
key: calendar
roles: [hunter, gatherer, farmer]
trigger: null
onboarding: false
onboarding_order: null
topic: getting_started
summary: Connect your calendar once — share your iCal URL and a farmer runs `mothertree calendar set <your-email> <ical_url>`.
---

Calendar integration is how I deliver meeting prep (two days before) and debrief prompts (three days after). It works via an iCal feed — one-time setup.

*Get your iCal URL (Google Calendar)*
1. Open Google Calendar → Settings.
2. Under *Settings for my calendars*, pick the calendar you want connected.
3. Scroll to *Integrate calendar*.
4. Copy the *Secret address in iCal format* (not the public URL).

Treat this URL as a secret — it exposes your calendar.

*Connect it*
Just DM me the URL — something like "here's my calendar: <paste>". I'll pick it up, store it on your user record, and confirm.

If the DM path doesn't work for you, a farmer can also set it via CLI:

```
mothertree calendar set <your-email> <ical_url>
```

The calendar sync cronjob runs every weekday morning and picks up your meetings from there. See `help calendar_prep` for what happens after.
