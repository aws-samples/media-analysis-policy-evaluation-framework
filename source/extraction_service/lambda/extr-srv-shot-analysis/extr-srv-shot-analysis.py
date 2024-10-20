import json
import boto3
import re
import numbers,decimal
from boto3.dynamodb.conditions import Key
import os

DYNAMO_VIDEO_ANALYSIS_TABLE = os.environ.get("DYNAMO_VIDEO_ANALYSIS_TABLE")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", os.environ['AWS_REGION'])
EXTR_SRV_S3_BUCKET = os.environ.get("EXTR_SRV_S3_BUCKET")

MODEL_ID = 'anthropic.claude-3-haiku-20240307-v1:0'
MODEL_VERSION = 'bedrock-2023-05-31'
PAGE_SIZE = 100
SHOT_SIMILARITY_THRESHOLD = 0.5
S3_KEY_PREFIX = "tasks/{task_id}/shot/"
S3_FILE_TEMPLATE = "shot_{index}.json"
S3_KEY_TEMPLATE = S3_KEY_PREFIX + S3_FILE_TEMPLATE

bedrock_runtime_client = boto3.client(service_name='bedrock-runtime', region_name=BEDROCK_REGION)
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

video_analysis_table = dynamodb.Table(DYNAMO_VIDEO_ANALYSIS_TABLE)
video_frame_table = dynamodb.Table(DYNAMO_VIDEO_FRAME_TABLE)

def lambda_handler(event, context):
    task_id = event.get("body",{}).get("Id")
    if not task_id:
        return {
            'statusCode': 200,
            'body': 'Task Id is required.'
        }
    shot_analysis = event.get("body",{}).get("Request",{}).get("AnalysisSetting", {}).get("ShotDetection", False)
    shot_similarity_threshold = event.get("body",{}).get("Request",{}).get("AnalysisSetting", {}).get("ShotSimilarityThreshold")
    if not shot_similarity_threshold:
        shot_similarity_threshold = SHOT_SIMILARITY_THRESHOLD
    shot_similarity_threshold = float(SHOT_SIMILARITY_THRESHOLD)

    if not shot_analysis:
        # Shot analysis is not required
        return event
    
    # Get all frames from DB
    frames = []
    last_evaluated_key = None
    while True:
        if last_evaluated_key:
            response = video_frame_table.query(
                IndexName='task_id-timestamp-index', 
                KeyConditionExpression=Key('task_id').eq(task_id), 
                ExclusiveStartKey=last_evaluated_key,
                Limit=1000
            )
        else:
            response = video_frame_table.query(
                IndexName='task_id-timestamp-index',
                KeyConditionExpression=Key('task_id').eq(task_id),
                Limit=1000
            )
        frames.extend(response.get("Items", []))
        last_evaluated_key = response.get('LastEvaluatedKey', None)
        if not last_evaluated_key:
            break
    frames = convert_dynamo_to_json_format(frames)

    # construct subtitls from frame metadata
    subtitles = []
    for frame in frames:
        if frame.get("subtitles"):
            subtitles.extend(frame.get("subtitles"))                
    
    # Identify shots from frames
    shots = []
    start_ts, end_ts, shot_frames = None, None, []
    for frame in frames:
        ts = frame.get("timestamp")
        if start_ts is None:
            start_ts = ts
        score = frame.get("similarity_score")
        if score and score > shot_similarity_threshold:
            shots.append({
                "start_ts": start_ts,
                "end_ts": ts,
                "duration": ts - start_ts,
                "frames": shot_frames
            })
            start_ts = ts
            shot_frames = []
        shot_frames.append({
            "timestamp": frame["timestamp"],
            "s3_bucket": frame["s3_bucket"],
            "s3_key": frame["s3_key"],
            "subtitles": frame.get("subtitles"),
            "image_caption": frame.get("image_caption"),
            "similarity_score": score,
        })

    # Cleanup existing shots in DB and S3
    cleanup(task_id, EXTR_SRV_S3_BUCKET, S3_KEY_PREFIX)

    # Generate shot summary: use captions and subtitles and store to DB/S3
    index = 0
    for s in shots:
        index += 1
        if s.get("frames"):
            caps, subs = [], []
            for f in s.get("frames"):
                if f.get("image_caption"):
                    caps.append({
                        "timestamp": f["timestamp"],
                        "caption": f["image_caption"]
                    })
                if f.get("subtitles"):
                    for sub in f.get("subtitles"):
                        subs.append(sub)

            s["summary"] = generate_summary(caps, subs)

        # Store to DB
        s["id"] = f"{task_id}_shot_{index}"
        s["index"] = index
        s["task_id"] = task_id
        s["analysis_type"] = 'shot'
        resposne = video_analysis_table.put_item(Item=convert_to_dynamo_format(s))

        # Store to S3
        s3.put_object(Bucket=EXTR_SRV_S3_BUCKET, 
            Key=S3_KEY_TEMPLATE.format(task_id=task_id, index=index), 
            Body=json.dumps(s), 
            ContentType='application/json'
        )

    #event["shots"] = shots
    return event

def generate_summary(captions, subtitles):
    example = {"summary":"This video shot shows"}
    messages = [
        {
            'role': 'user',
            'content': f'Here is the video frame summaries in <caption> tag:\n<caption>{json.dumps(captions)}\n</caption>\n; and the timestamp level audio transcription in <subtitle> tag:\n<subtitle>{json.dumps(subtitles)}\n</subtitle >\n'
        },
        {
            'role': 'assistant',
            'content': 'Got the caption and subtitle. What output format?'
        },
        {
            'role': 'user',
            'content': f'JSON format. An example of the output:\n{json.dumps(example)}\n'
        },
        {
            'role': 'assistant',
            'content': '{'
        }
    ]
    system = "You are a media operations assistant responsible for write video shot summary based on both visual frame description and audio transcription. Keep the summary within 200 tokens."

    model_params = {
        'anthropic_version': MODEL_VERSION,
        'max_tokens': 4096,
        'temperature': 0.1,
        'top_p': 0.7,
        'top_k': 20,
        'stop_sequences': ['\n\nHuman:'],
        'system': system,
        'messages': messages
    }

    try:
        response = inference(model_params, model_id=MODEL_ID)
        return json.loads("{" + response.get("content", [{}])[0].get("text")).get("summary")
    except Exception as e:
        print(f"ERR: inference: {str(e)}\n RETRY...")
        response = inference(model_params)
    return None

def inference(model_params, model_id=MODEL_ID):
    model_id = model_id
    accept = 'application/json'
    content_type = 'application/json'

    response = bedrock_runtime_client.invoke_model(
        body=json.dumps(model_params),
        modelId=model_id,
        accept=accept,
        contentType=content_type
    )

    response_body = json.loads(response.get('body').read())

    # patch the json string output with '{' and parse it
    response_content = response_body['content'][0]['text']
    if response_content[0] != '{':
        response_content = '{' + response_content

    try:
        response_content = json.loads(response_content)
    except Exception as e:
        print("Malformed JSON response. Try to repair it...")
        try:
            response_content = json_repair.loads(response_content, strict=False)
        except Exception as e:
            print("Failed to repair the JSON response...")
            return response_content
            #raise e

    response_body['content'][0]['json'] = response_content

    return response_body

def convert_to_dynamo_format(item):
    """
    Recursively convert an object to a DynamoDB item format.
    """
    if isinstance(item, dict):
        return {k: convert_to_dynamo_format(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [convert_to_dynamo_format(v) for v in item]
    elif isinstance(item, float):
        return decimal.Decimal(str(item))
    #elif isinstance(item, decimal.Decimal):
    #    return float(item)
    else:
        return item

def convert_dynamo_to_json_format(item):
    """
    Recursively convert a DynamoDB item to a JSON serializable format.
    """
    if isinstance(item, dict):
        return {k: convert_dynamo_to_json_format(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [convert_dynamo_to_json_format(v) for v in item]
    elif isinstance(item, decimal.Decimal):
        return float(item)
    else:
        return item

def cleanup(task_id, s3_bucket, s3_prefix):
    # Delete existing shot from DB
    response = video_analysis_table.query(
        IndexName='task_id-analysis_type-index',
        KeyConditionExpression=Key('task_id').eq(task_id) & 
                               Key('analysis_type').eq('shot')
    )
    for item in response['Items']:
        video_analysis_table.delete_item(
            Key={
                'id': item['id'], 
                'task_id': item['task_id']
            }
        )    
    
    # Delete s3 shot folder
    s3_res = boto3.resource('s3')
    bucket = s3_res.Bucket(s3_bucket)
    bucket.objects.filter(Prefix=s3_prefix).delete()
