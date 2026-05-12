# Video Counseling Implementation Documentation

## Overview

This document describes the comprehensive Video Counseling feature implementation for PiyuGuide. The system uses WebRTC for peer-to-peer video streaming and WebSocket for signaling, providing secure, real-time video communication between students and counselors.

## Architecture

### Frontend Components

1. **Student Module** (`static/js/student/websockets/counseling.js`)
   - VideoCounselingClient class
   - Handles student-side video calling logic
   - Manages media permissions and UI updates

2. **Office Module** (`static/js/office/websockets/counseling.js`)
   - VideoCounselingClientOffice class
   - Handles counselor-side video calling logic
   - Includes additional features like recording, notes, and screen sharing

### Backend Components

1. **WebSocket Handler** (`app/websockets/counseling.py`)
   - Manages real-time signaling between participants
   - Handles WebRTC offer/answer/ICE candidate exchange
   - Tracks session participation and status

2. **Routes** (`app/office/routes/office_counseling.py`)
   - Session management endpoints
   - Notes saving functionality
   - Session status updates

3. **Database Models** (`app/models.py`)
   - CounselingSession model with video-specific fields
   - SessionParticipation tracking
   - SessionRecording for optional recording feature

## Key Features

### Core Video Calling
- ✅ WebRTC peer-to-peer video streaming
- ✅ Audio/video mute/unmute controls
- ✅ Waiting room with device testing
- ✅ Real-time connection status indicators
- ✅ Automatic session timer
- ✅ Cross-browser compatibility (Chrome, Firefox, Edge, Safari)

### Advanced Features
- ✅ Screen sharing (counselor side)
- ✅ Session recording (counselor side)
- ✅ Real-time note taking
- ✅ Video quality controls
- ✅ Connection diagnostics
- ✅ Graceful error handling
- ✅ Automatic reconnection

### Security & Privacy
- ✅ Permission-based access control
- ✅ Session-specific rooms
- ✅ Secure WebSocket connections
- ✅ Media permission handling
- ✅ Privacy-focused UI design

## Usage Flow

### For Students

1. **Join Session**
   - Navigate to session from dashboard
   - Grant camera/microphone permissions
   - Test devices in waiting room
   - Wait for counselor to join

2. **During Call**
   - View counselor's video stream
   - Control own audio/video
   - Monitor connection status
   - View session information

3. **End Session**
   - Leave session gracefully
   - Redirected to session summary

### For Counselors

1. **Start Session**
   - Access session from office dashboard
   - Grant camera/microphone permissions
   - Set up devices in waiting room
   - Initiate call when student joins

2. **During Call**
   - View student's video stream
   - Control all media devices
   - Take real-time notes
   - Share screen if needed
   - Record session (optional)

3. **End Session**
   - Save session notes
   - End session properly
   - Generate session summary

## Technical Implementation

### WebRTC Configuration

```javascript
// ICE servers for NAT traversal
const iceServers = [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' }
];

// Media constraints
const constraints = {
    video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { ideal: 30 }
    },
    audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
    }
};
```

### WebSocket Events

| Event | Direction | Purpose |
|-------|-----------|---------|
| `connect` | Both | Initial connection |
| `join_session` | Both | Join specific session |
| `offer` | Counselor → Student | WebRTC offer |
| `answer` | Student → Counselor | WebRTC answer |
| `ice_candidate` | Both | ICE candidate exchange |
| `toggle_audio` | Both | Audio state change |
| `toggle_video` | Both | Video state change |
| `end_session` | Counselor | End session |

### Database Schema Updates

```sql
-- Added fields to counseling_sessions table
ALTER TABLE counseling_sessions ADD COLUMN is_video_session BOOLEAN DEFAULT FALSE;
ALTER TABLE counseling_sessions ADD COLUMN meeting_id VARCHAR(100) UNIQUE;
ALTER TABLE counseling_sessions ADD COLUMN meeting_url VARCHAR(255);
ALTER TABLE counseling_sessions ADD COLUMN counselor_in_waiting_room BOOLEAN DEFAULT FALSE;
ALTER TABLE counseling_sessions ADD COLUMN student_in_waiting_room BOOLEAN DEFAULT FALSE;
ALTER TABLE counseling_sessions ADD COLUMN call_started_at DATETIME;
```

## Browser Compatibility

### Supported Browsers
- ✅ Chrome 80+
- ✅ Firefox 75+
- ✅ Safari 14+
- ✅ Edge 80+

### Required Features
- WebRTC support
- getUserMedia API
- WebSocket support
- Modern JavaScript (ES6+)

## Error Handling

### Media Access Errors
- `NotAllowedError`: Permission denied
- `NotFoundError`: No devices available
- `NotSupportedError`: Browser not supported

### Connection Errors
- Network connectivity issues
- WebSocket disconnection
- WebRTC connection failures

### Graceful Fallbacks
- Audio-only mode if video fails
- Automatic reconnection attempts
- User-friendly error messages

## Security Considerations

### Access Control
- Session-specific authentication
- Role-based permissions
- Office-based access restriction

### Data Privacy
- No video data stored on server
- Optional recording with consent
- Secure WebSocket connections (WSS in production)

### Network Security
- STUN servers for NAT traversal
- No TURN servers (peer-to-peer only)
- Encrypted media streams

## Performance Optimization

### Video Quality
- Adaptive bitrate based on connection
- Multiple quality presets
- Bandwidth monitoring

### Network Usage
- Efficient signaling protocol
- Minimal server resources
- P2P reduces server load

## Deployment Notes

### Production Setup
1. Use HTTPS for WebRTC (required)
2. Configure WSS for WebSocket
3. Set up proper STUN/TURN servers
4. Enable gzip compression
5. Configure proper CORS headers

### Environment Variables
```env
SOCKETIO_ASYNC_MODE=eventlet
SOCKETIO_CORS_ALLOWED_ORIGINS=*
WEBRTC_STUN_SERVERS=stun:stun.l.google.com:19302
```

### Server Requirements
- Python 3.8+
- Flask-SocketIO with eventlet
- Modern web server (nginx/apache)
- SSL certificate (for WebRTC)

## Testing

### Manual Testing Checklist
- [ ] Camera/microphone permissions
- [ ] Video/audio quality
- [ ] Network disconnection recovery
- [ ] Cross-browser compatibility
- [ ] Mobile device support
- [ ] Session recording
- [ ] Note saving functionality

### Automated Testing
- WebSocket connection tests
- Media device simulation
- Error scenario testing
- Performance benchmarks

## Troubleshooting

### Common Issues

1. **Camera/Microphone Not Working**
   - Check browser permissions
   - Ensure HTTPS connection
   - Verify device availability

2. **Connection Failed**
   - Check network connectivity
   - Verify WebSocket connection
   - Test with different browser

3. **Poor Video Quality**
   - Check bandwidth
   - Lower video quality setting
   - Switch to audio-only mode

4. **Session Not Starting**
   - Verify session permissions
   - Check database session status
   - Ensure both participants joined

### Debug Information
- Browser console logs
- WebSocket connection status
- WebRTC statistics
- Network quality metrics

## Future Enhancements

### Planned Features
- [ ] Group video sessions
- [ ] Chat during video calls
- [ ] File sharing
- [ ] Virtual backgrounds
- [ ] Session analytics
- [ ] Mobile app support

### Technical Improvements
- [ ] Better error recovery
- [ ] Improved video quality
- [ ] Reduced latency
- [ ] Enhanced security
- [ ] Performance monitoring

## Support

For technical issues or questions about the video counseling implementation:

1. Check browser console for errors
2. Verify network connectivity
3. Test with different browsers
4. Review server logs
5. Contact system administrator

---

This implementation provides a robust, secure, and user-friendly video counseling solution that integrates seamlessly with the existing PiyuGuide platform while maintaining high standards for privacy, security, and performance.
