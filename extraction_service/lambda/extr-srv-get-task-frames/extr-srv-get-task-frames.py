'''
"Source": mm_embedding | text_embedding | text,
'''
import json
import boto3
import os
from opensearchpy import OpenSearch
import re
from urllib.parse import urlparse

OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME = os.environ.get("OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME")
OPENSEARCH_DEFAULT_K = os.environ.get("OPENSEARCH_DEFAULT_K", 20)
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")

S3_PRESIGNED_URL_EXPIRY_S = os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", 3600) # Default 1 hour 

AWS_REGION = os.environ['AWS_REGION']

opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )

s3 = boto3.client('s3')

def lambda_handler(event, context):
    task_id = event.get("TaskId")
    page_size = event.get("PageSize", 20)
    from_index = event.get("FromIndex", 0)

    if task_id is None:
        return {
            'statusCode': 400,
            'body': 'TaskId required.'
        }

    query = {
        "_source": ["image_s3_uri", "embedding_text", "timestamp", "detect_label", "detect_celebrity", "detect_logo", "detect_moderation", "detect_text"], 
        "size": page_size,
        "from": from_index,
        "query": {
            "match_all": {}
        },
        "sort": ["timestamp"]
    }
    response = opensearch_client.search(index=OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME + task_id, body=query)

    result = {"Frames": [], "Total":response["hits"]["total"]["value"]}
    for doc in response["hits"]["hits"]:
        try:
            s3_bucket, s3_key = parse_s3_uri(doc["_source"].get("image_s3_uri"))
            frame = {
                "S3Url": s3.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': s3_bucket, 'Key': s3_key},
                            ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
                        ),
                "Timestamp": doc["_source"]["timestamp"],
            }
            image_caption = None
            if "embedding_text" in doc["_source"] and doc["_source"]["embedding_text"] is not None and len(doc["_source"]["embedding_text"]) > 0:
                image_caption = doc["_source"]["embedding_text"]
            
            if image_caption:
                arr = image_caption.split(';\n')
                for a in arr:
                    if a.startswith("Summary:"):
                        frame["ImageCaption"] = a.replace("Summary:","")
                    elif a.startswith("Subtitle:"):
                        frame["Subtitle"] = a.replace("Subtitle:","").split(',')
                    elif a.startswith("Label:"):
                        frame["Label"] = a.replace("Label:","").split(',')
                    elif a.startswith("Text:"):
                        frame["Text"] = a.replace("Text:","").split(',')
                    elif a.startswith("Moderation:"):
                        frame["Moderation"] = a.replace("Moderation:","").split(',')
                    elif a.startswith("Celebrity:"):
                        frame["Celebrity"] = a.replace("Celebrity:","").split(',')
                if "ImageCaption" not in frame:
                    frame["ImageCaption"] = a
            
            result["Frames"].append(frame)
        except Exception as ex:
            print(ex)
    return {
        'statusCode': 200,
        'body': result
    }

def parse_s3_uri(s3_uri):
    parsed_uri = urlparse(s3_uri)
    if parsed_uri.scheme != 's3':
        raise ValueError('Not an S3 URI')
    bucket = parsed_uri.netloc
    key = parsed_uri.path.lstrip('/')
    return bucket, key