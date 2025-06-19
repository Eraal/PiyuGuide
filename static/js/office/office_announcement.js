/***
 * JAVASCRIPT FOR OFFICE ANNOUNCEMENT
 */

// Modal control functions
function openNewAnnouncementModal() {
    document.getElementById('newAnnouncementModal').classList.remove('hidden');
}

function closeNewAnnouncementModal() {
    document.getElementById('newAnnouncementModal').classList.add('hidden');
    document.getElementById('newAnnouncementForm').reset();
    
    // Reset image preview
    const previewContainer = document.getElementById('image-preview-container');
    if (previewContainer) {
        previewContainer.classList.add('hidden');
    }
    const imagePreview = document.getElementById('image-preview');
    if (imagePreview) {
        imagePreview.src = '';
    }
}

function openEditAnnouncementModal(announcementId) {
    // Reset the form
    document.getElementById('editAnnouncementForm').reset();
    
    // Hide current image container initially
    const currentImageContainer = document.getElementById('edit-current-image-container');
    if (currentImageContainer) {
        currentImageContainer.classList.add('hidden');
    }
    
    // Reset image preview
    const previewContainer = document.getElementById('edit-image-preview-container');
    if (previewContainer) {
        previewContainer.classList.add('hidden');
    }
    const imagePreview = document.getElementById('edit-image-preview');
    if (imagePreview) {
        imagePreview.src = '';
    }

    // Fetch the announcement data from the server - FIXED URL
    fetch(`/office/get-announcement/${announcementId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to fetch announcement');
            }
            return response.json();
        })
        .then(data => {
            document.getElementById('edit-announcement-id').value = data.id;
            document.getElementById('edit-announcement-title').value = data.title;
            document.getElementById('edit-announcement-content').value = data.content;
            
            // Set visibility toggle
            const isPublicCheckbox = document.getElementById('edit-is-public');
            const visibilityLabel = document.getElementById('edit-visibility-label');
            
            if (isPublicCheckbox && visibilityLabel) {
                isPublicCheckbox.checked = data.is_public;
                visibilityLabel.textContent = data.is_public ? 'Public' : 'Private';
            }
            
            // Show current images if they exist - FIXED to handle multiple images
            if (data.images && data.images.length > 0) {
                const currentImageContainer = document.getElementById('edit-current-images-container');
                if (currentImageContainer) {
                    currentImageContainer.innerHTML = '';
                    data.images.forEach(image => {
                        const imageDiv = document.createElement('div');
                        imageDiv.className = 'relative inline-block mr-4 mb-4';
                        imageDiv.innerHTML = `
                            <img src="${image.image_path}" alt="${image.caption || 'Announcement image'}" 
                                 class="w-32 h-32 object-cover rounded-lg cursor-pointer"
                                 onclick="showImagePreview('${image.image_path}', '${image.caption || ''}')" />
                            <button type="button" onclick="confirmDeleteImage(${image.id}, ${data.id})"
                                    class="absolute -top-2 -right-2 bg-red-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs hover:bg-red-600">
                                <i class="fas fa-times"></i>
                            </button>
                            <input type="hidden" name="existing_image_ids[]" value="${image.id}" />
                            <input type="text" name="existing_captions[]" value="${image.caption || ''}" 
                                   placeholder="Image caption..." class="mt-1 w-32 text-xs border rounded px-2 py-1" />
                            <input type="number" name="existing_display_orders[]" value="${image.display_order || 0}" 
                                   placeholder="Order" class="mt-1 w-32 text-xs border rounded px-2 py-1" />
                        `;
                        currentImageContainer.appendChild(imageDiv);
                    });
                    currentImageContainer.classList.remove('hidden');
                }
            }
            
            // Show the modal
            document.getElementById('editAnnouncementModal').classList.remove('hidden');
        })
        .catch(error => {
            console.error('Error fetching announcement data:', error);
            alert('Failed to load announcement data. Please try again.');
        });
}

function closeEditAnnouncementModal() {
    document.getElementById('editAnnouncementModal').classList.add('hidden');
}

function confirmDeleteAnnouncement(announcementId, creatorId) {
    // Check if the user is the creator of the announcement
    const currentUserIdElement = document.getElementById('current-user-id');
    if (!currentUserIdElement) {
        console.error('Current user ID element not found');
        return;
    }
    
    const currentUserId = currentUserIdElement.value;
    
    if (currentUserId != creatorId) {
        alert('You cannot delete announcements created by other users.');
        return;
    }
    
    // Set the announcement ID in the delete confirmation modal
    const deleteAnnouncementIdInput = document.getElementById('delete-announcement-id');
    if (deleteAnnouncementIdInput) {
        deleteAnnouncementIdInput.value = announcementId;
    }
    
    // Show delete confirmation modal
    document.getElementById('deleteConfirmationModal').classList.remove('hidden');
}

function closeDeleteConfirmationModal() {
    document.getElementById('deleteConfirmationModal').classList.add('hidden');
}

function confirmDeleteImage(imageId, announcementId) {
    if (confirm('Are you sure you want to delete this image? This action cannot be undone.')) {
        // Create a form to submit the deletion request
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/office/delete-announcement-image'; // FIXED URL

        // Add CSRF token from an existing form
        const csrfToken = document.querySelector('input[name="csrf_token"]').value;

        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrf_token';
        csrfInput.value = csrfToken;

        const imageIdInput = document.createElement('input');
        imageIdInput.type = 'hidden';
        imageIdInput.name = 'image_id';
        imageIdInput.value = imageId;

        const announcementIdInput = document.createElement('input');
        announcementIdInput.type = 'hidden';
        announcementIdInput.name = 'announcement_id';
        announcementIdInput.value = announcementId;

        form.appendChild(csrfInput);
        form.appendChild(imageIdInput);
        form.appendChild(announcementIdInput);

        document.body.appendChild(form);
        form.submit();
    }
}

// Image preview functions - FIXED to handle multiple images
function previewImages(input) {
    const previewContainer = input.id === 'announcement-images' 
        ? document.getElementById('image-preview-container') 
        : document.getElementById('edit-image-preview-container');
    
    if (!previewContainer) return;
    
    const imagePreviewsDiv = previewContainer.querySelector('.image-previews') || 
                           (() => {
                               const div = document.createElement('div');
                               div.className = 'image-previews grid grid-cols-2 md:grid-cols-3 gap-4';
                               previewContainer.appendChild(div);
                               return div;
                           })();

    if (input.files && input.files.length > 0) {
        imagePreviewsDiv.innerHTML = '';
        Array.from(input.files).forEach((file, index) => {
            const reader = new FileReader();
            reader.onload = function(e) {
                const previewDiv = document.createElement('div');
                previewDiv.className = 'relative';
                previewDiv.innerHTML = `
                    <img src="${e.target.result}" alt="Preview ${index + 1}" 
                         class="w-full h-32 object-cover rounded-lg" />
                    <div class="mt-2">
                        <input type="text" name="captions[]" placeholder="Image caption..." 
                               class="w-full text-sm border rounded px-2 py-1 mb-1" />
                        <input type="number" name="display_orders[]" placeholder="Display order" value="${index}"
                               class="w-full text-sm border rounded px-2 py-1" />
                    </div>
                `;
                imagePreviewsDiv.appendChild(previewDiv);
            };
            reader.readAsDataURL(file);
        });
        previewContainer.classList.remove('hidden');
    } else {
        previewContainer.classList.add('hidden');
    }
}

function removeImages(buttonId) {
    const input = buttonId === 'remove-images' 
        ? document.getElementById('announcement-images') 
        : document.getElementById('edit-announcement-images');
    
    const previewContainer = buttonId === 'remove-images' 
        ? document.getElementById('image-preview-container') 
        : document.getElementById('edit-image-preview-container');
    
    if (input) input.value = '';
    if (previewContainer) previewContainer.classList.add('hidden');
}

function showImagePreview(src, caption) {
    const modal = document.getElementById('imagePreviewModal');
    const image = document.getElementById('modal-image');
    const captionElement = document.getElementById('modal-caption');

    if (modal && image && captionElement) {
        image.src = src;
        captionElement.textContent = caption || '';
        modal.classList.remove('hidden');
    }
}

function closeImagePreviewModal() {
    const modal = document.getElementById('imagePreviewModal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

// Toggle visibility label when checkbox changes
function toggleVisibilityLabel(checkboxId, labelId) {
    const checkbox = document.getElementById(checkboxId);
    const label = document.getElementById(labelId);
    
    if (checkbox && label) {
        label.textContent = checkbox.checked ? 'Public' : 'Private';
    }
}

function applyFilters() {
    const visibilityFilter = document.getElementById('visibility-filter');
    const dateRangeFilter = document.getElementById('date-range-filter');
    
    if (!visibilityFilter || !dateRangeFilter) return;

    // Build query string
    let queryParams = new URLSearchParams();
    if (visibilityFilter.value && visibilityFilter.value !== 'all') {
        queryParams.append('visibility', visibilityFilter.value);
    }
    if (dateRangeFilter.value && dateRangeFilter.value !== 'all') {
        queryParams.append('date_range', dateRangeFilter.value);
    }

    // Redirect with filters
    window.location.href = `${window.location.pathname}?${queryParams.toString()}`;
}

function loadAnnouncements(page = 1) {
    // Get current filters from URL
    const urlParams = new URLSearchParams(window.location.search);
    const visibility = urlParams.get('visibility') || 'all';
    const dateRange = urlParams.get('date_range') || 'all';
    
    // Show loading indicator
    const container = document.getElementById('announcements-container');
    if (!container) return;
    
    container.innerHTML = '<div class="flex justify-center py-10"><i class="fas fa-circle-notch fa-spin text-blue-600 text-3xl"></i></div>';
    
    // Build query for fetch
    let queryParams = new URLSearchParams();
    queryParams.append('page', page);
    if (visibility !== 'all') queryParams.append('visibility', visibility);
    if (dateRange !== 'all') queryParams.append('date_range', dateRange);
    
    // Fetch announcements - FIXED URL
    fetch(`/office/api/office-announcements?${queryParams.toString()}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to fetch announcements');
            }
            return response.json();
        })
        .then(data => {
            renderAnnouncements(data.announcements);
            renderPagination(data.pagination);
        })
        .catch(error => {
            console.error('Error loading announcements:', error);
            container.innerHTML = `
                <div class="text-center py-10">
                    <i class="fas fa-exclamation-circle text-red-500 text-3xl mb-3"></i>
                    <p class="text-gray-700">Failed to load announcements. Please try again later.</p>
                </div>
            `;
        });
}

function renderAnnouncements(announcements) {
    const container = document.getElementById('announcements-container');
    if (!container) return;
    
    // Get current user ID for permission checks
    const currentUserIdElement = document.getElementById('current-user-id');
    const currentUserId = currentUserIdElement ? currentUserIdElement.value : null;
    
    if (!announcements || announcements.length === 0) {
        container.innerHTML = `
            <div class="text-center py-10">
                <i class="fas fa-info-circle text-blue-500 text-3xl mb-3"></i>
                <p class="text-gray-700">No announcements found.</p>
            </div>
        `;
        return;
    }
    
    let html = '';
    
    announcements.forEach(announcement => {
        const canEdit = announcement.can_edit || (currentUserId && announcement.author_id == currentUserId);
        
        html += `
            <div class="announcement-card bg-white rounded-lg shadow-md overflow-hidden transition-all duration-200 hover:shadow-lg">
                <div class="p-5">
                    <div class="flex flex-wrap justify-between items-start mb-3">
                        <div>
                            <h2 class="text-xl font-bold text-gray-800 mb-1">${escapeHtml(announcement.title)}</h2>
                            <div class="flex flex-wrap items-center text-sm text-gray-600 space-x-3">
                                <span class="flex items-center">
                                    <i class="far fa-clock mr-1"></i>
                                    ${new Date(announcement.created_at).toLocaleDateString()}
                                </span>
                                <span class="flex items-center">
                                    <i class="far fa-building mr-1"></i>
                                    ${escapeHtml(announcement.office_name || 'General')}
                                </span>
                                <span class="flex items-center ${announcement.is_public ? 'text-green-600' : 'text-blue-600'}">
                                    <i class="${announcement.is_public ? 'fas fa-globe' : 'fas fa-lock'} mr-1"></i>
                                    ${announcement.is_public ? 'Public' : 'Private'}
                                </span>
                            </div>
                        </div>
                        ${canEdit ? `
                            <div class="dropdown relative">
                                <button class="p-1 text-gray-500 hover:text-gray-700 focus:outline-none" type="button">
                                    <i class="fas fa-ellipsis-v"></i>
                                </button>
                                <div class="dropdown-content absolute right-0 mt-1 w-48 bg-white rounded-md shadow-lg z-10 hidden py-1">
                                    <a href="#" onclick="openEditAnnouncementModal(${announcement.id}); return false;" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">
                                        <i class="fas fa-edit mr-2"></i> Edit
                                    </a>
                                    <a href="#" onclick="confirmDeleteAnnouncement(${announcement.id}, ${announcement.author_id || currentUserId}); return false;" class="block px-4 py-2 text-sm text-red-600 hover:bg-gray-100">
                                        <i class="fas fa-trash-alt mr-2"></i> Delete
                                    </a>
                                </div>
                            </div>
                        ` : ''}
                    </div>
                    
                    <div class="prose max-w-none text-gray-700 mb-4">
                        ${escapeHtml(announcement.content).replace(/\n/g, '<br>')}
                    </div>
                    
                    ${announcement.images && announcement.images.length > 0 ? `
                        <div class="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            ${announcement.images.map(image => `
                                <div class="rounded-lg overflow-hidden">
                                    <img src="${image.image_path}" alt="${escapeHtml(image.caption || 'Announcement image')}" 
                                        class="w-full h-48 object-cover cursor-pointer hover:opacity-90 transition-opacity"
                                        onclick="showImagePreview('${image.image_path}', '${escapeHtml(image.caption || '')}')" />
                                    ${image.caption ? `<p class="text-sm text-gray-600 mt-2 px-2 pb-2">${escapeHtml(image.caption)}</p>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
    
    // Initialize dropdowns for the new content
    initializeDropdowns();
}

function renderPagination(pagination) {
    const container = document.getElementById('pagination-container');
    const nav = document.getElementById('pagination-nav');
    
    if (!container || !nav) return;
    
    if (!pagination || pagination.total_pages <= 1) {
        container.classList.add('hidden');
        return;
    }
    
    container.classList.remove('hidden');
    
    let html = '';
    
    // Previous button
    if (pagination.has_prev) {
        html += `
            <a href="#" onclick="loadAnnouncements(${pagination.current_page - 1}); return false;" 
               class="relative inline-flex items-center px-4 py-2 text-sm font-medium rounded-l-md bg-white text-gray-700 hover:bg-gray-50 border border-gray-300">
                <i class="fas fa-chevron-left mr-1"></i> Previous
            </a>
        `;
    } else {
        html += `
            <span class="relative inline-flex items-center px-4 py-2 text-sm font-medium rounded-l-md bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-300">
                <i class="fas fa-chevron-left mr-1"></i> Previous
            </span>
        `;
    }
    
    // Page numbers
    for (let i = 1; i <= pagination.total_pages; i++) {
        if (
            i === 1 || 
            i === pagination.total_pages || 
            (i >= pagination.current_page - 1 && i <= pagination.current_page + 1)
        ) {
            html += `
                <a href="#" onclick="loadAnnouncements(${i}); return false;" 
                   class="relative inline-flex items-center px-4 py-2 text-sm font-medium border-t border-b ${i === pagination.current_page ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 hover:bg-gray-50 border-gray-300'}">
                    ${i}
                </a>
            `;
        } else if (
            i === pagination.current_page - 2 || 
            i === pagination.current_page + 2
        ) {
            html += `
                <span class="relative inline-flex items-center px-4 py-2 text-sm font-medium bg-white text-gray-700 border-t border-b border-gray-300">
                    ...
                </span>
            `;
        }
    }
    
    // Next button
    if (pagination.has_next) {
        html += `
            <a href="#" onclick="loadAnnouncements(${pagination.current_page + 1}); return false;" 
               class="relative inline-flex items-center px-4 py-2 text-sm font-medium rounded-r-md bg-white text-gray-700 hover:bg-gray-50 border border-gray-300">
                Next <i class="fas fa-chevron-right ml-1"></i>
            </a>
        `;
    } else {
        html += `
            <span class="relative inline-flex items-center px-4 py-2 text-sm font-medium rounded-r-md bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-300">
                Next <i class="fas fa-chevron-right ml-1"></i>
            </span>
        `;
    }
    
    nav.innerHTML = html;
}

function initializeDropdowns() {
    document.querySelectorAll('.dropdown').forEach(dropdown => {
        const button = dropdown.querySelector('button');
        const content = dropdown.querySelector('.dropdown-content');

        if (button && content) {
            // Remove existing listeners to prevent duplicates
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);
            
            newButton.addEventListener('click', function(e) {
                e.stopPropagation();
                // Close all other dropdowns first
                document.querySelectorAll('.dropdown-content').forEach(dc => {
                    if (dc !== content) {
                        dc.classList.add('hidden');
                        dc.classList.remove('active');
                    }
                });
                // Toggle this dropdown
                content.classList.toggle('hidden');
                content.classList.toggle('active');
            });
        }
    });
}

function closeFlashMessage(element) {
    const flashMessage = element.closest('.flash-message');
    if (flashMessage) {
        flashMessage.remove();
    }
}

// Utility function to escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

// Initialize the page when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Set up visibility toggle listeners
    const isPublicCheckbox = document.getElementById('is-public');
    if (isPublicCheckbox) {
        isPublicCheckbox.addEventListener('change', function() {
            toggleVisibilityLabel('is-public', 'visibility-label');
        });
    }
    
    const editIsPublicCheckbox = document.getElementById('edit-is-public');
    if (editIsPublicCheckbox) {
        editIsPublicCheckbox.addEventListener('change', function() {
            toggleVisibilityLabel('edit-is-public', 'edit-visibility-label');
        });
    }
    
    // Set up image upload listeners - FIXED for multiple images
    const announcementImages = document.getElementById('announcement-images');
    if (announcementImages) {
        announcementImages.addEventListener('change', function() {
            previewImages(this);
        });
    }
    
    const editAnnouncementImages = document.getElementById('edit-announcement-images');
    if (editAnnouncementImages) {
        editAnnouncementImages.addEventListener('change', function() {
            previewImages(this);
        });
    }
    
    // Set up remove image button listeners
    const removeImagesBtn = document.getElementById('remove-images');
    if (removeImagesBtn) {
        removeImagesBtn.addEventListener('click', function() {
            removeImages('remove-images');
        });
    }
    
    const editRemoveImagesBtn = document.getElementById('edit-remove-images');
    if (editRemoveImagesBtn) {
        editRemoveImagesBtn.addEventListener('click', function() {
            removeImages('edit-remove-images');
        });
    }
    
    // Set up filter button
    const applyFiltersBtn = document.getElementById('apply-filters');
    if (applyFiltersBtn) {
        applyFiltersBtn.addEventListener('click', applyFilters);
    }
    
    // Set up form submit handlers - FIXED to use regular form submission
    const newAnnouncementForm = document.getElementById('newAnnouncementForm');
    if (newAnnouncementForm) {
        newAnnouncementForm.addEventListener('submit', function(e) {
            // Let the form submit normally to handle file uploads properly
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-circle-notch fa-spin mr-2"></i> Creating...';
            }
        });
    }
    
    const editAnnouncementForm = document.getElementById('editAnnouncementForm');
    if (editAnnouncementForm) {
        editAnnouncementForm.addEventListener('submit', function(e) {
            // Let the form submit normally to handle file uploads properly
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-circle-notch fa-spin mr-2"></i> Updating...';
            }
        });
    }
    
    // Set up delete confirmation buttons
    const cancelDeleteBtn = document.getElementById('cancel-delete');
    if (cancelDeleteBtn) {
        cancelDeleteBtn.addEventListener('click', closeDeleteConfirmationModal);
    }
    
    const confirmDeleteBtn = document.getElementById('confirm-delete');
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', function() {
            const announcementId = document.getElementById('delete-announcement-id').value;
            if (announcementId) {
                submitDeleteForm(announcementId);
            }
        });
    }
    
    // Set up image preview modal close
    const closeImagePreviewBtn = document.getElementById('close-image-preview');
    if (closeImagePreviewBtn) {
        closeImagePreviewBtn.addEventListener('click', closeImagePreviewModal);
    }
    
    // Set initial filter values from URL
    const url = new URL(window.location);
    const visibility = url.searchParams.get('visibility');
    const dateRange = url.searchParams.get('date_range');
    
    const visibilityFilter = document.getElementById('visibility-filter');
    const dateRangeFilter = document.getElementById('date-range-filter');
    
    if (visibility && visibilityFilter) visibilityFilter.value = visibility;
    if (dateRange && dateRangeFilter) dateRangeFilter.value = dateRange;
    
    // Initialize dropdowns
    initializeDropdowns();
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', function() {
        document.querySelectorAll('.dropdown-content.active').forEach(dropdown => {
            dropdown.classList.add('hidden');
            dropdown.classList.remove('active');
        });
    });
    
    // Load announcements
    loadAnnouncements();
});

function submitDeleteForm(announcementId) {
    const formData = new FormData();
    formData.append('announcement_id', announcementId);
    
    // Get CSRF token
    const csrfToken = document.querySelector('input[name="csrf_token"]');
    if (csrfToken) {
        formData.append('csrf_token', csrfToken.value);
    }
    
    // Show loading state in the delete confirmation modal
    const confirmDeleteBtn = document.getElementById('confirm-delete');
    const originalBtnHtml = confirmDeleteBtn.innerHTML;
    confirmDeleteBtn.disabled = true;
    confirmDeleteBtn.innerHTML = '<i class="fas fa-circle-notch fa-spin mr-2"></i> Deleting...';
    
    fetch('/office/delete-announcement', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        // Handle both JSON and redirect responses
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return response.json();
        } else {
            // If it's a redirect, reload the page
            window.location.reload();
            return Promise.resolve();
        }
    })
    .then(data => {
        if (data) {
            // Close the modal
            closeDeleteConfirmationModal();
            
            // Show success message if provided
            if (data.message) {
                showFlashMessage(data.message, 'success');
            }
            
            // Refresh the announcements
            loadAnnouncements();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Failed to delete announcement. Please try again.');
        
        // Restore button state
        confirmDeleteBtn.disabled = false;
        confirmDeleteBtn.innerHTML = originalBtnHtml;
        
        // Close the modal
        closeDeleteConfirmationModal();
    });
}

function showFlashMessage(message, type = 'success') {
    const flashContainer = document.createElement('div');
    const bgColor = type === 'success' ? 'bg-green-100 border-green-400 text-green-700' : 'bg-red-100 border-red-400 text-red-700';
    const icon = type === 'success' ? 'fas fa-check-circle' : 'fas fa-exclamation-circle';
    
    flashContainer.className = `flash-message fixed top-4 right-4 ${bgColor} border px-4 py-3 rounded z-50 flex items-center justify-between max-w-md`;
    flashContainer.innerHTML = `
        <div class="flex items-center">
            <i class="${icon} mr-2"></i>
            <span>${escapeHtml(message)}</span>
        </div>
        <button onclick="closeFlashMessage(this)" class="hover:opacity-75">
            <i class="fas fa-times"></i>
        </button>
    `;
    document.body.appendChild(flashContainer);
    
    // Auto-hide the message after 5 seconds
    setTimeout(() => {
        if (document.body.contains(flashContainer)) {
            flashContainer.remove();
        }
    }, 5000);
}