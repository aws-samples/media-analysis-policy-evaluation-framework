import json
import os
import utils

DYNAMO_EVAL_TASK_TABLE = os.environ.get("DYNAMO_EVAL_TASK_TABLE")

def lambda_handler(event, context):
    id = event.get("Id")
    if id is None:
        return {
            'statusCode': 400,
            'body': json.dumps('Require Id')
        }

    # Delete DB entries
    try:
        utils.dynamodb_delete_task_by_id(DYNAMO_EVAL_TASK_TABLE, id)
    except Exception as ex:
        print(f"Failed to delete index: {DYNAMO_EVAL_TASK_TABLE}", ex)

    return {
        'statusCode': 200,
        'body': json.dumps('Task deleted!')
    }
