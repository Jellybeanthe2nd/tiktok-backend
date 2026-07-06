import os
import subprocess
import requests
import cloudinary
import cloudinary.uploader

from flask import Flask, request, jsonify


app = Flask(__name__)


# =========================
# CONFIG
# =========================

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


cloudinary.config(
    cloud_name="cbtzmlen",
    api_key="761773767925476",
    api_secret="cLa3fC04tiT5ByxCqXYfJ9cYmVA"
)


# =========================
# HELPERS
# =========================

def run(cmd):
    print("RUNNING:")
    print(" ".join(cmd))

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print(result.stderr)
        raise Exception(result.stderr)

    return result


def download(url, filename):

    path = os.path.join(TEMP_DIR, filename)

    r = requests.get(url, timeout=120)

    if r.status_code != 200:
        raise Exception(
            f"Download failed {r.status_code}: {url}"
        )

    with open(path, "wb") as f:
        f.write(r.content)

    return path



def get_duration(file):

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



def normalize_video(input_file, output_file):

    run([
        FFMPEG,
        "-y",
        "-fflags",
        "+genpts",
        "-i",
        input_file,

        "-c:v",
        "libx264",

        "-pix_fmt",
        "yuv420p",

        output_file
    ])



def stretch_video(input_file, output_file, target_duration):

    current_duration = get_duration(input_file)

    if current_duration <= 0:
        raise Exception("Video duration is zero")


    multiplier = target_duration / current_duration


    print(
        f"Stretching video {current_duration}s -> {target_duration}s"
    )

    run([
        FFMPEG,
        "-y",

        "-i",
        input_file,

        "-vf",
        f"setpts={multiplier}*PTS",

        "-an",

        "-c:v",
        "libx264",

        "-preset",
        "fast",

        "-pix_fmt",
        "yuv420p",

        output_file
    ])



# =========================
# API
# =========================

@app.route("/generate-video", methods=["POST"])
def generate_video():

    try:

        data = request.json


        video_urls = data["video_urls"]
        audio_urls = data["audio_urls"]


        scenes = []


        for i in range(len(video_urls)):


            print("===================")
            print("SCENE", i)


            video = download(
                video_urls[i],
                f"input_video_{i}.mp4"
            )


            audio = download(
                audio_urls[i],
                f"audio_{i}.wav"
            )


            print(
                "SOURCE VIDEO:",
                get_duration(video)
            )

            print(
                "AUDIO:",
                get_duration(audio)
            )


            normalized = os.path.join(
                TEMP_DIR,
                f"normalized_{i}.mp4"
            )


            normalize_video(
                video,
                normalized
            )


            audio_duration = get_duration(audio)


            stretched = os.path.join(
                TEMP_DIR,
                f"stretched_{i}.mp4"
            )


            stretch_video(
                normalized,
                stretched,
                audio_duration
            )


            final_scene = os.path.join(
                TEMP_DIR,
                f"scene_{i}.mp4"
            )


            run([
                FFMPEG,
                "-y",

                "-i",
                stretched,

                "-i",
                audio,

                "-map",
                "0:v",

                "-map",
                "1:a",

                "-c:v",
                "libx264",

                "-c:a",
                "aac",

                "-pix_fmt",
                "yuv420p",

                final_scene
            ])


            print(
                "FINAL SCENE DURATION:",
                get_duration(final_scene)
            )


            scenes.append(final_scene)



        concat = os.path.join(
            TEMP_DIR,
            "concat.txt"
        )


        with open(concat,"w") as f:
            for s in scenes:
                f.write(
                    f"file '{os.path.abspath(s)}'\n"
                )


        final = os.path.join(
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
            concat,

            "-c",
            "copy",

            final
        ])



        upload = cloudinary.uploader.upload_large(
            final,
            resource_type="video"
        )


        return jsonify({
            "status":"success",
            "video_url":upload["secure_url"]
        })


    except Exception as e:

        print(e)

        return jsonify({
            "status":"error",
            "message":str(e)
        }),500



if __name__=="__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )
