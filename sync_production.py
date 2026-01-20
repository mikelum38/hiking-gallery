#!/usr/bin/env python3
"""
Script pour synchroniser les JSON de production vers le local
"""

import paramiko
import os
from datetime import datetime

def sync_json_from_production():
    """Synchronise les fichiers JSON depuis le serveur de production"""
    
    # Configuration à adapter
    PROD_CONFIG = {
        'hostname': 'votre-serveur.com',
        'port': 22,
        'username': 'votre-user',
        'password': 'votre-password',  # ou utiliser des clés SSH
        'remote_path': '/path/to/your/app',
        'local_path': './'
    }
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(**PROD_CONFIG)
        sftp = ssh.open_sftp()
        
        # Lister les fichiers JSON sur le serveur
        remote_files = sftp.listdir(PROD_CONFIG['remote_path'])
        
        json_files = [f for f in remote_files if f.startswith('galleries_') and f.endswith('.json')]
        
        print(f"📁 Trouvé {len(json_files)} fichiers JSON à synchroniser :")
        
        for json_file in json_files:
            remote_file = f"{PROD_CONFIG['remote_path']}/{json_file}"
            local_file = f"{PROD_CONFIG['local_path']}/{json_file}"
            
            # Vérifier si le fichier distant est plus récent
            remote_stat = sftp.stat(remote_file)
            
            if os.path.exists(local_file):
                local_stat = os.stat(local_file)
                if remote_stat.st_mtime <= local_stat.st_mtime:
                    print(f"⏭️  {json_file} - déjà à jour")
                    continue
            
            # Télécharger le fichier
            print(f"⬇️  Téléchargement de {json_file}...")
            sftp.get(remote_file, local_file)
            print(f"✅ {json_file} synchronisé")
        
        # Synchroniser aussi les index
        for index_file in ['galleries_index.json', 'galleries_by_year.json', 'galleries_metadata.json']:
            remote_index = f"{PROD_CONFIG['remote_path']}/{index_file}"
            local_index = f"{PROD_CONFIG['local_path']}/{index_file}"
            
            try:
                sftp.get(remote_index, local_index)
                print(f"✅ {index_file} synchronisé")
            except FileNotFoundError:
                print(f"⚠️  {index_file} non trouvé en production")
        
        print(f"🎉 Synchronisation terminée à {datetime.now().strftime('%H:%M:%S')}")
        
    except Exception as e:
        print(f"❌ Erreur de synchronisation : {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    sync_json_from_production()
