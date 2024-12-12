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

// Gestion de la lightbox
function openLightbox(imageSrc) {
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    
    lightboxImg.src = imageSrc;
    lightbox.classList.add('active');
    
    // Désactiver le défilement de la page
    document.body.style.overflow = 'hidden';
}

function closeLightbox() {
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    
    lightbox.classList.remove('active');
    lightboxImg.src = '';
    
    // Réactiver le défilement de la page
    document.body.style.overflow = '';
}

// Fermer la lightbox en cliquant en dehors de l'image
document.getElementById('lightbox').addEventListener('click', function(e) {
    if (e.target === this) {
        closeLightbox();
    }
});

// Fermer la lightbox avec la touche Echap
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeLightbox();
    }
});
