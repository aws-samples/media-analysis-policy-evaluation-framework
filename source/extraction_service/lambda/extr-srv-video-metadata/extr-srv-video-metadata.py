import json
import boto3
import os
import base64
from PIL import Image
from moviepy.editor import VideoFileClip
import utils

VIDEO_SAMPLE_CHUNK_DURATION_S = float(os.environ.get("VIDEO_SAMPLE_CHUNK_DURATION_S", 600)) # default to 10 minutes

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")

REKOGNITION_REGION = os.environ.get("REKOGNITION_REGION", os.environ.get('AWS_REGION'))
REKOGNITION_COLOR_PIXEL_PERCENT_THRESHOLD = 90
REKOGNITION_DOMINANT_COLOR_MIN_NUMBER = 2 

VIDEO_SAMPLE_S3_BUCKET = os.environ.get("VIDEO_SAMPLE_S3_BUCKET")
VIDEO_SAMPLE_S3_PREFIX = os.environ.get("VIDEO_SAMPLE_S3_PREFIX")

IMAGE_MAX_WIDTH = 2048
IMAGE_MAX_HEIGHT = 2048

s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')#, region_name=REKOGNITION_REGION)

local_path = '/tmp/'

def lambda_handler(event, context):
    if event is None or "Request" not in event:
        return 'Invalid request'
    
    task_id = event["Request"].get("TaskId")
    s3_bucket, s3_key, sample_interval = None, None, 1
    try:
        s3_bucket = event["Request"]["Video"]["S3Object"]["Bucket"]
        s3_key = event["Request"]["Video"]["S3Object"]["Key"]
        sample_interval = float(event["Request"]["PreProcessSetting"]["SampleIntervalS"])
    except:
        return 'Invalid Request'

    # Download video to local disk
    local_file_path = local_path + s3_key.split('/')[-1]
    s3.download_file(s3_bucket, s3_key, local_file_path)
    
    # Generate thumbnail and video metadata
    if "MetaData" not in event:
        event["MetaData"] = {}
    video_metadata = get_video_metadata(event, local_file_path)
    duration = video_metadata["Duration"]

    task = event
    task_db = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, task_id)
    if task_db:
        task["Id"] = task_db["Id"]
        task["RequestBy"] = task_db.get("RequestBy")
        task["RequestTs"] = task_db.get("RequestTs")
        task["Status"] = task_db.get("Status")

    task["MetaData"]["VideoMetaData"] = video_metadata
    
    # Frame metadata
    frame_metadata = task["MetaData"].get("VideoFrameS3", {})
    frame_metadata["TotalFramesPlaned"] = int(duration / sample_interval)
    frame_metadata["TotalFramesSampled"] = 0
    frame_metadata["S3Bucket"] = VIDEO_SAMPLE_S3_BUCKET
    frame_metadata["S3Prefix"] = f'tasks/{task_id}/{VIDEO_SAMPLE_S3_PREFIX}'
    task["MetaData"]["VideoFrameS3"] = frame_metadata

    task["Status"] = "processing"

    try:
        # update video_task index
        utils.dynamodb_table_upsert(DYNAMO_VIDEO_TASK_TABLE, document=task)
    except Exception as ex:
        print(ex)
        
    # Create array for chunk iteration
    chunks = []
    start_ts = 0
    while start_ts <= duration:
        chunks.append({
            "start_ts": start_ts,
            "end_ts": start_ts + VIDEO_SAMPLE_CHUNK_DURATION_S,
            "task_id": task_id
        })
        start_ts += VIDEO_SAMPLE_CHUNK_DURATION_S
    
    task["chunks"] = chunks
    
    return task

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
        
def get_video_metadata(event, file_path):
    video_file_name = event["Request"]["Video"]["S3Object"]["Key"].split('/')[-1]
    thumbnail_local_path = f'{local_path}thumbnail.jpg'
    thumbnail_s3_bucket = event["Request"]["Video"]["S3Object"]["Bucket"]
    thumbnail_s3_key = f'{event["Request"]["Video"]["S3Object"]["Key"].replace(video_file_name, "thumbnail.jpg")}'

    video_clip = VideoFileClip(file_path)    
    # Get thumbnail - avoid black screen
    for i in range(0, int(video_clip.duration)):
        # Get frame and store on local disk
        video_clip.save_frame(thumbnail_local_path, t=i)
        # Upload to S3
        s3.upload_file(thumbnail_local_path, thumbnail_s3_bucket, thumbnail_s3_key)
        
        # Check if image is black frame
        is_black_frame = is_single_color_frame(thumbnail_s3_bucket, thumbnail_s3_key)
        if is_black_frame is not None and not is_black_frame:
            break
    
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

def is_single_color_frame(thumbnail_s3_bucket, thumbnail_s3_key):
    # rekognition get dominant color 
    response = rekognition.detect_labels(
        Image={
            "S3Object": { "Bucket": thumbnail_s3_bucket, "Name": thumbnail_s3_key}
        },
        Features=[
            "IMAGE_PROPERTIES"
        ],
        Settings={
            "ImageProperties": {
                "MaxDominantColors": 5
            }
        }
    )
    #print(response["ImageProperties"]["DominantColors"])
    if "ImageProperties" in response and "DominantColors" in response["ImageProperties"] and len(response["ImageProperties"]["DominantColors"]) > 0:
        return len(response["ImageProperties"]["DominantColors"]) <= REKOGNITION_DOMINANT_COLOR_MIN_NUMBER or response["ImageProperties"]["DominantColors"][0]["PixelPercent"] >= REKOGNITION_COLOR_PIXEL_PERCENT_THRESHOLD
    
    return None