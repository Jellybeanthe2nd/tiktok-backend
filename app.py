import os
import uuid
import requests
import subprocess
from flask import Flask, request, jsonify
import cloudinary
import cloudinary.uploader
import imageio_ffmpeg

app = Flask(__name__)

# ----------------------------
# FFMPEG / FFPROBE (Render safe)
# ----------------------------
FFMPEG_DIR = imageio_ffmpeg.get_ffmpeg_exe()
FFMPEG = FFMPEG_DIR

# ffprobe is in same folder as ffmpeg
FFPROBE = FFMPEG.replace("ffmpeg", "ffprobe")

os.environ["FFMPEG_BINARY"] = FFMPEG

# ----------------------------
# CLOUDINARY CONFIG
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
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()

        path = os.path.join(TEMP_DIR, filename)

        with open(path, "wb") as f:
            for chunk in r.iter_content(1024):
                if chunk:
                    f.write(chunk)

        return path

    except Exception as e:
        raise Exception(f"Download failed: {url} | {str(e)}")


# FIXED: correct ffprobe usage
def get_duration(file_path):
    cmd = [
        FFPROBE,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]

    out = subprocess.check_output(cmd).decode().strip()
    return float(out)


# ----------------------------
# MAIN ENDPOINT
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
        # ----------------------------
        # PROCESS EACH SCENE
        # ----------------------------
        for i in range(len(video_urls)):

            vid_path = download_file(video_urls[i], f"vid_{i}.mp4")
            aud_path = download_file(audio_urls[i], f"aud_{i}.wav")

            # convert audio → safe mp3
            safe_audio = os.path.join(TEMP_DIR, f"safe_audio_{i}.mp3")

            run([
                FFMPEG, "-y",
                "-i", aud_path,
                safe_audio
            ])

            # get audio duration
            duration = get_duration(safe_audio)

            adjusted_video = os.path.join(TEMP_DIR, f"adj_{i}.mp4")
            final_scene = os.path.join(TEMP_DIR, f"scene_{i}.mp4")

            # ----------------------------
            # MATCH VIDEO SPEED TO AUDIO
            # ----------------------------
            speed_factor = 1 / duration if duration > 0 else 1

            run([
                FFMPEG, "-y",
                "-i", vid_path,
                "-filter:v", f"setpts={speed_factor}*PTS",
                adjusted_video
            ])

            # ----------------------------
            # MERGE AUDIO + VIDEO
            # ----------------------------
            run([
                FFMPEG, "-y",
                "-i", adjusted_video,
                "-i", safe_audio,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                final_scene
            ])

            scene_files.append(final_scene)

        # ----------------------------
        # CONCAT ALL SCENES
        # ----------------------------
        concat_file = os.path.join(TEMP_DIR, "concat.txt")

        with open(concat_file, "w") as f:
            for scene in scene_files:
                f.write(f"file '{scene}'\n")

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
# RUN (Render uses gunicorn)
# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
