import os
from aws_cdk import (
    aws_iam as _iam,
    aws_s3 as _s3,
    aws_s3_deployment as _s3_deployment,
    aws_cloudfront as _cloudfront,
    aws_cloudfront_origins as _origins,
    aws_lambda as _lambda,
    Stack,
    RemovalPolicy,
    CustomResource,
    Duration,
    custom_resources as cr,
    NestedStack,
)
from aws_cdk.aws_logs import RetentionDays
from constructs import Construct
from extraction_service.stack.constant import *


class ExtractionServiceSwaggerStack(NestedStack):
    instance_hash = None
    region = None
    account_id = None
    api_gw_base_url_extr_srv = None
    
    output_url = None

    def __init__(self, scope: Construct, construct_id: str, 
            instance_hash_code, 
            api_gw_base_url_extr_srv, 
            **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.instance_hash = instance_hash_code #str(uuid.uuid4())[0:5]
        
        self.account_id=os.environ.get("CDK_DEFAULT_ACCOUNT")
        self.region=os.environ.get("CDK_DEFAULT_REGION")
        
        self.api_gw_base_url_extr_srv = api_gw_base_url_extr_srv

        swagger_bucket = _s3.Bucket(
            self,
            id="SwaggerWebBucket",
            bucket_name=f'{S3_BUCKET_EXTRACTION_PREFIX}-web-{self.account_id}-{self.region}{self.instance_hash}',
            access_control=_s3.BucketAccessControl.PRIVATE,
            website_index_document="index.html",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            server_access_logs_prefix="access-log/",
            enforce_ssl=True
        )
        
        _s3_deployment.BucketDeployment(
            self,
            id="ExtrSrvSwaggerBucketDeployment",
            sources=[_s3_deployment.Source.asset("./extraction_service/swagger/dist")],
            destination_bucket=swagger_bucket)
        
        # CloudFront Distribution
        cf_oai = _cloudfront.OriginAccessIdentity(self, 'CloudFrontOriginAccessIdentity')
 
        swagger_bucket.add_to_resource_policy(_iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[swagger_bucket.arn_for_objects('*')],
            principals=[_iam.CanonicalUserPrincipal(
                cf_oai.cloud_front_origin_access_identity_s3_canonical_user_id
            )]
        ))
        
        cf_dist = _cloudfront.CloudFrontWebDistribution(self, "ExtrSrvSwaggerCloudfrontDist",
            origin_configs=[
                _cloudfront.SourceConfiguration(
                    s3_origin_source=_cloudfront.S3OriginConfig(
                        s3_bucket_source=swagger_bucket,
                        origin_access_identity=cf_oai
                    ),
                    behaviors=[_cloudfront.Behavior(
                        is_default_behavior=True,
                        viewer_protocol_policy=_cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    )]
                )
            ],
            default_root_object="index.html",
            logging_config = _cloudfront.LoggingConfiguration(
                bucket=_s3.Bucket(
                    self,
                    id="SwaggerLogBucket",
                    bucket_name=f'{S3_BUCKET_EXTRACTION_PREFIX}-swagger-log-{self.account_id}-{self.region}{self.instance_hash}',
                    object_ownership=_s3.ObjectOwnership.OBJECT_WRITER,
                    removal_policy=RemovalPolicy.DESTROY,
                    auto_delete_objects=True,
                    enforce_ssl=True,
                    server_access_logs_prefix="access-log/",
                ),
                include_cookies=False,
                prefix="logs/"
            ),
            http_version=_cloudfront.HttpVersion.HTTP2_AND_3,
        )

        self.output_url = cf_dist.distribution_domain_name

        # Custom Resource Lambda: provision-custom-resource
        # Replace APIGateway URL and Cognitio keys in S3 static website 
        lambda_provision_web_role = _iam.Role(
            self, "FrontendLambdaProvisionRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"frontend-lambda-provision-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:HeadObject"],
                        resources=[swagger_bucket.bucket_arn,f'{swagger_bucket.bucket_arn}/*']
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["cloudfront:CreateInvalidation"],
                        resources=[f"arn:aws:cloudfront::{self.account_id}:distribution/*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogGroup"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:*"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                        resources=[f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/lambda/front-end-provision-custom-resource{self.instance_hash}:*"]
                    ),
                ]
            )}
        )
        lambda_provision = _lambda.Function(self, 
            id='SwaggerProvisionLambda', 
            function_name=f"provision-swagger-custom-resource{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='provision-swagger-custom-resource.on_event',
            code=_lambda.Code.from_asset(os.path.join("./", "extraction_service/lambda/provision-swagger")),
            timeout=Duration.seconds(120),
            role=lambda_provision_web_role,
            memory_size=512,
            environment={
             'APIGW_URL_PLACE_HOLDER_EXTR_SRV': '[[[APIGW_URL_EXTR_SRV]]]',
             'APIGW_URL_EXTR_SRV': api_gw_base_url_extr_srv,
             'S3_SWAGGER_BUCKET_NAME': swagger_bucket.bucket_name,
             'CLOUD_FRONT_DISTRIBUTION_ID': cf_dist.distribution_id,
             }
        )
        
        lambda_provision_invoke_role = _iam.Role(
            self, "SwaggerLambdaProvisionInvokeRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"swagger-lambda-provision-invoke-poliy": _iam.PolicyDocument(
                statements=[
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["lambda:InvokeFunction", "lambda:InvokeAsync"],
                        resources=[lambda_provision.function_arn],
                    )
                ]
            )}
        )
        c_resource = cr.AwsCustomResource(
            self,
            f"SwaggerProvisionInvokeLambdaCustomResource",
            log_retention=RetentionDays.ONE_WEEK,
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                physical_resource_id=cr.PhysicalResourceId.of("Trigger"),
                parameters={
                    "FunctionName": lambda_provision.function_name,
                    "InvocationType": "RequestResponse",
                    "Payload": "{\"RequestType\": \"Create\"}"
                },
                output_paths=["Payload"]
            ),
            role=lambda_provision_invoke_role
        )     