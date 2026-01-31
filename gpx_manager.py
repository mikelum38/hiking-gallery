#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de gestion des fichiers GPX pour le hiking gallery
"""

import gpxpy
import gpxpy.gpx
import os
import json
import math
from typing import Dict, List, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)

class GPXManager:
    """Classe pour gérer les fichiers GPX"""
    
    def __init__(self):
        self.stats_cache = {}
    
    def parse_gpx_file(self, file_path: str) -> Dict[str, Any]:
        """
        Parser un fichier GPX et extraire les informations
        
        Args:
            file_path: Chemin vers le fichier GPX
            
        Returns:
            Dictionnaire contenant les informations extraites
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as gpx_file:
                gpx = gpxpy.parse(gpx_file)
            
            # Extraire les informations de base
            info = {
                'name': gpx.name or 'Trace sans nom',
                'description': gpx.description or '',
                'author': gpx.author_name or '',
                'time': gpx.time.isoformat() if gpx.time else None,
                'tracks': [],
                'waypoints': [],
                'routes': []
            }
            
            # Traiter les traces (tracks)
            for track in gpx.tracks:
                track_info = {
                    'name': track.name or f'Track {len(info["tracks"]) + 1}',
                    'segments': []
                }
                
                for segment in track.segments:
                    segment_info = self._process_segment(segment)
                    track_info['segments'].append(segment_info)
                
                # Calculer les statistiques de la trace
                if track_info['segments']:
                    track_stats = self._calculate_track_stats(track_info['segments'])
                    track_info.update(track_stats)
                
                info['tracks'].append(track_info)
            
            # Traiter les waypoints
            for waypoint in gpx.waypoints:
                waypoint_info = {
                    'name': waypoint.name or '',
                    'lat': waypoint.latitude,
                    'lon': waypoint.longitude,
                    'elevation': waypoint.elevation,
                    'time': waypoint.time.isoformat() if waypoint.time else None,
                    'description': waypoint.description or '',
                    'symbol': waypoint.symbol or ''
                }
                info['waypoints'].append(waypoint_info)
            
            # Traiter les routes
            for route in gpx.routes:
                route_info = {
                    'name': route.name or f'Route {len(info["routes"]) + 1}',
                    'points': []
                }
                
                for point in route.points:
                    point_info = {
                        'lat': point.latitude,
                        'lon': point.longitude,
                        'elevation': point.elevation,
                        'name': point.name or ''
                    }
                    route_info['points'].append(point_info)
                
                info['routes'].append(route_info)
            
            # Calculer les statistiques globales
            global_stats = self._calculate_global_stats(info)
            info.update(global_stats)
            
            return info
            
        except Exception as e:
            logger.error(f"Erreur lors du parsing du fichier GPX {file_path}: {str(e)}")
            raise ValueError(f"Fichier GPX invalide: {str(e)}")
    
    def _process_segment(self, segment) -> Dict[str, Any]:
        """Traiter un segment de trace"""
        points = []
        total_distance = 0
        elevation_gain = 0
        elevation_loss = 0
        elevations = []  # Pour calculer min/max
        
        for i, point in enumerate(segment.points):
            point_info = {
                'lat': point.latitude,
                'lon': point.longitude,
                'elevation': point.elevation,
                'time': point.time.isoformat() if point.time else None
            }
            points.append(point_info)
            
            # Collecter les altitudes valides
            if point.elevation is not None:
                elevations.append(point.elevation)
            
            # Calculer les distances et dénivelés
            if i > 0:
                prev_point = segment.points[i-1]
                
                # Distance
                distance = self._calculate_distance(
                    prev_point.latitude, prev_point.longitude,
                    point.latitude, point.longitude
                )
                total_distance += distance
                
                # Dénivelé
                if prev_point.elevation and point.elevation:
                    elevation_diff = point.elevation - prev_point.elevation
                    if elevation_diff > 0:
                        elevation_gain += elevation_diff
                    else:
                        elevation_loss += abs(elevation_diff)
        
        # Calculer les altitudes min/max
        min_elevation = min(elevations) if elevations else None
        max_elevation = max(elevations) if elevations else None
        
        return {
            'points': points,
            'distance': total_distance,
            'elevation_gain': elevation_gain,
            'elevation_loss': elevation_loss,
            'min_elevation': min_elevation,
            'max_elevation': max_elevation,
            'point_count': len(points)
        }
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculer la distance entre deux points en km"""
        R = 6371  # Rayon de la Terre en km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat/2)**2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def _calculate_track_stats(self, segments: List[Dict]) -> Dict[str, Any]:
        """Calculer les statistiques d'une trace"""
        total_distance = sum(seg['distance'] for seg in segments)
        total_elevation_gain = sum(seg['elevation_gain'] for seg in segments)
        total_elevation_loss = sum(seg['elevation_loss'] for seg in segments)
        total_points = sum(seg['point_count'] for seg in segments)
        
        # Trouver les altitudes min/max
        all_elevations = []
        for segment in segments:
            for point in segment['points']:
                if point['elevation'] is not None:
                    all_elevations.append(point['elevation'])
        
        min_elevation = min(all_elevations) if all_elevations else None
        max_elevation = max(all_elevations) if all_elevations else None
        
        return {
            'distance': round(total_distance, 3),
            'elevation_gain': round(total_elevation_gain, 1),
            'elevation_loss': round(total_elevation_loss, 1),
            'min_elevation': round(min_elevation, 1) if min_elevation else None,
            'max_elevation': round(max_elevation, 1) if max_elevation else None,
            'total_points': total_points
        }
    
    def _calculate_global_stats(self, gpx_info: Dict) -> Dict[str, Any]:
        """Calculer les statistiques globales du GPX"""
        total_distance = 0
        total_elevation_gain = 0
        total_elevation_loss = 0
        total_points = 0
        all_elevations = []  # Pour calculer les altitudes min/max globales
        
        # Agréger les statistiques de toutes les traces
        for track in gpx_info['tracks']:
            if 'distance' in track:
                total_distance += track['distance']
                total_elevation_gain += track['elevation_gain']
                total_elevation_loss += track['elevation_loss']
                total_points += track['total_points']
            
            # Collecter les altitudes min/max de chaque segment
            for segment in track['segments']:
                if 'min_elevation' in segment and segment['min_elevation'] is not None:
                    all_elevations.append(segment['min_elevation'])
                if 'max_elevation' in segment and segment['max_elevation'] is not None:
                    all_elevations.append(segment['max_elevation'])
        
        # Calculer les altitudes min/max globales
        min_elevation = min(all_elevations) if all_elevations else None
        max_elevation = max(all_elevations) if all_elevations else None
        
        # Durée totale
        all_times = []
        for track in gpx_info['tracks']:
            for segment in track['segments']:
                for point in segment['points']:
                    if point['time']:
                        all_times.append(point['time'])
        
        duration = None
        if len(all_times) >= 2:
            from datetime import datetime
            start_time = datetime.fromisoformat(all_times[0].replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(all_times[-1].replace('Z', '+00:00'))
            duration = (end_time - start_time).total_seconds()
        
        return {
            'total_distance': round(total_distance, 3),
            'total_elevation_gain': round(total_elevation_gain, 1),
            'total_elevation_loss': round(total_elevation_loss, 1),
            'total_points': total_points,
            'duration_seconds': duration,
            'track_count': len(gpx_info['tracks']),
            'waypoint_count': len(gpx_info['waypoints']),
            'route_count': len(gpx_info['routes']),
            'min_elevation': round(min_elevation, 1) if min_elevation else None,
            'max_elevation': round(max_elevation, 1) if max_elevation else None
        }
    
    def validate_gpx_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Valider un fichier GPX
        
        Args:
            file_path: Chemin vers le fichier GPX
            
        Returns:
            Tuple (valide, message_erreur)
        """
        try:
            # Vérifier que le fichier existe
            if not os.path.exists(file_path):
                return False, "Le fichier n'existe pas"
            
            # Vérifier la taille
            if os.path.getsize(file_path) == 0:
                return False, "Le fichier est vide"
            
            # Essayer de parser le fichier
            with open(file_path, 'r', encoding='utf-8') as gpx_file:
                gpx = gpxpy.parse(gpx_file)
            
            # Vérifier qu'il y a des données
            if not gpx.tracks and not gpx.waypoints and not gpx.routes:
                return False, "Le GPX ne contient aucune trace, waypoint ou route"
            
            # Vérifier qu'il y a des points valides
            has_valid_points = False
            for track in gpx.tracks:
                for segment in track.segments:
                    if len(segment.points) >= 1:  # Accepter même un seul point
                        has_valid_points = True
                        break
                if has_valid_points:
                    break
            
            if not has_valid_points:
                return False, "Le GPX ne contient aucun point valide. Vérifiez que votre fichier contient des coordonnées GPS."
            
            return True, "Fichier GPX valide"
            
        except gpxpy.gpx.GPXException as e:
            return False, f"Erreur de format GPX: {str(e)}"
        except Exception as e:
            return False, f"Erreur lors de la validation: {str(e)}"
    
    def extract_track_coordinates(self, gpx_info: Dict) -> List[List[float]]:
        """
        Extraire les coordonnées de toutes les traces pour affichage sur carte
        
        Args:
            gpx_info: Informations du GPX retournées par parse_gpx_file
            
        Returns:
            Liste de coordonnées [[lat, lon], ...]
        """
        coordinates = []
        
        for track in gpx_info['tracks']:
            for segment in track['segments']:
                for point in segment['points']:
                    coordinates.append([point['lat'], point['lon']])
        
        return coordinates
    
    def get_track_segments_for_leaflet(self, gpx_info: Dict) -> List[List[List[float]]]:
        """
        Extraire les segments de traces pour Leaflet
        
        Args:
            gpx_info: Informations du GPX
            
        Returns:
            Liste de segments [[[lat, lon], ...], ...]
        """
        segments = []
        
        for track in gpx_info['tracks']:
            for segment in track['segments']:
                segment_coords = [[point['lat'], point['lon']] for point in segment['points']]
                if len(segment_coords) > 1:
                    segments.append(segment_coords)
        
        return segments
    
    def update_gallery_from_gpx(self, gallery_data: Dict, gpx_info: Dict) -> Dict:
        """
        Mettre à jour les données d'une galerie avec les informations du GPX
        
        Args:
            gallery_data: Données actuelles de la galerie
            gpx_info: Informations extraites du GPX
            
        Returns:
            Données de galerie mises à jour
        """
        updated_gallery = gallery_data.copy()
        
        # Mettre à jour les informations de base si elles n'existent pas
        if not updated_gallery.get('name') or updated_gallery.get('name') == '':
            updated_gallery['name'] = gpx_info['name']
        
        if not updated_gallery.get('description') or updated_gallery.get('description') == '':
            updated_gallery['description'] = gpx_info['description']
        
        # Mettre à jour les statistiques
        if gpx_info.get('total_distance'):
            updated_gallery['distance'] = float(gpx_info['total_distance'])
        
        if gpx_info.get('total_elevation_gain'):
            updated_gallery['denivele'] = int(gpx_info['total_elevation_gain'])
        
        # Estimer la difficulté basée sur le dénivelé et la distance
        if gpx_info.get('total_elevation_gain') and gpx_info.get('total_distance'):
            difficulty = self._estimate_difficulty(
                gpx_info['total_elevation_gain'], 
                gpx_info['total_distance']
            )
            updated_gallery['difficulty'] = difficulty
        
        # Ajouter les coordonnées du début de la trace (premier point)
        coordinates = self.extract_track_coordinates(gpx_info)
        if coordinates:
            # Utiliser le premier point de la trace pour le marqueur
            start_lat, start_lon = coordinates[0]
            updated_gallery['lat'] = float(round(start_lat, 6))
            updated_gallery['lon'] = float(round(start_lon, 6))
        
        # Ajouter les métadonnées GPX optimisées (uniquement les champs essentiels)
        updated_gallery['gpx_metadata'] = {
            'duration_seconds': gpx_info.get('duration_seconds'),
            'min_elevation': gpx_info.get('min_elevation'),
            'max_elevation': gpx_info.get('max_elevation')
        }
        
        return updated_gallery
    
    def _estimate_difficulty(self, elevation_gain: float, distance: float) -> str:
        """Estimer la difficulté basée sur le dénivelé et la distance"""
        # Calculer un indice de difficulté
        if distance == 0:
            return 'facile'
        
        denivelage_par_km = elevation_gain / distance
        
        # Classification basée sur le dénivelage au kilomètre
        if denivelage_par_km < 50:
            return 'facile'
        elif denivelage_par_km < 100:
            return 'moyen'
        else:
            return 'difficile'

# Instance globale du gestionnaire GPX
gpx_manager = GPXManager()
