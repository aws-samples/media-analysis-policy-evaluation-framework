'''
Call Rekognition APIs to retrieve lable, text, moderation and celebrity
Call Bedrock to retrieve image summary 
Get sutitles match frame timestamp
Sync frame to DB
'''
import json
import boto3
import os
import utils
import base64
from io import BytesIO
import re
import time

REK_MIN_CONF_DETECT_LABEL = float(os.environ.get("REK_MIN_CONF_DETECT_LABEL"))
REK_MIN_CONF_DETECT_MODERATION = float(os.environ.get("REK_MIN_CONF_DETECT_MODERATION"))
REK_MIN_CONF_DETECT_TEXT = float(os.environ.get("REK_MIN_CONF_DETECT_TEXT"))
REK_MIN_CONF_DETECT_CELEBRITY = float(os.environ.get("REK_MIN_CONF_DETECT_CELEBRITY"))
REKOGNITION_REGION = os.environ.get("REKOGNITION_REGION", os.environ['AWS_REGION'])
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", os.environ['AWS_REGION'])

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
DYNAMO_VIDEO_TRANS_TABLE = os.environ.get("DYNAMO_VIDEO_TRANS_TABLE")

LOCAL_PATH = '/tmp/'


s3 = boto3.client('s3')
rekognition = boto3.client('rekognition', region_name=REKOGNITION_REGION)
bedrock = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION) 

def lambda_handler(event, context):
    if event is None or "Request" not in event or "Key" not in event:
        return {
            "Error": "Invalid Request"
        }
    task_id = event["Request"].get("TaskId")
    setting = event["Request"].get("ExtractionSetting")
    s3_bucket = event["MetaData"]["VideoFrameS3"]["S3Bucket"]
    s3_prefix = event["MetaData"]["VideoFrameS3"]["S3Prefix"]
    s3_key = event.get("Key")
    file_name = event["Request"].get("FileName", "")
    caption_prompts = event.get("Request",{}).get("ExtractionSetting",{}).get("ImageCaptionPromptTemplate")
    if not caption_prompts:
        caption_prompts = "Describe the image in detail limit in 100 tokens. Condition: If you are uncertain about the content or if the description violates any guardrail rules, return an empty result."

    if task_id is None or setting is None or s3_bucket is None or s3_key is None or not s3_key.endswith('.jpg'):
        return {
            "Error": "Invalid Request"
        }

    frame_id = s3_key.split('/')[-1].replace('.jpg','')
    ts = float(frame_id.split("_")[-1])

    frame = utils.get_frame_by_id(DYNAMO_VIDEO_FRAME_TABLE, f'{task_id}_{ts}', task_id)
    if frame is None:
        frame = {
            "id": f'{task_id}_{ts}',
            "timestamp": ts,
            "task_id": task_id,
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
        }

    if setting.get("DetectLabel") == True:
        labels, raw = rekognition_detect_label(s3_bucket, s3_key, threshold=setting.get("DetectLabelConfidenceThreshold"))
        frame["detect_label"] = labels
        s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/rekognition_detect_label/detect_label_{ts}.json', Body=json.dumps(raw))

    if setting.get("DetectText") == True:
        texts, raw = rekognition_detect_text(s3_bucket, s3_key, threshold=setting.get("DetectTextConfidenceThreshold"))
        frame["detect_text"] = texts
        s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/rekognition_detect_text/detect_text_{ts}.json', Body=json.dumps(raw))

    if setting.get("DetectCelebrity") == True:
        celes, raw = rekognition_detect_celebrity(s3_bucket, s3_key, threshold=setting.get("DetectCelebrityConfidenceThreshold"))
        frame["detect_celebrity"] = celes
        s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/rekognition_detect_celebrity/detect_celebrity_{ts}.json', Body=json.dumps(raw))

    if setting.get("DetectModeration") == True:
        mods, raw = rekognition_detect_moderation(s3_bucket, s3_key, threshold=setting.get("DetectModerationConfidenceThreshold"))
        frame["detect_moderation"] = mods
        s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/rekognition_detect_moderation/detect_moderation_{ts}.json', Body=json.dumps(raw))

    if setting.get("DetectLogo") == True:
        logos = None
        frame["detect_logo"] = logos

    # Get corresponding subtitle based on timestamp
    if setting.get("Transcription") == True:
        subtitle, transcription = None, None
        # Get prev_ts from DB
        prev_ts = 0
        db_frame = utils.dynamodb_get_by_id(table_name=DYNAMO_VIDEO_FRAME_TABLE, id=f'{task_id}_{ts}', key_name="id", sort_key="task_id", sort_key_value=task_id)
        if db_frame:
            prev_ts = db_frame.get("prev_timestamp", 0)
            frame["prev_timestamp"] = prev_ts
        subtitle, transcription = get_subtitle_by_ts(task_id, ts, prev_ts)
        if subtitle:
            frame["subtitles"] = subtitle

    # Image caption - Sonnet
    if setting.get("ImageCaption") == True:
        caption = bedrock_image_caption(s3_bucket, s3_key, caption_prompts)
        if caption and len(caption) > 0:
            frame["image_caption"] = caption

            # Store to S3
            s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/bedrock_image_caption/image_caption_{ts}.txt', Body=caption)

    # Update database: video_frame
    utils.dynamodb_table_upsert(DYNAMO_VIDEO_FRAME_TABLE, frame)

    # include frame into event object
    event["frame"] = frame

    return event

def rekognition_detect_label(s3_bucket, s3_key, threshold):
    threshold = float(threshold) if threshold else REK_MIN_CONF_DETECT_LABEL
    response = rekognition.detect_labels(
            Image={
                "S3Object": {
                    "Bucket": s3_bucket,
                    "Name": s3_key
                }
            },
            MinConfidence=threshold,
            MaxLabels=10
        )
    labels = []
    raw = response["Labels"]
    for i in raw:
        categories = []
        for c in i["Categories"]:
            cat = c["Name"]#.replace(' ','_')
            if cat not in categories:
                categories.append(cat)
        labels.append({
            "name": i["Name"],
            "confidence": i["Confidence"],
            "categories": categories
        })
    return labels, raw

def rekognition_detect_text(s3_bucket, s3_key, threshold):
    threshold = float(threshold) if threshold else REK_MIN_CONF_DETECT_TEXT
    response = rekognition.detect_text(
            Image={
                "S3Object": {
                    "Bucket": s3_bucket,
                    "Name": s3_key
                }
            },
            Filters={
                "WordFilter": {
                    "MinConfidence": threshold,
                }
            }
        )
    result = []
    raw = response["TextDetections"]
    for i in raw:
        if i["Type"] == "LINE":
            result.append({
                "name": i["DetectedText"],
                "confidence": i["Confidence"]
            })
    return result, raw

def rekognition_detect_celebrity(s3_bucket, s3_key, threshold):
    threshold = float(threshold) if threshold else REK_MIN_CONF_DETECT_CELEBRITY
    response = rekognition.recognize_celebrities(
            Image={
                "S3Object": {
                    "Bucket": s3_bucket,
                    "Name": s3_key
                }
            }
        )
    result = []
    raw = response["CelebrityFaces"]
    for i in raw:
        if i["MatchConfidence"] >= threshold:
            result.append({
                "name": i["Name"],
                "confidence": i["MatchConfidence"]
            })
    return result, response

def rekognition_detect_moderation(s3_bucket, s3_key, threshold):
    threshold = float(threshold) if threshold else REK_MIN_CONF_DETECT_MODERATION
    response = rekognition.detect_moderation_labels(
            Image={
                "S3Object": {
                    "Bucket": s3_bucket,
                    "Name": s3_key
                }
            },
            MinConfidence=threshold,
        )
    result = []
    raw = response["ModerationLabels"]
    for i in raw:
        if len(i["ParentName"]) > 0:
            result.append(
                {
                    "name": f'{i["ParentName"]}/{i["Name"]}',
                    "confidence": i["Confidence"]
                }
            )
    return result, raw

def bedrock_image_caption(s3_bucket, s3_key, caption_prompts, max_retries=3, retry_delay=1):
    retries = 0
    while retries < max_retries:
        try:
            # download
            file_name = s3_key.split('/')[-1]
            local_file_path = f'{LOCAL_PATH}{file_name}'
            s3.download_file(s3_bucket, s3_key, local_file_path)
            
            # Convert to Base64
            image_base64 = None
            with open(local_file_path, "rb") as image_file:
                image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        
            if image_base64 is not None:
                # Call Bedrock Anthropic Claude V3 Sonnet
                body = json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 1000,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": "image/jpeg",
                                            "data": image_base64
                                        }
                                    },
                                    {
                                        "type": "text",
                                        "text": caption_prompts
                                    }
                                ]
                            }
                        ]
                    })
                
                response = bedrock.invoke_model(
                    body=body, 
                    modelId="anthropic.claude-3-haiku-20240307-v1:0", 
                    accept="application/json", 
                    contentType="application/json",
                )
                
                return json.loads(response.get('body').read())["content"][0]["text"]

        except Exception as ex:
            print(ex)
            retries += 1
            time.sleep(retry_delay)

    return None

def get_subtitle_by_ts(task_id, ts, prev_ts):
    # Get transcription
    transcription = None
    trans = utils.dynamodb_trans_get_trans(DYNAMO_VIDEO_TRANS_TABLE, task_id, prev_ts, ts)
    if trans:
        transcription = ""
        for tran in trans:
            transcription += tran["transcription"] + '; '
    return trans, transcription
