import os
import requests
import subprocess
from flask import Flask, request, jsonify
import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# ----------------------------
# SYSTEM FFMPEG (Docker)
# ----------------------------
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# ----------------------------
# CLOUDINARY CONFIG
# ----------------------------
cloudinary.config(
    cloud_name="cbtzmlen",
    api_key="761773767925476",
    api_secret="YOUR_API_SECRET_HERE"
)

# ----------------------------
# TEMP DIRECTORY
# ----------------------------
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)


# ----------------------------
# HELPERS
# ----------------------------
def run(cmd):
    subprocess.run(cmd, check=True)


def download_file(url, filename):
    path = os.path.join(TEMP_DIR, filename)

    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()

    with open(path, "wb") as f:
        for chunk in r.iter_content(1024):
            if chunk:
                f.write(chunk)

    return path


def get_duration(file_path):
    result = subprocess.check_output([
        FFPROBE,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]).decode().strip()

    return float(result)


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

    scenes = []

    try:
        for i in range(len(video_urls)):

            # ----------------------------
            # DOWNLOAD FILES
            # ----------------------------
            video_path = download_file(video_urls[i], f"video_{i}.mp4")
            audio_path = download_file(audio_urls[i], f"audio_{i}.mp3")

            # ----------------------------
            # GET AUDIO DURATION
            # ----------------------------
            duration = get_duration(audio_path)

            # ----------------------------
            # FORCE VIDEO LENGTH MATCH AUDIO
            # ----------------------------
            adjusted_video = os.path.join(TEMP_DIR, f"adjusted_{i}.mp4")

            run([
                FFMPEG, "-y",
                "-i", video_path,
                "-t", str(duration),
                "-vf", "scale=720:1280,setsar=1",
                adjusted_video
            ])

            # ----------------------------
            # MERGE AUDIO + VIDEO (FIXED SYNC)
            # ----------------------------
            scene_path = os.path.join(TEMP_DIR, f"scene_{i}.mp4")

            run([
                FFMPEG, "-y",
                "-i", adjusted_video,
                "-i", audio_path,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-r", "30",
                "-fflags", "+genpts",
                scene_path
            ])

            scenes.append(scene_path)

        # ----------------------------
        # CONCAT SCENES
        # ----------------------------
        concat_file = os.path.join(TEMP_DIR, "concat.txt")

        with open(concat_file, "w") as f:
            for s in scenes:
                f.write(f"file '{os.path.abspath(s)}'\n")

        final_output = os.path.join(TEMP_DIR, "final.mp4")

        run([
            FFMPEG, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            final_output
        ])

        # ----------------------------
        # UPLOAD TO CLOUDINARY
        # ----------------------------
        upload = cloudinary.uploader.upload_large(
            final_output,
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
# RUN SERVER
# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
