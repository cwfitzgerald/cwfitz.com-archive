from PIL import Image
import filelock
import os


def get_thumbnail_url(stem : str, width : int, height : int) -> str:
    if not os.path.exists("static/video_thumbnails/thumb"):
        os.mkdir("static/video_thumbnails/thumb")

    source_path = os.path.join("static/video_thumbnails/src/", "{}.png".format(stem))
    dest_path = os.path.join("static/video_thumbnails/thumb/", "{:s}-{:.0f}x{:.0f}px.jpg".format(stem, width, height))

    if os.path.isfile(dest_path):
        return "/" + dest_path

    lock = filelock.FileLock(dest_path + ".lock")

    with lock:
        img = Image.open(source_path) # type: Image.Image

        if width == -1 and height == -1:
            raise RuntimeError("Either width or height has to be a number")
        if width == -1:
            width = int(img.width * (height / img.height))
        if height == -1:
            height = int(img.height * (width / img.width))

        img = img.resize((width, height), Image.LANCZOS).convert("RGB")

        img.save(dest_path, 'jpeg', optimize=True, quality=70, subsampling=2)

    if not lock.is_locked and os.path.exists(lock.lock_file):
        os.remove(lock.lock_file)

    return "/" + dest_path
