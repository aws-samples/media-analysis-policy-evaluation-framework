import json
import boto3
import os
from opensearchpy import OpenSearch
import base64
from io import BytesIO
import re
import time

OPENSEARCH_INDEX_NAME_VIDEO_TASK = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TASK")
OPENSEARCH_INDEX_NAME_VIDEO_TRANS = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TRANS")
OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME = os.environ.get("OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")

LOCAL_PATH = '/tmp/'
caption_prompts = "Describe the image in detail limit in 100 tokens. Condition: If you are uncertain about the content or if the description violates any guardrail rules, return an empty result."

opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )

s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')
bedrock = boto3.client('bedrock-runtime') 

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
    
    if task_id is None or setting is None or s3_bucket is None or s3_key is None or not s3_key.endswith('.jpg'):
        return {
            "Error": "Invalid Request"
        }

    frame_index_name = OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME + task_id
    frame_id = s3_key.split('/')[-1].replace('.jpg','')
    ts = float(frame_id.split("_")[-1])
    input_text = ""

    frame = {}

    # Get corresponding subtitle based on timestamp
    subtitle = None
    try:
        subtitle = get_subtitle_by_ts(task_id, ts)
    except Exception as ex:
        print(ex)
    if subtitle is not None:
        input_text += f'Subtitle: {subtitle};\n' 

    # Image caption - Sonnet
    if setting.get("ImageCaption") == True:
        caption = bedrock_image_caption(s3_bucket, s3_key)
        #frame["image_caption"] = caption
        if caption and len(caption) > 0:
            input_text += f"Summary: {caption};\n"
        
        # Store to S3
        s3.put_object(Bucket=s3_bucket, Key=f'tasks/{task_id}/bedrock_image_caption/image_caption_{ts}.txt', Body=caption)

    # Get the other metadata from DB
    frame_id = s3_key.split('/')[-1].replace('.jpg','')
    try:
        response = opensearch_client.get(index=OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME+task_id, id=frame_id)
        labels = response["_source"]["detect_label"]
        if labels and len(labels) > 0:
            input_text += f"Label: {','.join(labels)}" + ";\n"
        texts = response["_source"]["detect_text"]
        if texts and len(texts) > 0:
            input_text += f"Text: {','.join(texts)}" + ";\n"
        celebrites = response["_source"]["detect_celebrity"]
        if celebrites and len(celebrites) > 0:
            input_text += f"Celebrity: {','.join(celebrites)}" + ";\n"
        mods = response["_source"]["detect_moderation"]
        if mods and len(mods) > 0:
            input_text += f"Moderation: {','.join(mods)}" + ";\n"
    except Exception as ex:
        print(ex)
    
    # Multimodal Embedding
    mm_embedding = get_multimodal_vector(s3_bucket, s3_key, input_text)
    frame["mm_embedding"] = mm_embedding

    # Text Embedding
    txt_embedding = get_text_vector(input_text)
    frame["text_embedding"] = txt_embedding
    frame["embedding_text"] = input_text
    

    # Update database: video_frame_[]
    opensearch_client.update(index=frame_index_name, id=frame_id, body={"doc": frame})


    return True

def get_subtitle_by_ts(task_id, ts):
    if ts is None:
        return None
    
    request = {
                  "_source": ["inner_hits"],
                  "query": {
                    "bool": {
                      "must": [
                        {
                          "nested": {
                            "path": "subtitles",
                            "query": {
                              "bool": {
                                "must": [
                                  {"range": {"subtitles.start_ts": { "lte": ts }}},
                                  {"range": {"subtitles.end_ts": {"gte": ts}}}
                                ]
                              }
                            },
                            "inner_hits": {}
                          }
                        },
                        {
                          "term": {
                            "_id": task_id
                          }
                        }
                      ]
                    }
                  }
                }
    response = opensearch_client.search(
            index=OPENSEARCH_INDEX_NAME_VIDEO_TRANS,
            body=request
        )

    try:
        if "hits" in response and len(response["hits"]["hits"]) > 0:
            trans = response["hits"]["hits"][0]["inner_hits"]["subtitles"]["hits"]["hits"][0]["_source"]["transcription"]
            return trans
    except Exception as ex:
        print(ex)
        
    return None
    

def get_multimodal_vector(s3_bucket, s3_key, input_text=None):
    # Get image base64
    response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    image_content = response['Body'].read()
    base64_encoded_image = base64.b64encode(image_content).decode('utf-8')

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

def get_text_vector(input_text):
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

    return embedding

def bedrock_image_caption(s3_bucket, s3_key, max_retries=3, retry_delay=1):
    retries = 0
    while retries < max_retries:
        try:
            # download
            file_name = s3_key.split('/')[-1]
            local_file_path = f'{LOCAL_PATH}{file_name}'
            s3.download_file(s3_bucket, s3_key, local_file_path)
            
            # Convert to Base64
            image_base64 = None
            with open(local_file_path, "rb") as image_file:
                image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        
            if image_base64 is not None:
                # Call Bedrock Anthropic Claude V3 Sonnet
                body = json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 1000,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": "image/jpeg",
                                            "data": image_base64
                                        }
                                    },
                                    {
                                        "type": "text",
                                        "text": caption_prompts
                                    }
                                ]
                            }
                        ]
                    })
                
                response = bedrock.invoke_model(
                    body=body, 
                    modelId="anthropic.claude-3-haiku-20240307-v1:0", 
                    accept="application/json", 
                    contentType="application/json",
                )
                
                return json.loads(response.get('body').read())["content"][0]["text"]

        except Exception as ex:
            print(ex)
            retries += 1
            time.sleep(retry_delay)

    return None
