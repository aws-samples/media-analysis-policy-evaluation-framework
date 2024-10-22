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
    
def get_frame_by_id(table_name, frame_id, task_id):
    try:
        video_task_table = dynamodb.Table(table_name)
        response = video_task_table.get_item(Key={"id": frame_id, "task_id": task_id})
        if 'Item' in response:
            return convert_to_json_serializable(response['Item'])
        else:
            print(f"No item found with id: {document_id}")
            return None
    except Exception as e:
        print(f"An error occurred, dynamodb_get_by_id: {e}")
        return None
    return None

def dynamodb_delete_by_id(table_name, id, task_id):
    try:
        table = dynamodb.Table(table_name)
        return table.delete_item(
            Key={"id":id, "task_id": task_id}
        )
    except Exception as e:
        print(f"Error deleting item with id {id} from table {table_name}: {str(e)}")
    return None

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


def update_item_with_similarity_score(table_name, frame_id, task_id, similarity_score):
    table = dynamodb.Table(table_name)

    # Update the item to add the new field "similarity_score"
    response = table.update_item(
        Key={
            'id': frame_id,
            "task_id": task_id
        },
        UpdateExpression='SET similarity_score = :val',
        ExpressionAttributeValues={
            ':val': decimal.Decimal(str(similarity_score))  # Convert the similarity_score to Decimal if it's a float
        },
        ReturnValues="UPDATED_NEW"
    )

    return response

def convert_to_json_serializable(item):
    """
    Recursively convert a DynamoDB item to a JSON serializable format.
    """
    if isinstance(item, dict):
        return {k: convert_to_json_serializable(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [convert_to_json_serializable(v) for v in item]
    elif isinstance(item, float):
        return decimal.Decimal(str(item))
    #elif isinstance(item, decimal.Decimal):
    #    return str(item)
    else:
        return item
        