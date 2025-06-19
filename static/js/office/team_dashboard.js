/**
 * Team Dashboard JavaScript
 * Handles dynamic functionality for the Office Team Dashboard
 */

class TeamDashboard {
    constructor() {
        this.charts = {};
        this.refreshInterval = null;
        this.socket = null;
        
        // Initialize dashboard
        this.initializeEventListeners();
        this.initializeCharts();
        this.startAutoRefresh();
        this.connectWebsocket();
    }
    
    /**
     * Set up event listeners for UI interactions
     */
    initializeEventListeners() {
        // Toggle staff details sections
        document.querySelectorAll('.toggle-details').forEach(button => {
            button.addEventListener('click', this.toggleStaffDetails.bind(this));
        });
        
        // Team sorting dropdown
        const sortSelect = document.getElementById('sortTeamBy');
        if (sortSelect) {
            sortSelect.addEventListener('change', this.sortTeamMembers.bind(this));
        }
        
        // Quick action buttons
        const updateStatusBtn = document.getElementById('updateStatusBtn');
        if (updateStatusBtn) {
            updateStatusBtn.addEventListener('click', this.openStatusModal.bind(this));
        }
        
        const reassignBtn = document.getElementById('reassignInquiryBtn');
        if (reassignBtn) {
            reassignBtn.addEventListener('click', this.openReassignModal.bind(this));
        }
        
        const announcementBtn = document.getElementById('postAnnouncementBtn');
        if (announcementBtn) {
            announcementBtn.addEventListener('click', this.openAnnouncementModal.bind(this));
        }
        
        // Status update options
        document.querySelectorAll('.status-option').forEach(option => {
            option.addEventListener('click', this.updateStatus.bind(this));
        });
        
        // Modal close buttons
        document.querySelectorAll('[onclick^="closeModal"]').forEach(button => {
            const modalId = button.getAttribute('onclick').match(/closeModal\('(.+?)'\)/)[1];
            button.addEventListener('click', () => this.closeModal(modalId));
        });
        
        // Form submissions
        const reassignForm = document.getElementById('reassignForm');
        if (reassignForm) {
            reassignForm.addEventListener('submit', this.handleReassign.bind(this));
        }
    }
    
    /**
     * Toggle the visibility of staff detail sections
     * @param {Event} event - Click event
     */
    toggleStaffDetails(event) {
        const button = event.currentTarget;
        const staffId = button.getAttribute('data-staff-id');
        const detailsDiv = button.parentNode.querySelector('.staff-details');
        const showText = button.querySelector('.show-text');
        const hideText = button.querySelector('.hide-text');
        
        detailsDiv.classList.toggle('hidden');
        showText.classList.toggle('hidden');
        hideText.classList.toggle('hidden');
    }
    
    /**
     * Sort team members based on selected criteria
     * @param {Event} event - Change event
     */
    sortTeamMembers(event) {
        const sortBy = event.target.value;
        const container = document.getElementById('team-members-container');
        const cards = Array.from(container.querySelectorAll('.staff-card'));
        
        cards.sort((a, b) => {
            if (sortBy === 'status') {
                // Online first
                return (b.dataset.status === 'online') - (a.dataset.status === 'online');
            } else if (sortBy === 'activity') {
                // Most active first
                return parseInt(b.dataset.activity) - parseInt(a.dataset.activity);
            } else if (sortBy === 'workload') {
                // High workload first
                const workloadOrder = { 'high': 3, 'medium': 2, 'low': 1 };
                return workloadOrder[b.dataset.workload] - workloadOrder[a.dataset.workload];
            }
            return 0;
        });
        
        // Reorder DOM elements
        cards.forEach(card => container.appendChild(card));
    }
    
    /**
     * Initialize Chart.js visualizations
     */
    initializeCharts() {
        // Get workload distribution data
        const lowWorkload = parseInt(document.getElementById('workload-chart').dataset.low || 0);
        const mediumWorkload = parseInt(document.getElementById('workload-chart').dataset.medium || 0);
        const highWorkload = parseInt(document.getElementById('workload-chart').dataset.high || 0);
        
        // Workload distribution chart
        const workloadCtx = document.getElementById('workload-chart').getContext('2d');
        this.charts.workload = new Chart(workloadCtx, {
            type: 'pie',
            data: {
                labels: ['Low Workload', 'Medium Workload', 'High Workload'],
                datasets: [{
                    data: [lowWorkload, mediumWorkload, highWorkload],
                    backgroundColor: ['#10B981', '#F59E0B', '#EF4444'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
        
        // Team performance chart
        const performanceCtx = document.getElementById('performance-chart').getContext('2d');
        const avgResolved = parseFloat(document.getElementById('performance-chart').dataset.resolved || 0);
        const avgSessions = parseFloat(document.getElementById('performance-chart').dataset.sessions || 0);
        const avgResponseTime = parseFloat(document.getElementById('performance-chart').dataset.responseTime || 0);
        
        this.charts.performance = new Chart(performanceCtx, {
            type: 'bar',
            data: {
                labels: ['Inquiries Resolved', 'Sessions Conducted', 'Response Time (min)'],
                datasets: [{
                    label: 'Team Average',
                    data: [avgResolved, avgSessions, avgResponseTime],
                    backgroundColor: 'rgba(59, 130, 246, 0.6)',
                    borderColor: 'rgb(37, 99, 235)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                },
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }
    
    /**
     * Connect to WebSocket server (no-op - WebSocket functionality has been removed)
     */
    connectWebsocket() {
        // WebSocket functionality has been removed
        console.log('WebSocket functionality has been removed');
    }
    
    /**
     * Update staff status in the UI
     * @param {Object} data - Status update data
     */
    updateStaffStatus(data) {
        const staffElement = document.getElementById('staff-' + data.user_id);
        if (!staffElement) return;
        
        const statusIndicator = staffElement.querySelector('.status-indicator');
        if (!statusIndicator) return;
        
        // Clear existing status classes
        statusIndicator.classList.remove('bg-green-500', 'bg-yellow-500', 'bg-red-500', 'bg-gray-400');
        
        // Add appropriate class and title
        switch (data.status) {
            case 'online':
                statusIndicator.classList.add('bg-green-500');
                statusIndicator.setAttribute('title', 'Online');
                break;
            case 'away':
                statusIndicator.classList.add('bg-yellow-500');
                statusIndicator.setAttribute('title', 'Away');
                break;
            case 'busy':
                statusIndicator.classList.add('bg-red-500');
                statusIndicator.setAttribute('title', 'Busy');
                break;
            case 'offline':
                statusIndicator.classList.add('bg-gray-400');
                statusIndicator.setAttribute('title', 'Offline');
                break;
        }
        
        // Update sort attribute
        staffElement.dataset.status = data.status === 'online' ? 'online' : 'offline';
        
        // Re-sort if sorted by status
        if (document.getElementById('sortTeamBy').value === 'status') {
            this.sortTeamMembers({ target: { value: 'status' } });
        }
    }
    
    /**
     * Add a new activity item to the activity feed
     * @param {Object} data - Activity data
     */
    addActivityItem(data) {
        const activityFeed = document.getElementById('activity-feed');
        if (!activityFeed) return;
        
        const activityItem = document.createElement('div');
        activityItem.className = 'p-4 border-t border-gray-100 first:border-t-0';
        
        activityItem.innerHTML = `
            <div class="flex">
                <div class="flex-shrink-0 mr-3">
                    <div class="h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center">
                        <i class="fas fa-history text-gray-500 text-sm"></i>
                    </div>
                </div>
                <div>
                    <p class="text-sm text-gray-800">${data.action}</p>
                    <p class="text-xs text-gray-500 mt-1">
                        ${data.user_name ? 'By ' + data.user_name + ' • ' : ''}
                        ${new Date(data.timestamp).toLocaleString()}
                    </p>
                </div>
            </div>
        `;
        
        // Add to the beginning of the feed
        activityFeed.insertBefore(activityItem, activityFeed.firstChild);
        
        // Remove the last item if there are more than 10
        const items = activityFeed.querySelectorAll(':scope > div');
        if (items.length > 10) {
            activityFeed.removeChild(items[items.length - 1]);
        }
    }
    
    /**
     * Start automatic data refresh interval
     */
    startAutoRefresh() {
        this.refreshInterval = setInterval(() => {
            this.refreshTeamData();
        }, 60000); // Every minute
    }
    
    /**
     * Fetch fresh team data from the server
     */
    refreshTeamData() {
        fetch('/office/api/team-data')
            .then(response => response.json())
            .then(data => {
                // Update online status for each staff member
                data.staff_data.forEach(staff => {
                    const staffElement = document.getElementById('staff-' + staff.id);
                    if (staffElement) {
                        const statusIndicator = staffElement.querySelector('.status-indicator');
                        if (statusIndicator) {
                            if (staff.is_online) {
                                statusIndicator.classList.remove('bg-gray-400');
                                statusIndicator.classList.add('bg-green-500');
                                statusIndicator.setAttribute('title', 'Online');
                            } else {
                                statusIndicator.classList.remove('bg-green-500');
                                statusIndicator.classList.add('bg-gray-400');
                                statusIndicator.setAttribute('title', 'Offline');
                            }
                        }
                        
                        // Update data attributes for sorting
                        staffElement.dataset.status = staff.is_online ? 'online' : 'offline';
                    }
                });
                
                // Update counters
                const pendingElement = document.querySelector('.bg-yellow-500').closest('.rounded-lg').querySelector('.text-2xl');
                if (pendingElement) {
                    pendingElement.textContent = data.pending_inquiries;
                }
                
                const inProgressElement = document.querySelector('.bg-yellow-500').closest('.rounded-lg').querySelector('.font-medium');
                if (inProgressElement) {
                    inProgressElement.textContent = data.in_progress_inquiries;
                }
            })
            .catch(error => console.error('Error refreshing team data:', error));
    }
    
    /**
     * Open the status update modal
     */
    openStatusModal() {
        document.getElementById('statusModal').classList.remove('hidden');
    }
    
    /**
     * Open the inquiry reassignment modal
     */
    openReassignModal() {
        // Load pending inquiries via AJAX
        fetch('/office/api/pending-inquiries')
            .then(response => response.json())
            .then(data => {
                const select = document.getElementById('inquirySelect');
                select.innerHTML = '<option value="">Select an inquiry...</option>';
                
                data.inquiries.forEach(inquiry => {
                    const option = document.createElement('option');
                    option.value = inquiry.id;
                    option.textContent = `#${inquiry.id} - ${inquiry.subject}`;
                    select.appendChild(option);
                });
                
                document.getElementById('reassignModal').classList.remove('hidden');
            })
            .catch(error => {
                console.error('Error loading inquiries:', error);
                alert('Unable to load inquiries. Please try again.');
            });
    }
    
    /**
     * Open the announcement creation modal
     */
    openAnnouncementModal() {
        // Implement or link to your existing announcement creation modal
        alert('Announcement feature coming soon!');
    }
    
    /**
     * Close any modal by ID
     * @param {string} modalId - The modal element ID
     */
    closeModal(modalId) {
        document.getElementById(modalId).classList.add('hidden');
    }
    
    /**
     * Update user status via API
     * @param {Event} event - Click event
     */
    updateStatus(event) {
        const status = event.currentTarget.getAttribute('data-status');
        
        fetch('/office/api/update-staff-status', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken(),
            },
            body: JSON.stringify({ status }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.closeModal('statusModal');
                
                // Update UI status indicator
                const statusIndicator = document.getElementById('staff-status-indicator');
                if (statusIndicator) {
                    statusIndicator.classList.remove('bg-green-500', 'bg-yellow-500', 'bg-red-500', 'bg-gray-500');
                    
                    if (status === 'online') {
                        statusIndicator.classList.add('bg-green-500');
                    } else if (status === 'away') {
                        statusIndicator.classList.add('bg-yellow-500');
                    } else if (status === 'busy') {
                        statusIndicator.classList.add('bg-red-500');
                    } else {
                        statusIndicator.classList.add('bg-gray-500');
                    }
                }
            }
        })
        .catch(error => console.error('Error updating status:', error));
    }
    
    /**
     * Handle inquiry reassignment form submission
     * @param {Event} event - Form submit event
     */
    handleReassign(event) {
        event.preventDefault();
        
        const inquiryId = document.getElementById('inquirySelect').value;
        const staffId = document.getElementById('staffSelect').value;
        
        if (!inquiryId || !staffId) {
            alert('Please select both an inquiry and a staff member.');
            return;
        }
        
        fetch('/office/api/reassign-inquiry', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken(),
            },
            body: JSON.stringify({ inquiry_id: inquiryId, staff_id: staffId }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.closeModal('reassignModal');
                
                // Show success notification
                const notification = document.createElement('div');
                notification.className = 'fixed bottom-4 right-4 bg-green-500 text-white px-4 py-2 rounded-md shadow-lg';
                notification.textContent = 'Inquiry reassigned successfully!';
                document.body.appendChild(notification);
                
                // Remove after 3 seconds
                setTimeout(() => {
                    document.body.removeChild(notification);
                }, 3000);
            } else {
                alert('Error: ' + (data.error || 'Failed to reassign inquiry'));
            }
        })
        .catch(error => console.error('Error reassigning inquiry:', error));
    }
    
    /**
     * Get CSRF token from page
     * @returns {string} CSRF token
     */
    getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    window.teamDashboard = new TeamDashboard();
}); 