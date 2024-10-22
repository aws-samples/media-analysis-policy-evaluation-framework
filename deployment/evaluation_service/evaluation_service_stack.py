from aws_cdk import (
    NestedStack,
    Size,
    aws_ec2 as ec2,
    CfnParameter as _cfnParameter,
    aws_cognito as _cognito,
    aws_s3 as _s3,
    aws_s3_notifications as _s3_noti,
    aws_s3_deployment as _s3_deploy,
    aws_dynamodb as _dynamodb,
    aws_lambda as _lambda,
    aws_apigateway as _apigw,
    aws_iam as _iam,
    aws_sns as _sns,
    aws_sqs as _sqs,
    aws_lambda_event_sources as lambda_event_sources,
    Duration,
    aws_stepfunctions as _aws_stepfunctions,
    RemovalPolicy,
    custom_resources as cr,
    aws_logs as logs,
)
from aws_cdk.aws_logs import RetentionDays
from aws_cdk.aws_apigateway import IdentitySource
from aws_cdk.aws_kms import Key
from aws_cdk.aws_ec2 import SecurityGroup

from constructs import Construct
import os
import uuid
import json
from evaluation_service.constant import *

class EvaluationServiceStack(NestedStack):
    account_id = None
    region = None
    instance_hash = None
    api_gw_base_url = None
    cognito_user_pool_id = None
    cognito_app_client_id = None
    bedrock_region = None
    eval_task_sqs = None
    
    def __init__(self, scope: Construct, construct_id: str, instance_hash_code, cognito_user_pool_id, bedrock_region, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.account_id=os.environ.get("CDK_DEFAULT_ACCOUNT")
        self.region=os.environ.get("CDK_DEFAULT_REGION")
        
        self.instance_hash = instance_hash_code #str(uuid.uuid4())[0:5]

        self.cognito_user_pool_id = cognito_user_pool_id
        self.bedrock_region = bedrock_region

        self.deploy_db()
        self.deploy_async_task_processing()
        self.deploy_rest_api()

    def deploy_db(self):
        # Create DynamoDB tables
        # Task table                           
        task_table = _dynamodb.Table(self, 
            id='eval-task-table', 
            table_name=DYNAMO_EVAL_TASK_TABLE, 
            partition_key=_dynamodb.Attribute(name='Id', type=_dynamodb.AttributeType.STRING),
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY
        )
        # Index
        task_table.add_global_secondary_index(
            index_name="VideoTaskId-index",
            partition_key=_dynamodb.Attribute(
                name="VideoTaskId",
                type=_dynamodb.AttributeType.STRING
            ),
            projection_type=_dynamodb.ProjectionType.ALL 
        )

    def deploy_rest_api(self):
        # Load Cognitio user pool
        user_pool = _cognito.UserPool.from_user_pool_id(self, "WebUserPool", user_pool_id=self.cognito_user_pool_id)

        # Create API Gateway CognitioUeserPoolAuthorizer
        auth = _apigw.CognitoUserPoolsAuthorizer(self, f"EvalSrvAuth{self.instance_hash}", 
            cognito_user_pools=[user_pool],
            identity_source=IdentitySource.header('Authorization')
        )
        
        # API Gateway - start
        api = _apigw.RestApi(self, f"{API_NAME_PREFIX}{self.instance_hash}",
                                rest_api_name=f"{API_NAME_PREFIX}{self.instance_hash}",
                                deploy_options=_apigw.StageOptions(
                                        tracing_enabled=True,
                                        access_log_destination=_apigw.LogGroupLogDestination(logs.LogGroup(self, "ApiGatewayEvalSrvAccessLogs")),
                                        access_log_format=_apigw.AccessLogFormat.clf(),
                                        method_options={
                                            "/*/*": _apigw.MethodDeploymentOptions( # This special path applies to all resource paths and all HTTP methods
                                                logging_level=_apigw.MethodLoggingLevel.INFO,)
                                    }                               
                                ),   
                                )
        v1 = api.root.add_resource("v1")
        ev = v1.add_resource("evaluation")

        self.api_gw_base_url = api.url
                                     
        # POST v1/evaluation/invoke-llms
        # Lambda: eval-srv-llms-invoke
        lambda_eval_srv_evaluation_role = _iam.Role(   
            self, "EvalSrvLambdaEvalRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"eval-srv-lambda-eval-poliy": _iam.PolicyDocument(
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
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/eval-srv-llms-invoke{self.instance_hash}:*"]
                    ),
                ]
            )}
        )
        self.create_api_endpoint(id='ev-invoke-llm', 
            root=ev, path1="evaluation_service", path2="invoke-llm", method="POST", auth=auth, 
            role=lambda_eval_srv_evaluation_role, 
            lambda_file_name="eval-srv-llms-invoke", 
            instance_hash=self.instance_hash, memory_m=128, timeout_s=30, ephemeral_storage_size=512,
            evns={
             'BEDROCK_DEFAULT_MODEL_ID': BEDROCK_DEFAULT_MODEL_ID,
             'BEDROCK_REGION': self.bedrock_region
            })   

        # POST v1/evaluation/create-task
        # Lambda: eval-srv-create-task
        lambda_eval_srv_create_task_role = _iam.Role(   
            self, "EvalSrvLambdaCreateTaskRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"eval-srv-create-task-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/eval-srv-create-task{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["sqs:SendMessage","sqs:DeleteMessage","sqs:ChangeMessageVisibility","sqs:GetQueueAttributes","sqs:ReceiveMessage"],
                        resources=[self.eval_task_sqs.queue_arn]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_EVAL_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_EVAL_TASK_TABLE}",
                        ]
                    )
                ]
            )}
        )
        self.create_api_endpoint(id='eval-srv-create-task-ep', 
            root=ev, path1="evaluation_service", path2="create-task", method="POST", auth=auth, 
            role=lambda_eval_srv_create_task_role, 
            lambda_file_name="eval-srv-create-task", 
            instance_hash=self.instance_hash, memory_m=128, timeout_s=30, ephemeral_storage_size=512,
            evns={
             'DYNAMO_EVAL_TASK_TABLE': DYNAMO_EVAL_TASK_TABLE,
             'SQS_URL': self.eval_task_sqs.queue_url,
            })   

        # POST v1/evaluation/delete-task
        # Lambda: eval-srv-delete-task
        lambda_eval_srv_delete_task_role = _iam.Role(   
            self, "EvalSrvLambdaDeleteTaskRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"eval-srv-delete-task-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/eval-srv-delete-task{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_EVAL_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_EVAL_TASK_TABLE}",
                        ]
                    ),
                ]
            )}
        )
        self.create_api_endpoint(id='eval-srv-delete-task-ep', 
            root=ev, path1="evaluation_service", path2="delete-task", method="POST", auth=auth, 
            role=lambda_eval_srv_delete_task_role, 
            lambda_file_name="eval-srv-delete-task", 
            instance_hash=self.instance_hash, memory_m=128, timeout_s=30, ephemeral_storage_size=512,
            evns={
             'DYNAMO_EVAL_TASK_TABLE': DYNAMO_EVAL_TASK_TABLE,
            })   

        # POST v1/evaluation/get-tasks
        # Lambda: eval-srv-get-tasks
        lambda_eval_srv_get_tasks_role = _iam.Role(   
            self, "EvalSrvLambdaGetTasksRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"eval-srv-get-tasks-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/eval-srv-get-tasks{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_EVAL_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_EVAL_TASK_TABLE}",
                        ]
                    ),
                ]
            )}
        )
        self.create_api_endpoint(id='eval-srv-get-tasks-ep', 
            root=ev, path1="evaluation_service", path2="get-tasks", method="POST", auth=auth, 
            role=lambda_eval_srv_get_tasks_role, 
            lambda_file_name="eval-srv-get-tasks", 
            instance_hash=self.instance_hash, memory_m=128, timeout_s=30, ephemeral_storage_size=512,
            evns={
             'DYNAMO_EVAL_TASK_TABLE': DYNAMO_EVAL_TASK_TABLE,
            })   

    def deploy_async_task_processing(self):
        # Create an SQS dead-letter queue
        dl_queue = _sqs.Queue(
            self, "EvalSrvTaskDeadLetterQueue",
            queue_name=f"eval-srv-task-dead-letter-queue{self.instance_hash}",
            visibility_timeout=Duration.seconds(30),
            retention_period=Duration.days(14),
            removal_policy=RemovalPolicy.DESTROY,
            enforce_ssl=True,
        )

        # Create SQS: evaluation task
        self.eval_task_sqs = _sqs.Queue(self, 
            id="EvalSrvTaskQueue",
            queue_name=f"eval-srv-task-queue{self.instance_hash}",
            delivery_delay=Duration.seconds(30),
            visibility_timeout=Duration.seconds(900),
            removal_policy=RemovalPolicy.DESTROY,
            enforce_ssl=True,
            dead_letter_queue=_sqs.DeadLetterQueue(
                max_receive_count=1000, 
                queue=dl_queue
            )
        )

        # Create Lambda triggered by SQS
        # Lambda: eval-srv-create-task-processor
        lambda_eval_task_processor_role = _iam.Role(
            self, "EvalSrvLambdaTaskProcessorRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"eval-srv-create-task-processor-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["bedrock:InvokeModel"],
                        resources=["arn:aws:bedrock:*::foundation-model/amazon.titan*", "arn:aws:bedrock:*::foundation-model/anthropic.*"]
                    ), 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["sqs:SendMessage","sqs:DeleteMessage","sqs:ChangeMessageVisibility","sqs:GetQueueAttributes","sqs:ReceiveMessage"],
                        resources=[self.eval_task_sqs.queue_arn]
                    ), 
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/eval-srv-create-task-processor{self.instance_hash}:*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["dynamodb:DeleteItem","dynamodb:Query", "dynamodb:Scan", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
                        resources=[
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_EVAL_TASK_TABLE}/index/*",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{DYNAMO_EVAL_TASK_TABLE}",
                        ]
                    )
                ]
            )}
        )
        lambda_task_processor = _lambda.Function(self, 
            id='EvalSrvTaskProcessorLambda', 
            function_name=f"eval-srv-create-task-processor{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='eval-srv-create-task-processor.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", "evaluation_service/lambda/eval-srv-create-task-processor")),
            timeout=Duration.seconds(900),
            memory_size=128,
            ephemeral_storage_size=Size.mebibytes(512),
            role=lambda_eval_task_processor_role,
            environment={
                'DYNAMO_EVAL_TASK_TABLE': DYNAMO_EVAL_TASK_TABLE,
                'SQS_URL': self.eval_task_sqs.queue_url,
                'BEDROCK_REGION': self.bedrock_region,
                'BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3': BEDROCK_ANTHROPIC_CLAUDE_SONNET_V3
            },
        )

        lambda_task_processor.add_event_source(lambda_event_sources.SqsEventSource(
            queue=self.eval_task_sqs,
            batch_size=1 
        ))

    def create_api_endpoint(self, id, root, path1, path2, method, auth, role, lambda_file_name, instance_hash, memory_m, timeout_s, ephemeral_storage_size, evns, layers=None):
        lambda_funcation = _lambda.Function(self, 
            id=id, 
            function_name=f"{lambda_file_name}{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler=f'{lambda_file_name}.lambda_handler',
            code=_lambda.Code.from_asset(os.path.join("../source/", f"evaluation_service/lambda/{lambda_file_name}")),
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
                lambda_funcation,
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