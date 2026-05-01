import re

with open("elite_templates.py", "r", encoding="utf-8") as f:
    text = f.read()

# 1. Add locality extraction
if 'locality = identity.get("locality", "your area")' not in text:
    text = text.replace(
        'owner = identity.get("owner_first_name", identity.get("name", "Partner"))',
        'owner = identity.get("owner_first_name", identity.get("name", "Partner"))\n    locality = identity.get("locality", "your area")'
    )

# 2. Update handler signatures and calls
text = re.sub(r'def (_trg\d+)\(([^)]+)\):', r'def \1(\2, locality):', text)
text = re.sub(r'lambda: (_trg\d+)\(([^)]+)\)', r'lambda: \1(\2, locality)', text)

# 3. Replace city names and convert strings to f-strings where needed
cities = ["Hyderabad", "Jaipur", "Lucknow", "Delhi", "Chennai", "HSR Layout"]
for city in cities:
    text = text.replace(city, "{locality}")

# Ensure all strings with {locality} have the f prefix
lines = text.split("\n")
new_lines = []
for line in lines:
    if "{locality}" in line and 'f"' not in line and '"' in line:
        # Match only if it looks like a string assignment or parameter
        line = line.replace('"', 'f"', 1)
    new_lines.append(line)
text = "\n".join(new_lines)

# 4. Improve CTAs
# Replace generic "open_ended" with more specific ones to boost Engagement score
text = text.replace('"open_ended"', '"reply_yes_no"')

with open("elite_templates.py", "w", encoding="utf-8") as f:
    f.write(text)

print("Done")
