'''
1. Read Transcribe transcription and subtitle from s3
2. Update DB
3. Start extraction step functions workflow
'''
import json
import boto3
import os
import utils
import re

SQS_URL = os.environ.get("SQS_URL")
DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
DYNAMO_VIDEO_TRANS_TABLE = os.environ.get("DYNAMO_VIDEO_TRANS_TABLE")

s3 = boto3.client('s3')
sqs = boto3.client('sqs')
stepfunctions = boto3.client('stepfunctions')

def lambda_handler(event, context):
    #print(json.dumps(event))
    if event is None or "Records" not in event or len(event["Records"]) == 0:
         return {
            'statusCode': 400,
            'body': 'Invalid trigger'
        }
    s3_bucket, s3_key, task_id = None, None, None
    try:
        s3_bucket = event["Records"][0]["s3"]["bucket"]["name"]
        s3_key = event["Records"][0]["s3"]["object"]["key"]
        task_id = s3_key.split('/')[1]
    except ex as Exception:
        print(ex)
        return {
            'statusCode': 400,
            'body': f'Error parsing S3 trigger: {ex}'
        }
    
    # Get transcription result from S3
    response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    file_content = response['Body'].read().decode('utf-8')
    trans_data = json.loads(file_content)
    
    # Get subtitle from S3
    subtitle_data = read_vtt(s3_bucket, s3_key.replace('.json','.vtt'))
    
    # Get task doc from db
    doc = None
    try:
        doc = utils.dynamodb_get_by_id(DYNAMO_VIDEO_TASK_TABLE, id=task_id)
    except Exception as ex:
        print('Doc does not exist',ex)
    
    if doc is not None:
        # Update video task status
        try:
            doc["Status"] = "transcription_completed"
            doc["Id"] = task_id
        
            # update DB: video_task
            utils.dynamodb_table_upsert(DYNAMO_VIDEO_TASK_TABLE, doc)
        except Exception as ex:
            print('Failed to update video task status',ex)

        # Get transcription
        transcripts = []
        for t in trans_data["results"]["transcripts"]:
            transcripts.append(t["transcript"])

        # Update transciption to DB
        try:
            # add transcription to db: video_transcription
            trans_doc = {
                    "task_id": task_id,
                    "language_code": trans_data["results"]["language_code"],
                    "subtitles": subtitle_data
                }
            
            utils.dynamodb_table_upsert(DYNAMO_VIDEO_TRANS_TABLE, trans_doc)
        except Exception as ex:
            print('Failed to update transcription to DB',ex)
    
    doc = utils.convert_decimal_to_float(doc)
    response = sqs.send_message(QueueUrl=SQS_URL, MessageBody=json.dumps(doc))

    return {
        'statusCode': 200,
        'body': 'Task enqueued.'
    }

def read_vtt(s3_bucket, s3_key):
    # Read transcription file
    s3_clientobj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
    s3_clientdata = s3_clientobj["Body"].read().decode("utf-8")

    subtitles = []
    blocks = re.split(r'\n{2,}', s3_clientdata.strip())
    for block in blocks:
        lines = block.split('\n')
        if len(lines) <= 1:
            continue
        # Extract index, timecodes, and text
        index = int(lines[0]) if lines and lines[0].isdigit() else None
        timecodes = re.findall(r'(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})', lines[1])
        text = '\n'.join(lines[2:]).strip() if len(lines) > 2 else None

        if index is not None and timecodes and text is not None:
            start_ts, end_ts = timecodes[0]
            subtitles.append({
                "start_ts": convert_timestamp_to_ms(start_ts),
                "end_ts": convert_timestamp_to_ms(end_ts),
                "transcription": text
            })
    return subtitles

def convert_timestamp_to_ms(timestamp):
    try:
        # Split the timestamp into hours, minutes, seconds, and milliseconds
        hours, minutes, seconds_ms = timestamp.split(':')
        seconds, milliseconds = seconds_ms.split('.')
        
        # Convert to float and format the result
        result = float(hours) * 3600 + float(minutes) * 60 + float(seconds) + float(f"0.{milliseconds}")
        
        return round(result, 2)  # Round to 2 decimal places
    except ValueError as e:
        print(f"Error converting timestamp: {e}")
        return None
