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
from policy_eval_frontend.constant import *


class FrontendStack(NestedStack):
    instance_hash = None
    region = None
    account_id = None
    api_gw_base_url_extr_srv = None
    api_gw_base_url_eval_srv = None
    cognito_user_pool_id = None
    cognito_app_client_id = None
    user_emails = None
    opensearch_domain_arn = None
    bastion_host_id = None
    
    output_url = ""

    def __init__(self, scope: Construct, construct_id: str, 
            instance_hash_code, 
            api_gw_base_url_extr_srv, 
            api_gw_base_url_eval_srv, 
            cognito_user_pool_id, 
            cognito_app_client_id, 
            user_emails, 
            opensearch_domain_arn, 
            opensearch_domain_endpoint, 
            bastion_host_id,
            **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.instance_hash = instance_hash_code #str(uuid.uuid4())[0:5]
        
        self.account_id=os.environ.get("CDK_DEFAULT_ACCOUNT")
        self.region=os.environ.get("CDK_DEFAULT_REGION")
        
        self.api_gw_base_url_extr_srv = api_gw_base_url_extr_srv
        self.api_gw_base_url_eval_srv = api_gw_base_url_eval_srv
        self.cognito_user_pool_id = cognito_user_pool_id
        self.cognito_app_client_id = cognito_app_client_id

        self.user_emails = user_emails
        self.opensearch_domain_arn = opensearch_domain_arn
        self.bastion_host_id = bastion_host_id

        web_bucket = _s3.Bucket(
            self,
            id="FronendWebBucket",
            bucket_name=f'{S3_BUCKET_NAME_PREFIX}-web-{self.account_id}-{self.region}{self.instance_hash}',
            access_control=_s3.BucketAccessControl.PRIVATE,
            website_index_document="index.html",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            server_access_logs_prefix="access-log/",
            enforce_ssl=True
        )
        
        _s3_deployment.BucketDeployment(
            self,
            id="genai-content-analysis-web-bucket-deploy",
            sources=[_s3_deployment.Source.asset("../source/policy_eval_frontend/web/build")],
            destination_bucket=web_bucket)
        
        # CloudFront Distribution
        cf_oai = _cloudfront.OriginAccessIdentity(self, 'CloudFrontOriginAccessIdentity')
 
        web_bucket.add_to_resource_policy(_iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[web_bucket.arn_for_objects('*')],
            principals=[_iam.CanonicalUserPrincipal(
                cf_oai.cloud_front_origin_access_identity_s3_canonical_user_id
            )],
        ))

        # Create log bucket if doesn't exist
        web_log_bucket = _s3.Bucket(
            self,
            id="WebLogBucket",
            bucket_name=f'{S3_BUCKET_NAME_PREFIX}-log-{self.account_id}-{self.region}{self.instance_hash}',
            object_ownership=_s3.ObjectOwnership.OBJECT_WRITER,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            #server_access_logs_prefix="access-log/",
        )

        cf_dist = _cloudfront.CloudFrontWebDistribution(self, "genai-content-analysis-web-cloudfront-dist",
            origin_configs=[
                _cloudfront.SourceConfiguration(
                    s3_origin_source=_cloudfront.S3OriginConfig(
                        s3_bucket_source=web_bucket,
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
                bucket=web_log_bucket,
                include_cookies=False,
                prefix="access-log/"
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
                        actions=["cognito-idp:AdminCreateUser","cognito-idp:UpdateUserPool"],
                        resources=[f"arn:aws:cognito-idp:{self.region}:{self.account_id}:userpool/{self.cognito_user_pool_id}"]
                    ),
                    _iam.PolicyStatement(
                        effect=_iam.Effect.ALLOW,
                        actions=["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:HeadObject"],
                        resources=[web_bucket.bucket_arn,f'{web_bucket.bucket_arn}/*']
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
            id='provision-update-web-urls', 
            function_name=f"front-end-provision-custom-resource{self.instance_hash}", 
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler='provision-custom-resource.on_event',
            code=_lambda.Code.from_asset(os.path.join("../source/", "policy_eval_frontend/lambda/provision-web")),
            timeout=Duration.seconds(120),
            role=lambda_provision_web_role,
            memory_size=512,
            environment={
             'APIGW_URL_PLACE_HOLDER_EXTR_SRV': '[[[APIGATEWAY_BASE_URL_EXTR_SRV]]]',
             'APIGW_URL_PLACE_HOLDER_EVAL_SRV': '[[[APIGATEWAY_BASE_URL_EVAL_SRV]]]',
             'COGNITO_USER_POOL_ID_PLACE_HOLDER':'[[[COGNITO_USER_POOL_ID]]]',
             'COGNITO_USER_IDENTITY_POOL_ID_PLACE_HOLDER': '[[[COGNITO_IDENTITY_POOL_ID]]]',
             'COGNITO_REGION_PLACE_HOLDER': '[[[COGNITO_REGION]]]',
             'COGNITO_USER_POOL_CLIENT_ID_PLACE_HOLDER':'[[[COGNITO_USER_POOL_CLIENT_ID]]]',
             'COGNITO_USER_POOL_ID': self.cognito_user_pool_id,
             'COGNITO_USER_POOL_CLIENT_ID': self.cognito_app_client_id,
             'APIGW_URL_EXTR_SRV': api_gw_base_url_extr_srv + 'v1',
             'APIGW_URL_EVAL_SRV': api_gw_base_url_eval_srv + 'v1',
             'COGNITO_REGION': self.region,
             'COGNITO_USER_IDENTITY_POOL_ID': '',
             'S3_WEB_BUCKET_NAME': web_bucket.bucket_name,
             'S3_JS_PREFIX': 'static/js/',
             'CLOUD_FRONT_DISTRIBUTION_ID': cf_dist.distribution_id,
             'COGNITO_USER_EMAILS': self.user_emails,
             'COGNITO_INVITATION_EMAIL_TEMPLATE': COGNITO_INVITATION_EMAIL_TEMPLATE,
             'COGNITO_INVITATION_EMAIL_TITLE': COGNITO_INVITATION_EMAIL_TITLE,
             'CLOUD_FRONT_URL': cf_dist.distribution_domain_name,
             'APP_NAME': APP_NAME,
             'OPENSEARCH_DOMAIN_ENDPOINT': opensearch_domain_endpoint,
             'SSM_INSTRUCTION_URL': SSM_INSTRUCTION_URL,
             'BASTION_HOST_ID': self.bastion_host_id
            }
        )
        
        lambda_provision_invoke_role = _iam.Role(
            self, "FrontendLambdaProvisionInvokeRole",
            assumed_by=_iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={"frontend-lambda-provision-invoke-poliy": _iam.PolicyDocument(
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
            f"provision-web-provider{self.instance_hash}",
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