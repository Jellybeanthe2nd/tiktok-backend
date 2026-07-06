import os
import requests
import subprocess
from flask import Flask, request, jsonify
import cloudinary
import cloudinary.uploader
import imageio_ffmpeg
import wave
import contextlib

app = Flask(__name__)

# ----------------------------
# FFMPEG (Render-safe)
# ----------------------------
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

os.environ["FFMPEG_BINARY"] = FFMPEG

# ----------------------------
# CLOUDINARY (PUT KEYS)
# ----------------------------
cloudinary.config(
    cloud_name="YOUR_CLOUD_NAME",
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET"
)

# ----------------------------
# TEMP FOLDER
# ----------------------------
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)


# ----------------------------
# HELPERS
# ----------------------------
def run(cmd):
    subprocess.run(cmd, check=True)


def download_file(url, filename):
    r = requests.get(url, stream=True, timeout=30)
    r.raise_for_status()

    path = os.path.join(TEMP_DIR, filename)

    with open(path, "wb") as f:
        for chunk in r.iter_content(1024):
            if chunk:
                f.write(chunk)

    return path


# ----------------------------
# SAFE DURATION (NO FFMPEG PROBE)
# ----------------------------
def get_duration(file_path):
    if file_path.endswith(".wav"):
        with contextlib.closing(wave.open(file_path, 'r')) as f:
            frames = f.getnframes()
            rate = f.getframerate()
            return frames / float(rate)

    # fallback for mp3 or unknown formats
    return 3.0


# ----------------------------
# MAIN API
# ----------------------------
@app.route("/generate-video", methods=["POST"])
def generate_video():

    data = request.json
    video_urls = data.get("video_urls", [])
    audio_urls = data.get("audio_urls", [])

    if not video_urls or not audio_urls:
        return jsonify({
            "status": "error",
            "message": "Missing video_urls or audio_urls"
        }), 400

    scene_files = []

    try:
        for i in range(len(video_urls)):

            # DOWNLOAD
            vid = download_file(video_urls[i], f"vid_{i}.mp4")
            aud = download_file(audio_urls[i], f"aud_{i}.wav")

            # CONVERT AUDIO TO MP3 (SAFE FOR FFMPEG)
            safe_audio = os.path.join(TEMP_DIR, f"safe_{i}.mp3")

            run([
                FFMPEG, "-y",
                "-i", aud,
                safe_audio
            ])

            # DURATION
            duration = get_duration(aud)
            speed = 1 / duration if duration > 0 else 1

            # ADJUST VIDEO SPEED
            adj_video = os.path.join(TEMP_DIR, f"adj_{i}.mp4")

            run([
                FFMPEG, "-y",
                "-i", vid,
                "-filter:v", f"setpts={speed}*PTS",
                adj_video
            ])

            # MERGE AUDIO + VIDEO
            scene = os.path.join(TEMP_DIR, f"scene_{i}.mp4")

            run([
                FFMPEG, "-y",
                "-i", adj_video,
                "-i", safe_audio,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                scene
            ])

            scene_files.append(scene)

        # CONCAT SCENES
        concat_file = os.path.join(TEMP_DIR, "concat.txt")

        with open(concat_file, "w") as f:
            for s in scene_files:
                f.write(f"file '{s}'\n")

        final_video = os.path.join(TEMP_DIR, "final.mp4")

        run([
            FFMPEG, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            final_video
        ])

        # UPLOAD
        upload = cloudinary.uploader.upload_large(
            final_video,
            resource_type="video"
        )

        return jsonify({
            "status": "success",
            "video_url": upload["secure_url"]
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
