'''
1 step of the Extraction Step Function
1. Download video from S3 to local disk
2. Generate timestamps based on ProProcessing setting
3. Loop timestamps
3.1 Sample image from video - save to local disk
3.2 Upload to S3
3.3 Delete local image
4. Store to DB
'''
import json
from moviepy.editor import VideoFileClip
import boto3
import os
from opensearchpy import OpenSearch
import base64
from PIL import Image

VIDEO_SAMPLE_CHUNK_DURATION_S = float(os.environ.get("VIDEO_SAMPLE_CHUNK_DURATION_S", 600)) # default to 10 minutes
VIDEO_SAMPLE_S3_BUCKET = os.environ.get("VIDEO_SAMPLE_S3_BUCKET")
VIDEO_SAMPLE_S3_PREFIX = os.environ.get("VIDEO_SAMPLE_S3_PREFIX")
VIDEO_SAMPLE_FILE_PREFIX = os.environ.get("VIDEO_SAMPLE_FILE_PREFIX")
OPENSEARCH_INDEX_NAME_VIDEO_TASK = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TASK")
OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME = os.environ.get("OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")
OPENSEARCH_VIDEO_FRAME_INDEX_MAPPING = os.environ.get("OPENSEARCH_VIDEO_FRAME_INDEX_MAPPING")
OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_TEMP_PREFIX = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_TEMP_PREFIX")
OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD = float(os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD"))
OPENSEARCH_VIDEO_FRAME_SIMILAIRTY_INDEX_MAPPING = os.environ.get("OPENSEARCH_VIDEO_FRAME_SIMILAIRTY_INDEX_MAPPING")

REKOGNITION_COLOR_PIXEL_PERCENT_THRESHOLD = 90
REKOGNITION_DOMINANT_COLOR_MIN_NUMBER = 2 

IMAGE_MAX_WIDTH = 2048
IMAGE_MAX_HEIGHT = 2048

SEARCH_FIELDS = ["detect_label","detect_label_category","detect_text", "detect_celebrity", "detect_moderation", "detect_logo", "image_caption"]

s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')
opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )
bedrock = boto3.client('bedrock-runtime') 

local_path = '/tmp/'

def lambda_handler(event, context):
    if event is None or "Request" not in event:
        return 'Invalid request'
    
    task_id = event["Request"].get("TaskId")
    opensearch_temp_index_name = OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_TEMP_PREFIX + task_id
    print("opensearch_temp_index_name: ",opensearch_temp_index_name)

    enable_smart_sampling = False
    try:
        enable_smart_sampling = event["Request"]["PreProcessSetting"]["SmartSample"] == True
    except Exception as ex:
        print(ex)

    sample_start_s = event.get("SampleStartS", 0)
    video_duration = event.get("VideoDuration")

    if video_duration is not None and sample_start_s >= video_duration:
        event["SampleCompleted"] = True
        
        # Delete temp index for similiarity check
        opensearch_client.indices.delete(index=opensearch_temp_index_name)
        return event

    # Download video to local disk
    local_file_path = local_path + event["Request"]["Video"]["S3Object"]["Key"].split('/')[-1]
    s3.download_file(event["Request"]["Video"]["S3Object"]["Bucket"], event["Request"]["Video"]["S3Object"]["Key"], local_file_path)
    
    # Load video
    video_clip = VideoFileClip(local_file_path)
    if video_duration is None:
        video_duration = video_clip.duration

    # First iteration: generate thumbnail and get video metadata
    if sample_start_s == 0:
        if "MetaData" not in event:
            event["MetaData"] = {}
        event["MetaData"]["VideoMetaData"] = get_video_metadata(video_clip, event, local_file_path)
    
    if sample_start_s >= video_duration:
        event["SampleCompleted"] = True
        event["VideoDuration"] = video_duration

        # Delete temp index for similiarity check
        try:
            opensearch_client.indices.delete(index=opensearch_temp_index_name)
        except Exception as ex:
            print(ex)
        return event
    
    # Create similiarity check index if doesn't exists
    if not opensearch_client.indices.exists(index=opensearch_temp_index_name):
        opensearch_client.indices.create(index=opensearch_temp_index_name, body=OPENSEARCH_VIDEO_FRAME_SIMILAIRTY_INDEX_MAPPING)
    
    # Calculate sample timestamps based on request setting
    timestamps = generate_sample_timestamps(event["Request"].get("PreProcessSetting"), video_duration, sample_start_s, sample_start_s + VIDEO_SAMPLE_CHUNK_DURATION_S)

    # Create image frames
    resolution = event["MetaData"]["VideoMetaData"].get("Resolution")
    need_resize = resolution is None or resolution[0] > IMAGE_MAX_WIDTH or resolution[1] > IMAGE_MAX_HEIGHT
    frames = sample_video_at_timestamps(video_clip, timestamps, task_id, opensearch_temp_index_name, enable_smart_sampling, need_resize)

    # Get latest task from DB
    task = opensearch_client.get(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK, id=task_id)["_source"]
    task["MetaData"]["VideoMetaData"] = event["MetaData"]["VideoMetaData"]
    
    if "MetaData" not in task:
        task["MetaData"] = {}

    video_meta = task["MetaData"].get("VideoFrameS3", {})
    total_frames = video_meta.get("TotalFramesPlaned", 0)
    sampled_frames = video_meta.get("TotalFramesSampled", 0)
    
    video_meta["TotalFramesPlaned"] = total_frames + len(timestamps)
    video_meta["TotalFramesSampled"] = sampled_frames + len(frames)

    if "S3Bucket" not in video_meta:
        video_meta["S3Bucket"] = VIDEO_SAMPLE_S3_BUCKET
    if "S3Prefix" not in video_meta:
        video_meta["S3Prefix"] = f'tasks/{task_id}/{VIDEO_SAMPLE_S3_PREFIX}'
    task["MetaData"]["VideoFrameS3"] = video_meta

    task["Status"] = "processing"

    try:
        # update video_task index
        opensearch_client.update(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK, id=task_id, body={"doc": task})
    except Exception as ex:
        print(ex)
    
    frame_index_name = OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME + task_id
    # Create video_frame_[task_id] index
    if not opensearch_client.indices.exists(index=frame_index_name):
        response = opensearch_client.indices.create(
            index=frame_index_name,
            body=format_frame_index_mapping(OPENSEARCH_VIDEO_FRAME_INDEX_MAPPING,SEARCH_FIELDS)
        )
        
    # Add to video_frame_[task_id] index
    for f in frames:
        opensearch_client.index(
                    index = frame_index_name,
                    body = f,
                    id = f'{VIDEO_SAMPLE_FILE_PREFIX}{f["timestamp"]}',
                    refresh = True
                )
    
    task["SampleCompleted"] = False
    task["SampleStartS"] = sample_start_s + VIDEO_SAMPLE_CHUNK_DURATION_S
        
    return task

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
            current_time += setting["SampleIntervalS"]

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
        
def sample_video_at_timestamps(video_clip, timestamps, task_id, opensearch_temp_index_name, enable_smart_sampling, need_resize):
    # Save the sampled frame as an image
    result = []
    prev_ts, prev_vector = None, None
    for ts in timestamps:
        # save frame to local disk
        output_file = f'{VIDEO_SAMPLE_FILE_PREFIX}{ts["ts"]}.jpg'
        output_path = f'{local_path}{output_file}'
        video_clip.save_frame(output_path, ts["ts"])
        if need_resize:
            resize_if_large(output_path)

        # similarity check: compare with previous image
        cur_vector = get_mm_vector(output_path)
        if not enable_smart_sampling or not similarity_check(task_id, prev_ts, prev_vector, ts["ts"], cur_vector, opensearch_temp_index_name):
            # upload to s3
            upload_file_key = f'tasks/{task_id}/{VIDEO_SAMPLE_S3_PREFIX}/{output_file}'
            s3.upload_file(output_path, VIDEO_SAMPLE_S3_BUCKET, upload_file_key)
            
            # include image to result
            result.append({
                "image_s3_uri": f's3://{VIDEO_SAMPLE_S3_BUCKET}/{upload_file_key}',
                "timestamp": ts["ts"]
            })
            
            # delete image from local
            try:
                os.remove(output_path)
            except Exception as ex:
                print(f"Failed to delete {output_path}", ex)

            # set current image as prev
            prev_vector = cur_vector
            prev_ts = ts["ts"]
            print(f"Not similar. Current: {output_file}, previous ts: {prev_ts}")
        else:
            # Keep the previous image on local as an anchor
            print(f"Similar image. Current: {output_file}, previous ts: {prev_ts}")

    return result

def get_video_metadata(video_clip, event, file_path):
    video_file_name = event["Request"]["Video"]["S3Object"]["Key"].split('/')[-1]
    thumbnail_local_path = f'{local_path}thumbnail.jpg'
    thumbnail_s3_bucket = event["Request"]["Video"]["S3Object"]["Bucket"]
    thumbnail_s3_key = f'{event["Request"]["Video"]["S3Object"]["Key"].replace(video_file_name, "thumbnail.jpg")}'
    
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


def similarity_check(task_id, pre_ts, pre_vector, cur_ts, cur_vector, opensearch_temp_index_name, input_text=None):
    if pre_vector is None or cur_vector is None:
        return False

    prev_doc_id = f'{task_id}_{pre_ts}'

    # Store previous vector to DB
    opensearch_client.index(index=opensearch_temp_index_name, id=prev_doc_id, body={"mm_embedding": pre_vector}, refresh=True)

    # Apply similiarity search
    query = {
          "_source": False,
          "query": {
            "bool": {
              "must": [
                {
                  "terms": {
                    "_id": [prev_doc_id]
                  }
                },
                {
                  "knn": {
                    "mm_embedding": {
                      "vector": cur_vector,
                      "k": 10
                    }
                  }
                }
              ]
            }
          }
    }

    response = opensearch_client.search(
                index=opensearch_temp_index_name,
                body=query
            )    
    score = None
    if len(response["hits"]["hits"]) > 0:
        score = response["hits"]["hits"][0]["_score"]
    return score is not None and score > OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD

def get_mm_vector(local_image_path, input_text=None):
    # Get image base64
    base64_encoded_image = None
    with open(local_image_path, "rb") as img_file:
        base64_encoded_image = base64.b64encode(img_file.read()).decode("utf-8")

    request_body = {}
    
    if input_text:
        request_body["inputText"] = input_text
        
    if base64_encoded_image:
        request_body["inputImage"] = base64_encoded_image
    
    body = json.dumps(request_body)
    
    embedding = None
    try:
        response = bedrock.invoke_model(
            body=body, 
            modelId="amazon.titan-embed-image-v1", 
            accept="application/json", 
            contentType="application/json"
        )
        
        response_body = json.loads(response.get('body').read())
        embedding = response_body.get("embedding")
    except Exception as ex:
        print(ex)

    return embedding

def format_frame_index_mapping(mapping_template, search_fields):
    mapping = json.loads(mapping_template)
    for f in search_fields:
        mapping["mappings"]["properties"][f] = {
          "type": "text",
          "fields": {
            "raw": {
              "type": "keyword"
            }
          },
          "fielddata": True
        }
    return json.dumps(mapping)
