import json
import boto3
import os
import utils
import re
from urllib.parse import urlparse

DYNAMO_EVAL_TASK_TABLE = os.environ.get("DYNAMO_EVAL_TASK_TABLE")

def lambda_handler(event, context):
    video_task_id = event.get("VideoTaskId", "")
    search_text = event.get("SearchText", "")
    page_size = event.get("PageSize", 10)
    from_index = event.get("FromIndex", 0)

    if search_text is None:
        search_text = ""
    if len(search_text) > 0:
        search_text = search_text.strip()

    tasks, total = utils.query_task_with_pagination(DYNAMO_EVAL_TASK_TABLE, video_task_id=video_task_id, keyword=search_text, start_index=from_index, page_size=page_size)
    tasks = sorted(tasks, key=lambda x: x['RequestTs'], reverse=True)

    return {
        'statusCode': 200,
        'body': {
            "Tasks": tasks,
            "Total": total
        }
    }
