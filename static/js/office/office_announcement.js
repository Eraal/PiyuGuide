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
                const currentImageContainer = document.getElementById('edit-current-image-container');
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

// Image preview functions - handle single file input IDs used in template
function previewImages(input) {
    const previewContainer = input.id === 'announcement-image'
        ? document.getElementById('image-preview-container')
        : document.getElementById('edit-image-preview-container');
    if (!previewContainer) return;

    const imagePreviewsDiv = previewContainer.querySelector('.image-previews') || (function () {
        const div = document.createElement('div');
        div.className = 'image-previews grid grid-cols-2 md:grid-cols-3 gap-4';
        previewContainer.appendChild(div);
        return div;
    })();

    if (input.files && input.files.length > 0) {
        imagePreviewsDiv.innerHTML = '';
        Array.from(input.files).forEach((file, index) => {
            const reader = new FileReader();
            reader.onload = function (e) {
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
    const input = buttonId === 'remove-image'
        ? document.getElementById('announcement-image')
        : document.getElementById('edit-announcement-image');

    const previewContainer = buttonId === 'remove-image'
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
    // Update URL without reload
    const newUrl = `${window.location.pathname}?${queryParams.toString()}`;
    window.history.replaceState({}, '', newUrl);
    // Reset and reload feed from first page
    resetAnnouncementsFeed();
    loadAnnouncements(__officeAnnPage, true);
}

// Infinite scroll state
let __officeAnnPage = 1;
let __officeAnnHasMore = true;
let __officeAnnLoading = false;

function resetAnnouncementsFeed() {
    const container = document.getElementById('announcements-container');
    if (container) container.innerHTML = '';
    __officeAnnPage = 1;
    __officeAnnHasMore = true;
}

function loadAnnouncements(page = __officeAnnPage, append = true) {
    if (__officeAnnLoading || !__officeAnnHasMore) return;

    // Get current filters from URL
    const urlParams = new URLSearchParams(window.location.search);
    const visibility = urlParams.get('visibility') || 'all';
    const dateRange = urlParams.get('date_range') || 'all';

    const container = document.getElementById('announcements-container');
    const loading = document.getElementById('infinite-loading');
    if (!container) return;

    __officeAnnLoading = true;
    if (loading) loading.classList.remove('hidden');
    if (!append && container) container.innerHTML = '';

    // Build query for fetch (no template string side-effects)
    const queryParams = new URLSearchParams();
    queryParams.append('page', page);
    if (visibility !== 'all') queryParams.append('visibility', visibility);
    if (dateRange !== 'all') queryParams.append('date_range', dateRange);

    fetch(`/office/api/office-announcements?${queryParams.toString()}`)
        .then(res => {
            if (!res.ok) throw new Error('Failed to fetch announcements');
            return res.json();
        })
        .then(data => {
            if (!data || !Array.isArray(data.announcements)) data.announcements = [];
            if (append) {
                appendAnnouncements(data.announcements);
            } else {
                renderAnnouncements(data.announcements);
            }
            const pg = data.pagination || {};
            if (typeof pg.has_next === 'boolean') {
                __officeAnnHasMore = pg.has_next;
            } else if (typeof pg.total_pages === 'number' && typeof pg.current_page === 'number') {
                __officeAnnHasMore = pg.current_page < pg.total_pages;
            } else {
                __officeAnnHasMore = data.announcements.length > 0; // fallback
            }
            if (__officeAnnHasMore) __officeAnnPage = (pg.current_page || page) + 1;
        })
        .catch(err => {
            console.error('Error loading announcements:', err);
        })
        .finally(() => {
            __officeAnnLoading = false;
            if (loading) loading.classList.add('hidden');
        });
}

function appendAnnouncements(items) {
    const container = document.getElementById('announcements-container');
    if (!container) return;
    if (!items || items.length === 0) {
        if (container.children.length === 0) {
            renderAnnouncements([]); // empty state on first load
        }
        return;
    }
    const html = buildAnnouncementsHtml(items);
    container.insertAdjacentHTML('beforeend', html);
    initializeDropdowns();
}

function buildAnnouncementsHtml(announcements) {
    const currentUserIdElement = document.getElementById('current-user-id');
    const currentUserId = currentUserIdElement ? currentUserIdElement.value : null;
    let html = '';
    (announcements || []).forEach(announcement => {
        const canEdit = announcement.can_edit || (currentUserId && announcement.author_id == currentUserId);
        const createdDateText = announcement.created_at;
        const header = `
            <div class="ann-header mb-3">
                <div class="ann-avatar">
                    ${announcement.author_avatar ? `<img src="${announcement.author_avatar}" alt="Profile" class="w-full h-full object-cover" />` : `<i class=\"fas fa-user\"></i>`}
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-start gap-2 flex-wrap">
                        <span class="ann-name">${escapeHtml(announcement.author_name || 'Unknown')}</span>
                        ${announcement.is_public ? `<span class=\"ann-badge\">Public</span>` : `<span class=\"ann-badge\">${escapeHtml(announcement.office_name || 'Office')}</span>`}
                    </div>
                    <div class="ann-meta mt-1">
                        <i class="fas fa-clock text-xs"></i>
                        <span>${escapeHtml(createdDateText)}</span>
                    </div>
                </div>
                ${canEdit ? `
                <div class=\"ann-actions dropdown ml-auto\">
                    <button class=\"text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-full h-9 w-9 flex items-center justify-center transition-colors\" aria-haspopup=\"true\" aria-expanded=\"false\">
                        <i class=\"fas fa-ellipsis-h\"></i>
                    </button>
                    <div class=\"dropdown-content hidden\">
                        <a href=\"#\" onclick=\"openEditAnnouncementModal(${announcement.id})\" class=\"flex items-center px-4 py-2 hover:bg-blue-50 text-gray-700\"><i class=\"fas fa-edit mr-2 text-blue-600\"></i> Edit</a>
                        <a href=\"#\" onclick=\"confirmDeleteAnnouncement(${announcement.id}, ${announcement.author_id || currentUserId})\" class=\"flex items-center px-4 py-2 hover:bg-red-50 text-red-600\"><i class=\"fas fa-trash-alt mr-2\"></i> Delete</a>
                    </div>
                </div>` : ''}
            </div>`;

        const bodyId = `body-${announcement.id}`;
        const body = `
            ${announcement.title ? `<h2 class=\"ann-title\">${escapeHtml(announcement.title)}</h2>` : ''}
            <div class=\"ann-body mb-3\" data-clamped=\"true\" id=\"${bodyId}\">\n        <p>${escapeHtml(announcement.content)}</p>\n      </div>
            <button class=\"show-more-btn\" data-target=\"${bodyId}\" onclick=\"toggleClamp(this)\"><span>Show more</span><i class=\"fas fa-chevron-down text-xs\"></i></button>
        `;

        const images = (announcement.images && announcement.images.length > 0) ? `
            <div class=\"ann-gallery mt-4 ${announcement.images.length === 1 ? 'layout-1' : announcement.images.length === 2 ? 'layout-2' : 'layout-3'}\">
                ${announcement.images.slice(0, 6).map((image, idx) => `
                    <figure class=\"relative rounded-lg overflow-hidden ${idx===0 && announcement.images.length>3 ? 'span-2' : ''}\">
                        <img src=\"${image.image_path}\" alt=\"${escapeHtml(image.caption || 'Announcement image')}\" class=\"w-full ${idx===0 && announcement.images.length>3 ? 'md:h-80' : 'h-40'} object-cover preview-image cursor-pointer\" onclick=\"showImagePreview('${image.image_path}', '${escapeHtml(image.caption || '')}')\" />
                        ${image.caption ? `<figcaption>${escapeHtml(image.caption)}</figcaption>` : ''}
                        ${(idx===5 && announcement.images.length>6) ? `<div class=\"absolute inset-0 bg-black bg-opacity-60 flex items-center justify-center rounded-lg\"><span class=\"text-white text-xl font-bold\">+${announcement.images.length-6} more</span></div>` : ''}
                    </figure>
                `).join('')}
            </div>
        ` : '';

        const footer = `
            <div class=\"ann-footer\">
                <div class=\"flex items-center gap-3 text-xs\">
                    ${announcement.is_public ? `<span class=\"visibility-pill\"><i class=\"fas fa-globe\"></i> All Users</span>` : `<span class=\"visibility-pill office\"><i class=\"fas fa-building\"></i> ${escapeHtml(announcement.office_name || 'Office')} Office</span>`}
                </div>
                <div class=\"text-xs text-gray-400 tracking-wide uppercase font-medium\">Announcement</div>
            </div>`;

        html += `
            <div class=\"ann-card announcement-card p-6 border-l-4 ${announcement.is_public ? 'border-green-500' : 'border-blue-500'}\">\n        ${header}\n        ${body}\n        ${images}\n        ${footer}\n      </div>
        `;
    });
    return html;
}

function renderAnnouncements(announcements) {
    const container = document.getElementById('announcements-container');
    if (!container) return;
    
    // Get current user ID for permission checks
    const currentUserIdElement = document.getElementById('current-user-id');
    const currentUserId = currentUserIdElement ? currentUserIdElement.value : null;
    
        if (!announcements || announcements.length === 0) {
                container.innerHTML = `
                    <div class="ann-card p-12 text-center">
                        <div class="text-blue-400 mb-4">
                            <i class="fas fa-bullhorn fa-4x"></i>
                        </div>
                        <h3 class="text-xl font-medium text-gray-700 mb-2">No Announcements Yet</h3>
                        <p class="text-gray-500 mb-6">Create your first announcement to notify students and staff.</p>
                        <button onclick="openNewAnnouncementModal()" class="bg-blue-800 hover:bg-blue-900 text-white font-medium py-3 px-6 rounded-full transition-colors duration-200 flex items-center mx-auto shadow">
                            <i class="fas fa-plus mr-2"></i> Create Announcement
                        </button>
                    </div>
                `;
                return;
        }
    
        let html = '';
    
        announcements.forEach(announcement => {
                const canEdit = announcement.can_edit || (currentUserId && announcement.author_id == currentUserId);
                const createdDateText = announcement.created_at;

                // Header mapped to Campus styles
                const header = `
                        <div class="ann-header mb-3">
                            <div class="ann-avatar">
                                ${announcement.author_avatar ? `<img src="${announcement.author_avatar}" alt="Profile" class="w-full h-full object-cover" />` : `<i class=\"fas fa-user\"></i>`}
                            </div>
                            <div class="flex-1 min-w-0">
                                <div class="flex items-start gap-2 flex-wrap">
                                    <span class="ann-name">${escapeHtml(announcement.author_name || 'Unknown')}</span>
                                    ${announcement.is_public ? `<span class=\"ann-badge\">Public</span>` : `<span class=\"ann-badge\">${escapeHtml(announcement.office_name || 'Office')}</span>`}
                                </div>
                                <div class="ann-meta mt-1">
                                    <i class="fas fa-clock text-xs"></i>
                                    <span>${escapeHtml(createdDateText)}</span>
                                </div>
                            </div>
                            ${canEdit ? `
                            <div class=\"ann-actions dropdown ml-auto\">
                                <button class=\"text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-full h-9 w-9 flex items-center justify-center transition-colors\" aria-haspopup=\"true\" aria-expanded=\"false\">
                                    <i class=\"fas fa-ellipsis-h\"></i>
                                </button>
                                <div class=\"dropdown-content\">
                                    <a href=\"#\" onclick=\"openEditAnnouncementModal(${announcement.id})\" class=\"flex items-center px-4 py-2 hover:bg-blue-50 text-gray-700\"><i class=\"fas fa-edit mr-2 text-blue-600\"></i> Edit</a>
                                    <a href=\"#\" onclick=\"confirmDeleteAnnouncement(${announcement.id}, ${announcement.author_id || currentUserId})\" class=\"flex items-center px-4 py-2 hover:bg-red-50 text-red-600\"><i class=\"fas fa-trash-alt mr-2\"></i> Delete</a>
                                </div>
                            </div>` : ''}
                        </div>`;

                // Title and body with clamping and Show more
                const bodyId = `body-${announcement.id}`;
                const body = `
                        ${announcement.title ? `<h2 class=\"ann-title\">${escapeHtml(announcement.title)}</h2>` : ''}
                        <div class=\"ann-body mb-3\" data-clamped=\"true\" id=\"${bodyId}\">
                                <p>${escapeHtml(announcement.content)}</p>
                        </div>
                        <button class=\"show-more-btn\" data-target=\"${bodyId}\" onclick=\"toggleClamp(this)\"><span>Show more</span><i class=\"fas fa-chevron-down text-xs\"></i></button>
                `;

                // Images as gallery aligned with Campus style
                const images = (announcement.images && announcement.images.length > 0) ? `
                    <div class=\"ann-gallery mt-4 ${announcement.images.length === 1 ? 'layout-1' : announcement.images.length === 2 ? 'layout-2' : 'layout-3'}\">
                        ${announcement.images.slice(0, 6).map((image, idx) => `
                            <figure class=\"relative rounded-lg overflow-hidden ${idx===0 && announcement.images.length>3 ? 'span-2' : ''}\">
                                <img src=\"${image.image_path}\" alt=\"${escapeHtml(image.caption || 'Announcement image')}\" class=\"w-full ${idx===0 && announcement.images.length>3 ? 'md:h-80' : 'h-40'} object-cover preview-image cursor-pointer\" onclick=\"showImagePreview('${image.image_path}', '${escapeHtml(image.caption || '')}')\" />
                                ${image.caption ? `<figcaption>${escapeHtml(image.caption)}</figcaption>` : ''}
                                ${(idx===5 && announcement.images.length>6) ? `<div class=\"absolute inset-0 bg-black bg-opacity-60 flex items-center justify-center rounded-lg\"><span class=\"text-white text-xl font-bold\">+${announcement.images.length-6} more</span></div>` : ''}
                            </figure>
                        `).join('')}
                    </div>
                ` : '';

                // Footer with visibility pill
                const footer = `
                    <div class=\"ann-footer\">
                        <div class=\"flex items-center gap-3 text-xs\">
                            ${announcement.is_public ? `<span class=\"visibility-pill\"><i class=\"fas fa-globe\"></i> All Users</span>` : `<span class=\"visibility-pill office\"><i class=\"fas fa-building\"></i> ${escapeHtml(announcement.office_name || 'Office')} Office</span>`}
                        </div>
                        <div class=\"text-xs text-gray-400 tracking-wide uppercase font-medium\">Announcement</div>
                    </div>`;

                html += `
                    <div class=\"ann-card announcement-card p-6 border-l-4 ${announcement.is_public ? 'border-green-500' : 'border-blue-500'}\">
                        ${header}
                        ${body}
                        ${images}
                        ${footer}
                    </div>
                `;
        });
    
    container.innerHTML = html;
    
    // Initialize dropdowns for the new content
    initializeDropdowns();
}

// Toggle clamp for announcement content, shared with Campus Admin UX
function toggleClamp(btn){
    const id = btn.getAttribute('data-target');
    const body = document.getElementById(id);
    if(!body) return;
    const clamped = body.getAttribute('data-clamped') === 'true';
    if(clamped){
        body.setAttribute('data-clamped','false');
        const span = btn.querySelector('span');
        if (span) span.textContent = 'Show less';
        const icon = btn.querySelector('i');
        if (icon) icon.classList.add('rotate-180');
    } else {
        body.setAttribute('data-clamped','true');
        const span = btn.querySelector('span');
        if (span) span.textContent = 'Show more';
        const icon = btn.querySelector('i');
        if (icon) icon.classList.remove('rotate-180');
        body.scrollIntoView({behavior:'smooth', block:'center'});
    }
}

// Pagination renderer removed in favor of infinite scrolling

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
    
    // Set up image upload listeners (IDs aligned with template)
    const announcementImages = document.getElementById('announcement-image');
    if (announcementImages) {
        announcementImages.addEventListener('change', function() {
            previewImages(this);
        });
    }
    const editAnnouncementImages = document.getElementById('edit-announcement-image');
    if (editAnnouncementImages) {
        editAnnouncementImages.addEventListener('change', function() {
            previewImages(this);
        });
    }

    // Set up remove image button listeners (IDs aligned)
    const removeImageBtn = document.getElementById('remove-image');
    if (removeImageBtn) {
        removeImageBtn.addEventListener('click', function() {
            removeImages('remove-image');
        });
    }
    const editRemoveImageBtn = document.getElementById('edit-remove-image');
    if (editRemoveImageBtn) {
        editRemoveImageBtn.addEventListener('click', function() {
            removeImages('edit-remove-image');
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
    
        // Setup infinite scroll observer
        const sentinel = document.getElementById('infinite-scroll-sentinel');
        if ('IntersectionObserver' in window && sentinel) {
            const io = new IntersectionObserver(entries => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        loadAnnouncements(__officeAnnPage, true);
                    }
                });
            });
            io.observe(sentinel);
        } else {
            // Fallback: basic scroll listener
            window.addEventListener('scroll', () => {
                if (__officeAnnLoading || !__officeAnnHasMore) return;
                const nearBottom = (window.innerHeight + window.scrollY) >= (document.body.offsetHeight - 400);
                if (nearBottom) loadAnnouncements(__officeAnnPage, true);
            });
        }

        // Initial load (fresh)
        resetAnnouncementsFeed();
        loadAnnouncements(__officeAnnPage, true);
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