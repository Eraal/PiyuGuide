"""
Enhanced Notification System for Office Module

This module provides smart notification stacking and proper targeting 
for office administrators to reduce redundancy and improve clarity.
"""

from datetime import datetime, timedelta
from sqlalchemy import and_, or_, desc, func
from app.extensions import db
from app.models import Notification, OfficeAdmin, Inquiry, InquiryMessage, Announcement
try:
    from app.websockets.office import (
        push_office_notification_to_office,
        push_office_notification_to_user,
    )
except Exception:
    # WebSocket layer might not be available in some contexts (e.g., migrations)
    push_office_notification_to_office = None
    push_office_notification_to_user = None


class SmartNotificationManager:
    """
    Manages smart notification stacking and targeting for office admins
    """
    
    @staticmethod
    def create_inquiry_notification(inquiry, office_admin_user_id, notification_type='new_inquiry'):
        """
        Create or update a notification for office admins about inquiries
        
        Args:
            inquiry: The inquiry object
            office_admin_user_id: The user ID of the office admin
            notification_type: Type of notification ('new_inquiry', 'new_message', 'status_change')
        """
        # Validate that the user is actually an office admin for this office
        office_admin = OfficeAdmin.query.filter_by(
            user_id=office_admin_user_id,
            office_id=inquiry.office_id
        ).first()
        
        if not office_admin:
            # User is not an office admin for this office, skip notification
            return
            
        # Check if there's already a notification for this inquiry from this student
        existing_notification = Notification.query.filter(
            and_(
                Notification.user_id == office_admin_user_id,
                Notification.inquiry_id == inquiry.id,
                Notification.notification_type.in_(['new_inquiry', 'new_message']),
                Notification.created_at >= datetime.utcnow() - timedelta(hours=24)  # Within last 24 hours
            )
        ).first()
        
        if existing_notification:
            # Update existing notification instead of creating new one (smart stacking)
            SmartNotificationManager._update_stacked_notification(
                existing_notification, inquiry, notification_type
            )
        else:
            # Create new notification
            SmartNotificationManager._create_new_notification(
                inquiry, office_admin_user_id, notification_type
            )
    
    @staticmethod
    def _update_stacked_notification(existing_notification, inquiry, notification_type):
        """
        Update an existing notification to reflect new activity with smart stacking
        """
        # Count unread messages from the student in this inquiry
        unread_messages = InquiryMessage.query.filter(
            and_(
                InquiryMessage.inquiry_id == inquiry.id,
                InquiryMessage.sender_id == inquiry.student.user_id,
                InquiryMessage.read_at.is_(None)
            )
        ).count()
        
        # Update notification content with smart stacking
        student_name = inquiry.student.user.get_full_name()
        
        if notification_type == 'new_message':
            if unread_messages > 1:
                existing_notification.title = f"New Messages from {student_name}"
                existing_notification.message = f"You have {unread_messages} unread messages from {student_name} in inquiry '{inquiry.subject}'"
            else:
                existing_notification.title = f"New Message from {student_name}"
                existing_notification.message = f"New message from {student_name} in inquiry '{inquiry.subject}'"
        elif notification_type == 'new_inquiry':
            existing_notification.title = f"New Inquiry from {student_name}"
            existing_notification.message = f"New inquiry from {student_name}: '{inquiry.subject}'"
        else:
            existing_notification.title = f"Inquiry Update - {student_name}"
            existing_notification.message = f"Inquiry '{inquiry.subject}' from {student_name} has been updated"
        
        # Update timestamp and mark as unread to bring it to top
        existing_notification.created_at = datetime.utcnow()
        existing_notification.is_read = False
        existing_notification.notification_type = notification_type
        
        # Ensure the notification links to the correct inquiry
        existing_notification.link = f"/office/inquiry/{inquiry.id}"
        
        db.session.commit()
    
    @staticmethod
    def _create_new_notification(inquiry, office_admin_user_id, notification_type):
        """
        Create a new notification for office admin
        """
        student_name = inquiry.student.user.get_full_name()
        
        # Determine title and message based on notification type
        if notification_type == 'new_inquiry':
            title = f"New Inquiry from {student_name}"
            message = f"New inquiry from {student_name}: '{inquiry.subject}'"
        elif notification_type == 'new_message':
            title = f"New Message from {student_name}"
            message = f"New message from {student_name} in inquiry '{inquiry.subject}'"
        else:
            title = f"Inquiry Update - {student_name}"
            message = f"Inquiry '{inquiry.subject}' from {student_name} has been updated"
        
        notification = Notification(
            user_id=office_admin_user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            source_office_id=inquiry.office_id,
            inquiry_id=inquiry.id,
            is_read=False,
            created_at=datetime.utcnow(),
            link=f"/office/inquiry/{inquiry.id}"
        )
        
        db.session.add(notification)
        db.session.commit()

        # Broadcast real-time event to the specific user and office room
        # Build enriched payload so UI can render a full row instantly
        try:
            student_user = inquiry.student.user
            # Compute static-relative profile picture path if available
            profile_pic_path = None
            try:
                profile_pic_path = student_user.get_profile_pic_path()
            except Exception:
                profile_pic_path = getattr(student_user, 'profile_pic', None)

            # Collect concerns info
            concerns_list = []
            try:
                for ic in (inquiry.concerns or []):
                    c = getattr(ic, 'concern_type', None)
                    concerns_list.append({
                        'id': getattr(c, 'id', None),
                        'name': getattr(c, 'name', None),
                        'other_specification': getattr(ic, 'other_specification', None)
                    })
            except Exception:
                concerns_list = []

            # Attachments flag
            try:
                has_attachments = bool(inquiry.attachments and len(inquiry.attachments) > 0)
            except Exception:
                has_attachments = False

            created_at_fmt = None
            try:
                created_at_fmt = inquiry.created_at.strftime('%b %d, %Y') if inquiry.created_at else None
            except Exception:
                created_at_fmt = None

            payload = {
                'kind': 'inquiry',
                'type': notification_type,
                'title': title,
                'message': message,
                'inquiry_id': inquiry.id,
                'notification_id': notification.id,
                'office_id': inquiry.office_id,
                'student_name': student_user.get_full_name() if student_user else 'Student',
                'student': {
                    'id': getattr(student_user, 'id', None),
                    'first_name': getattr(student_user, 'first_name', None),
                    'last_name': getattr(student_user, 'last_name', None),
                    'full_name': student_user.get_full_name() if student_user else 'Student',
                    'profile_pic_path': profile_pic_path
                },
                'subject': inquiry.subject,
                'status': getattr(inquiry, 'status', 'pending') or 'pending',
                'created_at': getattr(inquiry, 'created_at', None).isoformat() if getattr(inquiry, 'created_at', None) else None,
                'created_at_fmt': created_at_fmt,
                'concerns': concerns_list,
                'has_attachments': has_attachments,
                'view_url': f"/office/inquiry/{inquiry.id}",
                'timestamp': notification.created_at.isoformat(),
                # Keep legacy field for any existing consumers
                'student_profile_pic': getattr(student_user, 'profile_pic', None)
            }
        except Exception:
            # Fallback to minimal payload
            payload = {
                'kind': 'inquiry',
                'type': notification_type,
                'title': title,
                'message': message,
                'inquiry_id': inquiry.id,
                'notification_id': notification.id,
                'office_id': inquiry.office_id,
                'student_name': inquiry.student.user.get_full_name(),
                'subject': inquiry.subject,
                'timestamp': notification.created_at.isoformat(),
                'student_profile_pic': getattr(inquiry.student.user, 'profile_pic', None)
            }
        try:
            # Important: emit only to the targeted user to avoid duplicate toasts.
            # Office admins join both their user room and the office-wide room.
            # Emitting to both causes each admin to receive two identical events.
            # Other admins will get their own user-targeted event when this
            # method is invoked for them in the caller loop.
            if push_office_notification_to_user:
                push_office_notification_to_user(office_admin_user_id, payload)
            # Do NOT emit to the office room here to prevent duplicate events per admin
            # if push_office_notification_to_office:
            #     push_office_notification_to_office(inquiry.office_id, payload)
        except Exception:
            pass
    
    @staticmethod
    def create_counseling_notification(session, office_admin_user_id, notification_type='new_counseling_request'):
        """
        Create notification for counseling session related activities
        """
        # Validate that the user is actually an office admin for this office
        office_admin = OfficeAdmin.query.filter_by(
            user_id=office_admin_user_id,
            office_id=session.office_id
        ).first()
        
        if not office_admin:
            # User is not an office admin for this office, skip notification
            return
            
        # Check for existing counseling notifications from same student
        existing_notification = Notification.query.filter(
            and_(
                Notification.user_id == office_admin_user_id,
                Notification.notification_type.in_(['new_counseling_request', 'counseling_scheduled']),
                Notification.message.contains(session.student.user.get_full_name()),
                Notification.created_at >= datetime.utcnow() - timedelta(hours=24)
            )
        ).first()
        
        student_name = session.student.user.get_full_name()
        
        if existing_notification:
            # Update existing notification timestamp and mark as unread
            existing_notification.created_at = datetime.utcnow()
            existing_notification.is_read = False
            existing_notification.link = f"/office/counseling-sessions"
            # Ensure title/message are defined for payload
            title = existing_notification.title
            message = existing_notification.message
        else:
            # Create new notification
            if notification_type == 'new_counseling_request':
                title = f"New Counseling Request from {student_name}"
                message = f"New video counseling request from {student_name}"
            elif notification_type == 'counseling_scheduled':
                title = f"Counseling Scheduled with {student_name}"
                message = f"Counseling session scheduled with {student_name}"
            else:
                title = f"Counseling Update - {student_name}"
                message = f"Counseling session updated for {student_name}"
            
            notification = Notification(
                user_id=office_admin_user_id,
                title=title,
                message=message,
                notification_type=notification_type,
                source_office_id=session.office_id,
                is_read=False,
                created_at=datetime.utcnow(),
                link=f"/office/counseling-sessions"
            )
            
            db.session.add(notification)
        
        db.session.commit()

        # Broadcast real-time event to user and office
        try:
            # Determine notification object and id for payload
            notification_obj = existing_notification if existing_notification else notification
            payload = {
                'kind': 'counseling',
                'type': notification_type,
                'title': title,
                'message': message,
                'session_id': getattr(session, 'id', None),
                'notification_id': getattr(notification_obj, 'id', None),
                'office_id': session.office_id,
                'student_name': session.student.user.get_full_name(),
                'scheduled_at': session.scheduled_at.isoformat() if session.scheduled_at else None,
                'timestamp': datetime.utcnow().isoformat(),
                'student_profile_pic': getattr(session.student.user, 'profile_pic', None)
            }
            if push_office_notification_to_user:
                push_office_notification_to_user(office_admin_user_id, payload)
            if push_office_notification_to_office:
                push_office_notification_to_office(session.office_id, payload)
        except Exception:
            pass
    
    @staticmethod
    def create_announcement_notification(announcement, office_admin_user_id):
        """
        Create notification for new announcements - only for designated office admins
        """
        # Only notify if the announcement is NOT from the same office admin
        if announcement.author_id == office_admin_user_id:
            return
            
        # Check if this is a targeted announcement for a specific office
        if announcement.target_office_id:
            # Validate that the user is actually an office admin for the target office
            office_admin = OfficeAdmin.query.filter_by(
                user_id=office_admin_user_id,
                office_id=announcement.target_office_id
            ).first()
            
            if not office_admin:
                # User is not an office admin for the target office, skip notification
                return
        
        # Create announcement notification
        author_name = announcement.author.get_full_name()
        author_role = "Super Admin" if announcement.author.role == 'super_admin' else "Office Admin"
        
        notification = Notification(
            user_id=office_admin_user_id,
            title=f"New Announcement from {author_role}",
            message=f"New announcement posted by {author_name}: {announcement.title[:100]}...",
            notification_type='announcement',
            source_office_id=announcement.target_office_id,
            announcement_id=announcement.id,
            is_read=False,
            created_at=datetime.utcnow(),
            link=f"/office/office-announcement"
        )
        
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def get_office_admin_for_notification(office_id, exclude_user_id=None):
        """
        Get the appropriate office admin user IDs for sending notifications
        
        Args:
            office_id: The office ID
            exclude_user_id: User ID to exclude (e.g., the sender)
        
        Returns:
            List of office admin user IDs for the specific office
        """
        query = OfficeAdmin.query.filter_by(office_id=office_id)
        
        if exclude_user_id:
            query = query.filter(OfficeAdmin.user_id != exclude_user_id)
        
        office_admins = query.all()
        return [admin.user_id for admin in office_admins]
    
    @staticmethod
    def cleanup_old_notifications(days_old=30):
        """
        Clean up old read notifications to prevent database bloat
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        old_notifications = Notification.query.filter(
            and_(
                Notification.is_read == True,
                Notification.created_at < cutoff_date
            )
        ).all()
        
        for notification in old_notifications:
            db.session.delete(notification)
        
        db.session.commit()
        return len(old_notifications)
    
    @staticmethod
    def get_notification_summary(user_id, office_id=None):
        """
        Get a summary of notifications for the user
        
        Returns:
            dict: Summary including counts by type and recent notifications
        """
        query = Notification.query.filter_by(user_id=user_id)
        
        if office_id:
            query = query.filter_by(source_office_id=office_id)
        
        # Get counts by type
        type_counts = db.session.query(
            Notification.notification_type,
            func.count(Notification.id).label('count')
        ).filter_by(user_id=user_id, is_read=False).group_by(
            Notification.notification_type
        ).all()
        
        # Get recent notifications
        recent_notifications = query.filter_by(is_read=False).order_by(
            desc(Notification.created_at)
        ).limit(10).all()
        
        return {
            'total_unread': sum(count for _, count in type_counts),
            'type_counts': {type_name: count for type_name, count in type_counts},
            'recent_notifications': recent_notifications
        }
    
    @staticmethod
    def mark_inquiry_messages_as_read(inquiry_id, office_admin_user_id):
        """
        Mark all messages in an inquiry as read when office admin views the inquiry
        """
        # Mark all messages from the student as read
        messages = InquiryMessage.query.filter(
            and_(
                InquiryMessage.inquiry_id == inquiry_id,
                InquiryMessage.read_at.is_(None)
            )
        ).all()
        
        # Track which messages were updated now to be able to broadcast
        to_emit = []
        now = datetime.utcnow()
        for message in messages:
            if message.sender_id != office_admin_user_id:  # Don't mark own messages as read
                message.read_at = now
                message.status = 'read'
                to_emit.append(message.id)
        
        db.session.commit()

        # Emit websocket events so the sender updates UI in real time
        if to_emit:
            try:
                from app.extensions import socketio
                room = f"inquiry_{inquiry_id}"
                for mid in to_emit:
                    socketio.emit('message_read', {
                        'message_id': mid,
                        'inquiry_id': inquiry_id,
                        'read_at': now.isoformat()
                    }, room=room, namespace='/chat')
            except Exception:
                pass
        # Also notify the office inquiries page to clear unread badge for this inquiry
        try:
            from app.extensions import socketio
            inq = Inquiry.query.get(inquiry_id)
            if inq:
                socketio.emit('office_notification', {
                    'kind': 'inquiry',
                    'type': 'inquiry_read_cleared',
                    'inquiry_id': inquiry_id,
                    'office_id': inq.office_id,
                    'timestamp': now.isoformat()
                }, room=f"office_{inq.office_id}", namespace='/office')
        except Exception:
            pass
    
    @staticmethod
    def get_stacked_notifications_for_office(office_admin_user_id, limit=10):
        """
        Get intelligently stacked notifications for an office admin
        
        Args:
            office_admin_user_id: The office admin user ID
            limit: Maximum number of notifications to return
        
        Returns:
            List of notifications with stacking information
        """
        # Get all unread notifications for this office admin
        notifications = Notification.query.filter_by(
            user_id=office_admin_user_id,
            is_read=False
        ).order_by(desc(Notification.created_at)).limit(limit * 2).all()
        
        # Group similar notifications
        grouped = {}
        for notification in notifications:
            if notification.notification_type in ['new_inquiry', 'new_message']:
                key = f"inquiry_{notification.inquiry_id}"
                if key not in grouped:
                    grouped[key] = {
                        'base_notification': notification,
                        'count': 1,
                        'latest_activity': notification.created_at
                    }
                else:
                    grouped[key]['count'] += 1
                    if notification.created_at > grouped[key]['latest_activity']:
                        grouped[key]['latest_activity'] = notification.created_at
                        grouped[key]['base_notification'] = notification
            else:
                # For non-inquiry notifications, treat individually
                key = f"single_{notification.id}"
                grouped[key] = {
                    'base_notification': notification,
                    'count': 1,
                    'latest_activity': notification.created_at
                }
        
        # Sort by latest activity and return top notifications
        sorted_groups = sorted(
            grouped.values(),
            key=lambda x: x['latest_activity'],
            reverse=True
        )
        
        return sorted_groups[:limit]
