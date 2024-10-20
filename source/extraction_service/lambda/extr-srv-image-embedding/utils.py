import boto3
import numbers,decimal
from boto3.dynamodb.types import TypeDeserializer

dynamodb = boto3.resource('dynamodb')

def dynamodb_table_upsert(table_name, document):
    try:
        document = convert_to_json_serializable(document)
        video_task_table = dynamodb.Table(table_name)
        return video_task_table.put_item(Item=document)
    except Exception as e:
        print(f"An error occurred, dynamodb_table_upsert: {e}")
        return None
    
def dynamodb_get_by_id(table_name, id, key_name="Id", sort_key_value=None, sort_key=None):
    try:
        table = dynamodb.Table(table_name)
        response = None
        if sort_key and sort_key_value:
            response = table.get_item(Key={key_name: id, sort_key: sort_key_value})
        else:
            response = table.get_item(Key={key_name: id})
        if 'Item' in response:
            return convert_to_json_serializable(response['Item'])
        else:
            print(f"No item found with id: {id}")
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
        return str(item)
    elif isinstance(item, decimal.Decimal):
        return str(item)
    else:
        return item
