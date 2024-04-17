'''
"Source": mm_embedding | text_embedding | text,
'''
import json
import boto3
import os
from opensearchpy import OpenSearch
import re
from urllib.parse import urlparse

OPENSEARCH_INDEX_NAME_VIDEO_TASK = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TASK")
OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME = os.environ.get("OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")
OPENSEARCH_INDEX_NAME_VIDEO_TRANS = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TRANS")
OPENSEARCH_DEFAULT_K = os.environ.get("OPENSEARCH_DEFAULT_K", 20)
S3_PRESIGNED_URL_EXPIRY_S = os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", 3600) # Default 1 hour 
VIDEO_SAMPLE_S3_BUCKET = os.environ.get("VIDEO_SAMPLE_S3_BUCKET")
VIDEO_SAMPLE_S3_PREFIX = os.environ.get("VIDEO_SAMPLE_S3_PREFIX")
VIDEO_SAMPLE_FILE_PREFIX = os.environ.get("VIDEO_SAMPLE_FILE_PREFIX")

BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID = os.environ.get("BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID")
OPENSEARCH_SCORE_THRESHOLD = 0.5

AWS_REGION = os.environ['AWS_REGION']

opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': 443}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )
bedrock = boto3.client('bedrock-runtime')
s3 = boto3.client('s3')

def lambda_handler(event, context):
    search_text = event.get("SearchText", "")
    page_size = event.get("PageSize", 10)
    from_index = event.get("FromIndex", 0)
    score_threshold = event.get("ScoreThreshold", OPENSEARCH_SCORE_THRESHOLD)
    request_by = event.get("RequestBy")
    image_bytes = event.get("ImageBytes", "")
    source = event.get("Source")
    
    if search_text is None:
        search_text = ""
    if image_bytes is None:
        image_bytes = ""
    if len(search_text) > 0:
        search_text = search_text.strip()
    
    # Get task Ids for the given user
    task_ids = get_task_ids_by_user(request_by)
    if task_ids is None or len(task_ids) == 0:
        return {
            'statusCode': 200,
            'body': []
        }
    
    result, embedding_result = None, None
    if len(search_text) == 0 and len(image_bytes) == 0:
       # No search keyword/image provided - return all authorized videos
       result = get_video_task(page_size, from_index, request_by, task_ids)
    else:
        # With keyword/image: apply filter
        if source == "mm_embedding" and (len(search_text) > 0 or len(image_bytes) > 0):
            embedding_result = search_mm_embedding(search_text, image_bytes, score_threshold, task_ids)
        elif source == "text_embedding" and len(search_text) > 0:
            embedding_result = search_text_embedding(search_text, task_ids, score_threshold)
        elif source == "text" and len(search_text) > 0:
            embedding_result = search_text_match(search_text, task_ids, score_threshold)
            
        task_ids = list(embedding_result.keys()) if embedding_result else []

        result = get_video_task(page_size, from_index, request_by, task_ids)
        
    if embedding_result is not None:
        for i in result:
            if i["TaskId"] in embedding_result:
                i["Frames"] = embedding_result[i["TaskId"]]

    return {
        'statusCode': 200,
        'body': result
    }

def get_task_ids_by_user(request_by):
    ids = []
    if request_by is None or len(request_by) == 0:
        return ids
    try:
        query = {
              "_source": False, 
              "query": {
                "nested": {
                  "path": "Request",
                  "query": {
                    "match": {
                      "Request.RequestBy": request_by
                    }
                  }
                }
              }
            }
        response = opensearch_client.search(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK, body=query)
        for d in response["hits"]["hits"]:
            ids.append(d["_id"])
        return ids
    except Exception as ex:
        print(ex)
        return ids
        
def get_video_task(page_size, from_index, request_by, task_ids):
    result = []
    query = {
        "query": {
            "match_all": {}
        },
        "sort":[{ "RequestTs": {"order": "desc"}}],
        "size": page_size,
        "from": from_index,
    }
    if request_by is not None or task_ids is not None:
        query["query"] = {
            "bool": {
              "must": []
            }
        }
        if request_by is not None:
            query["query"]["bool"]["must"].append({
              "nested": {
                "path": "Request",
                "query": {
                  "match_phrase": { "Request.RequestBy": request_by }
                }
              }
            })
        if task_ids is not None:
            query["query"]["bool"]["must"].append({ "terms": { "_id": task_ids }})
    
    response = opensearch_client.search(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK, body=query)
    for d in response["hits"]["hits"]:
        doc = d["_source"]
        thumbnail_url = None
        try:
            if "MetaData" in doc and "VideoMetaData" in doc["MetaData"]:
                thumbnail_bucket = doc["MetaData"]["VideoMetaData"].get("ThumbnailS3Bucket")
                thumbnail_key = doc["MetaData"]["VideoMetaData"].get("ThumbnailS3Key")
                print(thumbnail_bucket, thumbnail_key)
                
                if thumbnail_bucket and thumbnail_key:
                    thumbnail_url = s3.generate_presigned_url(
                                            'get_object',
                                            Params={'Bucket': thumbnail_bucket, 'Key': thumbnail_key},
                                            ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
                                        )

        except Exception as ex:
            print(ex)
            
        r = {
                "TaskId": doc["Request"]["TaskId"],
                "FileName": doc["Request"].get("FileName"),
                "RequestTs": doc.get("RequestTs"),
                "Status": doc.get("Status"),
            }
        if thumbnail_url is not None:
            r["ThumbnailUrl"] = thumbnail_url
        if "EvaluationResult" in doc:
            r["Violation"] = doc["EvaluationResult"].get("answer") == "Y"
        result.append(r)

    return result

def search_text_embedding(input_text, task_ids, score_threshold):
    # generate text embedding
    embedding = None
    body = json.dumps({"inputText": f"{input_text}"})
    try:
        response = bedrock.invoke_model(
            body=body, 
            modelId="amazon.titan-embed-text-v1", 
            accept="application/json", 
            contentType="application/json"
        )
        
        response_body = json.loads(response.get("body").read())
        embedding = response_body.get("embedding")
    except Exception as ex:
        print(ex)

    # Search DB
    query = {
        "_source": ["image_s3_uri","timestamp","embedding_text"], 
        "size": 100,
        "query": {
            "knn": {
                "text_embedding": {
                    "vector": embedding,
                    "k": OPENSEARCH_DEFAULT_K
                }
            }
        }
    }
    indices = []
    for id in task_ids:
        indices.append(f'{OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME}{id}')
    
    response = opensearch_client.search(
                index=indices,
                body=query
            )
    return format_frame_result(response, score_threshold)

def search_text_match(input_text, task_ids, score_threshold):
    # Search DB
    query = {
        "_source": ["image_s3_uri","timestamp","embedding_text"], 
        "size": 100,
        "query": {
            "term": {
                "embedding_text": input_text
            }
        }
    }
    indices = []
    for id in task_ids:
        indices.append(f'{OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME}{id}')
    
    response = opensearch_client.search(
                index=indices,
                body=query
            )
    return format_frame_result(response, score_threshold)

def search_mm_embedding(input_text, input_image_base64, score_threshold, task_ids): 
    # generate MM embedding
    request_body = {}
    if input_text is not None and len(input_text) > 0:
        request_body["inputText"] = input_text
        
    if input_image_base64:
        request_body["inputImage"] = input_image_base64
    
    body = json.dumps(request_body)
    
    embedding = None
    try:
        response = bedrock.invoke_model(
            body=body, 
            modelId=BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID, 
            accept="application/json", 
            contentType="application/json"
        )
        
        response_body = json.loads(response.get('body').read())
        embedding = response_body.get("embedding")
        
    except Exception as ex:
        raise ex
        
    if embedding is None:
        return None
        
    # Search in OpenSearch
    query = {
        "_source": ["image_s3_uri","timestamp","embedding_text"], 
        "size": 100,
        "query": {
            "knn": {
                "mm_embedding": {
                    "vector": embedding,
                    "k": OPENSEARCH_DEFAULT_K
                }
            }
        }
    }
    indices = []
    for id in task_ids:
        indices.append(f'{OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME}{id}')

    response = opensearch_client.search(
                index=indices,
                body=query
            )
    return format_frame_result(response, score_threshold)

def format_frame_result(response, score_threshold):
    result = {}
    for r in response["hits"]["hits"]:
        #print(r["_score"], score_threshold)
        if score_threshold is None or r["_score"] >= score_threshold:
            task_id = r["_index"].replace(OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME,"")
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