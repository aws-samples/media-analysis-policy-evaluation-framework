'''
Get frame metadata from DB
Construct vector text input using frame level data
Generate text embedding
Generate mm embedding
'''
import json
import boto3
import os
import utils
import base64
from io import BytesIO
import re
import time

LOCAL_PATH = '/tmp/'
LAMBDA_FUNCTION_ARN_EMBEDDING = os.environ.get("LAMBDA_FUNCTION_ARN_EMBEDDING")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")

s3 = boto3.client('s3')
lambda_client = boto3.client('lambda')

def lambda_handler(event, context):
    if event is None or "Error" in event or "Request" not in event or "Key" not in event:
        return {
            "Error": "Invalid Request"
        }

    task_id = event["Request"].get("TaskId")
    setting = event["Request"].get("ExtractionSetting")
    s3_bucket = event["MetaData"]["VideoFrameS3"]["S3Bucket"]
    s3_prefix = event["MetaData"]["VideoFrameS3"]["S3Prefix"]
    s3_key = event.get("Key")
    file_name = event["Request"].get("FileName", "")
    frame = event.get("frame")
    
    if task_id is None or setting is None or s3_bucket is None or s3_key is None or not s3_key.endswith('.jpg'):
        return {
            "Error": "Invalid Request"
        }

    enable_text_embedding, enable_mm_embedding = True, True
    if "EmbeddingSetting" in event["Request"]:
        enable_text_embedding = event["Request"]["EmbeddingSetting"]["Text"]
        enable_mm_embedding = event["Request"]["EmbeddingSetting"]["MultiModal"]

    if not enable_mm_embedding and not enable_text_embedding:
        return event
        
    frame_file_name = s3_key.split('/')[-1].replace('.jpg','')
    ts = float(frame_file_name.split("_")[-1])
    input_text = f"Video file name: {file_name};"

    # Get frame from DB
    frame = utils.dynamodb_get_by_id(table_name=DYNAMO_VIDEO_FRAME_TABLE, id=f'{task_id}_{ts}', key_name="id", sort_key="task_id", sort_key_value=task_id)
    embedding_frame = {
        "id": frame["id"],
        "task_id": task_id,
    }
    if frame:
        # Construct vector text input
        if "image_caption" in frame and frame["image_caption"] and len(frame["image_caption"]) > 0:
            input_text += f"Summary: {frame['image_caption']}" + ";"
        if "subtitles" in frame and frame["subtitles"] and len(frame["subtitles"]) > 0:
            transcription = ""
            for s in frame["subtitles"]:
                transcription += s["transcription"]
            input_text += f"Transcription: {transcription}" + ";"
        if "detect_label" in frame and frame["detect_label"] and len(frame["detect_label"]) > 0:
            input_text += f"Label: {get_rekognition_label_name(frame['detect_label'])}" + ";"
        if "detect_text" in frame and frame["detect_text"] and len(frame["detect_text"]) > 0:
            input_text += f"Text: {get_rekognition_label_name(frame['detect_text'])}" + ";"
        if "detect_celebrity" in frame and frame["detect_celebrity"] and len(frame["detect_celebrity"]) > 0:
            input_text += f"Celebrity: {get_rekognition_label_name(frame['detect_celebrity'])}" + ";"
        if "detect_moderation" in frame and frame["detect_moderation"] and len(frame["detect_moderation"]) > 0:
            input_text += f"Moderation: {get_rekognition_label_name(frame['detect_moderation'])}" + ";"
    
        if enable_mm_embedding:
            # Generate vector: Multimodal Embedding
            mm_embedding = get_multimodal_vector(s3_bucket, s3_key, input_text)
            embedding_frame["mm_embedding"] = mm_embedding
    
        if enable_text_embedding:
            # Generate vector: Text Embedding
            txt_embedding = get_text_vector(input_text)
            embedding_frame["text_embedding"] = txt_embedding
            embedding_frame["embedding_text"] = input_text
    
    # Update database
    utils.dynamodb_task_update_status(DYNAMO_VIDEO_TASK_TABLE, task_id, "embedding_generated")
    
    event["frame"] = embedding_frame
    return event

def get_rekognition_label_name(items):
    result = []
    if items:
        for i in items:
            result.append(i["name"])
    return ','.join(result)
    
def get_multimodal_vector(s3_bucket, s3_key, input_text=None):
    # Get image base64
    response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    image_content = response['Body'].read()
    base64_encoded_image = base64.b64encode(image_content).decode('utf-8')

    request_body = {"embedding_type": "mm"}
    if input_text is not None and len(input_text) > 0:
        request_body["text_input"] = input_text
        
    if base64_encoded_image:
        request_body["image_input"] = base64_encoded_image
    

    response = lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_ARN_EMBEDDING,  
        InvocationType='RequestResponse',
        Payload=json.dumps(request_body)
    )
    response_payload = json.loads(response['Payload'].read())
    embedding = response_payload.get("body")

    return embedding

def get_text_vector(input_text):
    response = lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_ARN_EMBEDDING,  
        InvocationType='RequestResponse',
        Payload=json.dumps({
                "embedding_type": "txt",
                "text_input": input_text
            }
        )
    )
    response_payload = json.loads(response['Payload'].read())
    embedding = response_payload.get("body")

    return embedding
