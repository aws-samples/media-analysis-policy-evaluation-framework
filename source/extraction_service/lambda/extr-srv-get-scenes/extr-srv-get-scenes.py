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
    scenes = []
    try:
        last_evaluated_key = None
        # Keep querying until there are no more pages of results
        while True:
            query_params = {
                'IndexName': 'task_id-analysis_type-index',  # Name of your index
                'KeyConditionExpression': 'task_id = :task_id_val AND analysis_type = :type_val',
                'ExpressionAttributeValues': {
                    ':task_id_val': task_id,
                    ':type_val': 'scene'
                }
            }
            if last_evaluated_key:
                query_params['ExclusiveStartKey'] = last_evaluated_key

            response = video_analysis_table.query(**query_params)
            scenes.extend(response.get('Items', []))
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
    except Exception as ex:
        print(ex)
        return {
            'statusCode': 400,
            'body': f'Task {task_id} does not exist.'
        }

    # Sort scenes by start_ts
    scenes = sorted(scenes, key=lambda x: x['index'], reverse=False)

    # Pagination
    total = len(scenes)
    to_index = from_index + page_size
    if to_index > len(scenes):
        to_index = len(scenes)
    scenes = scenes[from_index:to_index]

    result = {
        "Total": total,
        "Scenes": []
    }
    # Include frame information
    for s in scenes:
        item = {
            "Index": s["index"],
            "Summary": s.get("summary"),
            "StartTs": s["start_ts"],
            "EndTs": s["end_ts"],
            "Duration": s["end_ts"] - s["start_ts"],
            "Shots": [],
        }
        for sh in s.get("shots", []):
            shot = {
                "Index": sh.get("index"),
                "Summary": sh.get("Summary"),
                "StartTs": sh.get("start_ts"),
                "EndTs": sh.get("end_ts"),
                "Duration": sh.get("duration"),
                "Frames": []
            }
            for f in sh.get("frames",[]):
                shot["Frames"].append(
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
                shot["Frames"] = sorted(shot["Frames"], key=lambda x:x["Timestamp"], reverse=False)
            item["Shots"].append(shot)
            item["Shots"] = sorted(item["Shots"], key=lambda x: x['Index'], reverse=False)

        result["Scenes"].append(item)

    return {
        'statusCode': 200,
        'body': result
    }
