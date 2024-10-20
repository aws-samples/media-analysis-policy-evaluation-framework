import json
import boto3
import os
from opensearchpy import OpenSearch
import utils
import base64
from botocore.exceptions import ClientError

OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")
OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_TEMP_PREFIX = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_TEMP_PREFIX")
OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD = float(os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD"))
OPENSEARCH_VIDEO_FRAME_SIMILAIRTY_INDEX_MAPPING = os.environ.get("OPENSEARCH_VIDEO_FRAME_SIMILAIRTY_INDEX_MAPPING")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", os.environ.get('AWS_REGION'))
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")


s3 = boto3.client('s3')

opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )
bedrock = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION) 

def lambda_handler(event, context):
    task_id, start_ts, end_ts = None, None, None
    try:
        task_id = event["task_id"]
        start_ts = float(event["start_ts"])
        end_ts = float(event["end_ts"])
    except Exception as ex:
        print(ex)
        return 'Invalid request'

    task = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, task_id)
    if task is None:
        return 'Invalid request'

    enable_smart_sampling = False
    try:
        enable_smart_sampling = task["Request"]["PreProcessSetting"]["SmartSample"] == True
    except Exception as ex:
        print(ex)
    
    if not enable_smart_sampling:
        return event

    similarity_threshold = OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD
    if "SimilarityThreshold" in task["Request"]["PreProcessSetting"]:
        try:
            similarity_threshold = float(task["Request"]["PreProcessSetting"]["SimilarityThreshold"])
        except Exception as ex:
            print(ex)

            
    # Create similiarity check index
    opensearch_temp_index_name = f'{OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_TEMP_PREFIX}{task_id[0:5]}_{start_ts}_{end_ts}'
    print("opensearch_temp_index_name: ",opensearch_temp_index_name)
    if not opensearch_client.indices.exists(index=opensearch_temp_index_name):
        opensearch_client.indices.create(index=opensearch_temp_index_name, body=OPENSEARCH_VIDEO_FRAME_SIMILAIRTY_INDEX_MAPPING)

    # Read image frames from S3
    s3_bucket = task["MetaData"]["VideoFrameS3"]["S3Bucket"]
    s3_prefix = task["MetaData"]["VideoFrameS3"]["S3Prefix"]
    total_frames = task["MetaData"]["VideoFrameS3"]["TotalFramesPlaned"]
    paginator = s3.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(Bucket=s3_bucket, Prefix=s3_prefix)

    prev_ts, prev_vector, total_sampled = start_ts, None, 0
    for page in page_iterator:
        if 'Contents' in page:
            for obj in page['Contents']:
                try:
                    obj_key = obj['Key']
                    # validate format
                    if obj_key.split('.')[-1].lower() not in ["jpg","jpeg","png"]:
                        continue
                    
                    cur_ts = float(obj_key.replace(".jpg","").split('_')[-1])
                    if cur_ts <= start_ts or cur_ts > end_ts:
                        continue

                    # Get image base64 str
                    response = s3.get_object(Bucket=s3_bucket, Key=obj_key)
                    image_data = response['Body'].read()
                    base64_encoded_image = base64.b64encode(image_data).decode('utf-8')

                    if base64_encoded_image:
                        # similarity check: compare with previous image
                        cur_vector = get_mm_vector(base64_encoded_image)
                        score = similarity_check(task_id, prev_ts, prev_vector, cur_ts, cur_vector, opensearch_temp_index_name)
                        if score is not None and score > OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD:
                            # Delete image on S3
                            s3.delete_object(Bucket=s3_bucket, Key=obj_key)

                            # Delete from DB video_frame table
                            frame_id = f'{task_id}_{cur_ts}'
                            response = utils.dynamodb_delete_by_id(DYNAMO_VIDEO_FRAME_TABLE, frame_id, task_id)

                        else:
                            # set current image as prev
                            prev_vector = cur_vector
                            prev_ts = cur_ts

                            total_sampled += 1
                            
                            # update frame in db: include similarity score
                            if score:
                                response = utils.update_item_with_similarity_score(DYNAMO_VIDEO_FRAME_TABLE, f'{task_id}_{cur_ts}', task_id, score)

                except Exception as e:
                    print(e)

    # update video_task table
    try:
        # Get task from DB
        task_db = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, task_id)
        sampled = float(task_db["MetaData"]["VideoFrameS3"]["TotalFramesSampled"])
        task_db["MetaData"]["VideoFrameS3"]["TotalFramesSampled"] = sampled + float(total_sampled)
        # Update DB
        utils.dynamodb_table_upsert(DYNAMO_VIDEO_TASK_TABLE, task_db)
    except Exception as ex:
        print(ex)
                
    # Delete temp index
    try:
        opensearch_client.indices.delete(index=opensearch_temp_index_name)
    except Exception as ex:
        print(ex)
    return event

        
def similarity_check(task_id, pre_ts, pre_vector, cur_ts, cur_vector, opensearch_temp_index_name, input_text=None):
    if pre_vector is None or cur_vector is None:
        return False

    prev_doc_id = f'{task_id}_{pre_ts}'

    # Store previous vector to DB
    opensearch_client.index(index=opensearch_temp_index_name, id=prev_doc_id, body={"mm_embedding": pre_vector}, refresh=True)

    # Apply similiarity search
    query = {
          "_source": False,
          "query": {
            "bool": {
              "must": [
                {
                  "terms": {
                    "_id": [prev_doc_id]
                  }
                },
                {
                  "knn": {
                    "mm_embedding": {
                      "vector": cur_vector,
                      "k": 10
                    }
                  }
                }
              ]
            }
          }
    }

    response = opensearch_client.search(
                index=opensearch_temp_index_name,
                body=query
            )    
    score = None
    if len(response["hits"]["hits"]) > 0:
        score = response["hits"]["hits"][0]["_score"]
    return score

def get_mm_vector(base64_encoded_image, input_text=None):
    request_body = {}
    
    if input_text:
        request_body["inputText"] = input_text
        
    if base64_encoded_image:
        request_body["inputImage"] = base64_encoded_image
    
    body = json.dumps(request_body)
    
    embedding = None
    try:
        response = bedrock.invoke_model(
            body=body, 
            modelId="amazon.titan-embed-image-v1", 
            accept="application/json", 
            contentType="application/json"
        )
        
        response_body = json.loads(response.get('body').read())
        embedding = response_body.get("embedding")
    except Exception as ex:
        print(ex)

    return embedding