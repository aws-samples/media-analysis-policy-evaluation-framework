import json
from moviepy.editor import VideoFileClip
import boto3
import os
import utils
import base64
from PIL import Image

VIDEO_SAMPLE_CHUNK_DURATION_S = float(os.environ.get("VIDEO_SAMPLE_CHUNK_DURATION_S", 600)) # default to 10 minutes
VIDEO_SAMPLE_S3_BUCKET = os.environ.get("VIDEO_SAMPLE_S3_BUCKET")
VIDEO_SAMPLE_S3_PREFIX = os.environ.get("VIDEO_SAMPLE_S3_PREFIX")
VIDEO_SAMPLE_FILE_PREFIX = os.environ.get("VIDEO_SAMPLE_FILE_PREFIX")

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")

IMAGE_MAX_WIDTH = 2048
IMAGE_MAX_HEIGHT = 2048

s3 = boto3.client('s3')

local_path = '/tmp/'

def lambda_handler(event, context):
    task_id, start_ts, end_ts = None, None, None
    try:
        task_id = event["task_id"]
        start_ts = float(event["start_ts"])
        end_ts = float(event["end_ts"])
    except Exception as ex:
        print(ex)
        return 'Invalid request'

    task = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, task_id)
    if task is None:
        return 'Invalid request'
        
    # Download video to local disk
    local_file_path = local_path + task["Request"]["Video"]["S3Object"]["Key"].split('/')[-1]
    s3.download_file(task["Request"]["Video"]["S3Object"]["Bucket"], task["Request"]["Video"]["S3Object"]["Key"], local_file_path)
    
    # Load video
    video_clip = VideoFileClip(local_file_path)

    # Calculate sample timestamps based on request setting
    timestamps = generate_sample_timestamps(task["Request"].get("PreProcessSetting"), video_clip.duration, start_ts, end_ts)

    # Create image frames
    resolution = task["MetaData"]["VideoMetaData"].get("Resolution")
    width, height = None, None
    if resolution is None or len(resolution) == 0:
        width = float(resolution[0])
        height = float(resolution[1])
    need_resize = width is None or width > IMAGE_MAX_WIDTH or height is None or resolution[1] > IMAGE_MAX_HEIGHT
    frames = sample_video_at_timestamps(video_clip, timestamps, task_id, need_resize, start_ts)

    # Add to video_frame table
    for f in frames:
        f["task_id"] = task_id
        f["id"] = f'{task_id}_{f["timestamp"]}'
        utils.dynamodb_table_upsert(DYNAMO_VIDEO_FRAME_TABLE, document=f)
    return event

def generate_sample_timestamps(setting, duration, sample_start_s, sample_end_s):
    if setting is None or "SampleMode" not in setting or "SampleIntervalS" not in setting:
        return None
    
    timestamps = []
    if setting["SampleMode"] == "even":
        current_time = 0.0
    
        # Generate timestamps at regular intervals
        while current_time <= duration:
            if current_time > sample_start_s and current_time <= sample_end_s:
                timestamps.append({"ts": current_time})
            current_time += float(setting["SampleIntervalS"])

    return timestamps

def resize_if_large(file_path):
    # Open the image file
    image = Image.open(file_path)
    
    # Get the current dimensions of the image
    width, height = image.size
    
    # Check if the image needs to be resized
    if width > IMAGE_MAX_WIDTH or height > IMAGE_MAX_HEIGHT:
        # Calculate the new dimensions while maintaining the aspect ratio
        ratio = min(IMAGE_MAX_WIDTH / width, IMAGE_MAX_HEIGHT / height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        
        # Resize the image
        resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Save the resized image back to the same file path
        resized_image.save(file_path)
    else:
        print(f"Image does not need resizing. Width: {width}, height: {height}")
        
def sample_video_at_timestamps(video_clip, timestamps, task_id, need_resize, sample_start_s):
    # Save the sampled frame as an image
    result = []
    prev_ts = sample_start_s
    for ts in timestamps:
        # save frame to local disk
        output_file = f'{VIDEO_SAMPLE_FILE_PREFIX}{ts["ts"]}.jpg'
        output_path = f'{local_path}{output_file}'
        video_clip.save_frame(output_path, ts["ts"])
        if need_resize:
            resize_if_large(output_path)

        # upload to s3
        upload_file_key = f'tasks/{task_id}/{VIDEO_SAMPLE_S3_PREFIX}/{output_file}'
        s3.upload_file(output_path, VIDEO_SAMPLE_S3_BUCKET, upload_file_key)
        
        # include image to result
        frame = {
            "s3_bucket": VIDEO_SAMPLE_S3_BUCKET,
            "s3_key": upload_file_key,
            "timestamp": ts["ts"],
            "prev_timestamp": prev_ts
        }
        result.append(frame)
        prev_ts = ts["ts"]

        # delete image from local
        try:
            os.remove(output_path)
        except Exception as ex:
            print(f"Failed to delete {output_path}", ex)

    return result
    
    # construct metadata
    metadata = {
        'Size': os.path.getsize(file_path),
        'Resolution': video_clip.size,
        'Duration': video_clip.duration,
        'Fps': video_clip.fps,
        'NameFormat': file_path.split('.')[-1],
        'ThumbnailS3Bucket': thumbnail_s3_bucket,
        'ThumbnailS3Key': thumbnail_s3_key,
    }

    return metadata
