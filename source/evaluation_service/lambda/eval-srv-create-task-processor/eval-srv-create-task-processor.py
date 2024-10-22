import json
import boto3
import utils
import os
from datetime import datetime, timezone

DYNAMO_EVAL_TASK_TABLE = os.environ.get("DYNAMO_EVAL_TASK_TABLE")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", os.environ['AWS_REGION'])
BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3 = os.environ.get("BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3")
BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3_MODEL_VERSION = os.environ.get("BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3_MODEL_VERSION")

bedrock_runtime = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION)

def lambda_handler(event, context):
    task_id, receipt_handle=None, None
    try:
        receipt_handle = event["Records"][0]["receiptHandle"]
        task_id = json.loads(event["Records"][0]["body"])["task_id"]
    except Exception as ex:
        print(ex)
        return {
            'statusCode': 400,
            'body': 'Invalid message'
        }

    task = utils.dynamodb_get_by_id(DYNAMO_EVAL_TASK_TABLE, task_id, "Id")

    # Call bedrock LLM
    result = None
    max_tokens_to_sample= 300
    temperature=0
    top_k=250
    top_p=0.999
    
    llm_model_id = task.get("LlmModelId")
    prompts = task.get("Prompts")
    config = task.get("Config")
    if config:
        max_tokens_to_sample = config.get("MaxTokensToSample")
        temperature = config.get("Temperature")
        top_k = config.get("TopK")
        top_p = config.get("TopP")

    status, result = None, None
    try:
        if llm_model_id.startswith(BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3):
            result = call_bedrock_llm_sonnet(prompts, llm_model_id, max_tokens_to_sample, temperature, top_k, top_p)
        else:
            result = call_bedrock_llm(prompts, llm_model_id, max_tokens_to_sample, temperature, top_k, top_p)
        status = "completed"
    except Exception as ex:
        print(ex)
        status = "failed"
        
    # Update DB
    task["Result"] = result.get("response")
    task["Status"] = status
    task["CompleteBy"] = datetime.now(timezone.utc).isoformat()
    utils.dynamodb_table_upsert(DYNAMO_EVAL_TASK_TABLE, task)
    
    return {
            'statusCode': 200,
            'body': task
        }

def call_bedrock_llm_sonnet (prompt, llm_model_id, max_tokens_to_sample, temperature, top_k, top_p):
    body = json.dumps({
            "anthropic_version": BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3_MODEL_VERSION,
            "max_tokens": max_tokens_to_sample,
            "messages": [
              {
                "role": "user",
                "content": [
                  {
                    "type": "text",
                    "text": prompt
                  }
                ]
              }
            ]
          }
        )
    response = bedrock_runtime.invoke_model(
        body=body,
        contentType='application/json',
        accept='application/json',
        modelId=llm_model_id
    )

    response_text = response_text = json.loads(response.get('body').read())["content"][0]["text"]
    return {
        "response":response_text
    }
        
def call_bedrock_llm(prompt, llm_model_id, max_tokens_to_sample, temperature, top_k, top_p):
    body = json.dumps({
            "prompt": prompt,
            "max_tokens_to_sample": max_tokens_to_sample,
            "temperature": temperature,
            "top_k": top_k,
            "top_p": top_p
          })
    response = bedrock_runtime.invoke_model(
        body=body,
        contentType='application/json',
        accept='application/json',
        modelId=llm_model_id
    )

    response_text = json.loads(response.get('body').read()).get("completion")
    return {
        "response":response_text
    }
