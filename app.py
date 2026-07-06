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

    r = requests.get(url, timeout=60)
    r.raise_for_status()

    with open(path, "wb") as f:
        f.write(r.content)

    return path


def duration(file):
    result = subprocess.check_output([
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        file
    ])

    return float(result.decode().strip())


# ----------------------------
# API
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

            print(f"Processing scene {i}")


            # ----------------------------
            # DOWNLOAD
            # ----------------------------

            video = download(
                video_urls[i],
                f"video_{i}.mp4"
            )

            audio = download(
                audio_urls[i],
                f"audio_{i}.wav"
            )


            # ----------------------------
            # DURATIONS
            # ----------------------------

            video_duration = duration(video)
            audio_duration = duration(audio)


            print(
                "VIDEO:",
                video_duration,
                "AUDIO:",
                audio_duration
            )


            # ----------------------------
            # RESIZE VIDEO TIME TO AUDIO TIME
            # ----------------------------

            # Example:
            # video = 1 sec
            # audio = 5 sec
            #
            # setpts=5*PTS
            #
            # stretches video 5x

            multiplier = audio_duration / video_duration


            stretched_video = os.path.join(
                TEMP_DIR,
                f"stretched_{i}.mp4"
            )


            run([
                FFMPEG,
                "-y",
                "-i",
                video,

                "-filter:v",
                f"setpts={multiplier}*PTS",

                "-an",

                "-r",
                "24",

                "-c:v",
                "libx264",

                "-pix_fmt",
                "yuv420p",

                stretched_video
            ])



            # ----------------------------
            # MERGE VIDEO + VOICEOVER
            # ----------------------------

            scene = os.path.join(
                TEMP_DIR,
                f"scene_{i}.mp4"
            )


            run([
                FFMPEG,
                "-y",

                "-i",
                stretched_video,

                "-i",
                audio,

                "-map",
                "0:v:0",

                "-map",
                "1:a:0",

                "-c:v",
                "libx264",

                "-c:a",
                "aac",

                "-pix_fmt",
                "yuv420p",

                "-t",
                str(audio_duration),

                scene
            ])


            scenes.append(scene)



        # ----------------------------
        # CONCAT ALL SCENES
        # ----------------------------

        concat_file = os.path.join(
            TEMP_DIR,
            "concat.txt"
        )


        with open(concat_file, "w") as f:

            for scene in scenes:
                f.write(
                    f"file '{os.path.abspath(scene)}'\n"
                )


        final_video = os.path.join(
            TEMP_DIR,
            "final.mp4"
        )


        run([
            FFMPEG,
            "-y",

            "-f",
            "concat",

            "-safe",
            "0",

            "-i",
            concat_file,

            "-c:v",
            "libx264",

            "-c:a",
            "aac",

            "-pix_fmt",
            "yuv420p",

            final_video
        ])



        # ----------------------------
        # CLOUDINARY
        # ----------------------------

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
# START
# ----------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
