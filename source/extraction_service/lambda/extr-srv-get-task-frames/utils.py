import boto3
import numbers,decimal
from boto3.dynamodb.types import TypeDeserializer
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')

def dynamodb_table_upsert(table_name, document):
    try:
        document = convert_to_json_serializable(document)
        table = dynamodb.Table(table_name)
        return table.put_item(Item=document)
    except Exception as e:
        print(f"An error occurred, dynamodb_table_upsert: {e}")
        return None
    
def dynamodb_get_by_id(table_name, id, key_name="Id", sort_key_value=None, sort_key=None):
    try:
        table = dynamodb.Table(table_name)
        response = None
        if sort_key and sort_key_value:
            response = table.get_item(Key={key_name: sort_key_value, sort_key: sort_key})
        else:
            response = table.get_item(Key={key_name: id})
        if 'Item' in response:
            return convert_to_json_serializable(response['Item'])
        else:
            print(f"No item found with id: {document_id}")
            return None
    except Exception as e:
        print(f"An error occurred, dynamodb_get_by_id: {e}")
        return None
    return None

def dynamodb_delete_by_id(table_name, id):
    try:
        response = dynamodb_client.delete_item(
            TableName=table_name,
            Key=id
        )
        print(f"Item with key {key} deleted successfully from table '{table_name}'.")
    except Exception as e:
        print(f"Error deleting item with key {key} from table {table_name}: {str(e)}")


def convert_to_json_serializable(item):
    """
    Recursively convert a DynamoDB item to a JSON serializable format.
    """
    if isinstance(item, dict):
        return {k: convert_to_json_serializable(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [convert_to_json_serializable(v) for v in item]
    elif isinstance(item, float):
        return str(item)
    elif isinstance(item, decimal.Decimal):
        return str(item)
    else:
        return item

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

def count_items_by_task_id(table_name, task_id):
    table = dynamodb.Table(table_name)
    response = table.query(
        IndexName='task_id-timestamp-index', 
        KeyConditionExpression=Key('task_id').eq(task_id), 
        Select='COUNT'
    )
    return response['Count']

import boto3

def get_paginated_items(table_name, task_id, page_size, start_index):
    table = dynamodb.Table(table_name)

    items = []
    exclusive_start_key = None
    current_index = 0

    while True:
        response = None
        if exclusive_start_key:
            response = table.query(
                IndexName='task_id-timestamp-index',  
                KeyConditionExpression=Key('task_id').eq(task_id), 
                ExclusiveStartKey=exclusive_start_key,
                ScanIndexForward=True,
                Limit=page_size
            )
        else:
            response = table.query(
                IndexName='task_id-timestamp-index',  
                KeyConditionExpression=Key('task_id').eq(task_id), 
                ScanIndexForward=True,
                Limit=page_size
            )

        # Add items to the result list if the current index is past the start index
        if current_index >= start_index:
            items.extend(response['Items'][:page_size - len(items)])
            if len(items) >= page_size:
                break
        
        # Update the current index
        current_index += len(response['Items'])

        # Check if there are more items to fetch
        if 'LastEvaluatedKey' not in response:
            break

        # Set the exclusive start key for the next scan
        exclusive_start_key = response['LastEvaluatedKey']

    return items

