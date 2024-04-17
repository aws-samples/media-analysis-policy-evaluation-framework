import json
import boto3
import os
from opensearchpy import OpenSearch
import base64
from io import BytesIO
import re

OPENSEARCH_INDEX_NAME_VIDEO_TASK = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TASK")
OPENSEARCH_INDEX_NAME_VIDEO_TRANS = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TRANS")
OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME = os.environ.get("OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")

REK_MIN_CONF_DETECT_LABEL = float(os.environ.get("REK_MIN_CONF_DETECT_LABEL"))
REK_MIN_CONF_DETECT_MODERATION = float(os.environ.get("REK_MIN_CONF_DETECT_MODERATION"))
REK_MIN_CONF_DETECT_TEXT = float(os.environ.get("REK_MIN_CONF_DETECT_TEXT"))
REK_MIN_CONF_DETECT_CELEBRITY = float(os.environ.get("REK_MIN_CONF_DETECT_CELEBRITY"))

LOCAL_PATH = '/tmp/'

opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )

s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')
bedrock = boto3.client('bedrock-runtime') 

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

    if task_id is None or setting is None or s3_bucket is None or s3_key is None or not s3_key.endswith('.jpg'):
        return {
            "Error": "Invalid Request"
        }

    frame_index_name = OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME + task_id
    frame_id = s3_key.split('/')[-1].replace('.jpg','')
    ts = float(frame_id.split("_")[-1])
    input_mm_text = file_name + "; "

    frame = {}
    if setting.get("DetectLabel") == True:
        labels, categories, raw = rekognition_detect_label(s3_bucket, s3_key)
        frame["detect_label"] = labels
        frame["detect_label_category"] = categories
        s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/rekognition_detect_label/detect_label_{ts}.json', Body=json.dumps(raw))

        if len(labels) > 0:
            input_mm_text += 'labels: ' + ','.join(labels) + '; '
        
    if setting.get("DetectText") == True:
        texts, raw = rekognition_detect_text(s3_bucket, s3_key)
        frame["detect_text"] = texts
        s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/rekognition_detect_text/detect_text_{ts}.json', Body=json.dumps(raw))

        if len(texts) > 0:
            input_mm_text += 'texts: ' + ','.join(texts) + '; '

    if setting.get("DetectCelebrity") == True:
        celes, raw = rekognition_detect_celebrity(s3_bucket, s3_key)
        frame["detect_celebrity"] = celes
        s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/rekognition_detect_celebrity/detect_celebrity_{ts}.json', Body=json.dumps(raw))
        
        if len(celes) > 0:
            input_mm_text += 'celebrities: ' + ','.join(celes) + '; '
            
    if setting.get("DetectModeration") == True:
        mods, raw = rekognition_detect_moderation(s3_bucket, s3_key)
        frame["detect_moderation"] = mods
        s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/rekognition_detect_moderation/detect_moderation_{ts}.json', Body=json.dumps(raw))
        
        if len(mods) > 0:
            input_mm_text += 'moderation labels: ' + ','.join(mods) + '; '

    if setting.get("DetectLogo") == True:
        logos = bedrock_logo_detection(s3_bucket, s3_key)
        frame["detect_logo"] = logos

        if logos and len(logos) > 0:
            input_mm_text += 'Logos: ' + ','.join(logos) + '; '
    
    # Update database: video_frame_[]
    opensearch_client.update(index=frame_index_name, id=frame_id, body={"doc": frame})

    return event

def rekognition_detect_label(s3_bucket, s3_key):
    response = rekognition.detect_labels(
            Image={
                "S3Object": {
                    "Bucket": s3_bucket,
                    "Name": s3_key
                }
            },
            MinConfidence=REK_MIN_CONF_DETECT_LABEL,
            MaxLabels=10
        )
    labels, categories = [], []
    raw = response["Labels"]
    for i in raw:
        labels.append(i["Name"].replace(' ','_'))
        for c in i["Categories"]:
            cat = c["Name"].replace(' ','_')
            if cat not in categories:
                categories.append(cat)
    return labels, categories, raw

def rekognition_detect_text(s3_bucket, s3_key):
    response = rekognition.detect_text(
            Image={
                "S3Object": {
                    "Bucket": s3_bucket,
                    "Name": s3_key
                }
            },
            Filters={
                "WordFilter": {
                    "MinConfidence": REK_MIN_CONF_DETECT_TEXT,
                }
            }
        )
    result = []
    raw = response["TextDetections"]
    for i in raw:
        if i["Type"] == "LINE":
            result.append(i["DetectedText"].replace(' ','_'))
    return result, raw

def rekognition_detect_celebrity(s3_bucket, s3_key):
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
        if i["MatchConfidence"] >= REK_MIN_CONF_DETECT_CELEBRITY:
            result.append(i["Name"].replace(' ','_'))
    return result, response

def rekognition_detect_moderation(s3_bucket, s3_key):
    response = rekognition.detect_moderation_labels(
            Image={
                "S3Object": {
                    "Bucket": s3_bucket,
                    "Name": s3_key
                }
            },
            MinConfidence=REK_MIN_CONF_DETECT_MODERATION,
        )
    result = []
    raw = response["ModerationLabels"]
    for i in raw:
        if len(i["ParentName"]) > 0:
            result.append(f'{i["ParentName"]}/{i["Name"]}'.replace(' ','_'))
    return result, raw

def bedrock_logo_detection(s3_bucket, s3_key):
    # Place holder for logo detection
    return None

def parse_value(text, tag_name):
    pattern = fr'<{tag_name}>(.*?)<\/{tag_name}>'
    match = re.search(pattern, text)
    # Check if a match is found
    if match:
        # Extract the values from the first capturing group and split them by commas
        return  match.group(1).strip()
        if len(value) == 0:
            return None
    return None