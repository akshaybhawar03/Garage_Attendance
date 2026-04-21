"""
ArcFace face-embedding extraction  +  MediaPipe liveness detection.
"""

import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"

import base64
import cv2
import numpy as np
import mediapipe as mp
from deepface import DeepFace

# ──── MediaPipe landmarks for Eye Aspect Ratio ───────────────────
# Right eye (6 ordered points around the eye)
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
# Left eye
LEFT_EYE = [362, 385, 387, 263, 373, 380]

EAR_THRESHOLD = 0.15

mp_face_mesh = mp.solutions.face_mesh


# ──── Helpers ─────────────────────────────────────────────────────
def decode_base64_image(b64_string: str) -> np.ndarray:
    """Decode a base64 (optionally data-URI prefixed) string → BGR ndarray."""
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]
    raw = base64.b64decode(b64_string)
    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode base64 image")
    return img


def _ear(landmarks, indices, w, h) -> float:
    """Eye Aspect Ratio for one eye."""
    pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in indices]
    v1 = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
    v2 = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
    horiz = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
    if horiz == 0:
        return 0.0
    return (v1 + v2) / (2.0 * horiz)


# ──── Public API ──────────────────────────────────────────────────
def check_liveness(image: np.ndarray) -> bool:
    """
    Return True when MediaPipe detects 468+ landmarks AND both eyes
    have an Eye Aspect Ratio above the threshold (eyes open → live).
    """
    h, w = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.7, # Increased from 0.5
    ) as mesh:
        result = mesh.process(rgb)
        if not result.multi_face_landmarks:
            print("DEBUG: Liveness failed - No face landmarks found.")
            return False

        lm = result.multi_face_landmarks[0].landmark
        print(f"DEBUG: Landmarks found: {len(lm)}")
        if len(lm) < 468:
            return False

        left_ear = _ear(lm, LEFT_EYE, w, h)
        right_ear = _ear(lm, RIGHT_EYE, w, h)
        avg = (left_ear + right_ear) / 2.0
        print(f"DEBUG: Liveness EAR - Left: {left_ear:.3f}, Right: {right_ear:.3f}, Avg: {avg:.3f} (Threshold: {EAR_THRESHOLD})")
        return avg > EAR_THRESHOLD


def get_embedding(image: np.ndarray) -> list[float]:
    """Extract a 512-dim ArcFace embedding from a BGR image."""
    import gc
    gc.collect()
    results = DeepFace.represent(
        img_path=image,
        model_name="ArcFace",
        enforce_detection=True,
        detector_backend="mediapipe",
    )
    if not results:
        raise ValueError("No face detected in image")
    return results[0]["embedding"]


def compute_registration_vectors(
    photos: list[str],
) -> dict[str, list[float]]:
    """
    Accept 3 base64 photos (1 front · 1 left · 1 right).
    Return 3 × 512-dim vectors.
    Memory-optimized for low-RAM servers.
    """
    import gc

    # Support both 3 and 15 photos for backward compatibility
    if len(photos) == 15:
        # Pick first photo from each group of 5
        selected = [photos[0], photos[5], photos[10]]
    elif len(photos) == 3:
        selected = photos
    else:
        raise ValueError(f"Expected 3 or 15 photos, got {len(photos)}")

    angles = ["front", "left", "right"]
    vectors: dict[str, list[float]] = {}
    for i, angle in enumerate(angles):
        print(f"DEBUG: Processing {angle} photo...")
        img = decode_base64_image(selected[i])
        
        # Resize to a smaller size to save memory (ArcFace uses 112x112 anyway)
        # 400x400 is plenty for face detection
        img = cv2.resize(img, (400, 400))
        
        gc.collect() # Clear memory before heavy DeepFace call
        emb = get_embedding(img)
        del img
        gc.collect()
        vectors[angle] = emb
        print(f"DEBUG: {angle} done.")
    return vectors


