from flask import Flask, request, jsonify
import requests
import os
import statistics

app = Flask(__name__)

FACEPP_API_KEY = os.environ.get("FACEPP_API_KEY")
FACEPP_API_SECRET = os.environ.get("FACEPP_API_SECRET")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

FACEPP_DETECT_URL = "https://api-us.faceplusplus.com/facepp/v3/detect"


def score_face(face):
    # Simple baseline scoring logic (you can replace this)
    beauty = face.get("beauty", {})
    male = beauty.get("male_score")
    female = beauty.get("female_score")

    scores = [s for s in [male, female] if s is not None]
    return statistics.mean(scores) if scores else 0


def tier_from_score(score):
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

