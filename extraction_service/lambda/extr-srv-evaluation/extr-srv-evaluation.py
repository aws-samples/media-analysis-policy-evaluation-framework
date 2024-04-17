import json
import boto3
import os
from opensearchpy import OpenSearch
import re

OPENSEARCH_INDEX_NAME_VIDEO_TASK = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TASK")
OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME = os.environ.get("OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME")
OPENSEARCH_DOMAIN_ENDPOINT = os.environ.get("OPENSEARCH_DOMAIN_ENDPOINT")
OPENSEARCH_PORT = os.environ.get("OPENSEARCH_PORT")
OPENSEARCH_INDEX_NAME_VIDEO_TRANS = os.environ.get("OPENSEARCH_INDEX_NAME_VIDEO_TRANS")
BEDROCK_DEFAULT_MODEL_ID = os.environ.get("BEDROCK_DEFAULT_MODEL_ID")

PROMPTS_PLACE_HOLDER_CELEBRITY = os.environ.get("PROMPTS_PLACE_HOLDER_CELEBRITY")
PROMPTS_PLACE_HOLDER_LABELS = os.environ.get("PROMPTS_PLACE_HOLDER_LABELS")
PROMPTS_PLACE_HOLDER_MODERATION = os.environ.get("PROMPTS_PLACE_HOLDER_MODERATION")
PROMPTS_PLACE_HOLDER_TEXT = os.environ.get("PROMPTS_PLACE_HOLDER_TEXT")
PROMPTS_PLACE_HOLDER_KB_POLICY = os.environ.get("PROMPTS_PLACE_HOLDER_KB_POLICY")
PROMPTS_PLACE_HOLDER_TRANSCRIPTION = os.environ.get("PROMPTS_PLACE_HOLDER_TRANSCRIPTION")
PROMPTS_PLACE_HOLDER_IMAGE_CAPTION = os.environ.get("PROMPTS_PLACE_HOLDER_IMAGE_CAPTION")

opensearch_client = OpenSearch(
        hosts=[{'host': OPENSEARCH_DOMAIN_ENDPOINT, 'port': OPENSEARCH_PORT}],
        http_compress=True,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )
bedrock_runtime = boto3.client('bedrock-runtime')
bedrock_agent_runtime_client = boto3.client("bedrock-agent-runtime")

def lambda_handler(event, context):
    task_id, setting, prompts_template, llm_model_id, kb_id, save_to_db = None, None, None, None, None, True
    try: 
        task_id = event["Request"]["TaskId"]
        # Update task status
        opensearch_client.update(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK, id=task_id, body={"doc": {"Status": "extraction_completed"}})
        
        setting = event["Request"]["EvaluationSetting"]
        prompts_template = setting["PromptsTemplate"]
        llm_model_id = setting.get("LLMsModelId")
        kb_id = setting.get("KnowledgeBaseId")
        save_to_db = event.get("SaveToDb", True)
    except Exception as ex:
        return {
            'statusCode': 400,
            'body': f'Invalid request, {ex}'
        }
    
    if prompts_template is None or len(prompts_template) == 0:
        return {
            'statusCode': 400,
            'body': f'Invalid request, PromptsTemplate is required.'
        }
    
    
    # Get injection labels
    metadata = ""
    inj_labels = get_injection_labels(prompts_template)
    if len(inj_labels) > 0:
        for l in inj_labels:
            if l == PROMPTS_PLACE_HOLDER_CELEBRITY:
                celebrities = get_deduped_items(task_id, "detect_celebrity")
                prompts_template = prompts_template.replace(f"##{PROMPTS_PLACE_HOLDER_CELEBRITY}##", celebrities)
                metadata += "Celebrities: " + celebrities
                
            if l == PROMPTS_PLACE_HOLDER_LABELS:
                labels = get_deduped_items(task_id, "detect_label")
                prompts_template = prompts_template.replace(f"##{PROMPTS_PLACE_HOLDER_LABELS}##", labels)
                metadata += "Labels: " + labels
                
            if l == PROMPTS_PLACE_HOLDER_TEXT:
                texts = get_deduped_items(task_id, "detect_text")
                prompts_template = prompts_template.replace(f"##{PROMPTS_PLACE_HOLDER_TEXT}##", texts)
                metadata += "Texts: " + texts
                
            if l == PROMPTS_PLACE_HOLDER_MODERATION:
                modes = get_deduped_items(task_id, "detect_moderation")
                prompts_template = prompts_template.replace(f"##{PROMPTS_PLACE_HOLDER_MODERATION}##", modes)
                metadata += "Moderation labels: " + modes
                
            if l == PROMPTS_PLACE_HOLDER_TRANSCRIPTION:
                trans = get_transcription(task_id)
                if trans:
                    prompts_template = prompts_template.replace(f"##{PROMPTS_PLACE_HOLDER_TRANSCRIPTION}##", trans)
                    metadata += "Transcription: " + trans

            if l == PROMPTS_PLACE_HOLDER_IMAGE_CAPTION:
                texts = get_deduped_items(task_id, "image_caption")
                prompts_template = prompts_template.replace(f"##{PROMPTS_PLACE_HOLDER_IMAGE_CAPTION}##", texts)
                metadata += "Texts: " + texts

    # Call bedrock LLM
    result = evaluation(metadata, prompts_template, kb_id)
    
    # Save evaluation result to DB
    if save_to_db:
        doc = {"EvaluationResult": result, "Status": "evaluation_completed"}
        opensearch_client.update(index=OPENSEARCH_INDEX_NAME_VIDEO_TASK, id=task_id, body={'doc': doc})
    
    return {
        'statusCode': 200,
        'body': event
    }

def evaluation(metadata, prompts_template, kb_id):
    references = [] 

    if kb_id and len(kb_id) > 0:
        # Call bedrock knowledge base to retrieve references
        response = bedrock_agent_runtime_client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={
                'text': metadata
            },
            retrievalConfiguration={
                "vectorSearchConfiguration": { 
                    "numberOfResults": 3
                }
            }
        )
        retrieval_results = response.get("retrievalResults",[])
        policy = ""
        for r in retrieval_results:
            policy += f'\n{r["content"]["text"]}'
        prompts_template = prompts_template.replace(f"##{PROMPTS_PLACE_HOLDER_KB_POLICY}##", policy)
        
        for c in retrieval_results:
            r = {
                    'text':c['content']['text'],
                    's3_location': c['location']['s3Location']['uri']
                }
            if r not in references:
                references.append(r)

    # Call Bedrock LLM to evaluate
    analysis,answer = call_bedrock_llm(prompts_template)
    
    return {
        "answer":answer,
        "analysis":analysis,
        "references":references,
        "prompts": prompts_template
    }

def call_bedrock_llm(prompt):
    body = json.dumps({
            "prompt": prompt,
            "max_tokens_to_sample": 300,
            "temperature": 0,
            "top_k": 250,
            "top_p": 0.999
          })
    response = bedrock_runtime.invoke_model(
        body=body,
        contentType='application/json',
        accept='application/json',
        modelId=BEDROCK_DEFAULT_MODEL_ID
    )

    response_text = json.loads(response.get('body').read()).get("completion")
    analysis = parse_value(response_text,"analysis")
    answer = parse_value(response_text,"answer")

    return analysis,answer

def parse_value(text, key):
    arr = text.split(f'<{key}>')
    if len(arr) > 1:
        arr2 = arr[-1].split(f'</{key}>')
        if len(arr2) > 1:
            return arr2[0]
    return None
    
def get_injection_labels(prompts_template):
    pattern = r'##(.*?)##'
    matches = re.findall(pattern, prompts_template)
    
    result = []
    for m in matches:
        result.append(m.upper())
    return result

def get_deduped_items(task_id, field_name):
    index_name = OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME + task_id
    request={
          "_source": False, 
          "aggs": {
            "distinct": {
              "terms": {
                "field": field_name,
                "size": 100
              }
            }
          }
        }
        
    result = []
    try:
        response = opensearch_client.search(
                index=index_name,
                body=request
            )
        for i in response["aggregations"]["distinct"]["buckets"]:
            result.append(i["key"])
    except Exception as ex:
        print("Failed to retrieve aggreated result from OpenSearch", ex)
    return ",".join(result)

def get_transcription(task_id):
    result = [] 
    try:
        response = opensearch_client.get(index=OPENSEARCH_INDEX_NAME_VIDEO_TRANS, id=task_id)
        result = [' '.join(response["_source"]["subtitles"]["transcription"] for item in items)]
    except Exception as ex:
        print("Failed to retrieve transcription from OpenSearch", ex)
    return "\n".join(result)
