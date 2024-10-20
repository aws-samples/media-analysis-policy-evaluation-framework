import boto3
import numbers,decimal
from boto3.dynamodb.types import TypeDeserializer
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')

def dynamodb_table_upsert(table_name, document):
    try:
        document = convert_to_json_serializable(document)
        video_task_table = dynamodb.Table(table_name)
        return video_task_table.put_item(Item=document)
    except Exception as e:
        print(f"An error occurred, dynamodb_table_upsert: {e}")
        return None
    
def dynamodb_get_by_id(table_name, id, key_name="Id"):
    try:
        task_table = dynamodb.Table(table_name)
        response = task_table.get_item(Key={key_name: id})
        if 'Item' in response:
            return convert_to_json_serializable(response['Item'])
        else:
            print(f"No item found with id: {id}")
            return None
    except Exception as e:
        print(f"An error occurred, dynamodb_get_by_id: {e}")
        return None
    return None

def dynamodb_delete_frames_by_taskid(table_name, task_id):
    #try:
        table = dynamodb.Table(table_name)

        pagination_token = None

        # Loop until all items are deleted
        while True:
            # Query for items with the given task_id
            if pagination_token:
                response = table.query(
                    IndexName=table_name,
                    KeyConditionExpression=Key('task_id').eq(task_id),  # Use the task_id to query the index
                    ExclusiveStartKey=last_evaluated_key,
                    Limit=1000
                )
            else:
                response = table.query(
                    IndexName='task_id-timestamp-index',  # Specify the secondary index name
                    KeyConditionExpression=Key('task_id').eq(task_id),  # Use the task_id to query the index
                    Limit=1000
                )

            # Delete each item returned by the query
            for item in response['Items']:
                table.delete_item(
                    Key={
                        'id': item['id'],  # Replace with your partition key name
                        'task_id': item['task_id']  # Replace with your sort key name
                    }
                )

            # Check if there are more items to fetch
            if 'LastEvaluatedKey' in response:
                pagination_token = response['LastEvaluatedKey']
            else:
                break
    #except Exception as e:
    #    print(f"Error deleting items from table {table_name}: {str(e)}")

def dynamodb_delete_trans_by_taskid(table_name, task_id):
    try:
        table = dynamodb.Table(table_name)
        response = table.delete_item(
            Key={"task_id": task_id}
        )
    except Exception as e:
        print(f"Error deleting item with id {id} from table {table_name}: {str(e)}")

def dynamodb_delete_task_by_id(table_name, task_id):
    try:
        table = dynamodb.Table(table_name)
        response = table.delete_item(
            Key={"Id": task_id}
        )
    except Exception as e:
        print(f"Error deleting item with id {id} from table {table_name}: {str(e)}")

def dynamodb_task_update_status(table_name, task_id, new_status):    
    try:
        response = dynamodb.update_item(
            TableName=table_name,
            Key={
                'Id': {'S': task_id}
            },
            UpdateExpression="SET #status = :new_status",
            ExpressionAttributeNames={
                '#status': 'Status'
            },
            ExpressionAttributeValues={
                ':new_status': {'S': new_status}
            },
            ReturnValues="UPDATED_NEW"
        )
        print(f"Update succeeded: {response}")
    except Exception as e:
        print(f"Error updating item in table {table_name}: {str(e)}")

def convert_to_json_serializable(item):
    """
    Recursively convert a DynamoDB item to a JSON serializable format.
    """
    if isinstance(item, dict):
        return {k: convert_to_json_serializable(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [convert_to_json_serializable(v) for v in item]
    elif isinstance(item, float):
        return decimal.Decimal(item)
    #elif isinstance(item, decimal.Decimal):
    #    return str(item)
    else:
        return item

import boto3

def update_video_task_metadata(table_name, task_id, metadata):
    table = dynamodb.Table(table_name)
    try:
        response = table.update_item(
            Key={"Id": task_id},
            UpdateExpression="SET MetaData = :val",
            ExpressionAttributeValues={
                ':val': metadata
            },
            ReturnValues="UPDATED_NEW"
        )
        return response
    except Exception as e:
        print(f"Error updating item: {e}")
        return None
