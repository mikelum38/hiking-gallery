import os
from dotenv import load_dotenv

load_dotenv()

print("=== Vérification du fichier .env ===")
print()

required_vars = {
    'FLASK_SECRET_KEY': 'Clé secrète Flask',
    'CLOUDINARY_CLOUD_NAME': 'Nom du cloud Cloudinary',
    'CLOUDINARY_API_KEY': 'Clé API Cloudinary',
    'CLOUDINARY_API_SECRET': 'Secret API Cloudinary'
}

all_good = True

for var, description in required_vars.items():
    value = os.environ.get(var)
    if value:
        masked_value = '*' * (len(value) - 4) + value[-4:] if len(value) > 4 else '*' * len(value)
        print(f"✅ {description}: {masked_value}")
    else:
        print(f"❌ {description}: MANQUANTE")
        all_good = False

print()
if all_good:
    print("🎉 Toutes les variables d'environnement sont définies!")
else:
    print("⚠️  Variables manquantes - l'application ne démarrera pas correctement")
