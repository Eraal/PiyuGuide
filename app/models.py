from app.extensions import db
from datetime import datetime, timedelta
from flask_login import UserMixin

class JsonSerializableMixin:
    """Mixin to make models JSON serializable"""
    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

# Table of Different Kind of User Student, office_admin, super_admin
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50))  # optional
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, index=True)  # 'student', 'office_admin', 'super_admin', 'super_super_admin'
    profile_pic = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, index=True)  # Controls login permission
    
    # Campus assignment for super_admin users
    campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id', ondelete='SET NULL'), index=True)
    video_call_notifications = db.Column(db.Boolean, default=True)
    video_call_email_reminders = db.Column(db.Boolean, default=True)
    preferred_video_quality = db.Column(db.String(20), default='auto')  # 'auto', 'low', 'medium', 'high'
    
    # New fields for account violation tracking
    account_locked = db.Column(db.Boolean, default=False, index=True)  # For rule violations
    lock_reason = db.Column(db.String(255))  # Reason for account lock
    locked_at = db.Column(db.DateTime)  # When the account was locked
    locked_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))  # Admin who locked the account
    
    # Track online status separately
    is_online = db.Column(db.Boolean, default=False)
    last_activity = db.Column(db.DateTime)  # Last user activity timestamp
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Email verification fields
    email_verified = db.Column(db.Boolean, default=False, index=True)
    email_verified_at = db.Column(db.DateTime)
    email_verification_sent_at = db.Column(db.DateTime)

    student = db.relationship('Student', uselist=False, back_populates='user')
    office_admin = db.relationship('OfficeAdmin', uselist=False, back_populates='user')
    campus = db.relationship('Campus', back_populates='super_admins')  # For super_admin users only
    notifications = db.relationship('Notification', back_populates='user', lazy=True)
    inquiry_messages = db.relationship('InquiryMessage', back_populates='sender', lazy=True)
    announcements = db.relationship('Announcement', back_populates='author', lazy=True)
    counseling_sessions = db.relationship('CounselingSession', back_populates='counselor', lazy=True)
    
    # Self-referential relationship for the locked_by field
    locked_by = db.relationship('User', remote_side=[id], foreign_keys=[locked_by_id])
    
    # Add account_locks sent by this user (as admin)
    account_locks_issued = db.relationship('AccountLockHistory', 
                                          foreign_keys='AccountLockHistory.locked_by_id',
                                          backref='locked_by_admin', lazy=True)
    
    # Add account_locks received by this user (as violator)
    account_locks_received = db.relationship('AccountLockHistory', 
                                            foreign_keys='AccountLockHistory.user_id',
                                            backref='locked_user', lazy=True)

    def get_full_name(self):
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"
    
    # Property to match what's used in chat_sockets.py
    @property
    def full_name(self):
        return self.get_full_name()

    # --- Profile picture helpers ---
    def get_profile_pic_path(self):
        """Return a normalized static-relative path for the user's profile picture.

        Handles legacy stored values such as:
          - '/static/uploads/profile_pics/filename.jpg'
          - 'uploads/profile_pics/filename.jpg'
          - 'profile_pics/filename.jpg'
          - just 'filename.jpg'
        Always returns something suitable for: url_for('static', filename=returned_path)
        or None if no profile picture.
        """
        if not self.profile_pic:
            return None
        path = self.profile_pic.strip().lstrip('/')
        # Strip leading 'static/' if present
        if path.startswith('static/'):
            path = path[len('static/') :]
        # If already starts with uploads/ assume correct
        if path.startswith('uploads/'):
            return path
        # If contains profile_pics/ but missing uploads/ prefix
        if path.startswith('profile_pics/'):
            return f"uploads/{path}"
        # Bare filename case
        return f"uploads/profile_pics/{path}"

    @property
    def profile_pic_path(self):
        """Property alias to use in templates."""
        return self.get_profile_pic_path()
    
    def can_login(self):
        """Check if user can log in (is active and not locked)"""
        return self.is_active and not self.account_locked
    
    def lock_account(self, admin_user, reason=None):
        """Lock user account for rule violations"""
        self.account_locked = True
        self.lock_reason = reason
        self.locked_at = datetime.utcnow()
        self.locked_by_id = admin_user.id if admin_user else None
        
        # Create lock history record
        lock_history = AccountLockHistory(
            user_id=self.id,
            locked_by_id=admin_user.id if admin_user else None,
            reason=reason,
            lock_type='lock'
        )
        db.session.add(lock_history)
        return lock_history
    
    def unlock_account(self, admin_user, reason=None):
        """Unlock a previously locked account"""
        self.account_locked = False
        
        # Create unlock history record
        unlock_history = AccountLockHistory(
            user_id=self.id,
            locked_by_id=admin_user.id if admin_user else None,
            reason=reason,
            lock_type='unlock'
        )
        db.session.add(unlock_history)
        return unlock_history
    
    def can_access_campus(self, campus_id):
        """Check if super admin user can access the specified campus"""
        if self.role != 'super_admin':
            return True  # Non-super-admin users don't have campus restrictions
        
        if not self.campus_id:
            return False  # Super admin must have a campus assigned
        
        return self.campus_id == campus_id
    
    def get_accessible_campus_id(self):
        """Get the campus ID that this user can access"""
        if self.role == 'super_admin':
            return self.campus_id
        return None

    # Convenience methods for email verification
    def mark_email_verified(self):
        self.email_verified = True
        self.email_verified_at = datetime.utcnow()

# New model to track account lock history
class AccountLockHistory(db.Model):
    __tablename__ = 'account_lock_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    locked_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    reason = db.Column(db.String(255))
    lock_type = db.Column(db.String(50), nullable=False)  # 'lock' or 'unlock'
    
    # Relationships defined via back_populates in User model


class VerificationToken(db.Model):
    """One-time verification tokens for actions like email verification.

    Stores only hashes of tokens/codes. The raw token is sent to the user.
    """
    __tablename__ = 'verification_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    purpose = db.Column(db.String(50), nullable=False, index=True)  # e.g., 'email_verify'
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)  # sha256 hex digest
    code_hash = db.Column(db.String(64))  # sha256 hex digest for 6-digit code
    attempts = db.Column(db.Integer, default=0)
    max_attempts = db.Column(db.Integer, default=5)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User')

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > (self.expires_at or datetime.utcnow())

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

class Campus(db.Model):
    """Model for university campuses"""
    __tablename__ = 'campuses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)  # e.g., "LSPU San Pablo"
    code = db.Column(db.String(10), nullable=False, unique=True, index=True)  # e.g., "SP", "SC"
    address = db.Column(db.Text)  # Campus location
    description = db.Column(db.Text)  # Campus details
    # Campus-specific branding (applies only to Campus UI/templates)
    campus_logo_path = db.Column(db.String(255))  # Path under static/ or absolute URL
    campus_landing_bg_path = db.Column(db.String(255))  # Hero/landing background image
    campus_theme_key = db.Column(db.String(50), default='blue')  # Predefined theme key (e.g., 'blue', 'emerald', 'violet', 'sunset', 'teal')
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    offices = db.relationship('Office', back_populates='campus', lazy=True)
    super_admins = db.relationship('User', back_populates='campus', lazy=True)
    # Departments under this campus
    departments = db.relationship('Department', back_populates='campus', lazy=True, cascade='all, delete-orphan')
    
    def get_active_offices_count(self):
        """Get count of all offices in this campus"""
        from sqlalchemy import func
        return db.session.query(func.count(Office.id)).filter(Office.campus_id == self.id).scalar() or 0
    
    def get_super_admins_count(self):
        """Get count of super admins assigned to this campus"""
        return len([admin for admin in self.super_admins if admin.role == 'super_admin' and admin.is_active])
    
    def __repr__(self):
        return f'<Campus {self.name} ({self.code})>'

class Office(db.Model):
    __tablename__ = 'offices'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text)
    supports_video = db.Column(db.Boolean, default=False)
    campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Relationships
    campus = db.relationship('Campus', back_populates='offices')
    office_admins = db.relationship('OfficeAdmin', back_populates='office', lazy=True)
    inquiries = db.relationship('Inquiry', back_populates='office', lazy=True)
    counseling_sessions = db.relationship('CounselingSession', back_populates='office', lazy=True)
    announcements = db.relationship('Announcement', back_populates='target_office', lazy=True)
    supported_concerns = db.relationship('OfficeConcernType', back_populates='office', lazy=True)


class OfficeAdmin(db.Model):
    __tablename__ = 'office_admins'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    office_id = db.Column(db.Integer, db.ForeignKey('offices.id', ondelete='CASCADE'), nullable=False, index=True)

    user = db.relationship('User', back_populates='office_admin')
    office = db.relationship('Office', back_populates='office_admins')

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    student_number = db.Column(db.String(50), index=True)

    # New: direct campus assignment for students
    campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id', ondelete='SET NULL'), index=True)

    # Legacy free-text department (kept for backward compatibility)
    department = db.Column(db.String(100), index=True)  # e.g., "Computer Science", "Engineering"
    # New structured department reference
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'), index=True)
    section = db.Column(db.String(50), index=True)       # e.g., "A", "B", "CS-1", etc.
    year_level = db.Column(db.String(20), index=True)    # Optional: "1st Year", "2nd Year", etc.

    user = db.relationship('User', back_populates='student')
    campus = db.relationship('Campus')
    # Relationship to structured Department
    department_rel = db.relationship('Department')
    inquiries = db.relationship('Inquiry', back_populates='student', lazy=True)
    counseling_sessions = db.relationship('CounselingSession', back_populates='student', lazy=True)
    # Student feedback on counseling sessions
    feedbacks = db.relationship('Feedback', back_populates='student', lazy=True, cascade='all, delete-orphan')

    # Convenience: unified display name for department
    @property
    def department_name(self):
        return self.department_rel.name if getattr(self, 'department_rel', None) else self.department

# Add the missing InquiryConcern model
class ConcernType(db.Model):
    """Types of concerns that students can select when submitting inquiries"""
    __tablename__ = 'concern_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    allows_other = db.Column(db.Boolean, default=False)  # Whether this concern type allows "Other" specification
    # Auto-reply settings: when a student's first message is for this concern type, staff can auto-reply
    auto_reply_enabled = db.Column(db.Boolean, default=False)
    auto_reply_message = db.Column(db.Text)

    supporting_offices = db.relationship('OfficeConcernType', back_populates='concern_type', lazy=True)
    concerns = db.relationship('InquiryConcern', back_populates='concern_type', lazy=True)

class InquiryConcern(db.Model):
    """Junction table between inquiries and concern types with optional "other" specification"""
    __tablename__ = 'inquiry_concerns'
    id = db.Column(db.Integer, primary_key=True)
    inquiry_id = db.Column(db.Integer, db.ForeignKey('inquiries.id', ondelete='CASCADE'), nullable=False, index=True)
    concern_type_id = db.Column(db.Integer, db.ForeignKey('concern_types.id', ondelete='CASCADE'), nullable=False, index=True)
    other_specification = db.Column(db.String(255))  # Only used when concern_type.allows_other is True
    
    inquiry = db.relationship('Inquiry', back_populates='concerns')
    concern_type = db.relationship('ConcernType', back_populates='concerns')

class OfficeConcernType(db.Model):
    """Junction table defining which concern types each office supports"""
    __tablename__ = 'office_concern_types'
    id = db.Column(db.Integer, primary_key=True)
    office_id = db.Column(db.Integer, db.ForeignKey('offices.id', ondelete='CASCADE'), nullable=False, index=True)
    concern_type_id = db.Column(db.Integer, db.ForeignKey('concern_types.id', ondelete='CASCADE'), nullable=False, index=True)
    # Per-office auto-reply settings for this concern type
    auto_reply_enabled = db.Column(db.Boolean, default=False)
    auto_reply_message = db.Column(db.Text)
    # New: context flags to differentiate usage domains
    # for_inquiries: whether this concern type is selectable for inquiries in this office
    # for_counseling: whether this concern type is selectable for counseling sessions in this office
    for_inquiries = db.Column(db.Boolean, nullable=False, default=True)
    for_counseling = db.Column(db.Boolean, nullable=False, default=False)
    
    # Enforce a single association per (office, concern_type)
    __table_args__ = (
        db.UniqueConstraint('office_id', 'concern_type_id', name='uq_office_concern'),
    )
    
    office = db.relationship('Office', back_populates='supported_concerns')
    concern_type = db.relationship('ConcernType', back_populates='supporting_offices')

# Update to InquiryMessage class to include attachments and tracking fields
class InquiryMessage(db.Model):
    __tablename__ = 'inquiry_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    # Ensure DB-level cascade for future migrations; ORM will handle cascade deletes
    inquiry_id = db.Column(db.Integer, db.ForeignKey('inquiries.id', ondelete='CASCADE'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # New fields for message status tracking
    status = db.Column(db.String(20), default='sending', nullable=False)  # 'sending', 'sent', 'delivered', 'read'
    
    delivered_at = db.Column(db.DateTime, nullable=True)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    sender = db.relationship('User', foreign_keys=[sender_id], back_populates='inquiry_messages')
    # Use explicit relationship with delete-orphan cascade defined on Inquiry.messages
    inquiry = db.relationship('Inquiry', back_populates='messages')
    attachments = db.relationship('MessageAttachment', back_populates='message', lazy='joined', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<InquiryMessage {self.id}>'

# Update to Inquiry class to ensure it only references InquiryMessage
class Inquiry(db.Model):
    __tablename__ = 'inquiries'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False, index=True)
    office_id = db.Column(db.Integer, db.ForeignKey('offices.id', ondelete='CASCADE'), nullable=False, index=True)
    subject = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='pending', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    student = db.relationship('Student', back_populates='inquiries')
    office = db.relationship('Office', back_populates='inquiries')
    # Explicit one-to-many to messages with cascade so children are deleted before parent
    messages = db.relationship(
        'InquiryMessage',
        back_populates='inquiry',
        order_by='InquiryMessage.created_at',
        cascade='all, delete-orphan'
    )
    concerns = db.relationship('InquiryConcern', back_populates='inquiry', lazy=True, cascade='all, delete-orphan')
    attachments = db.relationship('InquiryAttachment', back_populates='inquiry', lazy=True, cascade='all, delete-orphan')
    
    def has_attachments(self):
        """Check if inquiry has any attachments"""
        return len(self.attachments) > 0
    
    def get_concern_types(self):
        """Return all concern types associated with this inquiry"""
        return [ic.concern_type for ic in self.concerns]
        
    def get_other_specifications(self):
        """Return specifications for any 'Other' concerns"""
        return {ic.concern_type_id: ic.other_specification for ic in self.concerns if ic.other_specification}
    
class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # New fields for better notification support
    notification_type = db.Column(db.String(50), default='general', index=True)  # 'inquiry_reply', 'announcement', 'status_change', etc.
    source_office_id = db.Column(db.Integer, db.ForeignKey('offices.id', ondelete='SET NULL'), index=True)  # Office that triggered the notification
    inquiry_id = db.Column(db.Integer, db.ForeignKey('inquiries.id', ondelete='SET NULL'), index=True)  # Related inquiry, if any
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id', ondelete='SET NULL'), index=True)  # Related announcement, if any
    link = db.Column(db.String(255))  # Direct link to related content
    
    # Relationships
    user = db.relationship('User', back_populates='notifications')
    source_office = db.relationship('Office', foreign_keys=[source_office_id])
    inquiry = db.relationship('Inquiry', foreign_keys=[inquiry_id])
    announcement = db.relationship('Announcement', foreign_keys=[announcement_id])
    
    @classmethod
    def create_inquiry_reply_notification(cls, user_id, inquiry, office, message_preview):
        """Create a notification for an inquiry reply"""
        notification = cls(
            user_id=user_id,
            title=f"{office.name} replied",
            message=message_preview,
            notification_type='inquiry_reply',
            source_office_id=office.id,
            inquiry_id=inquiry.id
        )
        db.session.add(notification)
        return notification
    
    @classmethod
    def create_announcement_notification(cls, user_id, announcement, office):
        """Create a notification for a new announcement"""
        notification = cls(
            user_id=user_id,
            title=f"New Announcement from {office.name}",
            message=announcement.title,
            notification_type='announcement',
            source_office_id=office.id,
            announcement_id=announcement.id
        )
        db.session.add(notification)
        return notification
    
    @classmethod
    def create_status_change_notification(cls, user_id, inquiry, new_status):
        """Create a notification for an inquiry status change"""
        office = inquiry.office
        notification = cls(
            user_id=user_id,
            title=f"Inquiry Status Updated",
            message=f"Your inquiry #{inquiry.id} has been marked as {new_status}",
            notification_type='status_change',
            source_office_id=office.id,
            inquiry_id=inquiry.id
        )
        db.session.add(notification)
        return notification

    @classmethod
    def create_campus_update_notification(cls, user_id, campus, old_name, new_name, updated_by_user):
        """Create a notification for campus name update targeting Super Admins.

        Args:
            user_id (int): Recipient user id (a super_super_admin).
            campus (Campus): The campus being updated.
            old_name (str): Previous campus name.
            new_name (str): New campus name.
            updated_by_user (User): Campus admin who made the update.

        Returns:
            Notification: The unsaved notification instance (added to session).
        """
        title = "Campus name updated"
        message = (
            f"{updated_by_user.get_full_name()} changed campus name "
            f"from '{old_name}' to '{new_name}'."
        )
        notification = cls(
            user_id=user_id,
            title=title,
            message=message,
            notification_type='campus_update',
            link=f"/super-admin/campus/{campus.id}"
        )
        db.session.add(notification)
        return notification

class FileAttachment(db.Model):
    """Base model for file attachments"""
    __tablename__ = 'file_attachments'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)  # Storage path
    file_size = db.Column(db.Integer)  # Size in bytes
    file_type = db.Column(db.String(100))  # MIME type
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Polymorphic identity column
    attachment_type = db.Column(db.String(50))
    
    # Relationship to uploader
    uploaded_by = db.relationship('User')
    
    __mapper_args__ = {
        'polymorphic_on': attachment_type,
        'polymorphic_identity': 'file_attachment'
    }

class InquiryAttachment(FileAttachment):
    """Files attached to an inquiry"""
    __tablename__ = 'inquiry_attachments'
    id = db.Column(db.Integer, db.ForeignKey('file_attachments.id', ondelete='CASCADE'), primary_key=True)
    inquiry_id = db.Column(db.Integer, db.ForeignKey('inquiries.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Relationship to inquiry
    inquiry = db.relationship('Inquiry', back_populates='attachments')
    
    __mapper_args__ = {
        'polymorphic_identity': 'inquiry_attachment'
    }

class MessageAttachment(FileAttachment):
    """Files attached to a message"""
    __tablename__ = 'message_attachments'
    id = db.Column(db.Integer, db.ForeignKey('file_attachments.id', ondelete='CASCADE'), primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('inquiry_messages.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Relationship to message
    message = db.relationship('InquiryMessage', back_populates='attachments')
    
    __mapper_args__ = {
        'polymorphic_identity': 'message_attachment'
    }

# Updates to CounselingSession model
class CounselingSession(db.Model):
    __tablename__ = 'counseling_sessions'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False, index=True)
    office_id = db.Column(db.Integer, db.ForeignKey('offices.id', ondelete='CASCADE'), nullable=False, index=True)
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    scheduled_at = db.Column(db.DateTime, nullable=False, index=True)
    duration_minutes = db.Column(db.Integer, default=60)  # Default session duration
    status = db.Column(db.String(50), default='pending', index=True)
    notes = db.Column(db.Text)
    # New fields for nature of concern (selected by student when requesting)
    nature_of_concern_id = db.Column(db.Integer, db.ForeignKey('concern_types.id', ondelete='SET NULL'), index=True)
    nature_of_concern_description = db.Column(db.Text)  # Optional elaboration provided by student
    
    # Video-specific fields
    is_video_session = db.Column(db.Boolean, default=False)
    meeting_id = db.Column(db.String(100), unique=True)  # Unique meeting identifier
    meeting_url = db.Column(db.String(255))  # URL for the meeting room
    meeting_password = db.Column(db.String(50))  # Optional password protection
    
    # Fields to track session activity
    counselor_joined_at = db.Column(db.DateTime)
    student_joined_at = db.Column(db.DateTime)
    session_ended_at = db.Column(db.DateTime)
    
    # Waiting room tracking
    counselor_in_waiting_room = db.Column(db.Boolean, default=False)
    student_in_waiting_room = db.Column(db.Boolean, default=False)
    call_started_at = db.Column(db.DateTime)  # Changed from call_started Boolean to call_started_at DateTime
    
    student = db.relationship('Student', back_populates='counseling_sessions')
    office = db.relationship('Office', back_populates='counseling_sessions')
    counselor = db.relationship('User', back_populates='counseling_sessions')
    recording = db.relationship('SessionRecording', uselist=False, back_populates='session', cascade='all, delete-orphan')
    # One feedback per session from the student
    feedback = db.relationship('Feedback', uselist=False, back_populates='session', cascade='all, delete-orphan')
    # Relationship to concern type (re-uses existing ConcernType model)
    nature_of_concern = db.relationship('ConcernType')

    def generate_meeting_details(self):
        """Generate a unique meeting ID and URL for this session"""
        import uuid
        import random
        import string
        
        if not self.meeting_id:
            # Generate a unique meeting ID
            self.meeting_id = str(uuid.uuid4())
            
            # Create a meeting URL (this would point to your video meeting endpoint)
            self.meeting_url = f"/video-session/{self.meeting_id}"
            
            # Optionally generate a password
            chars = string.ascii_letters + string.digits
            self.meeting_password = ''.join(random.choice(chars) for i in range(8))
            
        return self.meeting_url

    def is_active(self):
        """Check if the session is currently active"""
        now = datetime.utcnow()
        start_time = self.scheduled_at
        end_time = start_time + timedelta(minutes=self.duration_minutes)
        return start_time <= now <= end_time and self.status == 'in_progress'
    
    def get_waiting_room_status(self):
        """
        Get the current waiting room status
        Returns one of: 'empty', 'counselor_waiting', 'student_waiting', 'both_waiting', 'call_in_progress'
        """
        if self.call_started_at:
            return "call_in_progress"
        elif self.counselor_in_waiting_room and self.student_in_waiting_room:
            return "both_waiting"
        elif self.counselor_in_waiting_room:
            return "counselor_waiting"
        elif self.student_in_waiting_room:
            return "student_waiting"
        else:
            return "empty"
    
    # Properties for backward compatibility
    @property
    def started_at(self):
        """Alias for call_started_at for backward compatibility"""
        return self.call_started_at
    
    @started_at.setter
    def started_at(self, value):
        """Setter for started_at that updates call_started_at"""
        self.call_started_at = value
    
    @property
    def ended_at(self):
        """Alias for session_ended_at for backward compatibility"""
        return self.session_ended_at
    
    @ended_at.setter
    def ended_at(self, value):
        """Setter for ended_at that updates session_ended_at"""
        self.session_ended_at = value
    
    @property
    def meeting_link(self):
        """Alias for meeting_url for backward compatibility"""
        return self.meeting_url
    
    @meeting_link.setter
    def meeting_link(self, value):
        """Setter for meeting_link that updates meeting_url"""
        self.meeting_url = value


class Feedback(db.Model):
    """Student feedback for completed counseling sessions."""
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('counseling_sessions.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # relationships
    session = db.relationship('CounselingSession', back_populates='feedback')
    student = db.relationship('Student', back_populates='feedbacks')

    __table_args__ = (
        # Enforce one feedback per session
        db.UniqueConstraint('session_id', name='uq_feedback_session'),
    )

# New model for session recording (optional feature)
class SessionRecording(db.Model):
    __tablename__ = 'session_recordings'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('counseling_sessions.id', ondelete='CASCADE'), nullable=False, unique=True)
    recording_path = db.Column(db.String(255), nullable=False)
    duration_seconds = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # For consent tracking
    student_consent = db.Column(db.Boolean, default=False)
    counselor_consent = db.Column(db.Boolean, default=False)
    
    session = db.relationship('CounselingSession', back_populates='recording')

# New model for session participation tracking
class SessionParticipation(db.Model):
    __tablename__ = 'session_participations'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('counseling_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    joined_at = db.Column(db.DateTime, nullable=False)
    left_at = db.Column(db.DateTime)
    connection_quality = db.Column(db.String(20))  # 'excellent', 'good', 'fair', 'poor'
    device_info = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    
    session = db.relationship('CounselingSession')
    user = db.relationship('User')

# New model for session invitations and reminders
class SessionReminder(db.Model):
    __tablename__ = 'session_reminders'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('counseling_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    reminder_type = db.Column(db.String(20), nullable=False)  # 'email', 'sms', 'in_app'
    scheduled_at = db.Column(db.DateTime, nullable=False)
    sent_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'sent', 'failed'
    
    session = db.relationship('CounselingSession')
    user = db.relationship('User')

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    code = db.Column(db.String(20), index=True)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    campus = db.relationship('Campus', back_populates='departments')

    __table_args__ = (
        db.UniqueConstraint('campus_id', 'name', name='uq_department_campus_name'),
        db.UniqueConstraint('campus_id', 'code', name='uq_department_campus_code'),
    )


class Announcement(db.Model):
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    target_office_id = db.Column(db.Integer, db.ForeignKey('offices.id', ondelete='SET NULL'), index=True)
    is_public = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    author = db.relationship('User', back_populates='announcements')
    target_office = db.relationship('Office', back_populates='announcements')
    images = db.relationship('AnnouncementImage', back_populates='announcement', lazy=True, cascade='all, delete-orphan')

class AnnouncementImage(db.Model):
    __tablename__ = 'announcement_images'
    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id', ondelete='CASCADE'), nullable=False, index=True)
    image_path = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(255))
    display_order = db.Column(db.Integer, default=0)  # For ordering images
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    announcement = db.relationship('Announcement', back_populates='images')

# Audit log to track all actions by users (students, office admins, super admins all does they do in system)
class AuditLog(db.Model, JsonSerializableMixin):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True)
    actor_role = db.Column(db.String(20), index=True)  # 'student', 'office_admin', 'super_admin'
    action = db.Column(db.String(100), nullable=False, index=True)  # 'Submitted', 'Replied', etc.
    target_type = db.Column(db.String(50), index=True)  # 'user', 'office', 'inquiry', 'counseling_session', etc.
    target_id = db.Column(db.Integer, index=True)  # Generic target ID for any target type
    inquiry_id = db.Column(db.Integer, db.ForeignKey('inquiries.id', ondelete='SET NULL'), index=True)
    office_id = db.Column(db.Integer, db.ForeignKey('offices.id', ondelete='SET NULL'), index=True)
    status_snapshot = db.Column(db.String(50))
    is_success = db.Column(db.Boolean, default=True)
    failure_reason = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    retention_days = db.Column(db.Integer, default=365)  # Keep logs for 1 year by default

    actor = db.relationship('User')
    inquiry = db.relationship('Inquiry')
    office = db.relationship('Office')

    @classmethod
    def log_action(cls, actor, action, target_type=None, target_id=None, inquiry=None, office=None, status=None, is_success=True, 
                  failure_reason=None, ip_address=None, user_agent=None, retention_days=365):
        """Helper method to create a new audit log entry"""
        log = cls(
            actor_id=actor.id if actor else None,
            actor_role=actor.role if actor else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            inquiry_id=inquiry.id if inquiry else None,
            office_id=office.id if office else None,
            status_snapshot=status,
            is_success=is_success,
            failure_reason=failure_reason,
            ip_address=ip_address,
            user_agent=user_agent,
            retention_days=retention_days
        )
        db.session.add(log)
        return log


# Student activity log for tracking actions performed by students
class StudentActivityLog(db.Model, JsonSerializableMixin):
    __tablename__ = 'student_activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), index=True)
    action = db.Column(db.String(100), nullable=False, index=True)  # e.g. 'Requested Counseling'
    related_id = db.Column(db.Integer, index=True)
    related_type = db.Column(db.String(50), index=True)  # 'inquiry', 'counseling'
    is_success = db.Column(db.Boolean, default=True)
    failure_reason = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    retention_days = db.Column(db.Integer, default=365)  # Keep logs for 1 year by default

    student = db.relationship('Student')

    @classmethod
    def log_action(cls, student, action, related_id=None, related_type=None, is_success=True, 
                  failure_reason=None, ip_address=None, user_agent=None, retention_days=365):
        """Helper method to create a new student activity log entry"""
        log = cls(
            student_id=student.id,
            action=action,
            related_id=related_id,
            related_type=related_type,
            is_success=is_success,
            failure_reason=failure_reason,
            ip_address=ip_address,
            user_agent=user_agent,
            retention_days=retention_days
        )
        db.session.add(log)
        return log

# Office login logs to track the time when office admins log in
class OfficeLoginLog(db.Model, JsonSerializableMixin):
    __tablename__ = 'office_login_logs'
    id = db.Column(db.Integer, primary_key=True)
    office_admin_id = db.Column(db.Integer, db.ForeignKey('office_admins.id', ondelete='CASCADE'), index=True)
    login_time = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    logout_time = db.Column(db.DateTime)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    session_duration = db.Column(db.Integer)  # Duration in seconds
    is_success = db.Column(db.Boolean, default=True)
    failure_reason = db.Column(db.String(255))
    retention_days = db.Column(db.Integer, default=365)  # Keep logs for 1 year by default

    office_admin = db.relationship('OfficeAdmin')

    @classmethod
    def log_login(cls, office_admin, ip_address=None, user_agent=None, is_success=True,
                failure_reason=None, retention_days=365):
        """Helper method to create a new office login log entry"""
        log = cls(
            office_admin_id=office_admin.id,
            ip_address=ip_address,
            user_agent=user_agent,
            is_success=is_success,
            failure_reason=failure_reason,
            retention_days=retention_days
        )
        db.session.add(log)
        return log

    def update_logout(self, logout_time=None):
        """Update the logout time and calculate session duration"""
        self.logout_time = logout_time or datetime.utcnow()
        if self.login_time:
            # Calculate session duration in seconds
            self.session_duration = (self.logout_time - self.login_time).total_seconds()

# Super admin activity log to track super admin actions
class SuperAdminActivityLog(db.Model, JsonSerializableMixin):
    __tablename__ = 'super_admin_activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    super_admin_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True)
    action = db.Column(db.String(100), nullable=False, index=True)  # e.g. 'Activated Student', 'Reset Password'
    target_type = db.Column(db.String(50), index=True)  # 'user', 'office', 'system', etc.
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True)
    target_office_id = db.Column(db.Integer, db.ForeignKey('offices.id', ondelete='SET NULL'), index=True)
    details = db.Column(db.Text)  # Optional: more details
    is_success = db.Column(db.Boolean, default=True)
    failure_reason = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    retention_days = db.Column(db.Integer, default=730)  # Super admin logs kept longer by default (2 years)

    super_admin = db.relationship('User', foreign_keys=[super_admin_id])
    target_user = db.relationship('User', foreign_keys=[target_user_id])
    target_office = db.relationship('Office')

    @classmethod
    def log_action(cls, super_admin, action, target_type=None, target_user=None, target_office=None, 
                  details=None, is_success=True, failure_reason=None, ip_address=None, 
                  user_agent=None, retention_days=730):
        """Helper method to create a new super admin activity log entry"""
        log = cls(
            super_admin_id=super_admin.id,
            action=action,
            target_type=target_type,
            target_user_id=target_user.id if target_user else None,
            target_office_id=target_office.id if target_office else None,
            details=details,
            is_success=is_success,
            failure_reason=failure_reason,
            ip_address=ip_address,
            user_agent=user_agent,
            retention_days=retention_days
        )
        db.session.add(log)
        return log

# System Settings model to store dynamic configuration
class SystemSettings(db.Model):
    """Model to store system-wide configuration settings"""
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), nullable=False, unique=True, index=True)
    setting_value = db.Column(db.Text, nullable=False)
    setting_type = db.Column(db.String(50), default='string')  # 'string', 'integer', 'boolean', 'json'
    description = db.Column(db.Text)
    is_public = db.Column(db.Boolean, default=True)  # Whether this setting is public or admin-only
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True)
    
    # Relationship
    updated_by = db.relationship('User')
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get a setting value by key"""
        setting = cls.query.filter_by(setting_key=key).first()
        if setting:
            if setting.setting_type == 'boolean':
                return setting.setting_value.lower() in ('true', '1', 'yes')
            elif setting.setting_type == 'integer':
                try:
                    return int(setting.setting_value)
                except ValueError:
                    return default
            elif setting.setting_type == 'json':
                try:
                    import json
                    return json.loads(setting.setting_value)
                except (json.JSONDecodeError, ValueError):
                    return default
            else:
                return setting.setting_value
        return default
    
    @classmethod
    def set_setting(cls, key, value, setting_type='string', description=None, is_public=True, updated_by=None):
        """Set or update a setting value"""
        setting = cls.query.filter_by(setting_key=key).first()
        
        # Convert value to string for storage
        if setting_type == 'json':
            import json
            str_value = json.dumps(value)
        elif setting_type == 'boolean':
            str_value = str(bool(value)).lower()
        else:
            str_value = str(value)
        
        if setting:
            setting.setting_value = str_value
            setting.setting_type = setting_type
            setting.updated_at = datetime.utcnow()
            if updated_by:
                setting.updated_by_id = updated_by.id
            if description:
                setting.description = description
        else:
            setting = cls(
                setting_key=key,
                setting_value=str_value,
                setting_type=setting_type,
                description=description,
                is_public=is_public,
                updated_by_id=updated_by.id if updated_by else None
            )
            db.session.add(setting)
        
        return setting
    
    @classmethod
    def get_current_campus_name(cls):
        """Get the current active campus name for display"""
        return cls.get_setting('current_campus_name', 'KapiyuGuide')
    
    @classmethod
    def set_current_campus_name(cls, campus_name, updated_by=None):
        """Set the current active campus name"""
        return cls.set_setting(
            'current_campus_name', 
            campus_name, 
            'string', 
            'The current active campus name displayed throughout the system',
            True,
            updated_by
        )

    # Branding helpers
    @classmethod
    def get_brand_title(cls, default='PiyuGuide'):
        """Get the system brand/application title"""
        return cls.get_setting('system_brand_title', default)

    @classmethod
    def set_brand_title(cls, title, updated_by=None):
        """Set the system brand/application title"""
        return cls.set_setting(
            'system_brand_title',
            title,
            'string',
            'The system-wide application title/brand displayed across the UI',
            True,
            updated_by
        )

    @classmethod
    def get_brand_logo_path(cls, default='images/schoollogo.png'):
        """Get the static-relative path or absolute URL for the brand logo"""
        return cls.get_setting('system_brand_logo_path', default)

    @classmethod
    def set_brand_logo_path(cls, path, updated_by=None):
        """Set the brand logo path (relative to /static or absolute URL)"""
        return cls.set_setting(
            'system_brand_logo_path',
            path,
            'string',
            'Path (relative to static/) or absolute URL to the brand logo image',
            True,
            updated_by
        )

    @classmethod
    def get_brand_tagline(cls, default='Campus Inquiry Management System'):
        """Get the system brand tagline/subtitle"""
        return cls.get_setting('system_brand_tagline', default)

    @classmethod
    def set_brand_tagline(cls, tagline, updated_by=None):
        """Set the system brand tagline/subtitle"""
        return cls.set_setting(
            'system_brand_tagline',
            tagline,
            'string',
            'Short subtitle shown under the brand title in headers',
            True,
            updated_by
        )

    @classmethod
    def get_favicon_path(cls, default='images/schoollogo.png'):
        """Get favicon path or URL"""
        return cls.get_setting('system_favicon_path', default)

    @classmethod
    def set_favicon_path(cls, path, updated_by=None):
        """Set favicon path or URL"""
        return cls.set_setting(
            'system_favicon_path',
            path,
            'string',
            'Favicon path (relative to static/) or absolute URL',
            True,
            updated_by
        )

# Super Super Admin activity log to track super super admin actions
class SuperSuperAdminActivityLog(db.Model, JsonSerializableMixin):
    __tablename__ = 'super_super_admin_activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    super_super_admin_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True)
    action = db.Column(db.String(100), nullable=False, index=True)  # e.g. 'Created Campus', 'Assigned Super Admin'
    target_type = db.Column(db.String(50), index=True)  # 'campus', 'super_admin', 'system', etc.
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True)
    target_campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id', ondelete='SET NULL'), index=True)
    details = db.Column(db.Text)  # Optional: more details
    is_success = db.Column(db.Boolean, default=True)
    failure_reason = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    retention_days = db.Column(db.Integer, default=1095)  # Super super admin logs kept longest (3 years)

    super_super_admin = db.relationship('User', foreign_keys=[super_super_admin_id])
    target_user = db.relationship('User', foreign_keys=[target_user_id])
    target_campus = db.relationship('Campus')

    @classmethod
    def log_action(cls, super_super_admin, action, target_type=None, target_user=None, target_campus=None, 
                  details=None, is_success=True, failure_reason=None, ip_address=None, 
                  user_agent=None, retention_days=1095):
        """Helper method to create a new super super admin activity log entry"""
        log = cls(
            super_super_admin_id=super_super_admin.id,
            action=action,
            target_type=target_type,
            target_user_id=target_user.id if target_user else None,
            target_campus_id=target_campus.id if target_campus else None,
            details=details,
            is_success=is_success,
            failure_reason=failure_reason,
            ip_address=ip_address,
            user_agent=user_agent,
            retention_days=retention_days
        )
        db.session.add(log)
        return log