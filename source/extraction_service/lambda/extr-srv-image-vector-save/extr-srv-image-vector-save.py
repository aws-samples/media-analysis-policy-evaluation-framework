import json
import boto3
import os
from opensearchpy import OpenSearch
import base64
from io import BytesIO
import re
import time
from datetime import datetime
import utils
from opensearchpy import OpenSearch, helpers
from botocore.exceptions import ClientError

OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME = os.environ.get("OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")
OPENSEARCH_VIDEO_FRAME_INDEX_MAPPING = os.environ.get("OPENSEARCH_VIDEO_FRAME_INDEX_MAPPING")
OPENSEARCH_SHARD_SIZE_LIMIT = float(os.environ.get("OPENSEARCH_SHARD_SIZE_LIMIT",50 * 1024 * 1024)) # default 100M
DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")

opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )

def lambda_handler(event, context):
    if event is None or "Error" in event or "Request" not in event or "Key" not in event:
        return {
            "Error": "Invalid Request"
        }

    task_id = event["Request"].get("TaskId")
    setting = event["Request"].get("ExtractionSetting")
    s3_bucket = event["MetaData"]["VideoFrameS3"]["S3Bucket"]
    s3_prefix = event["MetaData"]["VideoFrameS3"]["S3Prefix"]
    s3_key = event.get("Key")
    file_name = event["Request"].get("FileName", "")
    frame = event.get("frame")
    
    if frame is None or task_id is None or setting is None or s3_bucket is None or s3_key is None or not s3_key.endswith('.jpg'):
        return {
            "Error": "Invalid Request"
        }

    enable_text_embedding, enable_mm_embedding = True, True
    if "EmbeddingSetting" in event["Request"]:
        enable_text_embedding = event["Request"]["EmbeddingSetting"]["Text"]
        enable_mm_embedding = event["Request"]["EmbeddingSetting"]["MultiModal"]
    if not enable_mm_embedding and not enable_text_embedding:
        return False
    
    opensearch_indices = []
    
    frame_index_name = get_index()
    if frame_index_name not in opensearch_indices:
        opensearch_indices.append(frame_index_name)
    
    frame_id = frame["id"]
    del frame["id"]
    frame["timestamp"] = float(frame_id.split('_')[-1])
    frame["image_s3_uri"] = f"s3://{event['MetaData']['VideoFrameS3']['S3Bucket']}/{event['Key']}"

    # Add frame to OpenSearch index    
    opensearch_client.index(
        index=frame_index_name,
        id=frame_id,
        body=frame
    )
    
    # Update task DB with opensearch index names
    task = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, task_id)
    if task:
        indices = []
        if "VectorMetaData" in task:
            indices = task["VectorMetaData"]["OpenSearch"]["IndexNames"]

        new_flag = False
        for idx in opensearch_indices:
            if idx not in indices:
                indices.append(idx)
                new_flag = True
        if new_flag:
            task["VectorMetaData"] = {
                "OpenSearch": {
                    "IndexNames": indices
                }
            }
            utils.dynamodb_table_upsert(DYNAMO_VIDEO_TASK_TABLE, task)
            print("Opensearch indices updated:", indices)
    
    return True

def get_index():
    current_date = datetime.utcnow().strftime('%Y_%m_%d')
    pattern = re.compile(rf"{OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME}{current_date}_(\d+)")

    # Get all index names
    index_names = opensearch_client.indices.get_alias("*").keys()
    matching_indices = [name for name in index_names if pattern.match(name)]

    latest_index, index_seq = None, 0
    if matching_indices:
        latest_index = max(matching_indices, key=lambda name: int(pattern.match(name).group(1)))
        # check shard size
        shard_size = 0
        shard_stats = opensearch_client.indices.stats(index=latest_index, metric='store')

        shards = shard_stats['indices'][latest_index].get('shards')
        if shards:
            for shard_id, shard_info in shards.items():
                for shard in shard_info:
                    shard_size = shard['store']['size_in_bytes']
        else:
            shard_size = shard_stats['indices'][latest_index]["primaries"]["store"]["size_in_bytes"]

        if shard_size >= OPENSEARCH_SHARD_SIZE_LIMIT: 
            # Exceed limit, create new one
            index_seq = int(latest_index.split("_")[-1]) + 1
            latest_index = None
    
    if latest_index is None or len(latest_index) == 0:
        latest_index = f"{OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME}{current_date}_{index_seq}"
        

    # create new index with current date's with index=0
    if not opensearch_client.indices.exists(index=latest_index):
        try:
            response = opensearch_client.indices.create(index=latest_index, body=OPENSEARCH_VIDEO_FRAME_INDEX_MAPPING)
        except Exception as ex:
            print(ex)

    return latest_index
