import json
import boto3
import uuid
from opensearchpy import OpenSearch
import os
from datetime import datetime, timezone

TRANSCRIBE_JOB_PREFIX = os.environ.get("TRANSCRIBE_JOB_PREFIX")
TRANSCRIBE_OUTPUT_BUCKET = os.environ.get('TRANSCRIBE_OUTPUT_BUCKET')
TRANSCRIBE_OUTPUT_PREFIX = os.environ.get('TRANSCRIBE_OUTPUT_PREFIX')
OPENSEARCH_INDEX_NAME_VIDEO_TASK = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TASK")
OPENSEARCH_INDEX_NAME_VIDEO_TASK_MAPPING = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TASK_MAPPING")
OPENSEARCH_INDEX_NAME_VIDEO_TRANS = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TRANS")
OPENSEARCH_INDEX_NAME_VIDEO_TRANS_MAPPING = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TRANS_MAPPING")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")

STEP_FUNCTIONS_STATE_MACHINE_ARN = os.environ.get("STEP_FUNCTIONS_STATE_MACHINE_ARN")
DEFAULT_K = os.environ["OPENSEARCH_DEFAULT_K"]
current_region = os.environ['AWS_REGION']

transcribe = boto3.client('transcribe')
stepfunctions = boto3.client('stepfunctions')

opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )
def lambda_handler(event, context):
    if event is None \
            or "Video" not in event \
            or "S3Object" not in event["Video"] \
            or "PreProcessSetting" not in event \
            or "ExtractionSetting" not in event \
            or "EvaluationSetting" not in event:
        return {
            'statusCode': 200,
            'body': 'Invalid request'
        }
    
    # Get task Id. Create a new one if not provided.
    task_id = event.get("TaskId",str(uuid.uuid4()))
    
    # Create indices if not exist
    if not opensearch_client.indices.exists(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK):
        opensearch_client.indices.create(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK, body=OPENSEARCH_INDEX_NAME_VIDEO_TASK_MAPPING)
    if not opensearch_client.indices.exists(index=OPENSEARCH_INDEX_NAME_VIDEO_TRANS):
        opensearch_client.indices.create(index=OPENSEARCH_INDEX_NAME_VIDEO_TRANS, body=OPENSEARCH_INDEX_NAME_VIDEO_TRANS_MAPPING)

    transcribe_output_key = f'tasks/{task_id}/{TRANSCRIBE_OUTPUT_PREFIX}/{task_id}_transcribe.json'
    # Store to DB
    doc = {
        "Request": event,
        "Status": "start_transcription",
        "RequestTs": datetime.now(timezone.utc),
        "MetaData": {
            "TrasnscriptionOutput": None if event["ExtractionSetting"]["Transcription"] == False else f's3://{TRANSCRIBE_OUTPUT_BUCKET}/{transcribe_output_key}'
        }
    }
    response = opensearch_client.index(
            index = OPENSEARCH_INDEX_NAME_VIDEO_TASK,
            body = doc,
            id = task_id,
            refresh = True
        )

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
    else:
        # Start stepfunction workflow if no transcription required
        stepfunctions.start_execution(
            stateMachineArn=STEP_FUNCTIONS_STATE_MACHINE_ARN,
            input=json.dumps(event)
        )
        
    return {
        'statusCode': 200,
        'body': {
            "TaskId": task_id
        }
    }
