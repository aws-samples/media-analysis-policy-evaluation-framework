import json
import boto3
import re
import numbers,decimal
from boto3.dynamodb.conditions import Key
import os

DYNAMO_VIDEO_ANALYSIS_TABLE = os.environ.get("DYNAMO_VIDEO_ANALYSIS_TABLE")

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", os.environ['AWS_REGION'])
EXTR_SRV_S3_BUCKET = os.environ.get("EXTR_SRV_S3_BUCKET")

MODEL_ID_SCENE_ANALYSIS = 'anthropic.claude-3-sonnet-20240229-v1:0'
MODEL_ID_SUMMARY = 'anthropic.claude-3-haiku-20240307-v1:0'
MODEL_VERSION = 'bedrock-2023-05-31'
PAGE_SIZE = 100
S3_KEY_PREFIX = "tasks/{task_id}/scene/"
S3_FILE_TEMPLATE = "scene_{index}.json"
S3_KEY_TEMPLATE = S3_KEY_PREFIX + S3_FILE_TEMPLATE

bedrock_runtime_client = boto3.client(service_name='bedrock-runtime', region_name=BEDROCK_REGION)
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

video_analysis_table = dynamodb.Table(DYNAMO_VIDEO_ANALYSIS_TABLE)

def lambda_handler(event, context):
    task_id = event.get("body",{}).get("Id")
    if not task_id:
        return {
            'statusCode': 200,
            'body': 'Task Id is required.'
        }
    scene_analysis = event.get("body",{}).get("Request",{}).get("AnalysisSetting", {}).get("SceneDetection", False)
    if not scene_analysis:
        # Scene analysis is not required
        return event

    # Get all shots from DB
    shots = []
    last_evaluated_key = None
    # Keep querying until there are no more pages of results
    while True:
        query_params = {
            'IndexName': 'task_id-analysis_type-index',  # Name of your index
            'KeyConditionExpression': 'task_id = :task_id_val AND analysis_type = :type_val',
            'ExpressionAttributeValues': {
                ':task_id_val': task_id,
                ':type_val': 'shot'
            }
        }
        if last_evaluated_key:
            query_params['ExclusiveStartKey'] = last_evaluated_key

        response = video_analysis_table.query(**query_params)
        shots.extend(response.get('Items', []))
        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break
    shots = convert_dynamo_to_json_format(shots)

    # construct metadata for LLM scene analysis
    metadata = []
    for s in shots:
        i = {
            "summary": s.get("summary"),
            "start_ts": s.get("start_ts"),
            "end_ts": s.get("end_ts"),
            "transcripts": []
        }
        for f in s.get("frames",[]):
            if f and f.get("subtitles"):
                for sub in f.get("subtitles",[]):
                    if sub not in i["transcripts"]:
                        i["transcripts"].append(sub)
        metadata.append(i)

    # Generate scenes using LLMs
    scenes = generate_scene(metadata)
    #if not scenes:
    #    # retry
    #   scenes = generate_scene(caps, subtitles)

    # Cleanup existing scenes in DB and S3
    cleanup(task_id, EXTR_SRV_S3_BUCKET, S3_KEY_PREFIX)

    # Align shots to scenes and store scenes to DB
    index = 0
    for s in scenes:
        if s:
            index += 1
            s["index"] = index
            s["shots"] = []

            caps, subs = [],[]
            for shot in shots:
                if (shot["start_ts"] >= s["start_ts"] and shot["start_ts"] < s["end_ts"]) or (shot["start_ts"] < s["start_ts"] and shot["end_ts"] >= s["end_ts"]):
                    s["shots"].append(shot)
                    if shot.get("summary"):
                        caps.append(shot["summary"])
                    if shot.get("frames"):
                        for f in shot.get("frames"):
                            if f and f.get("subtitles"):
                                subs.extend(f.get("subtitles"))

            # Re-generate summary
            s["summary"] = generate_summary(caps, subs)

            # Store to DB
            s["id"] = f"{task_id}_scene_{index}"
            s["task_id"] = task_id
            s["analysis_type"] = 'scene'
            resposne = video_analysis_table.put_item(Item=convert_to_dynamo_format(s))

            # Store to S3
            s3.put_object(Bucket=EXTR_SRV_S3_BUCKET, 
                Key=S3_KEY_TEMPLATE.format(task_id=task_id, index=index), 
                Body=json.dumps(s), 
                ContentType='application/json'
            )
    
    return event

def generate_summary(captions, subtitles):
    example = {"summary":""}
    messages = [
        {
            'role': 'user',
            'content': f'Here is the video scene frame summaries in <caption> tag:\n<caption>{json.dumps(captions)}\n</caption>\n; and the timestamp level audio transcription in <subtitle> tag:\n<subtitle>{json.dumps(subtitles)}\n</subtitle >\n'
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
    system = "You are a media operations assistant responsible for write video scene summary based on both visual frame description and audio transcription. Keep the summary within 200 tokens."

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
        response = inference(model_params, model_id=MODEL_ID_SUMMARY)
        return json.loads("{" + response.get("content", [{}])[0].get("text")).get("summary")
    except Exception as e:
        print(f"ERR: inference: {str(e)}\n RETRY...")
        response = inference(model_params, model_id=MODEL_ID_SUMMARY)
    return None

def generate_scene(metadata):
    # Construct LLMs prompts 
    example = {"scenes": [{"start_ts": 10.5, "end_ts": 20, "summary": ""}]}
    messages = [
        {
            'role': 'user',
            'content': f'Here is the shot-level information for the video, which includes the start and end times, a summary for each shot, and audio transcriptions aligned with the shots in <metadata> tag:<metadata>{json.dumps(metadata)}</metadata>'
        },
        {
            'role': 'assistant',
            'content': 'Got the metadata. What is the output formatt?'
        },
        {
            'role': 'user',
            'content': 'JSON format. An example of the output:\n{0}\n'.format(json.dumps(example))
        },
        {
            'role': 'assistant',
            'content': '{'
        }
    ]

    ## system prompt to role play
    system = '''You are a media expert tasked with analyzing a video to identify its scenes. 
        Scenes are continuous sequences of action occurring in a specific location and time, consisting of a series of frames. 
        Base your analysis on the visual frame summary and the audio transcription.
        "Credits, including the list of cast and crew at the beginning and end of the video, should be treated as independent scenes.
        '''

    ## setting up the model params
    model_params = {
        'anthropic_version': MODEL_VERSION,
        'max_tokens': 4096 * 10,
        'temperature': 0.1,
        'top_p': 0.7,
        'top_k': 20,
        'stop_sequences': ['\n\nHuman:'],
        'system': system,
        'messages': messages
    }

    try:
        response = inference(model_params, model_id=MODEL_ID_SCENE_ANALYSIS)
        return json.loads('{'+response.get("content",[{}])[0].get("text","").replace("\n","")).get("scenes")
    except Exception as e:
        print(f"ERR: inference: {str(e)}\n RETRY...")
        response = inference(model_params, model_id=MODEL_ID_SCENE_ANALYSIS)
    return None

def inference(model_params, model_id):
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
    # Delete existing scenes from DB
    response = video_analysis_table.query(
        IndexName='task_id-analysis_type-index',
        KeyConditionExpression=Key('task_id').eq(task_id) & 
                               Key('analysis_type').eq('scene')
    )
    for item in response['Items']:
        video_analysis_table.delete_item(
            Key={
                'id': item['id'], 
                'task_id': item['task_id']
            }
        )    
    
    # Delete s3 scene folder
    s3_res = boto3.resource('s3')
    bucket = s3_res.Bucket(s3_bucket)
    bucket.objects.filter(Prefix=s3_prefix).delete()
