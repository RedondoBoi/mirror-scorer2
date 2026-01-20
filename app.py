from flask import Flask, request, jsonify
import os
import statistics
import requests

app = Flask(__name__)

FACEPP_API_KEY = os.environ.get("FACEPP_API_KEY", "")
FACEPP_API_SECRET = os.environ.get("FACEPP_API_SECRET", "")

FACEPP_DETECT_URL = "https://api-us.faceplusplus.com/facepp/v3/detect"


@app.get("/health")
def health():
    return jsonify({"ok": True})


def score_face(attributes):
    beauty = attributes.get("beauty", {}) if isinstance(attributes, dict) else {}
    male = beauty.get("male_score")
    female = beauty.get("female_score")
    scores = [s for s in [male, female] if isinstance(s, (int, float))]
    return float(statistics.mean(scores)) if scores else 0.0


def tier_from_score(score):
    # You can swap this to your 1–6 tier system later.
    if score >= 85:
        return "Emerald"
    if score >= 75:
        return "Diamond"
    if score >= 65:
        return "Gold"
    if score >= 55:
        return "Silver"
    return "Bronze"


@app.route("/score", methods=["POST"])
def score_user():
    if not FACEPP_API_KEY or not FACEPP_API_SECRET:
        return jsonify({"error": "Missing FACEPP_API_KEY / FACEPP_API_SECRET"}), 500

    payload = request.get_json(silent=True) or {}
    photo_urls = payload.get("photo_urls", [])

    if not isinstance(photo_urls, list) or len(photo_urls) < 1:
        return jsonify({"error": "photo_urls must be a list with 1–3 signed URLs"}), 400

    photo_urls = photo_urls[:3]

    scores = []
    breakdown = []

    for url in photo_urls:
        try:
            r = requests.post(
                FACEPP_DETECT_URL,
                data={
                    "api_key": FACEPP_API_KEY,
                    "api_secret": FACEPP_API_SECRET,
                    "return_attributes": "beauty",
                    "image_url": url,
                },
                timeout=30,
            )
            data = r.json()
        except Exception as e:
            breakdown.append({"url": url, "error": f"facepp_request_failed: {str(e)}"})
            continue

        faces = data.get("faces", [])
        if not faces:
            breakdown.append({"url": url, "error": "no_face_detected"})
            continue

        attrs = faces[0].get("attributes", {})
        face_score = score_face(attrs)
        scores.append(face_score)
        breakdown.append({"url": url, "score": face_score})

    if not scores:
        return jsonify({"error": "No faces detected", "breakdown": breakdown}), 400

    final_score = round(float(statistics.mean(scores)), 1)
    tier = tier_from_score(final_score)

    return jsonify({
        "score": final_score,
        "tier": tier,
        "breakdown": breakdown,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

@app.route("/score", methods=["POST"])
def score_user():
    payload = request.json
    photo_paths = payload.get("photo_paths", [])

    if not photo_paths:
        return jsonify({"error": "No photos"}), 400

    scores = []
    breakdown = []

    for path in photo_paths:
        signed_url = f"{SUPABASE_URL}/storage/v1/object/sign/profile-photos/{path}"

        signed = requests.post(
            signed_url,
            headers={
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            json={"expiresIn": 60},
        )

        image_url = signed.json()["signedURL"]

        r = requests.post(
            FACEPP_DETECT_URL,
            data={
                "api_key": FACEPP_API_KEY,
                "api_secret": FACEPP_API_SECRET,
                "return_attributes": "beauty",
                "image_url": image_url,
            },
        )

        data = r.json()

        faces = data.get("faces", [])
        if not faces:
            continue

        face_score = score_face(faces[0]["attributes"])
        scores.append(face_score)
        breakdown.append(face_score)

    if not scores:
        return jsonify({"error": "No faces detected"}), 400

    final_score = round(statistics.mean(scores), 1)
    tier = tier_from_score(final_score)

    return jsonify({
        "score": final_score,
        "tier": tier,
        "breakdown": breakdown,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

