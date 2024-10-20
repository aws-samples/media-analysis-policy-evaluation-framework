import json
import boto3
import uuid
import utils
import os
from datetime import datetime, timezone

TRANSCRIBE_JOB_PREFIX = os.environ.get("TRANSCRIBE_JOB_PREFIX")
TRANSCRIBE_OUTPUT_BUCKET = os.environ.get('TRANSCRIBE_OUTPUT_BUCKET')
TRANSCRIBE_OUTPUT_PREFIX = os.environ.get('TRANSCRIBE_OUTPUT_PREFIX')
TRANSCRIBE_REGION = os.environ.get('TRANSCRIBE_REGION',os.environ['AWS_REGION'])

STEP_FUNCTIONS_STATE_MACHINE_ARN = os.environ.get("STEP_FUNCTIONS_STATE_MACHINE_ARN")
DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")

transcribe = boto3.client('transcribe')#, region_name=TRANSCRIBE_REGION)
stepfunctions = boto3.client('stepfunctions')

def lambda_handler(event, context):
    if event is None \
            or "Video" not in event \
            or "S3Object" not in event["Video"] \
            or "PreProcessSetting" not in event \
            or "ExtractionSetting" not in event:
        return {
            'statusCode': 200,
            'body': 'Invalid request'
        }
    
    # Get task Id. Create a new one if not provided.
    task_id = event.get("TaskId",str(uuid.uuid4()))
    
    transcribe_output_key = f'tasks/{task_id}/{TRANSCRIBE_OUTPUT_PREFIX}/{task_id}_transcribe.json'
    # Store to DB
    doc = {
        "Id": task_id,
        "Request": event,
        "RequestTs": datetime.now(timezone.utc).isoformat(),
        "RequestBy": event.get("RequestBy"),
        "MetaData": {
            "TrasnscriptionOutput": None if event["ExtractionSetting"]["Transcription"] == False else f's3://{TRANSCRIBE_OUTPUT_BUCKET}/{transcribe_output_key}'
        }
    }

    if event["ExtractionSetting"]["Transcription"]:
        transcribe.start_transcription_job(
                            TranscriptionJobName = TRANSCRIBE_JOB_PREFIX + task_id[0:5],
                            Media = { 'MediaFileUri': f's3://{event["Video"]["S3Object"]["Bucket"]}/{event["Video"]["S3Object"]["Key"]}'},
                            OutputBucketName = TRANSCRIBE_OUTPUT_BUCKET, 
                            OutputKey = transcribe_output_key,
                            IdentifyLanguage=True,
                            Subtitles = {
                                'Formats': ['vtt'],
                                'OutputStartIndex': 1 
                            }
                        ) 
        doc["Status"] = "start_transcription"
    else:
        # Start stepfunction workflow if no transcription required
        stepfunctions.start_execution(
            stateMachineArn=STEP_FUNCTIONS_STATE_MACHINE_ARN,
            input=json.dumps({"Request":event})
        )
        doc["Status"] = "enqueuing"

    # Update DB
    response = utils.dynamodb_table_upsert(DYNAMO_VIDEO_TASK_TABLE, doc)
        
    return {
        'statusCode': 200,
        'body': {
            "TaskId": task_id
        }
    }
