// WebSocket connection for counseling page for office

// Video Counseling WebSocket Client for Office/Counselor
class VideoCounselingClient {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.socket = null;
        this.peerConnection = null;
        this.localStream = null;
        this.remoteStream = null;
        this.isConnected = false;
        this.isAudioEnabled = true;
        this.isVideoEnabled = true;
        this.isScreenSharing = false;
        this.screenStream = null;
        this.role = 'counselor';
        this.otherParticipant = null;
        this.chatMessages = [];
        this.pendingIceCandidates = [];
        this.reconnectionAttempts = 0;
        this.mediaDevicesSupported = Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
        this.isHttps = location.protocol === 'https:' || 
                      location.hostname === 'localhost' || 
                      location.hostname === '127.0.0.1' ||
                      location.hostname.endsWith('.localhost');
        
        // Check if we're in a secure context for media access
        this.isSecureContext = window.isSecureContext || this.isHttps;
        
        // Track mock media state
        this.hasMockVideo = false;
        this.hasMockAudio = false;
        this.mockVideoCanvas = null;
        
        // More flexible media constraints with fallbacks
        this.mediaConstraints = {
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            },
            video: {
                width: { ideal: 1280, min: 640 },
                height: { ideal: 720, min: 480 },
                facingMode: "user"
            }
        };
        this.peerConnectionConfig = {
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' }
            ],
            iceCandidatePoolSize: 10
        };

        // Event callbacks
        this.onStatusChange = null;
        this.onRemoteStreamUpdate = null;
        this.onLocalStreamUpdate = null;
        this.onChatMessage = null;
        this.onParticipantJoined = null;
        this.onParticipantLeft = null;
        this.onCallStarted = null;
        this.onCallEnded = null;
        this.onError = null;
        this.onAudioStateChanged = null;
        this.onVideoStateChanged = null;
        this.onDeviceChange = null;
        
        // Set up device change listener
        if (navigator.mediaDevices && navigator.mediaDevices.ondevicechange !== undefined) {
            navigator.mediaDevices.ondevicechange = this.handleDeviceChange.bind(this);
        }
    }

    // Initialize the connection
    async init() {
        try {
            console.log('Initializing video counseling client...');
            
            // Connect to WebSocket server
            this.socket = io('/video-counseling', {
                transports: ['websocket'],
                upgrade: false
            });
            
            // Set up socket event listeners
            this.setupSocketListeners();
            
            // Request user media
            await this.setupLocalMedia();
            
            // Update status
            this.updateStatus('Connecting to session...');
            
            return true;
        } catch (error) {
            console.error('Error initializing video counseling client:', error);
            this.handleError(error);
            return false;
        }
    }

    // Set up socket event listeners
    setupSocketListeners() {
        console.log('Setting up socket listeners...');
        
        this.socket.on('connect', () => {
            console.log('Connected to video counseling server');
            this.isConnected = true;
            this.joinSession();
        });

        this.socket.on('disconnect', () => {
            console.log('Disconnected from video counseling server');
            this.isConnected = false;
            this.updateStatus('Disconnected from server');
        });

        this.socket.on('connection_success', (data) => {
            console.log('Connection success:', data);
        });

        this.socket.on('error', (data) => {
            console.error('Socket error:', data);
            this.handleError(new Error(data.message));
        });

        this.socket.on('session_joined', (data) => {
            console.log('Session joined:', data);
            this.role = data.user_role;
            this.otherParticipant = data.other_participant;
            
            // Update waiting room status
            this.updateStatus(this.getStatusMessage(data.waiting_room_status));
            
            // If call has already started, create peer connection
            if (data.call_started) {
                this.createPeerConnection();
                if (this.otherParticipant) {
                    this.initiateCall();
                }
            }
            
            // Notify about participant info
            if (this.otherParticipant && this.onParticipantJoined) {
                this.onParticipantJoined(this.otherParticipant);
            }
        });

        this.socket.on('user_joined', (data) => {
            console.log('User joined:', data);
            
            // Store other participant info
            if (data.role !== this.role) {
                this.otherParticipant = {
                    user_id: data.user_id,
                    username: data.username,
                    role: data.role
                };
                
                // Notify about participant joined
                if (this.onParticipantJoined) {
                    this.onParticipantJoined(this.otherParticipant);
                }
            }
            
            // Update waiting room status
            this.updateStatus(this.getStatusMessage(data.waiting_room_status));
        });

        this.socket.on('user_left', (data) => {
            console.log('User left:', data);
            
            // Check if it was the other participant
            if (this.otherParticipant && this.otherParticipant.user_id === data.user_id) {
                // Notify about participant left
                if (this.onParticipantLeft) {
                    this.onParticipantLeft(this.otherParticipant);
                }
                
                // Update status
                this.updateStatus('The other participant has left the session');
                
                // Close peer connection
                this.closePeerConnection();
                
                // Clear other participant
                this.otherParticipant = null;
            }
        });

        this.socket.on('start_call', (data) => {
            console.log('Start call:', data);
            
            // Create peer connection
            this.createPeerConnection();
            
            // If counselor, initiate call
            if (this.role === 'counselor' && this.otherParticipant) {
                this.initiateCall();
            }
            
            // Update status
            this.updateStatus('Call started');
            
            // Notify call started
            if (this.onCallStarted) {
                this.onCallStarted(data);
            }
        });

        this.socket.on('session_ended', (data) => {
            console.log('Session ended:', data);
            
            // Update status
            this.updateStatus('Session ended');
            
            // Close peer connection
            this.closePeerConnection();
            
            // Notify call ended
            if (this.onCallEnded) {
                this.onCallEnded(data);
            }
        });

        this.socket.on('offer', async (data) => {
            console.log('Received offer:', data);
            
            if (!this.peerConnection) {
                this.createPeerConnection();
            }
            
            try {
                await this.peerConnection.setRemoteDescription(new RTCSessionDescription(data.offer));
                console.log('Set remote description (offer)');
                
                const answer = await this.peerConnection.createAnswer();
                await this.peerConnection.setLocalDescription(answer);
                console.log('Created and set local description (answer)');
                
                this.socket.emit('answer', {
                    target: data.sender,
                    session_id: this.sessionId,
                    answer: answer
                });
                
                // Send any pending ICE candidates now that remote description is set
                this.sendPendingIceCandidates();
            } catch (error) {
                console.error('Error handling offer:', error);
                this.handleError(error);
            }
        });

        this.socket.on('answer', async (data) => {
            console.log('Received answer:', data);
            
            try {
                await this.peerConnection.setRemoteDescription(new RTCSessionDescription(data.answer));
                console.log('Set remote description (answer)');
                
                // Send any pending ICE candidates now that remote description is set
                this.sendPendingIceCandidates();
            } catch (error) {
                console.error('Error handling answer:', error);
                this.handleError(error);
            }
        });

        this.socket.on('ice_candidate', async (data) => {
            console.log('Received ICE candidate');
            
            try {
                if (this.peerConnection) {
                    await this.peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
                    console.log('Added ICE candidate');
                }
            } catch (error) {
                console.error('Error handling ICE candidate:', error);
            }
        });

        this.socket.on('audio_state_changed', (data) => {
            console.log('Audio state changed:', data);
            if (this.onAudioStateChanged) {
                this.onAudioStateChanged(data);
            }
        });

        this.socket.on('video_state_changed', (data) => {
            console.log('Video state changed:', data);
            if (this.onVideoStateChanged) {
                this.onVideoStateChanged(data);
            }
        });

        this.socket.on('chat_message', (data) => {
            console.log('Received chat message:', data);
            this.chatMessages.push(data);
            if (this.onChatMessage) {
                this.onChatMessage(data);
            }
        });
    }

    // Join the session
    joinSession() {
        if (!this.isConnected) {
            console.error('Cannot join session: not connected to server');
            return;
        }
        
        console.log('Joining session:', this.sessionId);
        this.socket.emit('join_session', {
            session_id: this.sessionId
        });
    }

    // Leave the session
    leaveSession() {
        if (!this.isConnected) {
            return;
        }
        
        console.log('Leaving session:', this.sessionId);
        this.socket.emit('leave_session', {
            session_id: this.sessionId
        });
        
        // Close peer connection
        this.closePeerConnection();
        
        // Stop local media
        this.stopLocalMedia();
    }

    // End the session (counselor only)
    endSession(notes) {
        if (!this.isConnected) {
            return;
        }
        
        console.log('Ending session:', this.sessionId);
        this.socket.emit('end_session', {
            session_id: this.sessionId,
            notes: notes
        });
        
        // Close peer connection
        this.closePeerConnection();
        
        // Stop local media
        this.stopLocalMedia();
    }

    // Set up local media
    async setupLocalMedia() {
        try {
            console.log('Setting up local media...');
            
            // Check if we're running on HTTPS or localhost
            if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
                throw new Error('Media access requires HTTPS unless on localhost');
            }
            
            // Check if media devices are available
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('Your browser does not support media devices access');
            }
            
            // Check for available devices first
            const devices = await navigator.mediaDevices.enumerateDevices();
            const hasVideoInput = devices.some(device => device.kind === 'videoinput');
            const hasAudioInput = devices.some(device => device.kind === 'audioinput');
            
            if (!hasVideoInput && !hasAudioInput) {
                throw new Error('No camera or microphone detected');
            }
            
            // Adjust constraints based on available devices
            const constraints = {
                audio: hasAudioInput,
                video: hasVideoInput ? {
                    width: { ideal: 1280, min: 640 },
                    height: { ideal: 720, min: 480 },
                    facingMode: "user"
                } : false
            };
            
            // Get user media with permission handling
            try {
                this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
                console.log('Got local stream');
                
                // Set up track ended event listeners
                this.localStream.getTracks().forEach(track => {
                    track.onended = () => {
                        console.log(`${track.kind} track ended`);
                        this.handleMediaTrackEnded(track);
                    };
                });
                
                // Notify about local stream
                if (this.onLocalStreamUpdate) {
                    this.onLocalStreamUpdate(this.localStream);
                }
                
                return true;
            } catch (err) {
                // Handle specific permission errors
                if (err.name === 'NotAllowedError') {
                    throw new Error('Camera/microphone permission denied. Please allow access in your browser settings.');
                } else if (err.name === 'NotFoundError') {
                    throw new Error('Camera/microphone not found or disconnected.');
                } else if (err.name === 'NotReadableError') {
                    throw new Error('Camera/microphone is already in use by another application.');
                } else if (err.name === 'OverconstrainedError') {
                    // Try again with lower constraints
                    return this.tryWithLowerConstraints();
                } else {
                    throw err; // Re-throw other errors
                }
            }
        } catch (error) {
            console.error('Error setting up local media:', error);
            this.handleError(error);
            return false;
        }
    }
    
    // Try with progressively lower constraints
    async tryWithLowerConstraints() {
        try {
            console.log('Trying with lower video constraints...');
            
            // Try with lower resolution
            const lowerConstraints = {
                audio: true,
                video: {
                    width: { ideal: 640, min: 320 },
                    height: { ideal: 480, min: 240 }
                }
            };
            
            this.localStream = await navigator.mediaDevices.getUserMedia(lowerConstraints);
            console.log('Got local stream with lower constraints');
            
            // Set up track ended event listeners
            this.localStream.getTracks().forEach(track => {
                track.onended = () => {
                    console.log(`${track.kind} track ended`);
                    this.handleMediaTrackEnded(track);
                };
            });
            
            // Notify about local stream
            if (this.onLocalStreamUpdate) {
                this.onLocalStreamUpdate(this.localStream);
            }
            
            return true;
        } catch (error) {
            // Try audio only as last resort
            console.log('Trying audio only...');
            try {
                this.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
                console.log('Got audio-only local stream');
                
                // Set up track ended event listeners
                this.localStream.getTracks().forEach(track => {
                    track.onended = () => {
                        console.log(`${track.kind} track ended`);
                        this.handleMediaTrackEnded(track);
                    };
                });
                
                // Notify about local stream
                if (this.onLocalStreamUpdate) {
                    this.onLocalStreamUpdate(this.localStream);
                }
                
                return true;
            } catch (finalError) {
                console.error('Failed to get media even with audio only:', finalError);
                this.handleError(new Error('Could not access any media devices. Please check your hardware and permissions.'));
                return false;
            }
        }
    }
    
    // Handle media track ended event
    handleMediaTrackEnded(track) {
        // Notify user that a device was disconnected
        const message = `Your ${track.kind} device was disconnected`;
        this.updateStatus(message);
        
        // Try to recover if possible
        if (this.localStream && this.isConnected) {
            // For now just notify, but could try to reacquire the track
            this.handleError(new Error(message));
        }
    }

    // Stop local media stream
    stopLocalMedia() {
        if (this.localStream) {
            console.log('Stopping local media...');
            
            this.localStream.getTracks().forEach(track => {
                track.stop();
            });
            
            this.localStream = null;
        }
        
        if (this.screenStream) {
            console.log('Stopping screen sharing...');
            
            this.screenStream.getTracks().forEach(track => {
                track.stop();
            });
            
            this.screenStream = null;
        }
    }

    // Create peer connection
    createPeerConnection() {
        if (this.peerConnection) {
            console.log('Peer connection already exists');
            return this.peerConnection;
        }
        
        try {
            console.log('Creating peer connection...');
            
            // Check for WebRTC support
            if (!window.RTCPeerConnection) {
                throw new Error('WebRTC is not supported in your browser');
            }
            
            this.peerConnection = new RTCPeerConnection(this.peerConnectionConfig);
            
            // Set up event handlers
            this.peerConnection.onicecandidate = this.handleIceCandidate.bind(this);
            this.peerConnection.ontrack = this.handleTrack.bind(this);
            this.peerConnection.oniceconnectionstatechange = this.handleIceConnectionStateChange.bind(this);
            this.peerConnection.onconnectionstatechange = this.handleConnectionStateChange.bind(this);
            
            // Add local stream tracks to peer connection if available
            this.addLocalTracksToConnection();
            
            console.log('Peer connection created');
            return this.peerConnection;
        } catch (error) {
            console.error('Error creating peer connection:', error);
            this.handleError(error);
            return null;
        }
    }
    
    // Add local tracks to peer connection
    addLocalTracksToConnection() {
        if (!this.peerConnection) {
            console.error('Cannot add tracks: peer connection not created');
            return false;
        }
        
        if (!this.localStream) {
            console.warn('Cannot add tracks: local stream not available');
            return false;
        }
        
        const tracks = this.localStream.getTracks();
        if (tracks.length === 0) {
            console.warn('No tracks found in local stream');
            return false;
        }
        
        console.log(`Adding ${tracks.length} tracks to peer connection`);
        tracks.forEach(track => {
            this.peerConnection.addTrack(track, this.localStream);
        });
        
        return true;
    }
    
    // Handle connection state change
    handleConnectionStateChange() {
        if (!this.peerConnection) return;
        
        console.log('Connection state:', this.peerConnection.connectionState);
        
        switch (this.peerConnection.connectionState) {
            case 'connected':
                this.updateStatus('Connected');
                break;
            case 'disconnected':
                this.updateStatus('Connection interrupted');
                this.attemptReconnection();
                break;
            case 'failed':
                this.updateStatus('Connection failed');
                this.handleError(new Error('Connection failed'));
                this.attemptReconnection();
                break;
            case 'closed':
                this.updateStatus('Connection closed');
                break;
        }
    }
    
    // Attempt to reconnect after connection failure
    attemptReconnection() {
        if (this.reconnectionAttempts >= 3) {
            console.log('Maximum reconnection attempts reached');
            return;
        }
        
        this.reconnectionAttempts = (this.reconnectionAttempts || 0) + 1;
        console.log(`Attempting reconnection (${this.reconnectionAttempts}/3)...`);
        
        // Wait a bit before trying to reconnect
        setTimeout(() => {
            if (this.peerConnection && 
                (this.peerConnection.iceConnectionState === 'disconnected' || 
                 this.peerConnection.iceConnectionState === 'failed')) {
                
                // Close the old connection
                this.closePeerConnection();
                
                // Create a new connection
                this.createPeerConnection();
                
                // Reinitiate the call if we're the initiator
                if (this.role === 'counselor' && this.otherParticipant) {
                    this.initiateCall();
                }
            }
        }, 2000);
    }

    // Close WebRTC peer connection
    closePeerConnection() {
        if (this.peerConnection) {
            console.log('Closing peer connection...');
            
            try {
                this.peerConnection.close();
            } catch (error) {
                console.error('Error closing peer connection:', error);
            }
            
            this.peerConnection = null;
            
            // Clear remote stream
            if (this.remoteStream) {
                this.remoteStream = null;
                if (this.onRemoteStreamUpdate) {
                    this.onRemoteStreamUpdate(null);
                }
            }
        }
    }

    // Initiate WebRTC call (counselor only)
    async initiateCall() {
        if (!this.peerConnection) {
            console.error('Cannot initiate call: peer connection not created');
            return;
        }
        
        if (!this.otherParticipant) {
            console.error('Cannot initiate call: no other participant');
            return;
        }
        
        console.log('Initiating call...');
        
        try {
            const offer = await this.peerConnection.createOffer({
                offerToReceiveAudio: true,
                offerToReceiveVideo: true
            });
            
            await this.peerConnection.setLocalDescription(offer);
            console.log('Created and set local description (offer)');
            
            this.socket.emit('offer', {
                target: this.otherParticipant.user_id,
                session_id: this.sessionId,
                offer: offer
            });
        } catch (error) {
            console.error('Error initiating call:', error);
            this.handleError(error);
        }
    }

    // Handle ICE candidate event
    handleIceCandidate(event) {
        if (event.candidate && this.otherParticipant) {
            console.log('ICE candidate generated');
            
            // Check if remote description is set before sending candidates
            if (this.peerConnection.currentRemoteDescription) {
                console.log('Sending ICE candidate');
                this.socket.emit('ice_candidate', {
                    target: this.otherParticipant.user_id,
                    session_id: this.sessionId,
                    candidate: event.candidate
                });
            } else {
                // Store candidates to send later
                if (!this.pendingIceCandidates) {
                    this.pendingIceCandidates = [];
                }
                
                console.log('Remote description not set yet, storing ICE candidate');
                this.pendingIceCandidates.push(event.candidate);
            }
        } else if (!event.candidate) {
            console.log('ICE candidate gathering completed');
        }
    }
    
    // Send any pending ICE candidates
    sendPendingIceCandidates() {
        if (this.pendingIceCandidates && this.pendingIceCandidates.length > 0 && 
            this.peerConnection && this.peerConnection.currentRemoteDescription && 
            this.otherParticipant) {
            
            console.log(`Sending ${this.pendingIceCandidates.length} stored ICE candidates`);
            
            this.pendingIceCandidates.forEach(candidate => {
                this.socket.emit('ice_candidate', {
                    target: this.otherParticipant.user_id,
                    session_id: this.sessionId,
                    candidate: candidate
                });
            });
            
            // Clear pending candidates
            this.pendingIceCandidates = [];
        }
    }

    // Handle track event
    handleTrack(event) {
        console.log(`Received remote ${event.track.kind} track`);
        
        if (!this.remoteStream) {
            this.remoteStream = new MediaStream();
            
            // Notify about remote stream update
            if (this.onRemoteStreamUpdate) {
                this.onRemoteStreamUpdate(this.remoteStream);
            }
        }
        
        // Check if we already have a track of this kind
        const existingTrack = this.remoteStream.getTracks().find(track => track.kind === event.track.kind);
        if (existingTrack) {
            console.log(`Replacing existing ${event.track.kind} track`);
            this.remoteStream.removeTrack(existingTrack);
        }
        
        // Add track to remote stream
        this.remoteStream.addTrack(event.track);
        
        // Set up ended event handler
        event.track.onended = () => {
            console.log(`Remote ${event.track.kind} track ended`);
            
            // Remove the track from the stream
            this.remoteStream.removeTrack(event.track);
            
            // Notify about track ended
            this.updateStatus(`Remote ${event.track.kind === 'audio' ? 'microphone' : 'camera'} disconnected`);
        };
        
        // Set up muted event handler
        event.track.onmute = () => {
            console.log(`Remote ${event.track.kind} track muted`);
            this.updateStatus(`Remote ${event.track.kind === 'audio' ? 'microphone' : 'camera'} muted`);
        };
        
        // Set up unmuted event handler
        event.track.onunmute = () => {
            console.log(`Remote ${event.track.kind} track unmuted`);
            this.updateStatus(`Remote ${event.track.kind === 'audio' ? 'microphone' : 'camera'} unmuted`);
        };
        
        // Update status based on track kind
        if (event.track.kind === 'video') {
            this.updateStatus('Remote video connected');
        } else if (event.track.kind === 'audio') {
            this.updateStatus('Remote audio connected');
        }
    }

    // Handle ICE connection state change
    handleIceConnectionStateChange() {
        console.log('ICE connection state:', this.peerConnection.iceConnectionState);
        
        switch (this.peerConnection.iceConnectionState) {
            case 'connected':
                this.updateStatus('Connected to peer');
                break;
            case 'disconnected':
                this.updateStatus('Disconnected from peer');
                break;
            case 'failed':
                this.updateStatus('Connection failed');
                this.handleError(new Error('ICE connection failed'));
                break;
            case 'closed':
                this.updateStatus('Connection closed');
                break;
        }
    }

    // Toggle audio
    toggleAudio() {
        if (!this.localStream) {
            console.error('Cannot toggle audio: no local stream');
            return false;
        }
        
        const audioTrack = this.localStream.getAudioTracks()[0];
        if (!audioTrack) {
            console.error('Cannot toggle audio: no audio track');
            return false;
        }
        
        this.isAudioEnabled = !this.isAudioEnabled;
        audioTrack.enabled = this.isAudioEnabled;
        console.log('Audio enabled:', this.isAudioEnabled);
        
        // Notify server about audio state change
        this.socket.emit('toggle_audio', {
            session_id: this.sessionId,
            enabled: this.isAudioEnabled
        });
        
        return this.isAudioEnabled;
    }

    // Toggle video with improved error handling and mock video support  
    toggleVideo() {
        if (!this.localStream) {
            console.error('Cannot toggle video: no local stream available');
            this.showNoMediaDialog('camera');
            return false;
        }
        
        const videoTrack = this.localStream.getVideoTracks()[0];
        if (!videoTrack) {
            console.log('No video track available, attempting to add mock video...');
            
            // Try to add a mock video track
            if (this.addMockVideoTrack()) {
                this.isVideoEnabled = true;
                this.hasMockVideo = true;
                
                // Notify server about video state change
                if (this.socket && this.socket.connected) {
                    this.socket.emit('toggle_video', {
                        session_id: this.sessionId,
                        enabled: this.isVideoEnabled
                    });
                }
                
                // Notify UI callback
                if (this.onVideoStateChanged) {
                    this.onVideoStateChanged({
                        user_id: 'local',
                        enabled: this.isVideoEnabled
                    });
                }
                
                this.showMockVideoAddedNotification();
                return true;
            } else {
                this.showNoMediaDialog('camera');
                return false;
            }
        }
        
        // Toggle existing video track
        this.isVideoEnabled = !this.isVideoEnabled;
        videoTrack.enabled = this.isVideoEnabled;
        console.log('Video enabled:', this.isVideoEnabled);
        
        // Update mock video canvas if needed
        if (this.hasMockVideo && this.mockVideoCanvas) {
            this.updateMockVideoCanvas(this.isVideoEnabled);
        }
        
        // Notify server about video state change
        if (this.socket && this.socket.connected) {
            this.socket.emit('toggle_video', {
                session_id: this.sessionId,
                enabled: this.isVideoEnabled
            });
        }
        
        // Notify UI callback if available
        if (this.onVideoStateChanged) {
            this.onVideoStateChanged({
                user_id: 'local',
                enabled: this.isVideoEnabled
            });
        }
        
        return this.isVideoEnabled;
    }

    // Toggle screen sharing
    async toggleScreenSharing() {
        try {
            // If already sharing screen, stop sharing
            if (this.isScreenSharing && this.screenStream) {
                console.log('Stopping screen sharing...');
                
                // Stop all screen share tracks
                this.screenStream.getTracks().forEach(track => {
                    track.stop();
                });
                
                // Remove screen share tracks from peer connection
                if (this.peerConnection) {
                    const senders = this.peerConnection.getSenders();
                    const screenTrack = this.screenStream.getVideoTracks()[0];
                    
                    if (screenTrack) {
                        const sender = senders.find(s => s.track === screenTrack);
                        if (sender) {
                            this.peerConnection.removeTrack(sender);
                        }
                    }
                }
                
                // Add back camera video track
                if (this.localStream && this.peerConnection) {
                    const videoTrack = this.localStream.getVideoTracks()[0];
                    if (videoTrack) {
                        this.peerConnection.addTrack(videoTrack, this.localStream);
                    }
                }
                
                this.screenStream = null;
                this.isScreenSharing = false;
                
                // Update local stream for UI
                if (this.onLocalStreamUpdate) {
                    this.onLocalStreamUpdate(this.localStream);
                }
                
                return false;
            }
            
            // Start screen sharing
            console.log('Starting screen sharing...');
            
            // Get screen share stream
            this.screenStream = await navigator.mediaDevices.getDisplayMedia({
                video: true,
                audio: false
            });
            
            // Replace video track in peer connection
            if (this.peerConnection) {
                const senders = this.peerConnection.getSenders();
                const videoTrack = this.localStream.getVideoTracks()[0];
                const screenTrack = this.screenStream.getVideoTracks()[0];
                
                if (videoTrack && screenTrack) {
                    const sender = senders.find(s => s.track.kind === 'video');
                    if (sender) {
                        sender.replaceTrack(screenTrack);
                    } else {
                        this.peerConnection.addTrack(screenTrack, this.screenStream);
                    }
                }
            }
            
            // Handle screen share ending
            this.screenStream.getVideoTracks()[0].addEventListener('ended', () => {
                this.toggleScreenSharing();
            });
            
            this.isScreenSharing = true;
            
            // Update local stream for UI with screen share
            if (this.onLocalStreamUpdate) {
                this.onLocalStreamUpdate(this.screenStream);
            }
            
            return true;
        } catch (error) {
            console.error('Error toggling screen share:', error);
            this.handleError(error);
            return false;
        }
    }

    // Send chat message
    sendChatMessage(message) {
        if (!this.isConnected) {
            console.error('Cannot send message: not connected to server');
            return false;
        }
        
        if (!message || !message.trim()) {
            return false;
        }
        
        console.log('Sending chat message:', message);
        
        this.socket.emit('chat_message', {
            session_id: this.sessionId,
            message: message
        });
        
        return true;
    }

    // Update status
    updateStatus(status) {
        console.log('Status:', status);
        if (this.onStatusChange) {
            this.onStatusChange(status);
        }
    }

    // Add mock video track to existing stream
    addMockVideoTrack() {
        try {
            const mockVideoTrack = this.createMockVideoTrack();
            if (mockVideoTrack) {
                this.localStream.addTrack(mockVideoTrack);
                this.hasMockVideo = true;
                
                // Update the peer connection if it exists
                if (this.peerConnection) {
                    this.peerConnection.addTrack(mockVideoTrack, this.localStream);
                }
                
                // Notify about stream update
                if (this.onLocalStreamUpdate) {
                    this.onLocalStreamUpdate(this.localStream);
                }
                
                return true;
            }
            return false;
        } catch (error) {
            console.error('Error adding mock video track:', error);
            return false;
        }
    }

    // Create a mock video track (black canvas)
    createMockVideoTrack() {
        try {
            // Create a canvas element
            const canvas = document.createElement('canvas');
            canvas.width = 640;
            canvas.height = 480;
            
            // Store canvas reference for updates
            this.mockVideoCanvas = canvas;
            
            // Get canvas context and fill with black
            const ctx = canvas.getContext('2d');
            this.updateMockVideoCanvas(true); // Initialize with enabled state
            
            // Create a video track from the canvas with animation
            const stream = canvas.captureStream(15); // 15 FPS
            const videoTrack = stream.getVideoTracks()[0];
            
            // Set up periodic updates to keep the stream "alive"
            if (videoTrack) {
                this.mockVideoUpdateInterval = setInterval(() => {
                    if (this.mockVideoCanvas && this.isVideoEnabled) {
                        // Add subtle animation to prevent stream from being considered "static"
                        const time = Date.now() / 1000;
                        const alpha = (Math.sin(time * 2) + 1) / 2 * 0.1 + 0.9; // Subtle opacity change
                        
                        ctx.save();
                        ctx.globalAlpha = alpha;
                        this.updateMockVideoCanvas(this.isVideoEnabled);
                        ctx.restore();
                    }
                }, 1000 / 15); // 15 FPS
                
                // Clean up interval when track ends
                videoTrack.onended = () => {
                    if (this.mockVideoUpdateInterval) {
                        clearInterval(this.mockVideoUpdateInterval);
                        this.mockVideoUpdateInterval = null;
                    }
                };
            }
            
            return videoTrack;
        } catch (error) {
            console.error('Error creating mock video track:', error);
            return null;
        }
    }

    // Update mock video canvas content
    updateMockVideoCanvas(isEnabled) {
        if (!this.mockVideoCanvas) return;
        
        const ctx = this.mockVideoCanvas.getContext('2d');
        
        if (isEnabled) {
            // Show "Camera Not Available" message
            ctx.fillStyle = '#000000';
            ctx.fillRect(0, 0, this.mockVideoCanvas.width, this.mockVideoCanvas.height);
            
            ctx.fillStyle = '#FFFFFF';
            ctx.font = '24px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('Camera Not Available', this.mockVideoCanvas.width / 2, this.mockVideoCanvas.height / 2 - 20);
            ctx.font = '16px Arial';
            ctx.fillText('Audio Only', this.mockVideoCanvas.width / 2, this.mockVideoCanvas.height / 2 + 20);
        } else {
            // Show "Video Disabled" message
            ctx.fillStyle = '#333333';
            ctx.fillRect(0, 0, this.mockVideoCanvas.width, this.mockVideoCanvas.height);
            
            ctx.fillStyle = '#888888';
            ctx.font = '24px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('Video Disabled', this.mockVideoCanvas.width / 2, this.mockVideoCanvas.height / 2 - 10);
            ctx.font = '16px Arial';
            ctx.fillText('Click to enable', this.mockVideoCanvas.width / 2, this.mockVideoCanvas.height / 2 + 20);
        }
    }

    // Show notification when mock video is added
    showMockVideoAddedNotification() {
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 bg-green-50 border border-green-200 rounded-lg p-4 shadow-lg z-40 max-w-sm';
        notification.innerHTML = `
            <div class="flex items-start">
                <div class="flex-shrink-0">
                    <i class="fas fa-video text-green-500"></i>
                </div>
                <div class="ml-3">
                    <h4 class="text-sm font-medium text-green-800">Video Enabled</h4>
                    <p class="mt-1 text-sm text-green-700">Using placeholder video since no camera is available.</p>
                </div>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-auto text-green-500 hover:text-green-700">
                    <i class="fas fa-times text-sm"></i>
                </button>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }

    // Show dialog when media is not available
    showNoMediaDialog(deviceType) {
        const dialog = document.createElement('div');
        dialog.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        
        const deviceName = deviceType === 'camera' ? 'Camera' : 'Microphone';
        const icon = deviceType === 'camera' ? 'fas fa-video-slash' : 'fas fa-microphone-slash';
        
        dialog.innerHTML = `
            <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
                <div class="flex items-center mb-4">
                    <div class="flex-shrink-0 w-10 h-10 bg-red-50 border-red-200 rounded-full flex items-center justify-center mr-3">
                        <i class="${icon} text-red-500"></i>
                    </div>
                    <h3 class="text-lg font-semibold text-gray-900">${deviceName} Not Available</h3>
                </div>
                <p class="text-gray-700 mb-4">
                    Your ${deviceType} is not available. This could be because:
                </p>
                <ul class="list-disc list-inside text-sm text-gray-600 mb-6 space-y-1">
                    <li>Permission was not granted</li>
                    <li>The device is being used by another application</li>
                    <li>The device is not connected</li>
                    <li>Your browser requires HTTPS for media access</li>
                </ul>
                <div class="flex justify-end space-x-3">
                    <button onclick="this.closest('div[class*=\"fixed inset-0\"]').remove()" class="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300">
                        Continue
                    </button>
                    <button onclick="this.closest('div[class*=\"fixed inset-0\"]').remove(); if(window.retryMediaAccess) window.retryMediaAccess();" class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
                        Try Again
                    </button>
                    <button onclick="window.location.reload()" class="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600">
                        Refresh Page
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        
        // Auto-remove after 15 seconds
        setTimeout(() => {
            if (dialog.parentElement) {
                dialog.remove();
            }
        }, 15000);
    }

    // Handle error
    handleError(error) {
        console.error('Error:', error);
        
        // Create user-friendly error message
        let userMessage = 'An error occurred';
        
        // Handle specific WebRTC errors
        if (error.name) {
            switch (error.name) {
                case 'NotAllowedError':
                    userMessage = 'Camera/microphone access denied. Please allow access in your browser settings.';
                    break;
                case 'NotFoundError':
                    userMessage = 'Camera or microphone not found. Please check your device connections.';
                    break;
                case 'NotReadableError':
                    userMessage = 'Camera or microphone is already in use by another application.';
                    break;
                case 'OverconstrainedError':
                    userMessage = 'Camera does not support the requested resolution.';
                    break;
                case 'AbortError':
                    userMessage = 'Media access was aborted.';
                    break;
                case 'SecurityError':
                    userMessage = 'Media access was blocked due to security restrictions.';
                    break;
                case 'TypeError':
                    userMessage = 'Invalid media constraints specified.';
                    break;
            }
        } else if (error.message) {
            // Use the error message if available
            userMessage = error.message;
        }
        
        // Update status with user-friendly message
        this.updateStatus(userMessage);
        
        // Call error callback if available
        if (this.onError) {
            this.onError({
                originalError: error,
                message: userMessage
            });
        }
    }

    // Get status message based on waiting room status
    getStatusMessage(waitingRoomStatus) {
        if (!waitingRoomStatus) {
            return 'Connecting to session...';
        }
        
        if (waitingRoomStatus.student_waiting && waitingRoomStatus.counselor_waiting) {
            return 'Both participants are ready. Starting call...';
        } else if (waitingRoomStatus.student_waiting) {
            return 'Student is waiting for you to join...';
        } else if (waitingRoomStatus.counselor_waiting) {
            return 'Waiting for student to join...';
        } else {
            return 'Waiting for participants...';
        }
    }

    // Handle device change
    async handleDeviceChange() {
        console.log('Media devices changed');
        
        // Check if we have a callback for device changes
        if (this.onDeviceChange) {
            try {
                // Get updated device list
                const devices = await navigator.mediaDevices.enumerateDevices();
                
                // Group devices by kind
                const audioInputs = devices.filter(device => device.kind === 'audioinput');
                const videoInputs = devices.filter(device => device.kind === 'videoinput');
                const audioOutputs = devices.filter(device => device.kind === 'audiooutput');
                
                // Notify about device change
                this.onDeviceChange({
                    audioInputs,
                    videoInputs,
                    audioOutputs,
                    hasAudioInput: audioInputs.length > 0,
                    hasVideoInput: videoInputs.length > 0,
                    hasAudioOutput: audioOutputs.length > 0
                });
                
                // If we're in a call and a device was disconnected, check if it affects our stream
                if (this.localStream) {
                    const audioTrack = this.localStream.getAudioTracks()[0];
                    const videoTrack = this.localStream.getVideoTracks()[0];
                    
                    // Check if we have audio but no audio devices
                    if (audioTrack && audioTrack.readyState === 'live' && audioInputs.length === 0) {
                        this.updateStatus('Audio device disconnected');
                        audioTrack.stop();
                    }
                    
                    // Check if we have video but no video devices
                    if (videoTrack && videoTrack.readyState === 'live' && videoInputs.length === 0) {
                        this.updateStatus('Video device disconnected');
                        videoTrack.stop();
                    }
                    
                    // If we're in an active call and devices changed, we might need to update our stream
                    if (this.peerConnection && this.peerConnection.connectionState === 'connected') {
                        // For now just notify, but could implement device switching here
                        this.updateStatus('Media devices changed during active call');
                    }
                }
            } catch (error) {
                console.error('Error handling device change:', error);
            }
        }
    }
}

// Export the client class
window.VideoCounselingClient = VideoCounselingClient;
