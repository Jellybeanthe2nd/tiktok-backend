import os
import uuid
import requests
import subprocess
from flask import Flask, request, jsonify
import cloudinary
import cloudinary.uploader
import imageio_ffmpeg
import os

os.environ["FFMPEG_BINARY"] = imageio_ffmpeg.get_ffmpeg_exe()
app = Flask(__name__)

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
def download_file(url, filename):
    """Download a file from URL to local storage"""
    response = requests.get(url, stream=True)
    if response.status_code != 200:
        raise Exception(f"Failed download: {url}")

    path = os.path.join(TEMP_DIR, filename)
    with open(path, "wb") as f:
        for chunk in response.iter_content(1024):
            f.write(chunk)

    return path


def get_duration(file_path):
    """Get audio duration using ffprobe"""
    cmd = [
        "ffprobe", "-i", file_path,
        "-show_entries", "format=duration",
        "-v", "quiet", "-of", "csv=p=0"
    ]
    result = subprocess.check_output(cmd).decode().strip()
    return float(result)


def run(cmd):
    """Run FFmpeg command"""
    subprocess.run(cmd, check=True)


# ----------------------------
# MAIN API
# ----------------------------
@app.route("/generate-video", methods=["POST"])
def generate_video():

    data = request.json

    video_urls = data["video_urls"]
    audio_urls = data["audio_urls"]

    scene_files = []

    try:
        # ----------------------------
        # PROCESS EACH SCENE
        # ----------------------------
        for i in range(len(video_urls)):

            vid_path = download_file(video_urls[i], f"vid_{i}.mp4")
            aud_path = download_file(audio_urls[i], f"aud_{i}.mp3")

            duration = get_duration(aud_path)

            adjusted_video = os.path.join(TEMP_DIR, f"adj_{i}.mp4")
            final_scene = os.path.join(TEMP_DIR, f"scene_{i}.mp4")

            # ----------------------------
            # 1. SPEED ADJUST VIDEO TO MATCH AUDIO
            # ----------------------------
            run([
                "ffmpeg", "-y",
                "-i", vid_path,
                "-filter:v", f"setpts={1/duration}*PTS",
                adjusted_video
            ])

            # ----------------------------
            # 2. ADD AUDIO TO VIDEO
            # ----------------------------
            run([
                "ffmpeg", "-y",
                "-i", adjusted_video,
                "-i", aud_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                final_scene
            ])

            scene_files.append(final_scene)

        # ----------------------------
        # CONCATENATE ALL SCENES
        # ----------------------------
        concat_file = os.path.join(TEMP_DIR, "concat.txt")

        with open(concat_file, "w") as f:
            for scene in scene_files:
                f.write(f"file '{scene}'\n")

        final_output = os.path.join(TEMP_DIR, "final.mp4")

        run([
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            final_output
        ])

        # ----------------------------
        # UPLOAD TO CLOUDINARY
        # ----------------------------
        upload_result = cloudinary.uploader.upload_large(
            final_output,
            resource_type="video"
        )

        return jsonify({
            "status": "success",
            "video_url": upload_result["secure_url"]
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
