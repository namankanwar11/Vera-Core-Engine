import re

with open("elite_templates.py", "r", encoding="utf-8") as f:
    text = f.read()

replacements = [
    ("Should I draft it?", "Competitors are already doing this. Reply 'Yes' and I'll draft it immediately!"),
    ("Should I draft both?", "Don't lose more traffic. Reply 'Yes' to draft both now!"),
    ("Should I send it now?", "Avoid penalties. Reply 'Yes' to receive it instantly!"),
    ("Should I reserve a spot?", "Spots are almost gone! Reply 'Yes' to lock it in!"),
    ("Interested?", "Limited time offer. Reply 'Yes' to claim it!"),
    ("Want me to help with that?", "Reply 'Yes' to get started and boost your views!"),
    ("Should I send both now?", "Don't risk patient trust. Reply 'Yes' to send both now!"),
    ("Should I walk you through it right now?", "Other pharmacies are taking your calls. Reply 'Yes' to verify now!"),
    ("Should I register you?", "Seats are limited. Reply 'Yes' to register!"),
    ("Should I create the GBP post + a WhatsApp broadcast?", "Reply 'Yes' to create both and secure these orders!"),
    ("Which slot works for you?", "These slots go fast! Reply 1 for the first slot, or 2 for the second to lock it in!"),
    ("Should I place the order for home delivery tomorrow morning?", "Don't risk missing a dose. Reply 'Yes' to confirm delivery!"),
    ("Should I draft the design?", "You're so close! Reply 'Yes' to draft the design and get your badge!"),
    ("Should I lock in the renewal now?", "Don't let your profile go dark. Reply 'Yes' to lock in the renewal!"),
    ("Should I draft the challenge rules?", "Members love this. Reply 'Yes' to draft the rules and boost retention!"),
    ("Should I draft a shelf-reset checklist for your team?", "Maximize your summer sales. Reply 'Yes' to draft the checklist!"),
    ("Should I book your first prep session for next Saturday?", "Our bridal slots book up months in advance. Reply 'Yes' to secure your spot!"),
    ("Just reply with the service name and I’ll update your highlights.", "Just reply with the service name and I’ll update your highlights to capture this demand!"),
    ("Should I draft the offer + GBP post?", "Beat the rush. Reply 'Yes' to draft the offer!"),
    ("Want me to pull it + draft a patient-ed WhatsApp you can share?", "Over 40 clinics have already done this. Reply 'Yes' and I'll draft it!")
]

for old, new in replacements:
    text = text.replace(old, new)

with open("elite_templates.py", "w", encoding="utf-8") as f:
    f.write(text)

print("Done")
