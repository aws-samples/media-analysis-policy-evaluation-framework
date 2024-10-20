import json
import boto3
import os

DYNAMO_VIDEO_ANALYSIS_TABLE = os.environ.get("DYNAMO_VIDEO_ANALYSIS_TABLE")
S3_PRESIGNED_URL_EXPIRY_S = os.environ.get("S3_PRESIGNED_URL_EXPIRY_S", 3600) # Default 1 hour 
DEFAULT_PAGE_SIZE = 10

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
video_analysis_table = dynamodb.Table(DYNAMO_VIDEO_ANALYSIS_TABLE)

def lambda_handler(event, context):
    task_id = event.get("TaskId")

    if not task_id:
        return {
            'statusCode': 400,
            'body': 'Task Id is required.'
        }
    page_size = event.get("PageSize", DEFAULT_PAGE_SIZE)
    from_index = event.get("FromIndex", 0)

    # Get analysis result from DB
    items = []
    try:
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
            items.extend(response.get('Items', []))
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
    except Exception as ex:
        print(ex)
        return {
            'statusCode': 400,
            'body': f'Task {task_id} does not exist.'
        }

    # Sort items by start_ts
    items = sorted(items, key=lambda x: x['index'], reverse=False)

    # Pagination
    total = len(items)
    to_index = from_index + page_size
    if to_index > len(items):
        to_index = len(items)
    items = items[from_index:to_index]

    result = {
        "Total": total,
        "Shots": []
    }
    # Include frame information
    for s in items:
        item = {
            "Index": s["index"],
            "Summary": s.get("summary"),
            "StartTs": s["start_ts"],
            "EndTs": s["end_ts"],
            "Duration": s["duration"],
            "Frames": [],
        }
        for f in s.get("frames",[]):
            item["Frames"].append(
                {
                    "S3Url": s3.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': f["s3_bucket"], 'Key': f["s3_key"]},
                        ExpiresIn=S3_PRESIGNED_URL_EXPIRY_S
                    ),
                    "Timestamp": f["timestamp"],
                    "ImageCaption": f.get("image_caption"),
                    "Subtitles": f.get("subtitles"),
                    "SimilarityScore": f.get("similarity_score"),
                }
            )

        result["Shots"].append(item)

    return {
        'statusCode': 200,
        'body': result
    }
