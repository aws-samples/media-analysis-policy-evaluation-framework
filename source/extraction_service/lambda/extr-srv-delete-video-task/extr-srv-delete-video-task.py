'''
Delete video task
1. Delete S3 folder: frames, extraction raw files
2. Delete Transcribe job
3. Delete from OpenSearch: video_task, video_transcription, video_frame_[task_id]
'''
import json
import boto3
import os
import utils

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
SQS_URL = os.environ.get("SQS_URL")

sqs = boto3.client('sqs')

def lambda_handler(event, context):
    task_id = event.get("TaskId")
    delete_s3 = event.get("DeleteS3", True)
    if task_id is None:
        return {
            'statusCode': 400,
            'body': json.dumps('Require TaskId')
        }
    
    # Get video task from DB
    task = None
    try:
        task = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, task_id)
    except Exception as ex:
        print(f'Task does not exist in {DYNAMO_VIDEO_TASK_TABLE}: {task_id}')

    # Enqueue
    response = sqs.send_message(QueueUrl=SQS_URL, MessageBody=json.dumps({
        "task_id": task_id,
        "delete_s3": delete_s3
    }))

    # Update task status
    task["Status"] = "deleting"
    utils.dynamodb_table_upsert(DYNAMO_VIDEO_TASK_TABLE, task)

    return {
        'statusCode': 200,
        'body': f'Deleting video task: {task_id}'
    }
