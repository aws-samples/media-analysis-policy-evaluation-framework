'''
Invoked by SQS
1. Get latest task from DB
2. Stop if task already started or completed extraction
3. Check #s of concurrent Step Function State Machine executions
3.1 If less then limit: invoke step function, delete message, update DB status to "processing"
3.2 If not: extend the message visibility time and leave it in the queue
'''
import json
import boto3
import os
import re
import utils

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")

STEP_FUNCTIONS_STATE_MACHINE_ARN = os.environ.get("STEP_FUNCTIONS_STATE_MACHINE_ARN")
STEP_FUNCTIONS_STATE_MACHINE_CONCURRENT_LIMIT = int(os.environ.get("STEP_FUNCTIONS_STATE_MACHINE_CONCURRENT_LIMIT"))
SQS_URL = os.environ.get("SQS_URL")

sqs = boto3.client('sqs')
stepfunctions = boto3.client('stepfunctions')

def lambda_handler(event, context):
    task, task_id, receipt_handle=None, None, None
    try:
        receipt_handle = event["Records"][0]["receiptHandle"]
        task_id = json.loads(event["Records"][0]["body"])["Request"]["TaskId"]
    except Exception as ex:
        print(ex)
        return {
            'statusCode': 400,
            'body': 'Invalid message'
        }
    
    # Get task from DB
    try:
        task = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, id=task_id)
    except Exception as ex:
        print('Doc does not exist',ex)
        
    # Check if status is already completed
    if task["Status"] in ["extraction_completed","evaluation_completed", "processing"]:
        # Delete the message and stop
        response = sqs.delete_message(QueueUrl=SQS_URL, ReceiptHandle=receipt_handle)
        print("Task status", response)
        return {
            'statusCode': 400,
            'body': 'Task already completed'
        }

    # Check Step Function State Machine concurrent executions
    concurrent_exes = 0
    try:
        response = stepfunctions.list_executions(
            stateMachineArn=STEP_FUNCTIONS_STATE_MACHINE_ARN,
            statusFilter='RUNNING',
            maxResults=100
        )
        concurrent_exes = len(response["executions"])
        print("Concurrency:", concurrent_exes)
    except Exception as ex:
        print(ex)
        return {
            'statusCode': 500,
            'body': 'Failed to get concurrent step function state machine executions'
        }

    if concurrent_exes < STEP_FUNCTIONS_STATE_MACHINE_CONCURRENT_LIMIT:
        # Start stepfunction workflow if no transcription required
        stepfunctions.start_execution(
            stateMachineArn=STEP_FUNCTIONS_STATE_MACHINE_ARN,
            input=json.dumps(task)
        )
        
        # Update task status in DB
        task["Status"] = "processing"
        utils.dynamodb_table_upsert(DYNAMO_VIDEO_TASK_TABLE, document=task)
        print("Updated DB status:",task["Status"])

    else:
        # Throw an error so the message stays in the queue
        raise Exception("Fake error so the message stays in SQS")
    
    return {
        'statusCode': 200,
        'body': 'Started the extraction process.'
    }
