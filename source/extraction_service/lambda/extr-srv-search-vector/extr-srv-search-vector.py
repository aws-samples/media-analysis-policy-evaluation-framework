'''
"Source": mm_embedding | text_embedding | text,
'''
import json
import boto3
import os
from opensearchpy import OpenSearch
import re
from urllib.parse import urlparse
import utils

OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME = os.environ.get("OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")
OPENSEARCH_DEFAULT_K = os.environ.get("OPENSEARCH_DEFAULT_K", 10)
S3_PRESIGNED_URL_EXPIRY_S = os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", 3600) # Default 1 hour 

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
LAMBDA_FUNCTION_ARN_EMBEDDING = os.environ.get("LAMBDA_FUNCTION_ARN_EMBEDDING")
OPENSEARCH_SCORE_DEFAULT_THRESHOLD = 0.5

opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': 443}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )
s3 = boto3.client('s3')
lambda_client = boto3.client('lambda')

def lambda_handler(event, context):
    search_text = event.get("SearchText", "")
    page_size = event.get("PageSize", 10)
    from_index = event.get("FromIndex", 0)
    score_threshold = 0#event.get("ScoreThreshold", OPENSEARCH_SCORE_DEFAULT_THRESHOLD)
    request_by = event.get("RequestBy")
    image_bytes = event.get("ImageBytes", "")
    source = event.get("Source")
    
    if search_text is None:
        search_text = ""
    if image_bytes is None:
        image_bytes = ""
    if len(search_text) > 0:
        search_text = search_text.strip()
    
    # Get Tasks by RequestBy
    db_tasks = utils.get_tasks_by_requestby(
                table_name=DYNAMO_VIDEO_TASK_TABLE, 
                request_by=request_by
            )

    if db_tasks is None or len(db_tasks) == 0:
        return {
            'statusCode': 200,
            'body': []
        }

    tasks, result = [], []
    for task in db_tasks:
       tasks.append(format_task_result(task))
    
    if not search_text and not image_bytes:
        result = tasks
    else:
        # Search with keywords
        # Dedup opensearch indices store task frames, prepare task id list
        opensearch_indices, task_ids = [], []
        if db_tasks:
            for task in db_tasks:
                task_ids.append(task["Id"])
                try:
                    idxs = task["VectorMetaData"]["OpenSearch"]["IndexNames"]
                    if idxs and len(idxs) > 0:
                        for idx in idxs:
                            if idx not in opensearch_indices:
                                opensearch_indices.append(idx)
                except Exception as ex:
                    print(ex)

        if len(opensearch_indices) == 0:
            return {
                'statusCode': 200,
                'body': []
            }

        # With keyword/image: apply filter
        if source == "mm_embedding" and (len(search_text) > 0 or len(image_bytes) > 0):
            frame_result = search_mm_embedding(search_text, image_bytes, score_threshold, task_ids, opensearch_indices)
        elif source == "text_embedding" and len(search_text) > 0:
            frame_result = search_text_embedding(search_text, task_ids, score_threshold, opensearch_indices)
        elif source == "text" and len(search_text) > 0:
            frame_result = search_text_match(search_text, task_ids, score_threshold, opensearch_indices)

        if frame_result and len(frame_result) > 0:
            for task in tasks:
                frames = frame_result.get(task["TaskId"])
                if frames:
                    task["Frames"] = frames
                    result.append(task)

    # Sort result
    result = sorted(result, key=lambda x: x.get("RequestTs", ""), reverse=True)

    # Pagination
    from_index = from_index if from_index > 0 else 0
    end_index = from_index + page_size if from_index + page_size < len(result) else len(tasks)
    result = result[from_index: end_index]

    return {
        'statusCode': 200,
        'body': result
    }

def search_text_embedding(input_text, task_ids, score_threshold, opensearch_indices):
    # generate text embedding
    response = lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_ARN_EMBEDDING,  
        InvocationType='RequestResponse',
        Payload=json.dumps({
                "embedding_type": "txt",
                "text_input": input_text
            }
        )
    )
    response_payload = json.loads(response['Payload'].read())
    embedding = response_payload.get("body")
    if not embedding:
        return None
        
    # Search DB
    query = {
        "_source": ["task_id","image_s3_uri","timestamp","embedding_text"], 
        "size": 10,
        "query": {
            "bool": {
                "must": [
                    {
                        "knn": {
                            "text_embedding": {
                                "vector": embedding,
                                "k": OPENSEARCH_DEFAULT_K
                            }
                        }
                    },
                    {
                        "terms": {
                            "task_id.keyword": task_ids
                        }
                    }
                ]
            }
        }
    }

    response = opensearch_client.search(
                index=opensearch_indices,
                body=query,
                allow_no_indices=True
            )

    return format_frame_result(response, score_threshold)

def search_text_match(input_text, task_ids, score_threshold, opensearch_indices):
    # Search DB
    query = {
        "_source": ["task_id","image_s3_uri","timestamp","embedding_text"], 
        "size": 20,
        "query": {
            "bool": {
                "must": [
                    {
                        "term": {
                            "embedding_text": input_text
                        }
                    },
                    {
                        "terms": {
                            "task_id.keyword": task_ids
                        }
                    }
                ]
            }
            
        }    

    }

    response = opensearch_client.search(
                index=opensearch_indices,
                body=query,
                allow_no_indices=True
            )
    return format_frame_result(response, score_threshold)

def search_mm_embedding(input_text, input_image_base64, score_threshold, task_ids, opensearch_indices): 
    # generate MM embedding
    request_body = {"embedding_type": "mm"}
    if input_text is not None and len(input_text) > 0:
        request_body["text_input"] = input_text
        
    if input_image_base64:
        request_body["image_input"] = input_image_base64
    

    response = lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_ARN_EMBEDDING,  
        InvocationType='RequestResponse',
        Payload=json.dumps(request_body)
    )
    response_payload = json.loads(response['Payload'].read())
    embedding = response_payload.get("body")

    if embedding is None:
        return None
        
    # Search in OpenSearch
    query = {
        "_source": ["task_id","image_s3_uri","timestamp","embedding_text"], 
        "size": 10,
        "query": {
            "bool": {
                "must": [
                    {
                        "knn": {
                            "mm_embedding": {
                                "vector": embedding,
                                "k": OPENSEARCH_DEFAULT_K
                            }
                        }
                    },
                    {
                        "terms": {
                            "task_id.keyword": task_ids
                        }
                    }
                ]
            }
            
        }    
    }

    response = opensearch_client.search(
                index=opensearch_indices,
                body=query,
                allow_no_indices=True
            )
    return format_frame_result(response, score_threshold)

def format_frame_result(response, score_threshold):
    result = {}
    for r in response["hits"]["hits"]:
        #print(r["_score"], score_threshold)
        if score_threshold is None or r["_score"] >= score_threshold:
            task_id = r["_source"]["task_id"]
            if task_id not in result:
                result[task_id] = []
    
            bucket, key = parse_s3_uri(r["_source"]["image_s3_uri"])
            result[task_id].append({
                    "timestamp": r["_source"]["timestamp"],
                    "score": r["_score"],
                    "image_uri": s3.generate_presigned_url(
                                        'get_object',
                                        Params={'Bucket': bucket, 'Key': key},
                                        ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
                                    ),
                    "embedding_text": r["_source"].get("embedding_text")
                })
    return result
    

def parse_s3_uri(s3_uri):
    parsed_uri = urlparse(s3_uri)
    if parsed_uri.scheme != 's3':
        raise ValueError('Not an S3 URI')
    bucket = parsed_uri.netloc
    key = parsed_uri.path.lstrip('/')
    return bucket, key

def format_task_result(task):
    r = {
            "TaskId": task["Id"],
            "FileName": task["Request"]["FileName"],
            "RequestTs": task["RequestTs"],
            "Status": task["Status"],
        }

    thumbnail_s3_bucket = task.get("MetaData",{}).get("VideoMetaData",{}).get("ThumbnailS3Bucket")
    thumbnail_s3_key = task.get("MetaData",{}).get("VideoMetaData",{}).get("ThumbnailS3Key")
    if thumbnail_s3_bucket and thumbnail_s3_key:
        r["ThumbnailUrl"] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': thumbnail_s3_bucket, 'Key': thumbnail_s3_key},
                ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
            )
    return r