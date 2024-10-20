import json
import boto3
import os
import utils
import base64
from langchain.vectorstores import FAISS

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", os.environ.get('AWS_REGION'))
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
VIDEO_FRAME_SIMILAIRTY_THRESHOLD = float(os.environ.get("VIDEO_FRAME_SIMILAIRTY_THRESHOLD","0.1"))
VIDEO_SAMPLE_FILE_PREFIX = os.environ.get("VIDEO_SAMPLE_FILE_PREFIX")
BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID = os.environ.get("BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID")

s3 = boto3.client('s3')
bedrock = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION) 

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

    enable_smart_sampling = False
    try:
        enable_smart_sampling = task["Request"]["PreProcessSetting"]["SmartSample"] == True
    except Exception as ex:
        print(ex)
    
    if not enable_smart_sampling:
        return event

    similarity_threshold = VIDEO_FRAME_SIMILAIRTY_THRESHOLD
    if "SimilarityThreshold" in task["Request"]["PreProcessSetting"]:
        try:
            similarity_threshold = float(task["Request"]["PreProcessSetting"]["SimilarityThreshold"])
        except Exception as ex:
            print(ex)

            
    # Read image frames from S3
    s3_bucket = task["MetaData"]["VideoFrameS3"]["S3Bucket"]
    s3_prefix = task["MetaData"]["VideoFrameS3"]["S3Prefix"]
    total_frames = task["MetaData"]["VideoFrameS3"]["TotalFramesPlaned"]

    video_duration = float(task["MetaData"]["VideoMetaData"]["Duration"])
    timestamps = generate_sample_timestamps(task["Request"].get("PreProcessSetting"), video_duration, start_ts, end_ts)
    
    prev_ts, prev_vector, total_sampled = start_ts, None, 0
    for ts in timestamps:
        cur_ts = ts["ts"]
        try:
            s3_key = f"{s3_prefix}/{VIDEO_SAMPLE_FILE_PREFIX}{cur_ts}.jpg"

            # Get image base64 str
            base64_encoded_image = None
            try:
                response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
                image_data = response['Body'].read()
                base64_encoded_image = base64.b64encode(image_data).decode('utf-8')
            except Exception as ex:
                print(ex)

            if base64_encoded_image:
                # Generate mm embedding
                cur_vector = get_mm_vector(base64_encoded_image)
                
                # similarity score: compare with previous image
                score = similarity_check(task_id, prev_ts, prev_vector, cur_ts, cur_vector)

                if score is not None and score <= similarity_threshold:
                    # Delete image on S3
                    s3.delete_object(Bucket=s3_bucket, Key=s3_key)

                    # Delete from DB video_frame table
                    frame_id = f'{task_id}_{cur_ts}'
                    response = utils.dynamodb_delete_by_id(DYNAMO_VIDEO_FRAME_TABLE, frame_id, task_id)

                else:
                    # set current image as prev
                    prev_vector = cur_vector
                    prev_ts = cur_ts

                    total_sampled += 1
                    
                    # update frame in db: include similarity score
                    if score:
                        response = utils.update_item_with_similarity_score(DYNAMO_VIDEO_FRAME_TABLE, f'{task_id}_{cur_ts}', task_id, score)

        except Exception as e:
            print(e)

    # update video_task table
    try:
        # Get task from DB
        task_db = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, task_id)
        sampled = float(task_db["MetaData"]["VideoFrameS3"]["TotalFramesSampled"])
        task_db["MetaData"]["VideoFrameS3"]["TotalFramesSampled"] = sampled + float(total_sampled)
        # Update DB
        utils.dynamodb_table_upsert(DYNAMO_VIDEO_TASK_TABLE, task_db)
    except Exception as ex:
        print(ex)

def similarity_check(task_id, pre_ts, pre_vector, cur_ts, cur_vector, input_text=None):
    if pre_vector is None or cur_vector is None:
        return None

    prev_doc_id = f'{task_id}_{pre_ts}'

    # Store previous vector to DB
    vector_store = FAISS.from_embeddings(text_embeddings=[("", pre_vector)], embedding=None, metadatas=[{"ts":pre_ts}])
    results = vector_store.similarity_search_with_score_by_vector(embedding=cur_vector, k=10, filter=dict(ts=pre_ts))
    
    score = None
    if results and len(results) > 0:
        score = results[0][1]

    # Delete temp index
    vector_store.index.reset()

    return score

def get_mm_vector(base64_encoded_image, input_text=None):
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
            modelId=BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID, 
            accept="application/json", 
            contentType="application/json"
        )
        
        response_body = json.loads(response.get('body').read())
        embedding = response_body.get("embedding")
    except Exception as ex:
        print(ex)

    return embedding

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