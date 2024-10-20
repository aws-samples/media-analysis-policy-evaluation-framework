import json
import os
import boto3

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", os.environ['AWS_REGION'])
BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID = os.environ.get("BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID")
BEDROCK_TITAN_TEXT_EMBEDDING_MODEL_ID = os.environ.get("BEDROCK_TITAN_TEXT_EMBEDDING_MODEL_ID")

bedrock = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION) 

def lambda_handler(event, context):
    embedding_type, text_input, image_input = None, None, None
    try:
        embedding_type = event.get("embedding_type", "txt") # txt | mm
        text_input = event.get("text_input")
        image_input = event.get("image_input")
    except Exception as ex:
        print(ex)
        return {
            'statusCode': 400,
            'body': 'Invalid request'
        }
    
    if (text_input is None or len(text_input) == 0) and (image_input is None or len(image_input) == 0):
        return {
            'statusCode': 400,
            'body': 'Invalid request'
        }
    
    embedding = None
    if embedding_type == "txt":
        body = json.dumps({"inputText": f"{text_input}"})
        try:
            response = bedrock.invoke_model(
                body=body, 
                modelId=BEDROCK_TITAN_TEXT_EMBEDDING_MODEL_ID, 
                accept="application/json", 
                contentType="application/json"
            )
            
            response_body = json.loads(response.get("body").read())
            embedding = response_body.get("embedding")
        except Exception as ex:
            print(ex)
    
    elif embedding_type == "mm":
        request_body = {}
        if text_input is not None and len(text_input) > 0:
            request_body["inputText"] = text_input
            
        if image_input:
            request_body["inputImage"] = image_input
        
        body = json.dumps(request_body)
        
        embedding = None
        try:
            response = bedrock.invoke_model(
                body=body, 
                modelId=BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID, 
                accept="application/json", 
                contentType="application/json"
            )
            
            response_body = json.loads(response.get('body').read())
            embedding = response_body.get("embedding")
            
        except Exception as ex:
            print(ex)

    return {
            'statusCode': 400,
            'body': embedding
        }