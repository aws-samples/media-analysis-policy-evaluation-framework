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
from opensearchpy import OpenSearch

TRANSCRIBE_JOB_PREFIX = os.environ.get("TRANSCRIBE_JOB_PREFIX")

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
DYNAMO_VIDEO_TRANS_TABLE = os.environ.get("DYNAMO_VIDEO_TRANS_TABLE")
DYNAMO_VIDEO_ANALYSIS_TABLE = os.environ.get("DYNAMO_VIDEO_ANALYSIS_TABLE")

OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")

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
    task, task_id, delete_s3, receipt_handle=None, None, True, None
    try:
        receipt_handle = event["Records"][0]["receiptHandle"]
        task_id = json.loads(event["Records"][0]["body"])["task_id"]
        delete_s3 = event.get("delete_s3", True)
    except Exception as ex:
        print(ex)
        return {
            'statusCode': 400,
            'body': 'Invalid message'
        }

    task = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, task_id)
    if task is None:
        print(f'Task does not exist in {DYNAMO_VIDEO_TASK_TABLE}: {task_id}')
    
    # Delete S3 task folder
    if delete_s3:
        s3_bucket, s3_prefix = None, None
        try:
            s3_bucket = task["MetaData"]["VideoFrameS3"]["S3Bucket"]
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
        job_name = TRANSCRIBE_JOB_PREFIX + task_id[0:5]
        transcribe.delete_transcription_job(TranscriptionJobName=job_name)
    except Exception as ex:
        print('Failed to delete the Transcribe transcription job.', ex)
    
    # Delete DB entries
    # Delete frames video_frame table
    try:
        utils.dynamodb_delete_frames_by_taskid(DYNAMO_VIDEO_FRAME_TABLE, task_id)
    except Exception as ex:
        print(f"Failed to delete video frame entries: {DYNAMO_VIDEO_FRAME_TABLE}", ex)

    # Delete video_analysis entries
    try:
        utils.dynamodb_delete_analysis_by_taskid(DYNAMO_VIDEO_ANALYSIS_TABLE, task_id)
    except Exception as ex:
        print(f"Failed to delete video analysis entries: {DYNAMO_VIDEO_ANALYSIS_TABLE}", ex)

    # Delete video_transcription entry
    try:
        utils.dynamodb_delete_trans_by_taskid(DYNAMO_VIDEO_TRANS_TABLE, task_id)
    except Exception as ex:
        print(f'Failed to delete task {task_id} from index: {DYNAMO_VIDEO_TRANS_TABLE}', ex)

    # Delete video_task entry
    try:
        utils.dynamodb_delete_task_by_id(DYNAMO_VIDEO_TASK_TABLE, task_id)
    except Exception as ex:
        print(f'Failed to delete task {task_id} from index: {DYNAMO_VIDEO_TASK_TABLE}', ex)
        
    # Delete Opensearch vector
    try:
        indices = task["VectorMetaData"]["OpenSearch"]["IndexNames"]
        if indices and len(indices) > 0:
            response = opensearch_client.delete_by_query(index=','.join(indices), 
                body={
                    "query": {
                        "match": {
                            "task_id": task_id
                        }
                    }
                })
            if 'acknowledged' not in response or not response["acknowledged"]:
                print(f"Failed to delete from index: {indices}, task_id:{task_id}")

    except Exception as ex:
        print(f'Failed to delete vectors {task_id} from Opensearch index', ex)
    
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