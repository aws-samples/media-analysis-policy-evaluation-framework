from aws_cdk import (
    Stack,
    NestedStack,
    Size,
    aws_s3 as _s3,
    aws_ec2 as ec2,
    CfnParameter as _cfnParameter,
    aws_s3_deployment as _s3_deploy,
    aws_lambda as _lambda,
    aws_iam as _iam,
    Environment,
    Duration,
    RemovalPolicy,
    CfnOutput,
    CustomResource,
    Token,
    Fn,
    CfnResource,
    custom_resources
)
from aws_cdk.aws_logs import RetentionDays
from aws_cdk.aws_apigateway import IdentitySource
from aws_cdk.aws_kms import Key
from aws_cdk.aws_ec2 import SecurityGroup

from constructs import Construct
import os
import uuid
import json
from extraction_service.constant import *

class ExtractionServicePreStack(NestedStack):
    account_id = None
    region = None
    instance_hash = None

    s3_extraction_bucket_name = None

    def __init__(self, scope: Construct, construct_id: str, instance_hash_code, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.account_id=os.environ.get("CDK_DEFAULT_ACCOUNT")
        self.region=os.environ.get("CDK_DEFAULT_REGION")
        
        self.instance_hash = instance_hash_code

        self.deploy_s3()
        self.deploy_provision()

    def deploy_s3(self):
        # Create extraction S3 bucket
        self.s3_bucket_name_extraction = f'{S3_BUCKET_EXTRACTION_PREFIX}-{self.account_id}-{self.region}{self.instance_hash}'
        s3_extraction_bucket = _s3.Bucket(self, "ExtractionBucket", 
            bucket_name=self.s3_bucket_name_extraction,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            server_access_logs_prefix="access-log/",
            enforce_ssl=True,
            cors=[_s3.CorsRule(
                allowed_methods=[_s3.HttpMethods.GET, _s3.HttpMethods.POST, _s3.HttpMethods.PUT, _s3.HttpMethods.DELETE, _s3.HttpMethods.HEAD],
                allowed_origins=["*"],
                allowed_headers=["*"],
                exposed_headers=["ETag"],
            )])
        self.s3_extraction_bucket_name = s3_extraction_bucket.bucket_name
    
    def deploy_provision(self):

        aws_layer = _lambda.LayerVersion.from_layer_version_arn(self, "AwsLayerPowerTool", 
            layer_version_arn=f"arn:aws:lambda:{self.region}:017000801446:layer:AWSLambdaPowertoolsPythonV2:68"
        )

        # Custom Resource Lambda: extr-srv-extr-provision
        # Upsert AWSServiceRoleForAmazonElasticsearchService
        lambda_provision_opensearch_role = _iam.Role(
            self, "ExtrSrvPreLambdaProvisionRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-lambda-opensearch-provision-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket","s3:GetObject","s3:PutObject","s3:DeleteObject","s3:HeadObject"],
                        resources=[f"arn:aws:s3:::{self.s3_bucket_name_extraction}",f"arn:aws:s3:::{self.s3_bucket_name_extraction}/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["iam:CreateRole", "iam:CreateServiceLinkedRole","iam:GetRole"],
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
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/extr-srv-extr-provision{self.instance_hash}:*"]
                    ),
                ]
            )},
        )
        lambda_provision_py12 = _lambda.Function(self, 
            id='provision_opensearch_function_py312', 
            function_name=f"extr-srv-extr-provision-py312{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='extr-srv-extr-provision.on_event',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-extr-provision")),
            timeout=Duration.minutes(15),
            role=lambda_provision_opensearch_role,
            memory_size=3008,
            layers=[aws_layer]
        )
        lambda_provision_py10 = _lambda.Function(self, 
            id='provision_opensearch_function_py310', 
            function_name=f"extr-srv-extr-provision-py310{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler='extr-srv-extr-provision.on_event',
            code=_lambda.Code.from_asset(os.path.join("../source/", "extraction_service/lambda/extr-srv-extr-provision")),
            timeout=Duration.minutes(15),
            role=lambda_provision_opensearch_role,
            memory_size=3008,
            layers=[aws_layer]
        )

        lambda_provision_invoke_role = _iam.Role(
            self, "ExtrSrvPreLambdaProvisionInvokeRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"extr-srv-lambda-opensearch-provision-invoke-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["ec2:DescribeInstances", "ec2:CreateNetworkInterface", "ec2:AttachNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"],
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["lambda:InvokeFunction", "lambda:InvokeAsync"],
                        resources=[lambda_provision_py12.function_arn, lambda_provision_py10.function_arn],
                    )
                ]
            )}
        )
        # Create ServiceLined role, lambda layers (Python3.12)
        c_resource = custom_resources.AwsCustomResource(self,
            id=f"provision-extr-srv-invoke-py312",
            log_retention=RetentionDays.ONE_WEEK,
            on_create=custom_resources.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=custom_resources.PhysicalResourceId.of("Trigger"),
                parameters={
                    "FunctionName": lambda_provision_py12.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": json.dumps(
                        {
                            "RequestType":"Create",
                            "Layers": [
                                {
                                    "name": "opensearch-py",
                                    "packages": [
                                        {
                                            "name":"opensearch-py",
                                            "version":"2.4.2",
                                        }
                                    ],
                                    "s3_bucket":self.s3_extraction_bucket_name,
                                    "s3_key":LAMBDA_LAYER_SOURCE_S3_KEY_OPENSEARCHPY
                                },
                                {
                                    "name": "moviepy",
                                    "packages": [
                                        {
                                            "name":"moviepy",
                                            "version":"1.0.3",
                                        }
                                    ],
                                    "s3_bucket":self.s3_extraction_bucket_name,
                                    "s3_key":LAMBDA_LAYER_SOURCE_S3_KEY_MOVIEPY
                                }
                            ]
                        }
                    )
                },
                output_paths=["Payload"]
            ),
            role=lambda_provision_invoke_role
        )    

        # Create ServiceLined role, lambda layers (Python3.10)
        c_resource = custom_resources.AwsCustomResource(self,
            id=f"provision-extr-srv-invoke-py310",
            log_retention=RetentionDays.ONE_WEEK,
            on_create=custom_resources.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=custom_resources.PhysicalResourceId.of("Trigger"),
                parameters={
                    "FunctionName": lambda_provision_py10.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": json.dumps(
                        {
                            "RequestType":"Create",
                            "Layers": [
                                {
                                    "name": "langchain_faiss",
                                    "packages": [
                                        {
                                            "name":"langchain",
                                            "version":"0.0.343",
                                        },
                                        {
                                            "name":"faiss-cpu",
                                            "version":"1.8.0",
                                        }                                    
                                    ],
                                    "s3_bucket":self.s3_extraction_bucket_name,
                                    "s3_key":LAMBDA_LAYER_SOURCE_S3_KEY_LANGCHAIN
                                }
                            ]
                        }
                    )
                },
                output_paths=["Payload"]
            ),
            role=lambda_provision_invoke_role
        )    

