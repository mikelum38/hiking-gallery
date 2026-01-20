# Approche Lazy Loading pour les Dimensions des Photos

## Principe
Au lieu de faire un batch massif d'appels API (qui cause des rate limits), nous utilisons une approche "lazy loading" où les dimensions sont récupérées uniquement lors de la visualisation des galeries.

## Fonctionnement

### 1. Lors de la visualisation d'une galerie
- Le code vérifie si chaque photo a déjà ses dimensions
- Si non, il appelle l'API Cloudinary pour cette photo spécifique
- Les dimensions récupérées sont immédiatement sauvegardées dans le JSON

### 2. Sauvegarde automatique
- La fonction `save_photo_dimensions_to_gallery()` met à jour le JSON
- Seul le fichier de l'année concernée est modifié
- Le cache est invalidé pour la prochaine lecture

## Avantages

### ✅ Évite les rate limits
- 1-2 appels API par visite de galerie (vs milliers en batch)
- Répartition naturelle dans le temps
- Pas de dépassement des 500 appels/heure

### ✅ Performance progressive
- Première visite : léger délai pour les photos sans dimensions
- Visites suivantes : dimensions déjà en cache, instantané
- Amélioration continue au fil des visites

### ✅ Efficacité ciblée
- Seules les photos visualisées récupèrent leurs dimensions
- Les photos jamais vues ne consomment pas d'appels API
- Priorité aux galeries populaires

### ✅ Robustesse
- Si une sauvegarde échoue, la prochaine visite retentera
- Pas de perte de données si le processus est interrompu
- Gestion d'erreurs individuelle par photo

## Implémentation

### Modifications apportées :
1. **`save_photo_dimensions_to_gallery()`** : Sauvegarde les dimensions dans le JSON
2. **Fonction `gallery()`** : Sauvegarde automatique lors de la récupération
3. **Flag `dimensions_updated`** : Suivi des modifications

### Flux :
```
Visite galerie → Vérification dimensions → API si besoin → Sauvegarde JSON → Cache invalidé
```

## Résultat attendu

Après quelques jours/semaines de visite normale :
- ✅ Toutes les galeries populaires auront leurs dimensions
- ✅ Plus aucun appel API pour les photos déjà visitées  
- ✅ Performance optimale pour les utilisateurs réguliers
- ✅ Zéro rate limit

## Monitoring

Les logs montrent :
- `"Dimensions récupérées via API pour photo_id: 1920x1080"`
- `"Dimensions sauvegardées pour photo_id: 1920x1080"`

Cette approche transforme un problème de rate limit en une optimisation progressive naturelle.
