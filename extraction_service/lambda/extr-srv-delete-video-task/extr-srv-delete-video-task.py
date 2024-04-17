'''
Delete video task
1. Delete S3 folder: frames, extraction raw files
2. Delete Transcribe job
3. Delete from OpenSearch: video_task, video_transcription, video_frame_[task_id]
'''
import json
import boto3
import os
from opensearchpy import OpenSearch

OPENSEARCH_INDEX_NAME_VIDEO_TASK = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TASK")
OPENSEARCH_INDEX_NAME_VIDEO_TRANS = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TRANS")
OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME = os.environ.get("OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")
VIDEO_SAMPLE_S3_BUCKET = os.environ.get("VIDEO_SAMPLE_S3_BUCKET")
VIDEO_SAMPLE_S3_PREFIX = os.environ.get("VIDEO_SAMPLE_S3_PREFIX")
VIDEO_SAMPLE_FILE_PREFIX = os.environ.get("VIDEO_SAMPLE_FILE_PREFIX")
TRANSCRIBE_JOB_PREFIX = os.environ.get("TRANSCRIBE_JOB_PREFIX")
opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )
s3 = boto3.client('s3')
transcribe = boto3.client('transcribe')

def lambda_handler(event, context):
    task_id = event.get("TaskId")
    if task_id is None:
        return {
            'statusCode': 400,
            'body': json.dumps('Require TaskId')
        }
    
    # Get video task from DB
    task = None
    try:
        response = opensearch_client.get(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK, id=task_id)
        task = response.get("_source")
    except Exception as ex:
        print(f'Task does not exist in {OPENSEARCH_INDEX_NAME_VIDEO_TASK}: {task_id}')
    
    s3_bucket, s3_prefix = None, None
    try:
        s3_bucket = task["MetaData"]["VideoFrameS3"]["S3Bucket"]
        #s3_prefix = task["MetaData"]["VideoFrameS3"]["S3Prefix"]
    except:
        print("S3 folder doesn't exist.")

    # Delete S3 folder
    if s3_bucket:
        try:
            delete_s3_folder(s3_bucket, f"tasks/{task_id}")
        except:
            print("Failed to delete the S3 folder")
    
    # Delete Transcribe Job
    try:
        transcribe.delete_transcription_job(TranscriptionJobName=TRANSCRIBE_JOB_PREFIX + task_id[0:5])
    except Exception as ex:
        print('Failed to delete the Transcribe transcription job.', ex)
    
    # Delete DB entries
    # Delete video_frame_[task_id] table
    try:
        response = opensearch_client.indices.delete(index=OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME+task_id)
        if 'acknowledged' not in response or not response["acknowledged"]:
            print(f"Failed to delete index: {OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME+task_id}")
    except Exception as ex:
        print(f"Failed to delete index: {OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME+task_id}", ex)
    
    # Delete video_transcription entry
    try:
        response = opensearch_client.delete(index=OPENSEARCH_INDEX_NAME_VIDEO_TRANS, id=task_id)
        if 'result' not in response or response['result'] != 'deleted':
            print(f'Failed to delete task {task_id} from index: {OPENSEARCH_INDEX_NAME_VIDEO_TRANS}')
    except Exception as ex:
        print(f'Failed to delete task {task_id} from index: {OPENSEARCH_INDEX_NAME_VIDEO_TRANS}', ex)

    # Delete video_task entry
    try:
        response = opensearch_client.delete(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK, id=task_id)
        if 'result' not in response or response['result'] != 'deleted':
            print(f'Failed to delete task {task_id} from index: {OPENSEARCH_INDEX_NAME_VIDEO_TASK}')
    except Exception as ex:
        print(f'Failed to delete task {task_id} from index: {OPENSEARCH_INDEX_NAME_VIDEO_TASK}', ex)
    
    return {
        'statusCode': 200,
        'body': f'Video task deleted. {task_id}'
    }

def delete_s3_folder(s3_bucket, s3_prefix):
    # List objects in the folder
    objects_to_delete = []
    paginator = s3.get_paginator('list_objects_v2')
    for result in paginator.paginate(Bucket=s3_bucket, Prefix=s3_prefix):
        if 'Contents' in result:
            for obj in result['Contents']:
                objects_to_delete.append({'Key': obj['Key']})
    
    # Delete objects in batches of 1000 (maximum allowed)
    delete_responses = []
    for i in range(0, len(objects_to_delete), 1000):
        delete_batch = {'Objects': objects_to_delete[i:i+1000]}
        delete_response = s3.delete_objects(Bucket=s3_bucket, Delete=delete_batch)
        delete_responses.append(delete_response)
    
    return delete_responses
    # List objects in the folder
    objects_to_delete = []
    paginator = s3.get_paginator('list_objects_v2')
    for result in paginator.paginate(Bucket=s3_bucket, Prefix=s3_prefix):
        if 'Contents' in result:
            for obj in result['Contents']:
                objects_to_delete.append({'Key': obj['Key']})
    
    # Delete objects in batches of 1000 (maximum allowed)
    delete_responses = []
    for i in range(0, len(objects_to_delete), 1000):
        delete_batch = {'Objects': objects_to_delete[i:i+1000]}
        delete_response = s3.delete_objects(Bucket=s3_bucket, Delete=delete_batch)
        delete_responses.append(delete_response)
    
    return delete_responses