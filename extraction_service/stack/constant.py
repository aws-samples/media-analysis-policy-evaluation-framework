COGNITO_NAME_PREFIX = "content-analysis-user-pool"
STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX = 'content-analysis-extraction-flow'
API_NAME_PREFIX = 'content-analysis-extraction-service'

VIDEO_EXTRACTION_CONCURRENT_LIMIT = "1" # Number of videos processed concurrently
VIDEO_IMAGE_EXTRACTION_CONCURRENT_LIMIT = "10" # Number of images processed concurrently by extraction workflow
VIDEO_EXTRACTION_WORKFLOW_TIMEOUT_HR = "5" # Step function state machine video extraction workflow timeout
VIDEO_SAMPLE_CHUNK_DURATION_S = "600" # For extraction workflow. Default 10 minutes means the flow will sample 10 minutes of the given video at a time to prevent Lambda timeout.

S3_BUCKET_EXTRACTION_PREFIX = 'content-analysis-extr'
S3_PRE_SIGNED_URL_EXPIRY_S = "3600" # 1 hour
TRANSCRIBE_JOB_PREFIX = 'video_analysis_'
TRANSCRIBE_OUTPUT_PREFIX = 'transcribe'
VIDEO_SAMPLE_FILE_PREFIX = "video_frame_"
VIDEO_SAMPLE_S3_PREFIX = "video_frame_"
VIDEO_UPLOAD_S3_PREFIX = 'upload'
LAMBDA_LAYER_SOURCE_S3_KEY_OPENSEARCHPY = "layer/opensearchpy_layer.zip"
LAMBDA_LAYER_SOURCE_S3_KEY_MOVIEPY = "layer/moviepy_layer.zip"

OPENSEARCH_DOMAIN_NAME_PREFIX = "content-analysis"
OPENSEARCH_PORT = "443"
OPENSEARCH_INDEX_NAME_VIDEO_TASK = "video_task"
OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME	= "video_frame_"
OPENSEARCH_INDEX_NAME_VIDEO_TRANS = "video_transcription"
OPENSEARCH_INDEX_NAME_VIDEO_TASK_MAPPING = '''{"mappings":{"dynamic_templates":[{"strings":{"match_mapping_type":"string","mapping":{"type":"text"}}},{"nested_objects":{"match":"*","match_mapping_type":"object","mapping":{"type":"nested"}}}]}}'''
OPENSEARCH_INDEX_NAME_VIDEO_TRANS_MAPPING = '''{"mappings":{"properties":{"language_code":{"type":"keyword"},"transcription":{"type":"text","fielddata":true,"fields":{"raw":{"type":"keyword"}}},"subtitles":{"type":"nested","properties":{"start_ts":{"type":"float"},"end_ts":{"type":"float"},"transcription":{"type":"text"}}}}}}'''
OPENSEARCH_VIDEO_FRAME_INDEX_MAPPING = '''{"settings":{"index.knn":true,"number_of_shards":2},"mappings":{"properties":{"mm_embedding":{"type":"knn_vector","dimension":1024,"method":{"name":"hnsw","engine":"lucene","space_type":"l2","parameters":{}}},"text_embedding":{"type":"knn_vector","dimension":1536},"timestamp":{"type":"double"},"image_s3_uri":{"type":"text","index":false},"subtitle":{"type":"text","fielddata":true,"fields":{"raw":{"type":"keyword"}}}}}}'''
OPENSEARCH_DEFAULT_K = "20"
OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_TEMP_PREFIX = 'video_frame_similiarity_check_temp_'
OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD = '1.7'
OPENSEARCH_VIDEO_FRAME_SIMILAIRTY_INDEX_MAPPING = '{"mappings":{"properties":{"mm_embedding":{"type":"knn_vector","dimension":1024,"method":{"name":"hnsw","engine":"lucene","space_type":"l2","parameters":{}}}}}}'

REK_MIN_CONF_DETECT_CELEBRITY = "90"
REK_MIN_CONF_DETECT_LABEL = "80"
REK_MIN_CONF_DETECT_MODERATION = "70"
REK_MIN_CONF_DETECT_TEXT = "60"

BEDROCK_DEFAULT_MODEL_ID = "anthropic.claude-v2:1"
BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID = "amazon.titan-embed-image-v1"
PROMPTS_PLACE_HOLDER_CELEBRITY = "CELEBRITY"
PROMPTS_PLACE_HOLDER_IMAGE_CAPTION = "IMAGE_CAPTION"
PROMPTS_PLACE_HOLDER_KB_POLICY = "KB_POLICY"
PROMPTS_PLACE_HOLDER_LABELS = "LABEL"