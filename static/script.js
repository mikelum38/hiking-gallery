// Gestion du champ de fichier
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('file-input');
    const fileInputText = document.querySelector('.file-input-text');
    
    if (fileInput && fileInputText) {
        fileInput.addEventListener('change', function() {
            const files = this.files;
            if (files.length > 0) {
                fileInputText.textContent = `${files.length} photo${files.length > 1 ? 's' : ''} sélectionnée${files.length > 1 ? 's' : ''}`;
            } else {
                fileInputText.textContent = 'Choisir des photos';
            }
        });
    }
});

// Variables globales pour la lightbox
let currentImageIndex = 0;
let images = [];

// Fonction pour ouvrir la lightbox
function openLightbox(imageSrc) {
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    
    // Récupérer toutes les images de la galerie
    images = Array.from(document.querySelectorAll('.photo-thumbnail')).map(img => img.src);
    currentImageIndex = images.indexOf(imageSrc);
    
    updateLightboxImage();
    updateCounter();
    
    lightbox.style.display = 'block';
    document.body.style.overflow = 'hidden';

    // Ajouter les écouteurs d'événements
    document.addEventListener('keydown', handleKeyPress);
}

// Fonction pour fermer la lightbox
function closeLightbox() {
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    
    lightbox.style.display = 'none';
    document.body.style.overflow = 'auto';
    
    // Réinitialiser le zoom
    lightboxImg.classList.remove('zoomed');
    
    // Retirer les écouteurs d'événements
    document.removeEventListener('keydown', handleKeyPress);
}

// Fonction pour mettre à jour l'image de la lightbox
function updateLightboxImage() {
    const lightboxImg = document.getElementById('lightbox-img');
    lightboxImg.src = images[currentImageIndex];
    lightboxImg.classList.remove('zoomed');
}

// Fonction pour mettre à jour le compteur
function updateCounter() {
    document.getElementById('current-index').textContent = currentImageIndex + 1;
    document.getElementById('total-photos').textContent = images.length;
}

// Fonction pour passer à l'image suivante
function nextImage() {
    currentImageIndex = (currentImageIndex + 1) % images.length;
    updateLightboxImage();
    updateCounter();
}

// Fonction pour passer à l'image précédente
function previousImage() {
    currentImageIndex = (currentImageIndex - 1 + images.length) % images.length;
    updateLightboxImage();
    updateCounter();
}

// Fonction pour gérer le zoom
function toggleZoom() {
    const lightboxImg = document.getElementById('lightbox-img');
    lightboxImg.classList.toggle('zoomed');
}

// Gérer les touches du clavier
function handleKeyPress(e) {
    switch(e.key) {
        case 'Escape':
            closeLightbox();
            break;
        case 'ArrowRight':
            nextImage();
            break;
        case 'ArrowLeft':
            previousImage();
            break;
        case ' ': // Barre d'espace
            toggleZoom();
            break;
    }
}

// Fermer la lightbox en cliquant en dehors de l'image
document.getElementById('lightbox').addEventListener('click', function(e) {
    if (e.target.classList.contains('lightbox-container')) {
        closeLightbox();
    }
});
