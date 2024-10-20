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
    task_id = event.get("TaskId")
    page_size = event.get("PageSize", 20)
    from_index = event.get("FromIndex", 0)

    if task_id is None:
        return {
            'statusCode': 400,
            'body': 'TaskId required.'
        }

    result = {"Frames":[], "Total": utils.count_items_by_task_id(DYNAMO_VIDEO_FRAME_TABLE, task_id)}
    frames = utils.get_paginated_items(table_name=DYNAMO_VIDEO_FRAME_TABLE, task_id=task_id, start_index=from_index, page_size=page_size)
    for f in frames:
        try:
            frame = {
                "S3Url": s3.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': f["s3_bucket"], 'Key': f["s3_key"]},
                            ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
                        ),
                "Timestamp": f["timestamp"],
            }
            if "image_caption" in f and f["image_caption"] and len(f["image_caption"]) > 0:
                frame["ImageCaption"] = f["image_caption"]
            if "detect_label" in f and f["detect_label"] and len(f["detect_label"]) > 0:
                txt = ""
                for l in f["detect_label"]:
                    if len(txt) > 0:
                        txt += ", "
                    txt += f"{l['name']} ({round(l['confidence'],1)}%)"
                frame["Label"] = txt
            if "detect_moderation" in f and f["detect_moderation"] and len(f["detect_moderation"]) > 0:
                txt = ""
                for l in f["detect_moderation"]:
                    if len(txt) > 0:
                        txt += ", "
                    txt += f"{l['name']} ({round(l['confidence'],1)}%)"
                frame["Moderation"] = txt
            if "detect_text" in f and f["detect_text"] and len(f["detect_text"]) > 0:
                txt = ""
                for l in f["detect_text"]:
                    if len(txt) > 0:
                        txt += ", "
                    txt += f"{l['name']} ({round(l['confidence'],1)}%)"
                frame["Text"] = txt
            if "detect_celebrity" in f and f["detect_celebrity"] and len(f["detect_celebrity"]) > 0:
                txt = ""
                for l in f["detect_celebrity"]:
                    if len(txt) > 0:
                        txt += ", "
                    txt += f"{l['name']} ({round(l['confidence'],1)}%)"
                frame["Celebrity"] = txt
            if "subtitles" in f and f["subtitles"] and len(f["subtitles"]) > 0:
                txt = ""
                for l in f["subtitles"]:
                    txt += f"[{l['start_ts']} - {l['end_ts']}] {l['transcription']}"
                frame["Subtitle"] = txt

            frame["PrevTs"] = f.get("prev_timestamp")
            frame["SimilarityScore"] = f.get("similarity_score")

            result["Frames"].append(frame)
        except Exception as ex:
            print(ex)
    return {
        'statusCode': 200,
        'body': result
    }
