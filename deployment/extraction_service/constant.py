COGNITO_NAME_PREFIX = "video-analysis-user-pool"
STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX = 'video-analysis-extraction-flow'
API_NAME_PREFIX = 'video-analysis-extraction-service'

VIDEO_EXTRACTION_CONCURRENT_LIMIT = "1" # Number of videos processed concurrently
VIDEO_IMAGE_EXTRACTION_CONCURRENT_LIMIT = "10" # Max number of images processed concurrently by extraction workflow
VIDEO_IMAGE_EXTRACTION_SAMPLE_CONCURRENT_LIMIT = "2" # Max numbers of sampling tasks processed concurrently
VIDEO_EXTRACTION_WORKFLOW_TIMEOUT_HR = "5" # Step function state machine video extraction workflow timeout
VIDEO_SAMPLE_CHUNK_DURATION_S = "600" # For extraction workflow. Default 10 minutes means the flow will sample 10 minutes of the given video at a time to prevent Lambda timeout.

S3_BUCKET_EXTRACTION_PREFIX = 'video-analysis-extr'
S3_PRE_SIGNED_URL_EXPIRY_S = "3600" # 1 hour
TRANSCRIBE_JOB_PREFIX = 'video_analysis_'
TRANSCRIBE_OUTPUT_PREFIX = 'transcribe'
VIDEO_SAMPLE_FILE_PREFIX = "video_frame_"
VIDEO_SAMPLE_S3_PREFIX = "video_frame_"
VIDEO_UPLOAD_S3_PREFIX = 'upload'
LAMBDA_LAYER_SOURCE_S3_KEY_OPENSEARCHPY = "layer/opensearchpy_layer.zip"
LAMBDA_LAYER_SOURCE_S3_KEY_MOVIEPY = "layer/moviepy_layer.zip"
LAMBDA_LAYER_SOURCE_S3_KEY_LANGCHAIN = "layer/langchain_layer.zip"

SECRET_MANAGER_PREFIX = "prod/shoppable/"
SECRET_MANAGER_OPENSEARCH_LOGIN_KEY = "opensearchlogin"
OPENSERACH_USER_NAME = "extr_srv_admin"
OPENSEARCH_DOMAIN_NAME_PREFIX = "video-analysis"
OPENSEARCH_PORT = "443"
OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME	= "video_frame_"
OPENSEARCH_VIDEO_FRAME_INDEX_MAPPING = '''{"settings":{"index.knn":true,"number_of_shards":2},"mappings":{"properties":{"mm_embedding":{"type":"knn_vector","dimension":1024,"method":{"name":"hnsw","space_type":"l2","engine":"faiss"}},"text_embedding":{"type":"knn_vector","dimension":1536,"method":{"name":"hnsw","space_type":"l2","engine":"faiss"}},"timestamp":{"type":"double"},"task_id":{"type":"text","fields":{"keyword":{"type":"keyword","ignore_above":256}}}}}}'''
OPENSEARCH_DEFAULT_K = "20"
OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_TEMP_PREFIX = 'video_frame_similiarity_check_temp_'
OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD = '1.7'
OPENSEARCH_VIDEO_FRAME_SIMILAIRTY_INDEX_MAPPING = '{"mappings":{"properties":{"mm_embedding":{"type":"knn_vector","dimension":1024,"method":{"name":"hnsw","engine":"lucene","space_type":"l2","parameters":{}}}}}}'
OPENSEARCH_SHARD_SIZE_LIMIT = "104857600" # 100M

DYNAMO_VIDEO_TASK_TABLE = "extr_srv_video_task"
DYNAMO_VIDEO_TRANS_TABLE = "extr_srv_video_transcription"
DYNAMO_VIDEO_FRAME_TABLE = "extr_srv_video_frame"
DYNAMO_VIDEO_ANALYSIS_TABLE = "extr_srv_video_analysis"

REK_MIN_CONF_DETECT_CELEBRITY = "90"
REK_MIN_CONF_DETECT_LABEL = "80"
REK_MIN_CONF_DETECT_MODERATION = "70"
REK_MIN_CONF_DETECT_TEXT = "60"

BEDROCK_DEFAULT_MODEL_ID = "anthropic.claude-v2:1"
BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID = "amazon.titan-embed-image-v1"
BEDROCK_TITAN_TEXT_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
BEDROCK_ANTHROPIC_CLAUDE_HAIKU = "anthropic.claude-3-haiku-20240307-v1:0"
BEDROCK_ANTHROPIC_CLAUDE_HAIKU_MODEL_VERSION = "bedrock-2023-05-31"
BEDROCK_ANTHROPIC_CLAUDE_SONNET_V35="anthropic.claude-3-sonnet-20240229-v1:0"
PROMPTS_PLACE_HOLDER_CELEBRITY = "CELEBRITY"
PROMPTS_PLACE_HOLDER_IMAGE_CAPTION = "IMAGE_CAPTION"
PROMPTS_PLACE_HOLDER_KB_POLICY = "KB_POLICY"
PROMPTS_PLACE_HOLDER_LABELS = "LABEL"
VIDEO_FRAME_SIMILAIRTY_THRESHOLD_FAISS = '0.8'