# -*- coding: utf-8 -*-
"""
Module de recherche pour Hiking Gallery
Recherche dans : noms, descriptions, dates, lieux
"""

import json
from datetime import datetime
from typing import List, Dict, Any
import re

class SearchEngine:
    """Moteur de recherche simple mais efficace"""
    
    def __init__(self, galleries_file='galleries.json'):
        self.galleries_file = galleries_file
        self.galleries = self._load_galleries()
        self._build_index()
    
    def _load_galleries(self) -> Dict:
        """Charge les galeries"""
        try:
            with open(self.galleries_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def _normalize_text(self, text: str) -> str:
        """Normalise le texte pour la recherche"""
        if not text:
            return ""
        
        # Minuscules
        text = text.lower()
        
        # Retirer accents (simple)
        accents = {
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'à': 'a', 'â': 'a', 'ä': 'a',
            'ù': 'u', 'û': 'u', 'ü': 'u',
            'ô': 'o', 'ö': 'o',
            'î': 'i', 'ï': 'i',
            'ç': 'c'
        }
        for accent, plain in accents.items():
            text = text.replace(accent, plain)
        
        return text
    
    def _build_index(self):
        """Construit un index inversé pour recherche rapide"""
        self.index = {}
        
        for gallery_id, gallery in self.galleries.items():
            # Extraire tous les mots cherchables
            searchable_text = ' '.join([
                gallery.get('name', ''),
                gallery.get('description', ''),
                gallery.get('date', ''),
                str(gallery.get('formatted_date', ''))
            ])
            
            # Normaliser et splitter
            words = self._normalize_text(searchable_text).split()
            
            # Ajouter à l'index
            for word in words:
                if word not in self.index:
                    self.index[word] = set()
                self.index[word].add(gallery_id)
    
    def search(self, query: str, filters: Dict[str, Any] = None) -> List[Dict]:
        """
        Recherche dans les galeries
        
        Args:
            query: Terme de recherche
            filters: Filtres optionnels (year, month, etc.)
        
        Returns:
            Liste de galeries correspondantes
        """
        if not query:
            return self._apply_filters(list(self.galleries.values()), filters)
        
        # Normaliser la requête
        normalized_query = self._normalize_text(query)
        query_words = normalized_query.split()
        
        # Rechercher dans l'index
        matching_ids = None
        
        for word in query_words:
            # Recherche exacte
            word_matches = self.index.get(word, set())
            
            # Recherche partielle (commence par)
            for indexed_word, ids in self.index.items():
                if indexed_word.startswith(word):
                    word_matches = word_matches.union(ids)
            
            # Intersection des résultats (AND logique)
            if matching_ids is None:
                matching_ids = word_matches
            else:
                matching_ids = matching_ids.intersection(word_matches)
        
        # Récupérer les galeries complètes
        results = []
        for gallery_id in (matching_ids or []):
            gallery = self.galleries[gallery_id].copy()
            gallery['id'] = gallery_id
            results.append(gallery)
        
        # Appliquer les filtres
        results = self._apply_filters(results, filters)
        
        # Trier par pertinence (date décroissante)
        results.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        return results
    
    def _apply_filters(self, results: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
        """Applique les filtres aux résultats"""
        if not filters:
            return results
        
        filtered = results
        
        # Filtre par année
        if 'year' in filters and filters['year']:
            year = int(filters['year'])
            filtered = [r for r in filtered 
                       if datetime.strptime(r['date'], '%Y-%m-%d').year == year]
        
        # Filtre par mois
        if 'month' in filters and filters['month']:
            month = int(filters['month'])
            filtered = [r for r in filtered 
                       if datetime.strptime(r['date'], '%Y-%m-%d').month == month]
        
        # Filtre par tag (si disponible)
        if 'tag' in filters and filters['tag']:
            tag = filters['tag'].lower()
            filtered = [r for r in filtered 
                       if tag in [t.lower() for t in r.get('tags', [])]]
        
        return filtered
    
    def suggest(self, partial_query: str, max_suggestions: int = 5) -> List[str]:
        """
        Auto-complétion basée sur l'index
        
        Args:
            partial_query: Début du mot
            max_suggestions: Nombre max de suggestions
        
        Returns:
            Liste de suggestions
        """
        if not partial_query:
            return []
        
        normalized = self._normalize_text(partial_query)
        suggestions = set()
        
        # Trouver tous les mots qui commencent par la requête
        for word in self.index.keys():
            if word.startswith(normalized):
                suggestions.add(word)
        
        # Aussi suggérer des noms de galeries
        for gallery in self.galleries.values():
            name = self._normalize_text(gallery.get('name', ''))
            if name.startswith(normalized):
                suggestions.add(gallery.get('name', ''))
        
        return sorted(list(suggestions))[:max_suggestions]
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistiques de recherche"""
        return {
            'total_galleries': len(self.galleries),
            'total_indexed_words': len(self.index),
            'years': sorted(set(
                datetime.strptime(g['date'], '%Y-%m-%d').year 
                for g in self.galleries.values() 
                if 'date' in g
            )),
            'months_with_hikes': len(set(
                f"{datetime.strptime(g['date'], '%Y-%m-%d').year}-{datetime.strptime(g['date'], '%Y-%m-%d').month}"
                for g in self.galleries.values()
                if 'date' in g
            ))
        }


# Routes Flask pour la recherche
def setup_search_routes(app, search_engine):
    """Configure les routes de recherche"""
    
    @app.route('/search')
    def search_page():
        """Page de recherche"""
        from flask import render_template, request
        
        query = request.args.get('q', '')
        year_filter = request.args.get('year', '')
        month_filter = request.args.get('month', '')
        
        filters = {}
        if year_filter:
            filters['year'] = year_filter
        if month_filter:
            filters['month'] = month_filter
        
        results = search_engine.search(query, filters) if query else []
        stats = search_engine.get_stats()
        
        return render_template('search.html',
                             query=query,
                             results=results,
                             stats=stats,
                             year_filter=year_filter,
                             month_filter=month_filter,
                             dev_mode=app.config.get('DEV_MODE', False))
    
    @app.route('/api/search/suggest')
    def search_suggest():
        """API auto-complétion"""
        from flask import jsonify, request
        
        q = request.args.get('q', '')
        suggestions = search_engine.suggest(q)
        
        return jsonify({
            'query': q,
            'suggestions': suggestions
        })
    
    @app.route('/api/search')
    def api_search():
        """API de recherche JSON"""
        from flask import jsonify, request
        
        query = request.args.get('q', '')
        year = request.args.get('year', '')
        month = request.args.get('month', '')
        
        filters = {}
        if year:
            filters['year'] = year
        if month:
            filters['month'] = month
        
        results = search_engine.search(query, filters)
        
        return jsonify({
            'query': query,
            'filters': filters,
            'total_results': len(results),
            'results': results
        })