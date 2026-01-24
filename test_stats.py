import json
from datetime import datetime
import os

# Charger les galeries
galleries = {}
for year_file in sorted([f for f in os.listdir('.') if f.startswith('galleries_') and f.endswith('.json') and f != 'galleries_index.json']):
    with open(year_file, 'r', encoding='utf-8') as f:
        year_galleries = json.load(f)
        galleries.update(year_galleries)

# Statistiques 2026 uniquement
stats_2026 = {'hikes': 0, 'totalKm': 0, 'elevation': 0, 'photos': 0}
for gallery_id, gallery in galleries.items():
    date = datetime.strptime(gallery['date'], '%Y-%m-%d')
    if date.year == 2026:
        stats_2026['hikes'] += 1
        stats_2026['photos'] += len(gallery.get('photos', []))
        stats_2026['totalKm'] += gallery.get('distance', 0) or 0
        stats_2026['elevation'] += gallery.get('denivele', 0) or 0
        print(f'{gallery["name"]}: {gallery.get("distance", 0)} km, {gallery.get("denivele", 0)}m')

print()
print(f'Total 2026: {stats_2026["hikes"]} randonnées, {stats_2026["totalKm"]} km, {stats_2026["elevation"]}m dénivelé, {stats_2026["photos"]} photos')
