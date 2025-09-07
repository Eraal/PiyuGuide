import os
import uuid
import mimetypes
from datetime import datetime
from werkzeug.utils import secure_filename

# Allowed extensions for uploads (images and common docs)
ALLOWED_EXTENSIONS = {
	'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp',
	'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
	'txt', 'csv'
}

# Maximum file size in bytes (default ~20MB to match server limits)
MAX_FILE_SIZE = 20 * 1024 * 1024


def allowed_file(filename: str) -> bool:
	if not filename or '.' not in filename:
		return False
	ext = filename.rsplit('.', 1)[1].lower()
	return ext in ALLOWED_EXTENSIONS


def _ensure_upload_dir(subfolder: str) -> str:
	"""Ensure the target upload folder exists under static/uploads/<subfolder> and return abs path."""
	base_static = os.path.join(os.getcwd(), 'static')
	uploads_dir = os.path.join(base_static, 'uploads', subfolder)
	os.makedirs(uploads_dir, exist_ok=True)
	return uploads_dir


def save_upload(file_storage, subfolder: str = 'messages') -> tuple[str, dict]:
	"""Save an uploaded Werkzeug FileStorage to static/uploads.

	Returns (static_relative_path, meta) where static_relative_path is like
	'uploads/messages/<uuid>_<filename>' suitable for url_for('static', filename=...).

	meta contains: filename, file_size, file_type.
	"""
	if not file_storage or not getattr(file_storage, 'filename', None):
		raise ValueError('No file provided')

	filename = secure_filename(file_storage.filename)
	if not allowed_file(filename):
		raise ValueError('File type not allowed')

	# Determine size safely (read pointer preserving)
	pos = file_storage.stream.tell()
	file_storage.stream.seek(0, os.SEEK_END)
	size = file_storage.stream.tell()
	file_storage.stream.seek(pos)
	if size and size > MAX_FILE_SIZE:
		raise ValueError('File too large')

	ext = filename.rsplit('.', 1)[1].lower()
	unique = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
	unique_filename = f"{unique}_{filename}"

	target_dir = _ensure_upload_dir(subfolder)
	abs_path = os.path.join(target_dir, unique_filename)
	file_storage.save(abs_path)

	# Guess MIME
	mime, _ = mimetypes.guess_type(filename)

	static_relative = os.path.join('uploads', subfolder, unique_filename).replace('\\', '/')
	meta = {
		'filename': filename,
		'file_size': int(size) if size is not None else None,
		'file_type': mime or getattr(file_storage, 'content_type', None)
	}
	return static_relative, meta

