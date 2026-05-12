import os
import uuid
import mimetypes
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image

# NOTE: High-resolution profile image handling additions:
# Added helper save_profile_image() to accept larger images (up to PROFILE_MAX_BYTES),
# normalize orientation, convert to RGB, and emit multiple responsive sizes plus webp variant.
# This keeps backward compatibility: existing code using save_upload unchanged.

# Allowed extensions for uploads (images and common docs)
ALLOWED_EXTENSIONS = {
	'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp',
	'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
	'txt', 'csv'
}

# Maximum file size in bytes (default ~20MB to match server limits)
MAX_FILE_SIZE = 20 * 1024 * 1024

# Profile image specific constraints (stricter than generic uploads)
PROFILE_ALLOWED_EXTS = {'jpg', 'jpeg', 'png', 'webp'}
PROFILE_MAX_BYTES = 5 * 1024 * 1024  # allow up to 5MB high-res source
PROFILE_MAX_DIM = 1600  # cap longest side to prevent extremely huge originals
PROFILE_DERIVATIVE_SIZES = [512, 256, 128]  # square crops


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


def _normalize_image(img: Image.Image) -> Image.Image:
	"""Ensure image is in RGB and auto-orient if exif present."""
	try:
		exif = img.getexif()
		orientation = exif.get(0x0112)
		if orientation == 3:
			img = img.rotate(180, expand=True)
		elif orientation == 6:
			img = img.rotate(270, expand=True)
		elif orientation == 8:
			img = img.rotate(90, expand=True)
	except Exception:
		pass
	if img.mode not in ("RGB", "RGBA"):
		img = img.convert("RGB")
	return img


def save_profile_image(file_storage, user_id: int) -> dict:
	"""Save a high-quality user profile image with responsive derivatives.

	Returns dict with keys:
	  original, size_512, size_256, size_128, webp (paths relative to static/)
	Only sizes successfully generated are included.
	"""
	if not file_storage or not getattr(file_storage, 'filename', None):
		raise ValueError('No file provided')
	filename = secure_filename(file_storage.filename)
	if '.' not in filename:
		raise ValueError('Invalid filename')
	ext = filename.rsplit('.', 1)[1].lower()
	if ext not in PROFILE_ALLOWED_EXTS:
		raise ValueError('Unsupported profile image type')

	# Size check
	pos = file_storage.stream.tell()
	file_storage.stream.seek(0, os.SEEK_END)
	size = file_storage.stream.tell()
	file_storage.stream.seek(pos)
	if size and size > PROFILE_MAX_BYTES:
		raise ValueError('Profile image exceeds 5MB limit')

	# Load image via Pillow
	from io import BytesIO
	file_storage.stream.seek(0)
	img = Image.open(file_storage.stream)
	img = _normalize_image(img)

	# Resize down if over max dimension (maintain aspect)
	w, h = img.size
	longest = max(w, h)
	if longest > PROFILE_MAX_DIM:
		scale = PROFILE_MAX_DIM / float(longest)
		new_size = (int(w * scale), int(h * scale))
		img = img.resize(new_size, Image.LANCZOS)

	# Ensure upload dir
	base_static = os.path.join(os.getcwd(), 'static')
	base_dir = os.path.join(base_static, 'uploads', 'profile_pics')
	os.makedirs(base_dir, exist_ok=True)

	timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
	base_id = f"u{user_id}_{timestamp}_{uuid.uuid4().hex[:6]}"
	original_filename = f"{base_id}.jpg"  # store canonical original as jpg
	original_path = os.path.join(base_dir, original_filename)

	# Save "original" (already possibly downsized) as high-quality JPEG
	save_kwargs = {'quality': 90, 'optimize': True}
	img_rgb = img.convert('RGB') if img.mode != 'RGB' else img
	img_rgb.save(original_path, 'JPEG', **save_kwargs)

	rel = lambda name: os.path.join('uploads', 'profile_pics', name).replace('\\', '/')
	result = {'original': rel(original_filename)}

	# Derivatives (square center-crops)
	def square_crop(im: Image.Image) -> Image.Image:
		w2, h2 = im.size
		d = min(w2, h2)
		left = (w2 - d) // 2
		top = (h2 - d) // 2
		return im.crop((left, top, left + d, top + d))

	base_sq = square_crop(img_rgb)
	for sz in PROFILE_DERIVATIVE_SIZES:
		try:
			deriv = base_sq.resize((sz, sz), Image.LANCZOS)
			fname = f"{base_id}_{sz}.jpg"
			deriv.save(os.path.join(base_dir, fname), 'JPEG', **save_kwargs)
			result[f'size_{sz}'] = rel(fname)
		except Exception:
			# Skip on any failure; continue gracefully
			continue

	# WebP variant (largest useful square 512 or fallback original)
	try:
		source_for_webp = base_sq
		webp_fname = f"{base_id}.webp"
		source_for_webp.save(os.path.join(base_dir, webp_fname), 'WEBP', quality=85, method=6)
		result['webp'] = rel(webp_fname)
	except Exception:
		pass

	return result

