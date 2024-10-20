import json
import boto3
import uuid
import utils
import os
from datetime import datetime, timezone

DYNAMO_EVAL_TASK_TABLE = os.environ.get("DYNAMO_EVAL_TASK_TABLE")
SQS_URL = os.environ.get("SQS_URL")

sqs = boto3.client('sqs')

def lambda_handler(event, context):
    if event is None or "VideoTaskId" not in event:
        return {
            'statusCode': 200,
            'body': 'Invalid request'
        }

    if "Id" not in event or event["Id"] is None or len(event["Id"]) == 0:
        event["Id"] = str(uuid.uuid4())
    
    # Save to DB
    event["Status"] = "enqueuing"
    event["RequestTs"] = datetime.now(timezone.utc).isoformat()
    response = utils.dynamodb_table_upsert(DYNAMO_EVAL_TASK_TABLE, event)

    # Send to queue
    response = sqs.send_message(QueueUrl=SQS_URL, MessageBody=json.dumps({"task_id": event["Id"]}))
    
    return {
            'statusCode': 200,
            'body': 'Enqueue'
        }