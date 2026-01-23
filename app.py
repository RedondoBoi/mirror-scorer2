import os
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

FACEPP_API_KEY = os.getenv("FACEPP_API_KEY", "")
FACEPP_API_SECRET = os.getenv("FACEPP_API_SECRET", "")
FACEPP_DETECT_URL = os.getenv("FACEPP_DETECT_URL", "https://api-us.faceplusplus.com/facepp/v3/detect")

# Tweakable
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
MAX_PHOTOS = 3

def _fail(msg, status=400, **extra):
  payload = {"error": msg}
  payload.update(extra)
  return jsonify(payload), status

def _facepp_detect_image_url(url: str):
  data = {
    "api_key": FACEPP_API_KEY,
    "api_secret": FACEPP_API_SECRET,
    "image_url": url,
    "return_attributes": "beauty,facequality",
  }
  r = requests.post(FACEPP_DETECT_URL, data=data, timeout=HTTP_TIMEOUT)
  return r.status_code, r.text, _safe_json(r)

def _facepp_detect_image_bytes(file_bytes: bytes, filename="photo.jpg"):
  data = {
    "api_key": FACEPP_API_KEY,
    "api_secret": FACEPP_API_SECRET,
    "return_attributes": "beauty,facequality",
  }
  files = {
    "image_file": (filename, file_bytes, "image/jpeg"),
  }
  r = requests.post(FACEPP_DETECT_URL, data=data, files=files, timeout=HTTP_TIMEOUT)
  return r.status_code, r.text, _safe_json(r)

def _safe_json(resp):
  try:
    return resp.json()
  except Exception:
    return None

def _extract_beauty_score(facepp_json):
  """
  Face++ returns beauty as:
  face["attributes"]["beauty"]["male_score"], ["female_score"]
  We'll average them (works regardless of gender).
  """
  faces = (facepp_json or {}).get("faces") or []
  if not faces:
    return None, {"error": "no_face_detected"}

  face = faces[0]
  attrs = (face.get("attributes") or {})
  beauty = (attrs.get("beauty") or {})
  m = beauty.get("male_score")
  f = beauty.get("female_score")

  if m is None and f is None:
    return None, {"error": "no_beauty_score"}

  vals = [v for v in [m, f] if isinstance(v, (int, float))]
  if not vals:
    return None, {"error": "no_beauty_score"}

  score = sum(vals) / len(vals)
  return float(score), {"faces": len(faces), "beauty": beauty}

def _best_2_of_3(scores):
  # MVP rule: best 2/3 averaged
  scores_sorted = sorted(scores, reverse=True)
  if len(scores_sorted) >= 2:
    return (scores_sorted[0] + scores_sorted[1]) / 2.0
  return scores_sorted[0]

@app.get("/")
def health():
  return jsonify({"ok": True, "service": "mirror-scorer2"}), 200

@app.post("/score")
def score_from_urls():
  if not FACEPP_API_KEY or not FACEPP_API_SECRET:
    return _fail("Missing FACEPP_API_KEY / FACEPP_API_SECRET", 500)

  payload = request.get_json(silent=True) or {}
  photo_urls = payload.get("photo_urls")

  if not isinstance(photo_urls, list) or not (1 <= len(photo_urls) <= MAX_PHOTOS):
    return _fail("photo_urls must be a list with 1–3 signed URLs")

  breakdown = []
  good_scores = []

  for url in photo_urls:
    if not isinstance(url, str) or not url.startswith("http"):
      breakdown.append({"error": "invalid_url", "url": url})
      continue

    status, text, js = _facepp_detect_image_url(url)
    if status != 200 or not js:
      breakdown.append({"error": "facepp_non_200", "url": url, "status": status, "body": text[:300]})
      continue

    score, meta = _extract_beauty_score(js)
    if score is None:
      breakdown.append({"error": meta.get("error", "no_face_detected"), "url": url})
      continue

    good_scores.append(score)
    breakdown.append({"ok": True, "url": url, "score_0_100": score})

  if not good_scores:
    return jsonify({
      "error": "no_face_detected",
      "message": "No faces detected",
      "breakdown": breakdown,
    }), 400

  final = _best_2_of_3(good_scores)
  return jsonify({
    "score_0_100": final,
    "used": len(good_scores),
    "breakdown": breakdown,
  }), 200

@app.post("/score_upload")
def score_from_upload():
  if not FACEPP_API_KEY or not FACEPP_API_SECRET:
    return _fail("Missing FACEPP_API_KEY / FACEPP_API_SECRET", 500)

  # Expect multiple files under key "photos"
  files = request.files.getlist("photos")
  if not files or not (1 <= len(files) <= MAX_PHOTOS):
    return _fail("photos must be 1–3 uploaded files (multipart/form-data)")

  breakdown = []
  good_scores = []

  for f in files:
    try:
      b = f.read()
    except Exception as e:
      breakdown.append({"error": "read_failed", "detail": str(e)})
      continue

    if not b or len(b) < 100:
      breakdown.append({"error": "empty_file"})
      continue

    status, text, js = _facepp_detect_image_bytes(b, filename=f.filename or "photo.jpg")
    if status != 200 or not js:
      breakdown.append({"error": "facepp_non_200", "status": status, "body": text[:300]})
      continue

    score, meta = _extract_beauty_score(js)
    if score is None:
      breakdown.append({"error": meta.get("error", "no_face_detected")})
      continue

    good_scores.append(score)
    breakdown.append({"ok": True, "filename": f.filename, "score_0_100": score})

  if not good_scores:
    return jsonify({
      "error": "no_face_detected",
      "message": "No faces detected",
      "breakdown": breakdown,
    }), 400

  final = _best_2_of_3(good_scores)
  return jsonify({
    "score_0_100": final,
    "used": len(good_scores),
    "breakdown": breakdown,
  }), 200

if __name__ == "__main__":
  # local dev
  app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
