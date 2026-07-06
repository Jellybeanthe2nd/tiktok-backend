import os
import requests
import subprocess
from flask import Flask, request, jsonify
import cloudinary
import cloudinary.uploader

app = Flask(__name__)


# ==========================
# CONFIG
# ==========================

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)


cloudinary.config(
    cloud_name="cbtzmlen",
    api_key="761773767925476",
    api_secret="cLa3fC04tiT5ByxCqXYfJ9cYmVA"
)



# ==========================
# HELPERS
# ==========================

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

    return result.stdout



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

    output = run([
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        file
    ])

    return float(output.strip())



# ==========================
# VIDEO PROCESSING
# ==========================

def resize_video_to_audio(video, audio, index):

    video_duration = get_duration(video)
    audio_duration = get_duration(audio)


    print("======================")
    print("Scene", index)
    print("Original video:", video_duration)
    print("Audio:", audio_duration)
    print("======================")


    if video_duration <= 0:
        raise Exception("Video duration is zero")


    if audio_duration <= 0:
        raise Exception("Audio duration is zero")


    # This is the important part:
    #
    # Example:
    # video = 1 sec
    # audio = 5 sec
    #
    # factor = 0.2
    #
    # setpts=0.2*PTS
    #
    # slows video 5x


   speed_factor = audio_duration / video_duration


    stretched_video = os.path.join(
        TEMP_DIR,
        f"stretched_{index}.mp4"
    )


    run([
        FFMPEG,
        "-y",

        "-i",
        video,

        "-vf",
        f"setpts={speed_factor}*PTS",

        "-r",
        "24",

        "-vsync",
        "cfr",

        "-an",

        "-c:v",
        "libx264",

        "-preset",
        "fast",

        "-pix_fmt",
        "yuv420p",

        stretched_video
    ])


    new_duration = get_duration(stretched_video)


    print("After stretching:", new_duration)
    print("Target:", audio_duration)


    # Allow 0.15 second difference
    if abs(new_duration - audio_duration) > 0.15:

        raise Exception(
            f"Video resize failed. Got {new_duration}s expected {audio_duration}s"
        )


    return stretched_video



def merge_audio_video(video, audio, index):

    output = os.path.join(
        TEMP_DIR,
        f"scene_{index}.mp4"
    )


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

        "-c:a",
        "aac",

        "-pix_fmt",
        "yuv420p",

        output
    ])


    return output



# ==========================
# API
# ==========================

@app.route("/generate-video", methods=["POST"])
def generate_video():

    try:

        data = request.json


        video_urls = data.get("video_urls", [])
        audio_urls = data.get("audio_urls", [])


        if len(video_urls) != len(audio_urls):

            return jsonify({
                "status":"error",
                "message":"video_urls and audio_urls count mismatch"
            }),400



        scenes=[]


        for i in range(len(video_urls)):


            video = download(
                video_urls[i],
                f"video_{i}.mp4"
            )


            audio = download(
                audio_urls[i],
                f"audio_{i}.wav"
            )


            fixed_video = resize_video_to_audio(
                video,
                audio,
                i
            )


            scene = merge_audio_video(
                fixed_video,
                audio,
                i
            )


            scenes.append(scene)



        # ==========================
        # CONCAT
        # ==========================

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

            "-c:a",
            "aac",

            "-pix_fmt",
            "yuv420p",

            final
        ])



        # ==========================
        # CLOUDINARY
        # ==========================

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




# ==========================
# START
# ==========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=10000
    )
