import json
import boto3
import os
from opensearchpy import OpenSearch

OPENSEARCH_INDEX_NAME_VIDEO_TASK = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TASK")
OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME = os.environ.get("OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")
OPENSEARCH_INDEX_NAME_VIDEO_TRANS = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TRANS")

S3_PRESIGNED_URL_EXPIRY_S = os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", 3600) # Default 1 hour 

opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )
s3 = boto3.client("s3")

def lambda_handler(event, context):
    task_id = event.get("TaskId")    
    if task_id is None:
        return {
            'statusCode': 400,
            'body': 'Invalid request. Missing TaskId.'
        }
    
    # Supported values: 
    # ["Request","VideoMetaData",
    #   "Transcription","DetectLabel","DetectLabelCategory","DetectText","DetectCelebrity","DetectModeration","DetectLogo","ImageCaption",
    #   "DetectLabelAgg","DetectLabelCategoryAgg","DetectTextAgg","DetectCelebrityAgg","DetectModerationAgg","DetectLogoAgg"
    # ]
    data_types = event.get("DataTypes", ["Request","VideoMetaData","Subtitle","DetectLabelCategoryAgg","DetectTextAgg","DetectCelebrityAgg","DetectModerationAgg"]) 
    page_size = event.get("PageSize", 500)
    from_index = event.get("FromIndex", 0)

    # get from video_task DB table
    task = {}
    try:
        if "Request" in data_types:
            response = opensearch_client.get(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK, id=task_id)
            task = response["_source"]
    except Exception as ex:
        return {
            'statusCode': 400,
            'body': f'Invalid request. Task does not exist: {task_id}.'
        }
    
    if "Request" in data_types and "VideoMetaData" in data_types:
        # Get Video pre-signed S3 URL
        s3_bucket = task["Request"]["Video"]["S3Object"]["Bucket"]
        s3_key = task["Request"]["Video"]["S3Object"]["Key"]
        task["VideoUrl"] = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': s3_bucket, 'Key': s3_key},
                ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
            )
    
    # Get Transcription and Subtitles
    if "Transcription" in data_types:
        try:
            response = opensearch_client.get(index=OPENSEARCH_INDEX_NAME_VIDEO_TRANS, id=task_id)
            task["Transcription"] = response["_source"]
        except Exception as ex:
            print("No transcription.", ex)
    
    # Get aggregated items
    if "DetectLabelAgg" in data_types:
        task["DetectLabelAgg"] = get_deduped_items(task_id, "detect_label", from_index, page_size)
    if "DetectLabelCategoryAgg" in data_types:
        task["DetectLabelCategoryAgg"] = get_deduped_items(task_id, "detect_label_category", from_index, page_size)
    if "DetectCelebrityAgg" in data_types:
        task["DetectCelebrityAgg"] = get_deduped_items(task_id, "detect_celebrity", from_index, page_size)
    if "DetectTextAgg" in data_types:
        task["DetectTextAgg"] = get_deduped_items(task_id, "detect_text", from_index, page_size)
    if "DetectModerationAgg" in data_types:
        task["DetectModerationAgg"] = get_deduped_items(task_id, "detect_moderation", from_index, page_size)
    if "DetectLogoAgg" in data_types:
        task["DetectLogoAgg"] = get_deduped_items(task_id, "detect_logo", from_index, page_size)
    
    # Get items
    if "ImageCaption" in data_types:
        task["ImageCaption"] = get_items(task_id, "embedding_text", from_index, page_size, False)
    if "DetectLabel" in data_types:
        task["DetectLabel"] = get_items(task_id, "detect_label", from_index, page_size)
    if "DetectLabelCategory" in data_types:
        task["DetectLabelCategory"] = get_items(task_id, "detect_label_category", from_index, page_size)
    if "DetectCelebrity" in data_types:
        task["DetectCelebrity"] = get_items(task_id, "detect_celebrity", from_index, page_size)
    if "DetectText" in data_types:
        task["DetectText"] = get_items(task_id, "detect_text", from_index, page_size)
    if "DetectModeration" in data_types:
        task["DetectModeration"] = get_items(task_id, "detect_moderation", from_index, page_size)
    if "DetectLogo" in data_types:
        task["DetectLogo"] = get_items(task_id, "detect_logo", from_index, page_size)

    return {
        'statusCode': 200,
        'body': task
    }

def get_items(task_id, field_name, from_index, page_size, is_array=True):
    index_name = OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME + task_id
    request={
                "size": page_size,  
                "from": from_index,
                "_source": ["timestamp", field_name],
                "query": {
                    "bool": {
                      "must": [
                        {
                          "exists": {
                            "field": field_name
                          }
                        }
                      ]
                    }
                  }
            }
    if is_array:
        request["query"]["bool"]["must"].append(
            {
              "script": {
                "script": {
                  "source": f"doc['{field_name}'].size() > 0"
                }
              }
            })
        
    total,result = 0, []
    try:
        response = opensearch_client.search(
                index=index_name,
                body=request
            )
        total = response["hits"]["total"]["value"]
        for i in response["hits"]["hits"]:
            result.append({
                "value": i["_source"][field_name],
                "timestamp": i["_source"]["timestamp"]
            })            
    except Exception as ex:
        print("Failed to retrieve aggreated result from OpenSearch", ex)
    return {
        "Total": total,
        "Items": result
    }

def get_deduped_items(task_id, field_name, from_index, page_size):
    index_name = OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME + task_id
    request={
              "size": 0,
              "from": from_index,
              "aggs": {
                "item_aggs": {
                  "terms": {
                    "field": field_name,
                    "size": page_size
                  },
                  "aggs": {
                    "timestamp_aggs": {
                      "terms": {
                        "field": "timestamp",
                        "size": 10000
                      }
                    }
                  }
                }
              }
            }
        
    result = []
    try:
        response = opensearch_client.search(
                index=index_name,
                body=request
            )
        for i in response["aggregations"]["item_aggs"]["buckets"]:
            item = {
                "name": i["key"],
                "timestamps": []
            }
            for a in i["timestamp_aggs"]["buckets"]:
                item["timestamps"].append(a["key"])
            result.append(item)
            
    except Exception as ex:
        print("Failed to retrieve aggreated result from OpenSearch", ex)
    return result
