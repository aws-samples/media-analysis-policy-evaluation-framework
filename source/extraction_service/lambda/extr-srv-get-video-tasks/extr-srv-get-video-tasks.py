'''
"Source": mm_embedding | text_embedding | text,
'''
import json
import boto3
import os
import utils
import re
from urllib.parse import urlparse

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
DYNAMO_VIDEO_TRANS_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")

S3_PRESIGNED_URL_EXPIRY_S = os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", 3600) # Default 1 hour 

s3 = boto3.client('s3')

def lambda_handler(event, context):
    search_text = event.get("SearchText", "")
    page_size = event.get("PageSize", 10)
    from_index = event.get("FromIndex", 0)
    request_by = event.get("RequestBy")
    source = event.get("Source")
    
    if search_text is None:
        search_text = ""
    if len(search_text) > 0:
        search_text = search_text.strip()

    tasks = utils.query_task_with_pagination(DYNAMO_VIDEO_TASK_TABLE, request_by=request_by, keyword=search_text, start_index=from_index, page_size=page_size)
    result = []
    if tasks:
        for task in tasks:
            r = {
                    "TaskId": task["Id"],
                    "FileName": task["Request"]["FileName"],
                    "RequestTs": task["RequestTs"],
                    "Status": task["Status"],
                }
            if "MetaData" in task and "VideoMetaData" in task["MetaData"] and "ThumbnailS3Bucket" in task["MetaData"]["VideoMetaData"]:
                r["ThumbnailUrl"] = s3.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': task["MetaData"]["VideoMetaData"]["ThumbnailS3Bucket"], 'Key': task["MetaData"]["VideoMetaData"]["ThumbnailS3Key"]},
                        ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
                    )
            result.append(r)

    return {
        'statusCode': 200,
        'body': result
    }
