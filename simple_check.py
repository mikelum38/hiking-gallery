import json

with open('galleries.json', 'r', encoding='utf-8') as f:
    galleries = json.load(f)

# Vérifier les années 2024 et 2025
galleries_2024 = [g for g in galleries.values() if g.get('date','').startswith('2024')]
galleries_2025 = [g for g in galleries.values() if g.get('date','').startswith('2025')]

print(f"Galeries 2024: {len(galleries_2024)}")
print(f"Galeries 2025: {len(galleries_2025)}")

if galleries_2024:
    print("Premières galeries 2024:")
    for i, g in enumerate(galleries_2024[:3]):
        print(f"  {i+1}. {g.get('name','N/A')} - {g.get('date','N/A')}")

if galleries_2025:
    print("Premières galeries 2025:")
    for i, g in enumerate(galleries_2025[:3]):
        print(f"  {i+1}. {g.get('name','N/A')} - {g.get('date','N/A')}")
