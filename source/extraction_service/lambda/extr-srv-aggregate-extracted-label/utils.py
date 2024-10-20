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
    
def dynamodb_get_by_id(table_name, id, key_name="Id"):
    try:
        video_task_table = dynamodb.Table(table_name)
        response = video_task_table.get_item(Key={key_name: id})
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

def get_items_by_sort_key(table_name, task_id, page_size=1000):
    items = []
    last_evaluated_key = None
    table = dynamodb.Table(table_name)

    while True:
        if last_evaluated_key:
            response = table.query(
                IndexName='task_id-timestamp-index',  # Specify the secondary index name
                KeyConditionExpression=Key('task_id').eq(task_id),  # Use the task_id to query the index
                ExclusiveStartKey=last_evaluated_key,
                Limit=page_size
            )
        else:
            response = table.query(
                IndexName='task_id-timestamp-index',  # Specify the secondary index name
                KeyConditionExpression=Key('task_id').eq(task_id),  # Use the task_id to query the index
                Limit=page_size
            )
        
        if 'Items' in response and len(response['Items']) > 0:
            for item in response['Items']:
                items.append(convert_to_json_serializable(item))

        last_evaluated_key = response.get('LastEvaluatedKey', None)
        
        if not last_evaluated_key:
            break
    
    return items
