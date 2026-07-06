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

    r = requests.get(
        url,
        timeout=120
    )

    r.raise_for_status()

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



# =========================
# VIDEO PROCESSING
# =========================

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

        "-preset",
        "ultrafast",

        "-crf",
        "28",

        "-pix_fmt",
        "yuv420p",

        "-threads",
        "1",

        output_file
    ])



def stretch_video(input_file, output_file, target_duration):

    current_duration = get_duration(input_file)

    if current_duration <= 0:
        raise Exception("Video duration invalid")


    multiplier = target_duration / current_duration


    print(
        f"Stretching {current_duration}s -> {target_duration}s"
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
        "ultrafast",

        "-crf",
        "28",

        "-pix_fmt",
        "yuv420p",

        "-threads",
        "1",

        output_file
    ])



def merge_audio(video, audio, output):

    run([
        FFMPEG,
        "-y",

        "-i",
        video,

        "-i",
        audio,

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-c:v",
        "libx264",

        "-preset",
        "ultrafast",

        "-crf",
        "28",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-pix_fmt",
        "yuv420p",

        "-threads",
        "1",

        output
    ])



# =========================
# API
# =========================

@app.route("/generate-video", methods=["POST"])
def generate_video():

    try:

        data = request.json


        video_urls = data.get("video_urls", [])
        audio_urls = data.get("audio_urls", [])


        if not video_urls or not audio_urls:
            return jsonify({
                "status":"error",
                "message":"Missing video_urls or audio_urls"
            }),400



        scenes = []


        for i in range(len(video_urls)):


            print("================")
            print("SCENE", i)


            video = download(
                video_urls[i],
                f"video_{i}.mp4"
            )


            audio = download(
                audio_urls[i],
                f"audio_{i}.wav"
            )


            video_duration = get_duration(video)
            audio_duration = get_duration(audio)


            print(
                "SOURCE VIDEO:",
                video_duration
            )

            print(
                "AUDIO:",
                audio_duration
            )



            normalized = os.path.join(
                TEMP_DIR,
                f"normalized_{i}.mp4"
            )


            normalize_video(
                video,
                normalized
            )



            stretched = os.path.join(
                TEMP_DIR,
                f"stretched_{i}.mp4"
            )


            stretch_video(
                normalized,
                stretched,
                audio_duration
            )



            scene = os.path.join(
                TEMP_DIR,
                f"scene_{i}.mp4"
            )


            merge_audio(
                stretched,
                audio,
                scene
            )


            print(
                "FINAL SCENE:",
                get_duration(scene)
            )


            scenes.append(scene)



        concat_file = os.path.join(
            TEMP_DIR,
            "concat.txt"
        )


        with open(concat_file,"w") as f:

            for scene in scenes:

                f.write(
                    f"file '{os.path.abspath(scene)}'\n"
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
            concat_file,

            "-c:v",
            "libx264",

            "-preset",
            "ultrafast",

            "-crf",
            "28",

            "-c:a",
            "aac",

            "-threads",
            "1",

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




if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )
