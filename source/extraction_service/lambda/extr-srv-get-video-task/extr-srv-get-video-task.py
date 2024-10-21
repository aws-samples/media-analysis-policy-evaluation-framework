import json
import boto3
import os
import utils
from datetime import datetime

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
DYNAMO_VIDEO_TRANS_TABLE = os.environ.get("DYNAMO_VIDEO_TRANS_TABLE")
DYNAMO_VIDEO_ANALYSIS_TABLE = os.environ.get("DYNAMO_VIDEO_ANALYSIS_TABLE")

S3_PRESIGNED_URL_EXPIRY_S = os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", 3600) # Default 1 hour 
s3 = boto3.client("s3")
dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    task_id = event.get("TaskId")    
    if task_id is None:
        return {
            'statusCode': 400,
            'body': 'Invalid request. Missing TaskId.'
        }
    
    # Supported values: 
    # ["Request","VideoMetaData",
    #   "Transcription","DetectLabel","DetectLabelCategory","DetectText","DetectCelebrity","DetectModeration","DetectLogo","ImageCaption",
    #   "DetectLabelAgg","DetectLabelCategoryAgg","DetectTextAgg","DetectCelebrityAgg","DetectModerationAgg","DetectLogoAgg"
    # ]
    data_types = event.get("DataTypes", ["Request","VideoMetaData","Subtitle","DetectLabelCategoryAgg","DetectTextAgg","DetectCelebrityAgg","DetectModerationAgg"]) 
    page_size = event.get("PageSize", 500)
    from_index = event.get("FromIndex", 0)

    # get from video_task DB table
    db_task = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, task_id)
    if db_task is None:
        return {
            'statusCode': 400,
            'body': f'Invalid request. Task does not exist: {task_id}.'
        }
    
    task = {}
    if "Request" in data_types and "VideoMetaData" in data_types:
        # Get Video pre-signed S3 URL
        s3_bucket = db_task["Request"]["Video"]["S3Object"]["Bucket"]
        s3_key = db_task["Request"]["Video"]["S3Object"]["Key"]
        task["Request"] = db_task["Request"]
        task["VideoUrl"] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': s3_bucket, 'Key': s3_key},
                ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
            )
        task["MetaData"] = db_task["MetaData"]
        try:
            task["MetaData"]["VideoMetaData"]["Fps"] = float(task["MetaData"]["VideoMetaData"]["Fps"])
            task["MetaData"]["VideoMetaData"]["Size"] = float(task["MetaData"]["VideoMetaData"]["Size"])
            task["MetaData"]["VideoMetaData"]["Duration"] = float(task["MetaData"]["VideoMetaData"]["Duration"])
            task["MetaData"]["VideoFrameS3"]["TotalFramesPlaned"] = float(task["MetaData"]["VideoFrameS3"]["TotalFramesPlaned"])
            task["MetaData"]["VideoFrameS3"]["TotalFramesSampled"] = float(task["MetaData"]["VideoFrameS3"]["TotalFramesSampled"])
            task["RequestTs"] = db_task["RequestTs"]
    
        except Exception as ex:
            print(ex)
    
    # Get Transcription and Subtitles
    if "Transcription" in data_types:
        task["Transcription"] = utils.dynamodb_get_by_id(table_name=DYNAMO_VIDEO_TRANS_TABLE, id=task_id, key_name="task_id")

    # Get aggregated items
    if "DetectLabelAgg" in data_types and "AggResult" in db_task:
        task["DetectLabelAgg"] = get_agg_items(db_task["AggResult"].get("DetectLabelAgg"))
    if "DetectLabelCategoryAgg" in data_types and "AggResult" in db_task:
        task["DetectLabelCategoryAgg"] = get_agg_items(db_task["AggResult"].get("DetectLabelCategoryAgg"))
    if "DetectCelebrityAgg" in data_types and "AggResult" in db_task:
        task["DetectCelebrityAgg"] = get_agg_items(db_task["AggResult"].get("DetectCelebrityAgg"))
    if "DetectTextAgg" in data_types and "AggResult" in db_task:
        task["DetectTextAgg"] = get_agg_items(db_task["AggResult"].get("DetectTextAgg"))
    if "DetectModerationAgg" in data_types and "AggResult" in db_task:
        task["DetectModerationAgg"] = get_agg_items(db_task["AggResult"].get("DetectModerationAgg"))
    if "DetectLogoAgg" in data_types:
        task["DetectLogoAgg"] = []
    
    # Get items
    frames = None
    if "ImageCaption" in data_types:
        task["ImageCaption"] = get_items(task_id, "image_caption", from_index, page_size)
    if "DetectLabel" in data_types:
        task["DetectLabel"] = get_items(task_id, "detect_label", from_index, page_size)
    if "DetectLabelCategory" in data_types:
        task["DetectLabelCategory"] = get_items(task_id, "detect_label_category", from_index, page_size)
    if "DetectCelebrity" in data_types:
        task["DetectCelebrity"] = get_items(task_id, "detect_celebrity", from_index, page_size)
    if "DetectText" in data_types:
        task["DetectText"] = get_items(task_id, "detect_text", from_index, page_size)
    if "DetectModeration" in data_types:
        task["DetectModeration"] = get_items(task_id, "detect_moderation", from_index, page_size)
    if "DetectLogo" in data_types:
        task["DetectLogo"] = get_items(task_id, "detect_logo", from_index, page_size)
    if "DetectShot" in data_types:
        task["DetectShot"] = get_shots(task_id, from_index, page_size)

    return {
        'statusCode': 200,
        'body': task
    }

def get_agg_items(items):
    for item in items:
        tss = []
        for ts in item["timestamps"]:
            tss.append(float(ts))
        item["timestamps"] = tss
    return items
    
FRAMES = None
def get_items(task_id, field_name, from_index, page_size):
    global FRAMES
    if FRAMES is None:
        FRAMES = utils.get_paginated_items(table_name=DYNAMO_VIDEO_FRAME_TABLE, task_id=task_id, start_index=from_index, page_size=page_size)

        print("!!!!",len(FRAMES))
        
    total = utils.count_items_by_task_id(DYNAMO_VIDEO_FRAME_TABLE, task_id)
    result = []
    for f in FRAMES:
        ts = float(f["timestamp"])
        print(ts)
        if field_name == "detect_label_category":
            items = f.get("detect_label")
            if items:
                for item in items:
                    if "categories" in item:
                        for c in item["categories"]:
                            result.append({
                                "value": c,
                                "timestamp": ts
                            })
        elif field_name == "image_caption":
            item = f.get(field_name)
            if item:
                result.append({
                        "value": item,
                        "timestamp": ts
                    })
        else:
            items = f.get(field_name)
            if items:
                for item in items:
                    result.append({
                            "value": item["name"],
                            "timestamp": ts
                        })
    
    # Sort result
    result.sort(key=lambda x: x['timestamp'], reverse=False)

    return {
        "Total": total,
        "Items": result
    }

def get_shots(task_id, from_index, page_size):
    video_analysis_table = dynamodb.Table(DYNAMO_VIDEO_ANALYSIS_TABLE)  
    items = []
    try:
        last_evaluated_key = None
        # Keep querying until there are no more pages of results
        while True:
            query_params = {
                'IndexName': 'task_id-analysis_type-index',  # Name of your index
                'KeyConditionExpression': 'task_id = :task_id_val AND analysis_type = :type_val',
                'ExpressionAttributeValues': {
                    ':task_id_val': task_id,
                    ':type_val': 'shot'
                }
            }
            if last_evaluated_key:
                query_params['ExclusiveStartKey'] = last_evaluated_key

            response = video_analysis_table.query(**query_params)
            for s in response.get('Items', []):
                i = {
                    "summary": s.get("summary"),
                    "start_ts": s.get("start_ts"),
                    "end_ts": s.get("end_ts"),
                    "transcripts": []
                }
                for f in s.get("frames",[]):
                    if f and f.get("subtitles"):
                        for sub in f.get("subtitles",[]):
                            if sub not in i["transcripts"]:
                                if sub.get("transcription"):
                                    if len(i["transcripts"]) > 0 and i["transcripts"][-1] == sub["transcription"]:
                                        continue
                                    i["transcripts"].append(sub["transcription"])
                items.append(i)
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
    except Exception as ex:
        print(ex)
        return {
            'statusCode': 400,
            'body': f'Task {task_id} does not exist.'
        }

    items = sorted(items, key=lambda x: x['start_ts'], reverse=False)
    end_index = from_index + page_size
    if end_index > len(items):
        end_index = len(items)
    return items[from_index: end_index]