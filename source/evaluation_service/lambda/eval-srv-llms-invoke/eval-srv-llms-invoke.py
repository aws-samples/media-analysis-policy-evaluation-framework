import json
import boto3
import os

BEDROCK_DEFAULT_MODEL_ID = os.environ.get("BEDROCK_DEFAULT_MODEL_ID")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", os.environ['AWS_REGION'])
BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3 = os.environ.get('BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3')
BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3_MODEL_VERSION = os.environ.get('BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3_MODEL_VERSION')

bedrock_runtime = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION)

def lambda_handler(event, context):
    prompts = event.get("Prompts")
    llm_model_id = event.get("LLMsModelId", BEDROCK_DEFAULT_MODEL_ID)
    config = event.get("LlmConfig")
    
    if prompts is None or len(prompts) == 0:
        return {
            'statusCode': 400,
            'body': f'Invalid request, Prompt is required.'
        }
    
    if not prompts.startswith("Human:"):
        prompts = "Human:" + prompts
    if not prompts.endswith("Assistant:"):
        prompts = prompts + "\nAssistant:"

    # Call bedrock LLM
    result = None
    max_tokens_to_sample=300
    temperature=0
    top_k=250
    top_p=0.999
    if config is not None:
        max_tokens_to_sample = config.get("MaxLength")
        temperature = config.get("Temperature")
        top_k = config.get("TopK")
        top_p = config.get("TopP")

    if llm_model_id.startswith(BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3):
        result = call_bedrock_llm_sonnet(prompts, llm_model_id, max_tokens_to_sample, temperature, top_k, top_p)
    else:
        result = call_bedrock_llm(prompts, llm_model_id, max_tokens_to_sample, temperature, top_k, top_p)

    return {
        'statusCode': 200,
        'body': result
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
