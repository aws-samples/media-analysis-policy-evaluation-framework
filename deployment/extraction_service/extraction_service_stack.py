from aws_cdk import (
    Stack,
    NestedStack,
    Size,
    aws_ec2 as ec2,
    CfnParameter as _cfnParameter,
    aws_cognito as _cognito,
    aws_s3 as _s3,
    aws_s3_notifications as _s3_noti,
    aws_lambda as _lambda,
    aws_apigateway as _apigw,
    aws_iam as _iam,
    aws_sqs as _sqs,
    aws_opensearchservice as opensearch,
    aws_lambda_event_sources as lambda_event_sources,
    aws_dynamodb as _dynamodb,
    Duration,
    aws_stepfunctions as _aws_stepfunctions,
    RemovalPolicy,
    custom_resources as cr,
    CustomResource,
    Token,
    Fn,
    CfnResource,
    custom_resources,
    aws_logs as logs,
    CfnCondition as condition,
    CfnOutput
)
from aws_cdk.aws_apigateway import IdentitySource
from aws_cdk.aws_kms import Key
from aws_cdk.aws_ec2 import SecurityGroup

from constructs import Construct
import os
import uuid
import json
from extraction_service.constant import *

class ExtractionServiceStack(NestedStack):
    account_id = None
    region = None
    instance_hash = None
    api_gw_base_url = None
    cognito_user_pool_id = None
    cognito_app_client_id = None
    s3_bucket_name_extraction = None
    opensearch_domain = None
    opensearch_domain_endpoint = None
    vpc = None
    vpc_name = None
    bastion_host_id = None
    auth_mode = None
    api_key_value = None
    opensearch_security_group = None

    s3_extraction_bucket = None
    cognito_authorizer = None
    opensearch_layer = None
    langchain_layer = None
    sf_state_machine = None
    api = None
    delete_task_q = None
    lambda_arn_gen_embedding = None
    
    def __init__(self, scope: Construct, construct_id: str, 
            instance_hash_code, opensearch_config, s3_bucket_name_extraction, 
            transcribe_region, rekognition_region, bedrock_region,
            auth_mode="cognito_authorizer", **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.account_id=os.environ.get("CDK_DEFAULT_ACCOUNT")
        self.region=os.environ.get("CDK_DEFAULT_REGION")
        
        self.instance_hash = instance_hash_code
        self.opensearch_config = opensearch_config
        self.auth_mode= auth_mode
        self.s3_bucket_name_extraction = s3_bucket_name_extraction

        self.transcribe_region = transcribe_region
        self.rekognition_region = rekognition_region
        self.bedrock_region = bedrock_region

        self.deploy_opensearch_with_vpc()
        self.deploy_dynamodb()
        self.deploy_s3()
        self.deploy_cognito()
        self.deploy_step_function()
        self.deploy_sqs()
        self.deploy_delete_task_sqs()
        self.deploy_apigw()

    def deploy_opensearch_with_vpc(self):
        # Launch OpenSearch with VPC stack: start
        # VPC
        self.vpc_name = f"OpenSearchVpc{self.instance_hash}"
        self.vpc = ec2.Vpc(self, id=f"OpenSearchVpc{self.instance_hash}",
            vpc_name=self.vpc_name,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
                )
            ],
            ip_addresses=ec2.IpAddresses.cidr(self.opensearch_config["default_vpc_cidr"])
        )

        # Create a flow log
        flow_log = ec2.FlowLog(
            self, "OpenSearchFlowLog",
            resource_type=ec2.FlowLogResourceType.from_vpc(self.vpc),
            traffic_type=ec2.FlowLogTrafficType.ALL,
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(),
        )


        # Security Group
        bastion_security_group = SecurityGroup(
            self, f"BastionSecurityGroup{self.instance_hash}",
            vpc=self.vpc,
            allow_all_outbound=True,
            security_group_name="BastionSecurityGroup"
        )
        # Add an ingress rule to allow traffic on port 443
        bastion_security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(int(OPENSEARCH_PORT)),
            description="Bastion host security group - allow inbound HTTPS traffic"
        )

        self.opensearch_security_group = SecurityGroup(
            self, f"OpensearchSecurityGroup{self.instance_hash}",
            vpc=self.vpc,
            security_group_name=f"OpensearchSecurityGroup{self.instance_hash}",
            description="Opensearch security group"
        )
        # Add an ingress rule to allow traffic on port 443
        self.opensearch_security_group.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(int(OPENSEARCH_PORT)),
            description="Allow inbound HTTPS traffic"
        )

        # Bastion host to access Opensearch Dashboards
        bastion_host = ec2.BastionHostLinux(
            self, f"BastionHost{self.instance_hash}",
            vpc=self.vpc,
            security_group=bastion_security_group,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(volume_size=10, encrypted=True)
                )
            ]
        )

        # OpenSearch domain
        self.opensearch_domain = opensearch.Domain(
            self, f"OpenSearchDomain{self.instance_hash}",
            domain_name=f'{OPENSEARCH_DOMAIN_NAME_PREFIX}{self.instance_hash}',
            version=opensearch.EngineVersion.OPENSEARCH_2_7,
            node_to_node_encryption=True,
            enforce_https=True,
            encryption_at_rest=opensearch.EncryptionAtRestOptions(enabled=True),
            vpc=self.vpc,
            removal_policy=RemovalPolicy.DESTROY,
            security_groups=[self.opensearch_security_group],
            capacity=opensearch.CapacityConfig(
                    master_nodes=self.opensearch_config["master_nodes"],
                    master_node_instance_type=self.opensearch_config["master_node_instance_type"],
                    data_nodes=self.opensearch_config["data_nodes"],
                    data_node_instance_type=self.opensearch_config["data_node_instance_type"],
                ),
            ebs=opensearch.EbsOptions(
                        volume_size=self.opensearch_config["ebs_volume_size_gb"],
                        volume_type=ec2.EbsDeviceVolumeType.GP2
                    ),
            zone_awareness=None,
            vpc_subnets=[{
                    'subnets':  [item for item in self.vpc.private_subnets][:self.opensearch_config["subnets_count"]],
                }],
            logging=opensearch.LoggingOptions(
                slow_search_log_enabled=True,
                slow_index_log_enabled=True
            )
        )

        self.opensearch_domain.add_access_policies(
            _iam.PolicyStatement(
                principals=[_iam.AnyPrincipal()],
                actions=["es:ESHttp*"],
                resources=[f"{self.opensearch_domain.domain_arn}/*"]
            )
        )

        # Outputs
        self.opensearch_domain_arn = self.opensearch_domain.domain_arn
        self.opensearch_domain_endpoint = self.opensearch_domain.domain_endpoint
        self.bastion_host_id = bastion_host.instance_id

        # Launch OpenSearch with VPC stack: end

    def deploy_dynamodb(self):
        # Create DynamoDB tables
        # Video task table                           
        video_task_table = _dynamodb.Table(self, 
            id='video-task-table', 
            table_name=DYNAMO_VIDEO_TASK_TABLE, 
            partition_key=_dynamodb.Attribute(name='Id', type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        )
        video_task_table.add_global_secondary_index(
            index_name="RequestBy-index",
            partition_key=_dynamodb.Attribute(
                name="RequestBy",
                type=_dynamodb.AttributeType.STRING
            ),
            projection_type=_dynamodb.ProjectionType.ALL 
        )
        # Video transcription table
        video_trans_table = _dynamodb.Table(self, 
            id='video-trans-table', 
            table_name=DYNAMO_VIDEO_TRANS_TABLE, 
            partition_key=_dynamodb.Attribute(name='task_id', type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        ) 
        # Video frame table
        video_frame_table = _dynamodb.Table(self, 
            id='video-frame-table', 
            table_name=DYNAMO_VIDEO_FRAME_TABLE, 
            partition_key=_dynamodb.Attribute(name='id', type=_dynamodb.AttributeType.STRING),
            sort_key=_dynamodb.Attribute(name='task_id', type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        ) 
        video_frame_table.add_global_secondary_index(
            index_name="task_id-timestamp-index",
            partition_key=_dynamodb.Attribute(
                name="task_id",
                type=_dynamodb.AttributeType.STRING
            ),
            sort_key=_dynamodb.Attribute(
                name="timestamp",
                type=_dynamodb.AttributeType.NUMBER
            ),
            projection_type=_dynamodb.ProjectionType.ALL 
        )
        # Video analysis table: shot and scene
        video_analysis_table = _dynamodb.Table(self, 
            id='video-analysis-table', 
            table_name=DYNAMO_VIDEO_ANALYSIS_TABLE, 
            partition_key=_dynamodb.Attribute(name='id', type=_dynamodb.AttributeType.STRING),
            sort_key=_dynamodb.Attribute(name='task_id', type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        ) 
        video_analysis_table.add_global_secondary_index(
            index_name="task_id-analysis_type-index",
            partition_key=_dynamodb.Attribute(
                name="task_id",
                type=_dynamodb.AttributeType.STRING
            ),
            sort_key=_dynamodb.Attribute(
                name="analysis_type",
                type=_dynamodb.AttributeType.STRING
            ),
            projection_type=_dynamodb.ProjectionType.ALL 
        )

    def deploy_s3(self):
        if self.s3_bucket_name_extraction:
            self.s3_extraction_bucket = _s3.Bucket.from_bucket_name(self, "ExtractionBucket", bucket_name=self.s3_bucket_name_extraction)
        else:
            # Create extraction S3 bucket
            self.s3_bucket_name_extraction = f'{S3_BUCKET_EXTRACTION_PREFIX}-{self.account_id}-{self.region}{self.instance_hash}'
            self.s3_extraction_bucket = _s3.Bucket(self, "ExtractionBucket", 
                bucket_name=self.s3_bucket_name_extraction,
                removal_policy=RemovalPolicy.DESTROY,
                auto_delete_objects=True,
                server_access_logs_prefix="access-log",
                enforce_ssl=True,
                cors=[_s3.CorsRule(
                    allowed_methods=[_s3.HttpMethods.GET, _s3.HttpMethods.POST, _s3.HttpMethods.PUT, _s3.HttpMethods.DELETE, _s3.HttpMethods.HEAD],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    exposed_headers=["ETag"],
                )])

    def deploy_cognito(self):
        # Create Cognitio User pool and authorizer
        user_pool = _cognito.UserPool(self, "WebUserPool",
            user_pool_name=f"{COGNITO_NAME_PREFIX}{self.instance_hash}",
            self_sign_up_enabled=False,
            password_policy=_cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
                temp_password_validity=Duration.days(7)
            ),
            advanced_security_mode=_cognito.AdvancedSecurityMode.ENFORCED,
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.cognito_user_pool_id = user_pool.user_pool_id

        web_client = user_pool.add_client("AppClient", 
            auth_flows=_cognito.AuthFlow(
                user_password=True,
                user_srp=True
            ),
            supported_identity_providers=[_cognito.UserPoolClientIdentityProvider.COGNITO],
        )
        self.cognito_app_client_id = web_client.user_pool_client_id

        # Create API Gateway CognitioUeserPoolAuthorizer
        self.cognito_authorizer = _apigw.CognitoUserPoolsAuthorizer(self, f"WebAuth{self.instance_hash}", 
            cognito_user_pools=[user_pool],
            identity_source=IdentitySource.header('Authorization')
        )

    def deploy_step_function(self):
        # Create Lambda Layers which will be used by later Lambda deployment
        layer_bucket = _s3.Bucket.from_bucket_name(self, "LayerBucket", bucket_name=self.s3_extraction_bucket.bucket_name)
        self.opensearch_layer = _lambda.LayerVersion(self, 'OpenSearchPyLayer',
            code=_lambda.S3Code(bucket=layer_bucket, key=LAMBDA_LAYER_SOURCE_S3_KEY_OPENSEARCHPY),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Python 3.12 with opensearch-py and boto3"
        )
        self.langchain_layer = _lambda.LayerVersion(self, 'LangChainFaissLayer',
            code=_lambda.S3Code(bucket=layer_bucket, key=LAMBDA_LAYER_SOURCE_S3_KEY_LANGCHAIN),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_10],
            description="Langchain "
        )
        moviepy_layer = _lambda.LayerVersion(self, 'MoviePyLayer',
            code=_lambda.S3Code(bucket=layer_bucket, key=LAMBDA_LAYER_SOURCE_S3_KEY_MOVIEPY),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Python 3.12 with movie.py"
        )
        
        # Util function generate embedding
        # Lambda: extr-srv-generate-embedding
        lambda_extration_srv_gen_embedding_role = _iam.Role(
            self, "ExtrSrvLambdaGenEmbeddingRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-generate-embedding-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["bedrock:InvokeModel"],
                        resources=["arn:aws:bedrock:*::foundation-model/amazon.titan*", "arn:aws:bedrock:*::foundation-model/anthropic.*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-generate-embedding{self.instance_hash}:*"]
                    )
                ]
            )}
        )
        lambda_gen_embedding = _lambda.Function(self, 
            id='ExtractionFlowGenEmbeddingLambda', 
            function_name=f"extr-srv-generate-embedding{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-generate-embedding.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-generate-embedding")),
            timeout=Duration.seconds(10),
            environment={
                'BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID': BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID,
                'BEDROCK_TITAN_TEXT_EMBEDDING_MODEL_ID': BEDROCK_TITAN_TEXT_EMBEDDING_MODEL_ID,
                'BEDROCK_REGION': self.bedrock_region
            },
            role=lambda_extration_srv_gen_embedding_role,
        )
        self.lambda_arn_gen_embedding = lambda_gen_embedding.function_arn

        # Step Function - start
        # Lambda: extr-srv-video-metadata
        lambda_extration_srv_metadata_role = _iam.Role(
            self, "ExtrSrvLambdaMetaDataRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-metadata-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["rekognition:DetectModerationLabels", "rekognition:DetectFaces", "rekognition:DetectLabels", "rekognition:DetectText", "rekognition:RecognizeCelebrities"],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-sample-video{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_metadata_video = _lambda.Function(self, 
            id='ExtractionFlowMetadataLambda', 
            function_name=f"extr-srv-video-metadata{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-video-metadata.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-video-metadata")),
            timeout=Duration.seconds(900),
            memory_size=3008,
            ephemeral_storage_size=Size.mebibytes(10240),
            environment={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'VIDEO_SAMPLE_CHUNK_DURATION_S': VIDEO_SAMPLE_CHUNK_DURATION_S,
                'VIDEO_SAMPLE_FILE_PREFIX': VIDEO_SAMPLE_FILE_PREFIX,
                'VIDEO_SAMPLE_S3_PREFIX': VIDEO_SAMPLE_S3_PREFIX,
                'VIDEO_SAMPLE_S3_BUCKET': self.s3_bucket_name_extraction,
            },
            role=lambda_extration_srv_metadata_role,
            layers=[moviepy_layer],
        )

        # Lambda: extr-srv-sample-video
        lambda_extration_srv_sample_video_role = _iam.Role(
            self, "ExtrSrvLambdaSampleVideoRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-sample-video-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),              
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["rekognition:DetectModerationLabels", "rekognition:DetectFaces", "rekognition:DetectLabels", "rekognition:DetectText", "rekognition:RecognizeCelebrities"],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-sample-video{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_re_sample_video = _lambda.Function(self, 
            id='ExtractionFlowSampleVideoLambda', 
            function_name=f"extr-srv-sample-video{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-sample-video.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-sample-video")),
            timeout=Duration.seconds(900),
            memory_size=3008,
            ephemeral_storage_size=Size.mebibytes(10240),
            environment={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'VIDEO_SAMPLE_CHUNK_DURATION_S': VIDEO_SAMPLE_CHUNK_DURATION_S,
                'VIDEO_SAMPLE_FILE_PREFIX': VIDEO_SAMPLE_FILE_PREFIX,
                'VIDEO_SAMPLE_S3_PREFIX': VIDEO_SAMPLE_S3_PREFIX,
                'VIDEO_SAMPLE_S3_BUCKET': self.s3_bucket_name_extraction,
                'REKOGNITION_REGION': self.rekognition_region,
            },
            role=lambda_extration_srv_sample_video_role,
            layers=[moviepy_layer],
        )

        # Lambda: extr-srv-sample-video-dedup
        lambda_extration_srv_sample_video_dedup_role = _iam.Role(
            self, "ExtrSrvLambdaSampleVideoDedupRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-sample-video-dedup-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["es:ESHttpGet", "es:ESHttpHead", "es:ESHttpPut", "es:ESHttpDelete", "es:ESHttpPost", "es:DescribeDomains", "es:ListDomainNames", "es:DescribeDomain"],
                        resources=[self.opensearch_domain.domain_arn]
                    ),                    
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["bedrock:InvokeModel"],
                        resources=["arn:aws:bedrock:*::foundation-model/amazon.titan*", "arn:aws:bedrock:*::foundation-model/anthropic.*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-sample-video-dedup{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:DescribeNetworkInterfaces", "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_re_sample_video_dedup = _lambda.Function(self, 
            id='ExtractionFlowSampleVideoDedupLambda', 
            function_name=f"extr-srv-sample-video-dedup{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-sample-video-dedup.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-sample-video-dedup")),
            timeout=Duration.seconds(900),
            memory_size=3008,
            ephemeral_storage_size=Size.mebibytes(10240),
            environment={
                'OPENSEARCH_DOMAIN_ENDPOINT': self.opensearch_domain.domain_endpoint,
                'OPENSEARCH_PORT': OPENSEARCH_PORT,
                'VIDEO_SAMPLE_CHUNK_DURATION_S': VIDEO_SAMPLE_CHUNK_DURATION_S,
                'VIDEO_SAMPLE_FILE_PREFIX': VIDEO_SAMPLE_FILE_PREFIX,
                'VIDEO_SAMPLE_S3_PREFIX': VIDEO_SAMPLE_S3_PREFIX,
                'VIDEO_SAMPLE_S3_BUCKET': self.s3_bucket_name_extraction,
                'OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_TEMP_PREFIX': OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_TEMP_PREFIX,
                'OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD': OPENSEARCH_INDEX_NAME_VIDEO_FRAME_SIMILAIRTY_THRESHOLD,
                'OPENSEARCH_VIDEO_FRAME_SIMILAIRTY_INDEX_MAPPING': OPENSEARCH_VIDEO_FRAME_SIMILAIRTY_INDEX_MAPPING,
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'BEDROCK_REGION': self.bedrock_region,
                'BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID': BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID
            },
            role=lambda_extration_srv_sample_video_dedup_role,
            layers=[self.opensearch_layer],
            vpc=self.vpc,
        )

        # Grant access to OpenSearch
        self.opensearch_domain.connections.allow_from(
            other=lambda_re_sample_video_dedup,
            port_range=ec2.Port.tcp(int(OPENSEARCH_PORT))
        )


        # Lambda: extr-srv-sample-video-dedup-faiss
        lambda_extration_srv_sample_video_dedup_faiss_role = _iam.Role(
            self, "ExtrSrvLambdaSampleVideoDedupFaissRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-sample-video-dedup-faiss-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),                
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["bedrock:InvokeModel"],
                        resources=["arn:aws:bedrock:*::foundation-model/amazon.titan*", "arn:aws:bedrock:*::foundation-model/anthropic.*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-sample-video-dedup-faiss{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:DescribeNetworkInterfaces", "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_re_sample_video_dedup_faiss = _lambda.Function(self, 
            id='ExtractionFlowSampleVideoDedupFaissLambda', 
            function_name=f"extr-srv-sample-video-dedup-faiss{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler='extr-srv-sample-video-dedup-faiss.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-sample-video-dedup-faiss")),
            timeout=Duration.seconds(900),
            memory_size=3008,
            ephemeral_storage_size=Size.mebibytes(10240),
            environment={
                'BEDROCK_REGION': self.bedrock_region,
                'VIDEO_FRAME_SIMILAIRTY_THRESHOLD_FAISS': self.s3_bucket_name_extraction,
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'VIDEO_SAMPLE_FILE_PREFIX': VIDEO_SAMPLE_FILE_PREFIX,
                'BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID': BEDROCK_TITAN_MULTIMODEL_EMBEDDING_MODEL_ID
            },
            role=lambda_extration_srv_sample_video_dedup_faiss_role,
            layers=[self.langchain_layer]
        )

        # Lambda: extr-srv-image-extraction
        lambda_extration_srv_image_extraction_role = _iam.Role(
            self, "ExtrSrvLambdaImageExtractionRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-image-extraction-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ), 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["rekognition:DetectModerationLabels", "rekognition:DetectFaces", "rekognition:DetectLabels", "rekognition:DetectText", "rekognition:RecognizeCelebrities"],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["bedrock:InvokeModel"],
                        resources=["arn:aws:bedrock:*::foundation-model/amazon.titan*", "arn:aws:bedrock:*::foundation-model/anthropic.*"]
                    ), 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-image-extraction{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_extraction_srv_image_extraction = _lambda.Function(self, 
            id='ExtrSrvImageExtractionLambda', 
            function_name=f"extr-srv-image-extraction{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-image-extraction.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-image-extraction")),
            timeout=Duration.seconds(900),
            role=lambda_extration_srv_image_extraction_role,
            environment={
                'REKOGNITION_REGION': self.rekognition_region,
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'REK_MIN_CONF_DETECT_CELEBRITY': REK_MIN_CONF_DETECT_CELEBRITY,
                'REK_MIN_CONF_DETECT_MODERATION': REK_MIN_CONF_DETECT_MODERATION,
                'REK_MIN_CONF_DETECT_TEXT': REK_MIN_CONF_DETECT_TEXT,
                'REK_MIN_CONF_DETECT_LABEL': REK_MIN_CONF_DETECT_LABEL,
                'BEDROCK_REGION': self.bedrock_region,
                'BEDROCK_ANTHROPIC_CLAUDE_HAIKU': BEDROCK_ANTHROPIC_CLAUDE_HAIKU,
                'BEDROCK_ANTHROPIC_CLAUDE_HAIKU_MODEL_VERSION': BEDROCK_ANTHROPIC_CLAUDE_HAIKU_MODEL_VERSION
            },
        )

        # Lambda: extr-srv-image-embedding
        lambda_extration_srv_image_caption_mm_role = _iam.Role(
            self, "ExtrSrvLambdaImageEmbeddingRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-image-embedding-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),                 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["lambda:InvokeFunction"],
                        resources=[self.lambda_arn_gen_embedding]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-image-embedding{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_extraction_srv_image_extraction = _lambda.Function(self, 
            id='ExtrSrvImageCaptionMmLambda', 
            function_name=f"extr-srv-image-embedding{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-image-embedding.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-image-embedding")),
            timeout=Duration.seconds(60),
            role=lambda_extration_srv_image_caption_mm_role,
            environment={
             'LAMBDA_FUNCTION_ARN_EMBEDDING': self.lambda_arn_gen_embedding,
             'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
             'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
            },
        )

        # Lambda: extr-srv-image-vector-save
        lambda_extration_srv_image_vector_save_role = _iam.Role(
            self, "ExtrSrvLambdaImageVectorSaveRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-image-vector-save-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["es:ESHttpGet", "es:ESHttpHead", "es:ESHttpPut", "es:ESHttpDelete", "es:ESHttpPost", "es:DescribeDomains", "es:ListDomainNames", "es:DescribeDomain"],
                        resources=[self.opensearch_domain.domain_arn]
                    ), 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-image-embedding{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:DescribeNetworkInterfaces", "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_extraction_srv_image_vector_save = _lambda.Function(self, 
            id='ExtrSrvImageVectorSaveLambda', 
            function_name=f"extr-srv-image-vector-save{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-image-vector-save.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-image-vector-save")),
            timeout=Duration.seconds(60),
            role=lambda_extration_srv_image_vector_save_role,
            environment={
             'OPENSEARCH_DOMAIN_ENDPOINT': self.opensearch_domain.domain_endpoint,
             'OPENSEARCH_PORT': OPENSEARCH_PORT,
             'OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME': OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME,
             'OPENSEARCH_VIDEO_FRAME_INDEX_MAPPING': OPENSEARCH_VIDEO_FRAME_INDEX_MAPPING,
             'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
             'OPENSEARCH_SHARD_SIZE_LIMIT': OPENSEARCH_SHARD_SIZE_LIMIT
            },
            layers=[self.opensearch_layer],
            vpc=self.vpc,
        )

        # Grant access to OpenSearch
        self.opensearch_domain.connections.allow_from(
            other=lambda_extraction_srv_image_vector_save,
            port_range=ec2.Port.tcp(int(OPENSEARCH_PORT))
        )

        # Lambda: extr-srv-aggregate-extracted-label
        lambda_extration_srv_agg_role = _iam.Role(
            self, "ExtrSrvLambdaAggRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-aggregate-extracted-label-poliy": _iam.PolicyDocument(
                statements=[ 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-image-embedding{self.instance_hash}:*"]
                    ),           
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_extraction_srv_image_vector_save = _lambda.Function(self, 
            id='ExtrSrvAggLambda', 
            function_name=f"extr-srv-aggregate-extracted-label{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-aggregate-extracted-label.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-aggregate-extracted-label")),
            timeout=Duration.seconds(900),
            memory_size=3008,
            ephemeral_storage_size=Size.mebibytes(10240),
            role=lambda_extration_srv_agg_role,
            environment={             
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
            },
        )

        # Lambda: extr-srv-shot-analysis
        lambda_extration_srv_shot_analysis_role = _iam.Role(
            self, "ExtrSrvLambdaShotAnalysisRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-shot-analysis-poliy": _iam.PolicyDocument(
                statements=[ 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),                 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["bedrock:InvokeModel"],
                        resources=["arn:aws:bedrock:*::foundation-model/amazon.titan*", "arn:aws:bedrock:*::foundation-model/anthropic.*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-shot-analysis{self.instance_hash}:*"]
                    ),           
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_extraction_srv_shot_analysis = _lambda.Function(self, 
            id='ExtrSrvShotAnalysisLambda', 
            function_name=f"extr-srv-shot-analysis{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-shot-analysis.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-shot-analysis")),
            timeout=Duration.seconds(900),
            memory_size=3008,
            ephemeral_storage_size=Size.mebibytes(10240),
            role=lambda_extration_srv_shot_analysis_role,
            environment={             
                'DYNAMO_VIDEO_ANALYSIS_TABLE': DYNAMO_VIDEO_ANALYSIS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'BEDROCK_REGION': self.bedrock_region,
                'EXTR_SRV_S3_BUCKET': self.s3_bucket_name_extraction,
                'BEDROCK_ANTHROPIC_CLAUDE_HAIKU': BEDROCK_ANTHROPIC_CLAUDE_HAIKU,
                'BEDROCK_ANTHROPIC_CLAUDE_HAIKU_MODEL_VERSION': BEDROCK_ANTHROPIC_CLAUDE_HAIKU_MODEL_VERSION
            },
        )

        # Lambda: extr-srv-scene-analysis
        lambda_extration_srv_scene_analysis_role = _iam.Role(
            self, "ExtrSrvLambdaSceneAnalysisRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-scene-analysis-poliy": _iam.PolicyDocument(
                statements=[ 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),                 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["bedrock:InvokeModel"],
                        resources=["arn:aws:bedrock:*::foundation-model/amazon.titan*", "arn:aws:bedrock:*::foundation-model/anthropic.*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-scene-analysis{self.instance_hash}:*"]
                    ),           
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_extraction_srv_scene_analysis = _lambda.Function(self, 
            id='ExtrSrvSceneAnalysisLambda', 
            function_name=f"extr-srv-scene-analysis{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-scene-analysis.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-scene-analysis")),
            timeout=Duration.seconds(900),
            memory_size=3008,
            ephemeral_storage_size=Size.mebibytes(10240),
            role=lambda_extration_srv_shot_analysis_role,
            environment={             
                'DYNAMO_VIDEO_ANALYSIS_TABLE': DYNAMO_VIDEO_ANALYSIS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'BEDROCK_REGION': self.bedrock_region,
                'EXTR_SRV_S3_BUCKET': self.s3_bucket_name_extraction,
                'BEDROCK_ANTHROPIC_CLAUDE_SONNET_V35': BEDROCK_ANTHROPIC_CLAUDE_SONNET_V35,
                'BEDROCK_ANTHROPIC_CLAUDE_HAIKU': BEDROCK_ANTHROPIC_CLAUDE_HAIKU,
                'BEDROCK_ANTHROPIC_CLAUDE_HAIKU_MODEL_VERSION': BEDROCK_ANTHROPIC_CLAUDE_HAIKU_MODEL_VERSION
            },
        )
        
        # StepFunctions StateMachine
        sm_json = None
        with open('../source/extraction_service/stepfunctions/video_extraction_workflow/genai-policy-eval-srv-extraction-flow.txt', "r") as f:
            sm_json = str(f.read())

        if sm_json is not None:
            sm_json = sm_json.replace("##LAMBDA_METADATA_VIDEO##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-video-metadata{self.instance_hash}")
            sm_json = sm_json.replace("##LAMBDA_ES_SAMPLE_VIDEO##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-sample-video{self.instance_hash}")
            sm_json = sm_json.replace("##LAMBDA_ES_SAMPLE_VIDEO_DEDUP##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-sample-video-dedup-faiss{self.instance_hash}")
            sm_json = sm_json.replace("##LAMBDA_ES_IMAGE_EXTRACTION##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-image-extraction{self.instance_hash}")
            sm_json = sm_json.replace("##LAMBDA_ES_IMAGE_EMBEDDING##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-image-embedding{self.instance_hash}")
            sm_json = sm_json.replace("##LAMBDA_ES_IMAGE_EMBEDDING_SAVE##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-image-vector-save{self.instance_hash}")
            sm_json = sm_json.replace("##LAMBDA_ES_AGG##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-aggregate-extracted-label{self.instance_hash}")
            sm_json = sm_json.replace("##LAMBDA_ES_SHOT_ANALYSIS##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-shot-analysis{self.instance_hash}")
            #sm_json = sm_json.replace("##LAMBDA_ES_SCENE_ANALYSIS##", f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-scene-analysis{self.instance_hash}")
            sm_json = sm_json.replace("##VIDEO_IMAGE_EXTRACTION_CONCURRENT_LIMIT##", VIDEO_IMAGE_EXTRACTION_CONCURRENT_LIMIT)
            sm_json = sm_json.replace("##VIDEO_IMAGE_EXTRACTION_SAMPLE_CONCURRENT_LIMIT##", VIDEO_IMAGE_EXTRACTION_SAMPLE_CONCURRENT_LIMIT)

        stepfunction_extration_srv_workflow_role = _iam.Role(
            self, "ExtrSrvStepFunctionRole",
            assumed_by=_iam.ServicePrincipal("states.amazonaws.com"),
            inline_policies={"extr-srv-step-function-extr-flow-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["states:StartExecution","states:ListExecutions"],
                        resources=[f"arn:aws:states:{self.region}:{self.account_id}:stateMachine:{STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX}{self.instance_hash}"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["sns:Publish"],
                        resources=[f"arn:aws:sns:{self.region}:{self.account_id}:*"]
                    ),
                     _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["lambda:InvokeFunction"],
                        resources=[
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-video-metadata{self.instance_hash}",
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-sample-video{self.instance_hash}",
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-sample-video-dedup-faiss{self.instance_hash}",
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-image-extraction{self.instance_hash}",
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-image-embedding{self.instance_hash}",
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-image-vector-save{self.instance_hash}",
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-aggregate-extracted-label{self.instance_hash}",
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-shot-analysis{self.instance_hash}",
                            f"arn:aws:lambda:{self.region}:{self.account_id}:function:extr-srv-scene-analysis{self.instance_hash}",
                        ]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"],
                        resources=[f"*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:DescribeNetworkInterfaces", "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                ]
            )}
        )
        self.sf_state_machine = _aws_stepfunctions.StateMachine(self, "StepFunctionExtractionWorkflow",
            state_machine_name=f'{STEP_FUNCTION_STATE_MACHINE_NAME_PREFIX}{self.instance_hash}', 
            definition_body=_aws_stepfunctions.DefinitionBody.from_string(sm_json),
            removal_policy=RemovalPolicy.DESTROY,
            role=stepfunction_extration_srv_workflow_role,
            timeout=Duration.hours(int(VIDEO_EXTRACTION_WORKFLOW_TIMEOUT_HR)),
            tracing_enabled=True,
            logs= _aws_stepfunctions.LogOptions(
                destination=logs.LogGroup(self, "/aws/vendedlogs/states/extrsrvworkflow"),
                level=_aws_stepfunctions.LogLevel.ALL
            )
        )
        # Step Function - end

    def deploy_delete_task_sqs(self):
        # Create an SQS dead-letter queue
        dl_delete_queue = _sqs.Queue(
            self, "ExtrSrvDeleteTaskDeadLetterQueue",
            queue_name=f"extr-srv-delete-task-dead-letter-queue{self.instance_hash}",
            visibility_timeout=Duration.seconds(600),
            retention_period=Duration.days(14),
            removal_policy=RemovalPolicy.DESTROY,
            enforce_ssl=True,
        )

        # Create SQS - for delete task workflow
        self.delete_task_q = _sqs.Queue(self, 
            id="ExtrSrvDeleteTaskQueue",
            queue_name=f"extr-srv-delete-task-queue{self.instance_hash}",
            delivery_delay=Duration.seconds(0),
            visibility_timeout=Duration.seconds(600),
            removal_policy=RemovalPolicy.DESTROY,
            enforce_ssl=True,
            dead_letter_queue=_sqs.DeadLetterQueue(
                max_receive_count=1000,
                queue=dl_delete_queue
            )
        )

        # Create Lambda triggered by SQS
        # Lambda: extr-srv-delete-video-task-processor
        lambda_ex_delete_task_processor_role = _iam.Role(
            self, "ExtrSrvLambdaDeleteTaskProcessorRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-delete-task-processor-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["es:ESHttpGet", "es:ESHttpHead", "es:ESHttpPut", "es:ESHttpDelete", "es:ESHttpPost", "es:DescribeDomains", "es:ListDomainNames", "es:DescribeDomain"],
                        resources=[self.opensearch_domain.domain_arn]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:DescribeNetworkInterfaces", "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["transcribe:DeleteTranscriptionJob"],
                        resources=["*"]
                    ),                     
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-delete-video-task-processor{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["sqs:SendMessage","sqs:DeleteMessage","sqs:ChangeMessageVisibility","sqs:GetQueueAttributes","sqs:ReceiveMessage"],
                        resources=[self.delete_task_q.queue_arn]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_delete_task_processor = _lambda.Function(self, 
            id='ExtrSrvDeleteTaskProcessorLambda', 
            function_name=f"extr-srv-delete-video-task-processor{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-delete-video-task-processor.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-delete-video-task-processor")),
            timeout=Duration.seconds(600),
            memory_size=1280,
            ephemeral_storage_size=Size.mebibytes(5120),
            role=lambda_ex_delete_task_processor_role,
            environment={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'DYNAMO_VIDEO_ANALYSIS_TABLE': DYNAMO_VIDEO_ANALYSIS_TABLE,
                'TRANSCRIBE_JOB_PREFIX': TRANSCRIBE_JOB_PREFIX,
                'OPENSEARCH_DOMAIN_ENDPOINT': self.opensearch_domain.domain_endpoint,
                'OPENSEARCH_PORT': OPENSEARCH_PORT,
            },
            vpc=self.vpc,
            layers=[self.opensearch_layer]
        )
        lambda_delete_task_processor.node.add_dependency(self.delete_task_q)

        lambda_delete_task_processor.add_event_source(lambda_event_sources.SqsEventSource(
            queue=self.delete_task_q,
            batch_size=1 
        ))


    def deploy_sqs(self):
        # Create an SQS dead-letter queue
        dl_queue = _sqs.Queue(
            self, "ExtrSrvTaskDeadLetterQueue",
            queue_name=f"extr-srv-task-dead-letter-queue{self.instance_hash}",
            visibility_timeout=Duration.seconds(600),
            retention_period=Duration.days(14),
            removal_policy=RemovalPolicy.DESTROY,
            enforce_ssl=True,
        )

        # Create SQS 
        extr_task_sqs = _sqs.Queue(self, 
            id="ExtrSrvTaskQueue",
            queue_name=f"extr-srv-task-queue{self.instance_hash}",
            delivery_delay=Duration.seconds(30),
            visibility_timeout=Duration.seconds(600),
            removal_policy=RemovalPolicy.DESTROY,
            enforce_ssl=True,
            dead_letter_queue=_sqs.DeadLetterQueue(
                max_receive_count=1000, #~8.3 hours (with 30 seconds retry)
                queue=dl_queue
            )
        )

        # Create Lambda triggered by SQS
        # Lambda: extr-srv-invoke-extraction-flow
        lambda_extr_invoke_flow_role = _iam.Role(
            self, "ExtrSrvLambdaInvokeFlowRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-lambda-invoke-flow-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["sqs:SendMessage","sqs:DeleteMessage","sqs:ChangeMessageVisibility","sqs:GetQueueAttributes","sqs:ReceiveMessage"],
                        resources=[extr_task_sqs.queue_arn]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["states:StartExecution","states:ListExecutions"],
                        resources=[self.sf_state_machine.state_machine_arn]
                    ), 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-invoke-extraction-flow{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_invoke_extr_flow = _lambda.Function(self, 
            id='ExtrSrvInvokeFlowLambda', 
            function_name=f"extr-srv-invoke-extraction-flow{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-invoke-extraction-flow.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-invoke-extraction-flow")),
            timeout=Duration.seconds(10),
            memory_size=128,
            ephemeral_storage_size=Size.mebibytes(512),
            role=lambda_extr_invoke_flow_role,
            environment={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'SQS_URL': extr_task_sqs.queue_url,
                'STEP_FUNCTIONS_STATE_MACHINE_ARN': self.sf_state_machine.state_machine_arn,
                'STEP_FUNCTIONS_STATE_MACHINE_CONCURRENT_LIMIT': VIDEO_EXTRACTION_CONCURRENT_LIMIT
            },
        )

        lambda_invoke_extr_flow.add_event_source(lambda_event_sources.SqsEventSource(
            queue=extr_task_sqs,
            batch_size=1 
        ))

        # Create Lambda will triggered by file drop to the S3 bucket
        # Lambda: extr-srv-transcription-s3-trigger  
        lambda_es_s3_listener_role = _iam.Role(
            self, "ExtrSrvLambdaS3ListenerRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-s3-listener-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["sqs:SendMessage","sqs:DeleteMessage","sqs:ChangeMessageVisibility","sqs:GetQueueAttributes","sqs:ReceiveMessage"],
                        resources=[extr_task_sqs.queue_arn]
                    ),                           
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-transcription-s3-trigger{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        lambda_es_s3_listener = _lambda.Function(self, 
            id='ExtrSrvTranscribeS3ListenerLambda', 
            function_name=f"extr-srv-transcription-s3-trigger{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-transcription-s3-trigger.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-transcription-s3-trigger")),
            timeout=Duration.seconds(10),
            memory_size=128,
            ephemeral_storage_size=Size.mebibytes(512),
            role=lambda_es_s3_listener_role,
            environment={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'SQS_URL': extr_task_sqs.queue_url,
            },
        )

        # Add S3 trigger
        if self.s3_extraction_bucket is not None and self.s3_extraction_bucket.bucket_name is not None and len(self.s3_extraction_bucket.bucket_name) > 0:
            # Grand S3 access to trigger the Lambda function
            self.s3_extraction_bucket.grant_read(lambda_es_s3_listener)
            # Subscribe to S3 file creat event
            self.s3_extraction_bucket.add_object_created_notification(
                _s3_noti.LambdaDestination(lambda_es_s3_listener),
                _s3.NotificationKeyFilter(prefix="tasks/", suffix="_transcribe.json")
            )

    def deploy_apigw(self):
        # API Gateway - start
        api = _apigw.RestApi(self, f"{API_NAME_PREFIX}{self.instance_hash}",
                                rest_api_name=f"{API_NAME_PREFIX}{self.instance_hash}",
                                cloud_watch_role=True,
                                cloud_watch_role_removal_policy=RemovalPolicy.DESTROY,
                                deploy_options=_apigw.StageOptions(
                                        tracing_enabled=True,
                                        access_log_destination=_apigw.LogGroupLogDestination(logs.LogGroup(self, f"ApiGatewayExtrSrvAccessLog")),
                                        access_log_format=_apigw.AccessLogFormat.clf(),
                                        method_options={
                                            "/*/*": _apigw.MethodDeploymentOptions( # This special path applies to all resource paths and all HTTP methods
                                                logging_level=_apigw.MethodLoggingLevel.INFO,)
                                    }                               
                                ),   
                            )
        
        plan = api.add_usage_plan("UsagePlan",
            name="Easy",
            throttle=_apigw.ThrottleSettings(
                rate_limit=10,
                burst_limit=2
            )
        )
        key = api.add_api_key("ApiKey")
        plan.add_api_key(key)

        # Create resources
        v1 = api.root.add_resource("v1")
        ex = v1.add_resource("extraction")
        ex_video = ex.add_resource("video")
        an = v1.add_resource("analysis")
        an_video = an.add_resource("video")
        
        self.api_gw_base_url = api.url
                                     
        # POST v1/extraction/video/delete-task
        # Lambda: extr-srv-delete-video-task 
        lambda_ex_delete_task_role = _iam.Role(
            self, "ExtrSrvLambdaDeleteTaskRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-delete-task-poliy": _iam.PolicyDocument(
                statements=[              
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-delete-video-task{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["sqs:SendMessage","sqs:DeleteMessage","sqs:ChangeMessageVisibility","sqs:GetQueueAttributes","sqs:ReceiveMessage"],
                        resources=[self.delete_task_q.queue_arn]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    )
                ]
            )}
        )
        self.create_api_endpoint_novpc(id='ExtrSrvDeleteTaskEp', 
            root=ex_video, path1="extraction_service", path2="delete-task", method="POST", auth=self.cognito_authorizer, 
            role=lambda_ex_delete_task_role, 
            lambda_file_name="extr-srv-delete-video-task", 
            instance_hash=self.instance_hash, memory_m=128, timeout_s=20, ephemeral_storage_size=512,
            evns={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'TRANSCRIBE_JOB_PREFIX': TRANSCRIBE_JOB_PREFIX,
                'SQS_URL': self.delete_task_q.queue_url,
            },
        )   

        # POST /v1/extraction/video/get-task
        # Lambda: extr-srv-get-video-task
        lambda_es_get_task_role = _iam.Role(
            self, "ExtrSrvLambdaGetTaskRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-get-task-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject","s3:ListMultipartUploadParts","s3:ListBucketMultipartUploads"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-get-video-task{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}"
                        ]
                    ) 
                ]
            )}
        )
        self.create_api_endpoint_novpc(id='ExtrSrvGetTaskEp', root=ex_video, path1="extraction_service", path2="get-task", method="POST", auth=self.cognito_authorizer, 
                role=lambda_es_get_task_role, 
                lambda_file_name="extr-srv-get-video-task",
                instance_hash=self.instance_hash, memory_m=128, timeout_s=20, ephemeral_storage_size=1024,
            evns={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'DYNAMO_VIDEO_ANALYSIS_TABLE': DYNAMO_VIDEO_ANALYSIS_TABLE,
                'S3_PRESIGNED_URL_EXPIRY_S':S3_PRE_SIGNED_URL_EXPIRY_S,
            })        
        
        # POST /v1/extraction/get-task-frames
        # Lambda: extr-srv-get-task-frames
        lambda_es_get_task_frames_role = _iam.Role(
            self, "ExtrSrvLambdaGetTaskFramesRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-get-task-frames-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-get-task-frames{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}"
                        ]
                    )              
                ]
            )}
        )
            
        self.create_api_endpoint_novpc(id='ExtrSrvGetTaskFramesEp', root=ex_video, path1="extraction_service", path2="get-task-frames", method="POST", auth=self.cognito_authorizer, 
                role=lambda_es_get_task_frames_role, 
                lambda_file_name="extr-srv-get-task-frames",
                instance_hash=self.instance_hash, memory_m=128, timeout_s=20, ephemeral_storage_size=1024,
            evns={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'S3_PRESIGNED_URL_EXPIRY_S':S3_PRE_SIGNED_URL_EXPIRY_S,
            })        

        # POST /v1/extraction/get-task-shots
        # Lambda: extr-srv-get-shots
        lambda_es_get_task_shots_role = _iam.Role(
            self, "ExtrSrvLambdaGetTaskShotsRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-get-shots-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-get-shots{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}"
                        ]
                    )              
                ]
            )}
        )
            
        self.create_api_endpoint_novpc(id='ExtrSrvGetTaskShotsEp', root=ex_video, path1="extraction_service", path2="get-task-shots", method="POST", auth=self.cognito_authorizer, 
                role=lambda_es_get_task_frames_role, 
                lambda_file_name="extr-srv-get-shots",
                instance_hash=self.instance_hash, memory_m=1280, timeout_s=30, ephemeral_storage_size=1024,
            evns={
                'DYNAMO_VIDEO_ANALYSIS_TABLE': DYNAMO_VIDEO_ANALYSIS_TABLE,
                'S3_PRESIGNED_URL_EXPIRY_S':S3_PRE_SIGNED_URL_EXPIRY_S,
            })      
        
        # POST /v1/extraction/get-task-scenes
        # Lambda: extr-srv-get-scenes
        lambda_es_get_task_scenes_role = _iam.Role(
            self, "ExtrSrvLambdaGetTaskScenesRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-get-scenes-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-get-scenes{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_ANALYSIS_TABLE}"
                        ]
                    )              
                ]
            )}
        )
            
        self.create_api_endpoint_novpc(id='ExtrSrvGetTaskScenesEp', root=ex_video, path1="extraction_service", path2="get-task-scenes", method="POST", auth=self.cognito_authorizer, 
                role=lambda_es_get_task_frames_role, 
                lambda_file_name="extr-srv-get-scenes",
                instance_hash=self.instance_hash, memory_m=1280, timeout_s=30, ephemeral_storage_size=1024,
            evns={
                'DYNAMO_VIDEO_ANALYSIS_TABLE': DYNAMO_VIDEO_ANALYSIS_TABLE,
                'S3_PRESIGNED_URL_EXPIRY_S':S3_PRE_SIGNED_URL_EXPIRY_S,
            })    
        
        # POST /v1/extraction/video/manage-s3-presigned-url
        # Lambda: extr-srv-manage-s3-presigned-url
        lambda_es_manage_s3_url_role = _iam.Role(
            self, "ExtrSrvLambdaManageS3PresignedUrlRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-manage-s3-presigned-url-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject","s3:ListMultipartUploadParts","s3:ListBucketMultipartUploads"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-manage-s3-presigned-url{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:DescribeNetworkInterfaces", "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",],
                        resources=["*"]
                    )
                ]
            )}
        )
        self.create_api_endpoint_novpc(id='ExtrSrvManageS3UrlEp', root=ex_video, path1="extraction_service", path2="manage-s3-presigned-url", method="POST", auth=self.cognito_authorizer, 
                role=lambda_es_manage_s3_url_role,
                lambda_file_name="extr-srv-manage-s3-presigned-url",
                instance_hash=self.instance_hash, memory_m=128, timeout_s=10, ephemeral_storage_size=512,
                evns={
                'S3_PRESIGNED_URL_EXPIRY_S': S3_PRE_SIGNED_URL_EXPIRY_S,
                'VIDEO_UPLOAD_S3_PREFIX': VIDEO_UPLOAD_S3_PREFIX,
                'VIDEO_UPLOAD_S3_BUCKET': self.s3_bucket_name_extraction
                },
                layers=[self.opensearch_layer]
            )   
              
        # POST /v1/extraction/search-task
        # Lambda: extr-srv-get-video-tasks 
        lambda_es_get_tasks_role = _iam.Role(
            self, "ExtrSrvLambdaGetTasksRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-get-tasks-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject","s3:ListMultipartUploadParts","s3:ListBucketMultipartUploads"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),                    
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-get-video-tasks{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    ) 
                ]
            )}
        )
        self.create_api_endpoint_novpc(id='ExtrSrvGetTasksEp', root=ex_video, path1="extraction_service", path2="search-task", method="POST", auth=self.cognito_authorizer, 
                role=lambda_es_get_tasks_role,
                lambda_file_name="extr-srv-get-video-tasks",
                instance_hash=self.instance_hash, memory_m=128, timeout_s=10, ephemeral_storage_size=1024,
                evns={
                    'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                    'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                    'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                    'S3_PRE_SIGNED_URL_EXPIRY_S': S3_PRE_SIGNED_URL_EXPIRY_S,
                }
        )

        # POST /v1/extraction/search-task-vector
        # Lambda: extr-srv-search-vector 
        lambda_search_vector_role = _iam.Role(
            self, "ExtrSrvLambdaSearchVectorRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-search-vector-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject","s3:ListMultipartUploadParts","s3:ListBucketMultipartUploads"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["es:ESHttpGet", "es:ESHttpHead", "es:ESHttpPut", "es:ESHttpDelete", "es:ESHttpPost", "es:DescribeDomains", "es:ListDomainNames", "es:DescribeDomain"],
                        resources=[self.opensearch_domain.domain_arn]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:DescribeNetworkInterfaces", "ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["lambda:InvokeFunction"],
                        resources=[self.lambda_arn_gen_embedding]
                    ),                    
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-get-video-tasks{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}"
                        ]
                    ) 
                ]
            )}
        )
        self.create_api_endpoint(id='ExtrSrvSearchVectorEp', root=ex_video, path1="extraction_service", path2="search-task-vector", method="POST", auth=self.cognito_authorizer, 
                role=lambda_search_vector_role,
                lambda_file_name="extr-srv-search-vector",
                instance_hash=self.instance_hash, memory_m=1024, timeout_s=30, ephemeral_storage_size=1024,
                evns={
                    'LAMBDA_FUNCTION_ARN_EMBEDDING': self.lambda_arn_gen_embedding,
                    'OPENSEARCH_DEFAULT_K': OPENSEARCH_DEFAULT_K,
                    'OPENSEARCH_DOMAIN_ENDPOINT': self.opensearch_domain.domain_endpoint,
                    'OPENSEARCH_PORT': OPENSEARCH_PORT,
                    'OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME': OPENSEARCH_INDEX_PREFIX_VIDEO_FRAME,
                    'S3_PRE_SIGNED_URL_EXPIRY_S': S3_PRE_SIGNED_URL_EXPIRY_S,
                    'VIDEO_SAMPLE_FILE_PREFIX': VIDEO_SAMPLE_FILE_PREFIX,
                    'VIDEO_SAMPLE_S3_BUCKET': self.s3_bucket_name_extraction,
                    'VIDEO_SAMPLE_S3_PREFIX': VIDEO_SAMPLE_S3_PREFIX,
                    'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE
                }, 
                layers=[self.opensearch_layer]
        )
            
        # POST /v1/extraction/video/start-task
        # Lambda: extr-srv-start-task 
        lambda_es_start_task_role = _iam.Role(
            self, "ExtrSrvLambdaStartTaskRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-start-task-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject","s3:ListMultipartUploadParts","s3:ListBucketMultipartUploads"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["states:StartExecution","states:ListExecutions"],
                        resources=[self.sf_state_machine.state_machine_arn]
                    ), 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["transcribe:StartTranscriptionJob", "transcribe:DeleteTranscriptionJob"],
                        resources=["*"]
                    ),                     
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-start-task{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TRANS_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_VIDEO_FRAME_TABLE}/index/*"
                        ]
                    )
                ]
            )}
        )
        self.create_api_endpoint_novpc(id='ExtrSrvStartTaskEp', root=ex_video, path1="extraction_service", path2="start-task", method="POST", auth=self.cognito_authorizer, 
                role=lambda_es_start_task_role, 
                lambda_file_name="extr-srv-start-task",
                instance_hash=self.instance_hash, memory_m=128, timeout_s=10, ephemeral_storage_size=512,
            evns={
                'DYNAMO_VIDEO_TASK_TABLE': DYNAMO_VIDEO_TASK_TABLE,
                'DYNAMO_VIDEO_TRANS_TABLE': DYNAMO_VIDEO_TRANS_TABLE,
                'DYNAMO_VIDEO_FRAME_TABLE': DYNAMO_VIDEO_FRAME_TABLE,
                'STEP_FUNCTIONS_STATE_MACHINE_ARN': self.sf_state_machine.state_machine_arn,
                'TRANSCRIBE_JOB_PREFIX': TRANSCRIBE_JOB_PREFIX,
                'TRANSCRIBE_OUTPUT_BUCKET': self.s3_bucket_name_extraction,
                'TRANSCRIBE_OUTPUT_PREFIX': TRANSCRIBE_OUTPUT_PREFIX,
            },
            layers=[self.opensearch_layer])
        # API Gateway - end

    def create_api_endpoint_novpc(self, id, root, path1, path2, method, auth, role, lambda_file_name, instance_hash, memory_m, timeout_s, ephemeral_storage_size, evns, layers=None):
        lambda_function = _lambda.Function(self, 
            id=id, 
            function_name=f"{lambda_file_name}{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler=f'{lambda_file_name}.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", f"extraction_service/lambda/{lambda_file_name}")),
            timeout=Duration.seconds(timeout_s),
            memory_size=memory_m,
            ephemeral_storage_size=Size.mebibytes(ephemeral_storage_size),
            role=role,
            environment=evns,
            layers=layers,
        )

        resource = root.add_resource(
                path2, 
                default_cors_preflight_options=_apigw.CorsOptions(
                allow_methods=['POST', 'OPTIONS'],
                allow_origins=_apigw.Cors.ALL_ORIGINS),
        )

        method = resource.add_method(
            method, 
            _apigw.LambdaIntegration(
                lambda_function,
                proxy=False,
                integration_responses=[
                    _apigw.IntegrationResponse(
                        status_code="200",
                        response_parameters={
                            'method.response.header.Access-Control-Allow-Origin': "'*'"
                        }
                    )
                ]
            ),
            method_responses=[
                _apigw.MethodResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True
                    }
                )
            ],
            authorizer=auth,
            authorization_type=_apigw.AuthorizationType.COGNITO
        )


    def create_api_endpoint(self, id, root, path1, path2, method, auth, role, lambda_file_name, instance_hash, memory_m, timeout_s, ephemeral_storage_size, evns, layers=None):
        lambda_function = _lambda.Function(self, 
            id=id, 
            function_name=f"{lambda_file_name}{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler=f'{lambda_file_name}.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", f"extraction_service/lambda/{lambda_file_name}")),
            timeout=Duration.seconds(timeout_s),
            memory_size=memory_m,
            ephemeral_storage_size=Size.mebibytes(ephemeral_storage_size),
            role=role,
            environment=evns,
            layers=layers,
            vpc=self.vpc,
        )

        # Grant access to OpenSearch
        self.opensearch_domain.connections.allow_from(
            other=lambda_function,
            port_range=ec2.Port.tcp(int(OPENSEARCH_PORT))
        )

        resource = root.add_resource(
                path2, 
                default_cors_preflight_options=_apigw.CorsOptions(
                allow_methods=['POST', 'OPTIONS'],
                allow_origins=_apigw.Cors.ALL_ORIGINS),
        )

        if auth is not None:
            method = resource.add_method(
                method, 
                _apigw.LambdaIntegration(
                    lambda_function,
                    proxy=False,
                    integration_responses=[
                        _apigw.IntegrationResponse(
                            status_code="200",
                            response_parameters={
                                'method.response.header.Access-Control-Allow-Origin': "'*'"
                            }
                        )
                    ]
                ),
                method_responses=[
                    _apigw.MethodResponse(
                        status_code="200",
                        response_parameters={
                            'method.response.header.Access-Control-Allow-Origin': True
                        }
                    )
                ],
                authorizer=auth,
                authorization_type=_apigw.AuthorizationType.COGNITO
            )
        else:
            method = resource.add_method(
                method, 
                _apigw.LambdaIntegration(
                    lambda_function,
                    proxy=False,
                    integration_responses=[
                        _apigw.IntegrationResponse(
                            status_code="200",
                            response_parameters={
                                'method.response.header.Access-Control-Allow-Origin': "'*'"
                            }
                        )
                    ]
                ),
                method_responses=[
                    _apigw.MethodResponse(
                        status_code="200",
                        response_parameters={
                            'method.response.header.Access-Control-Allow-Origin': True
                        }
                    )
                ],
                api_key_required=True
            )
