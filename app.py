import os
import requests
import subprocess
from flask import Flask, request, jsonify
import cloudinary
import cloudinary.uploader

app = Flask(__name__)

# ----------------------------
# CONFIG
# ----------------------------
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

cloudinary.config(
    cloud_name="cbtzmlen",
    api_key="761773767925476",
    api_secret="cLa3fC04tiT5ByxCqXYfJ9cYmVA"
)

# ----------------------------
# HELPERS
# ----------------------------
def run(cmd):
    subprocess.run(cmd, check=True)

def download(url, name):
    path = os.path.join(TEMP_DIR, name)
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(1024):
            if chunk:
                f.write(chunk)
    return path

def duration(file):
    return float(subprocess.check_output([
        FFPROBE,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file
    ]).decode().strip())

# ----------------------------
# MAIN API
# ----------------------------
@app.route("/generate-video", methods=["POST"])
def generate_video():
    data = request.json

    video_urls = data.get("video_urls", [])
    audio_urls = data.get("audio_urls", [])

    if not video_urls or not audio_urls:
        return jsonify({"status": "error", "message": "missing inputs"}), 400

    scenes = []

    try:
        for i in range(len(video_urls)):

            # ----------------------------
            # DOWNLOAD FILES
            # ----------------------------
            video = download(video_urls[i], f"v{i}.mp4")
            audio = download(audio_urls[i], f"a{i}.mp3")

            # ----------------------------
            # GET DURATIONS
            # ----------------------------
            v_dur = duration(video)
            a_dur = duration(audio)

            # ----------------------------
            # SPEED MATCH VIDEO TO AUDIO
            # ----------------------------
            speed = v_dur / a_dur

            adjusted = os.path.join(TEMP_DIR, f"adj_{i}.mp4")

            # IMPORTANT FIX:
            # reset timestamps + force CFR + prevent freeze frames
            run([
                FFMPEG, "-y",
                "-i", video,
                "-filter:v", f"setpts={speed}*PTS",
                "-r", "30",
                "-vsync", "cfr",
                "-an",
                adjusted
            ])

            # ----------------------------
            # MERGE AUDIO + VIDEO
            # ----------------------------
            scene = os.path.join(TEMP_DIR, f"scene_{i}.mp4")

            run([
                FFMPEG, "-y",
                "-i", adjusted,
                "-i", audio,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-pix_fmt", "yuv420p",
                "-shortest",
                scene
            ])

            scenes.append(scene)

        # ----------------------------
        # CONCAT SCENES
        # ----------------------------
        list_file = os.path.join(TEMP_DIR, "list.txt")

        with open(list_file, "w") as f:
            for s in scenes:
                f.write(f"file '{os.path.abspath(s)}'\n")

        final = os.path.join(TEMP_DIR, "final.mp4")

        run([
            FFMPEG, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            final
        ])

        # ----------------------------
        # UPLOAD TO CLOUDINARY
        # ----------------------------
        upload = cloudinary.uploader.upload_large(
            final,
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
