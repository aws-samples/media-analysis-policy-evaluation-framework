#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import CfnParameter as _cfnParameter
from aws_cdk import Stack,CfnOutput
from aws_cdk import aws_s3 as _s3
from aws_cdk import Duration
from aws_cdk import Fn, Token, CfnCondition
from aws_cdk import aws_opensearchservice as opensearch, aws_ec2 as ec2

import uuid, os, json
from extraction_service.extraction_service_pre_stack import ExtractionServicePreStack
from extraction_service.extraction_service_stack import ExtractionServiceStack
from evaluation_service.evaluation_service_stack import EvaluationServiceStack
from policy_eval_frontend.frontend_stack import FrontendStack
from cdk_nag import AwsSolutionsChecks, NagSuppressions

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"), 
    region=os.environ.get("CDK_DEFAULT_REGION")
)

class RootStack(Stack):
    instance_hash = None
    user_emails = None
    opensearch_config = None
    extraction_service_only = True

    def __init__(self, scope):
        super().__init__(scope, id="VideoAnalysisRootStack", env=env, description="Video analysis stack.",
        )
        self.instance_hash = ""#str(uuid.uuid4())[0:5]
        self.opensearch_config = None

        # Inputs
        input_user_emails = _cfnParameter(self, "inputUserEmails", type="String",
                                description="Use your email to log in to the web portal. Split by comma if there are multiple emails."
                                )
        if input_user_emails is not None:
            self.user_emails = input_user_emails.value_as_string

        env_key = self.node.try_get_context("env")
        if env_key is None or len(env_key) == 0:
            env_key = "Dev"
        self.config = self.node.try_get_context(env_key)
        self.opensearch_config = self.config["opensearch"]
        
        # Extraction service pre stack
        extraction_service_pre_stack = ExtractionServicePreStack(self, "ExtractionServicePreStack", description="Upsert OpenSearch ServiceLinkedRole to avoid conflict",
            instance_hash_code=self.instance_hash,
            timeout = Duration.hours(1)
        )
        # Extraction service stack
        extraction_service_stack = ExtractionServiceStack(self, "ExtractionServiceStack", description="Deploy extraction backend services: VPC, OpenSearch, BastionHost, Cognito, API Gateway, Lambda, Step Functions, S3, etc.",
            instance_hash_code=self.instance_hash,
            timeout = Duration.hours(4),
            opensearch_config = self.opensearch_config,
            s3_bucket_name_extraction = extraction_service_pre_stack.s3_extraction_bucket_name,
            transcribe_region = self.config.get("transcribe_region", env.region), 
            rekognition_region= self.config.get("rekognition_region", env.region), 
            bedrock_region= self.config.get("bedrock_region", env.region),
        )
        extraction_service_stack.node.add_dependency(extraction_service_pre_stack)

        # Evaluation service stack
        evaluation_service_stack = EvaluationServiceStack(self, "EvaluationServiceStack", description="Deploy evaluation service: API Gateway, Lambda",
            instance_hash_code=self.instance_hash,
            timeout = Duration.hours(1),
            cognito_user_pool_id=extraction_service_stack.cognito_user_pool_id,
            bedrock_region= self.config.get("bedrock_region", env.region),
        )
        evaluation_service_stack.node.add_dependency(extraction_service_stack)
        
        # Policy evaluation Frontend stack
        frontend_stack = FrontendStack(self, "FrontStack", description="Deploy policy evaluation frontend static website: S3, CloudFormation, provision Lambda",
            instance_hash_code=self.instance_hash,
            api_gw_base_url_extr_srv = extraction_service_stack.api_gw_base_url,
            api_gw_base_url_eval_srv = evaluation_service_stack.api_gw_base_url,
            cognito_user_pool_id = extraction_service_stack.cognito_user_pool_id,
            cognito_app_client_id = extraction_service_stack.cognito_app_client_id,
            user_emails = self.user_emails,
            opensearch_domain_arn=extraction_service_stack.opensearch_domain_arn,
            bastion_host_id=extraction_service_stack.bastion_host_id,
            opensearch_domain_endpoint=extraction_service_stack.opensearch_domain_endpoint
        )
        frontend_stack.node.add_dependency(extraction_service_stack)

        CfnOutput(self, "Website URL", value=f"https://{frontend_stack.output_url}")
        CfnOutput(self, "API Gateway Base URL: Evaluation Service", value=evaluation_service_stack.api_gw_base_url)
        
        CfnOutput(self, "Bastion Host Id", value=extraction_service_stack.bastion_host_id)
        CfnOutput(self, "OpenSearch Domain Endpoint", value=extraction_service_stack.opensearch_domain_endpoint)
        CfnOutput(self, "Cognito User Pool Id", value=extraction_service_stack.cognito_user_pool_id)
        CfnOutput(self, "Cognito App Client Id", value=extraction_service_stack.cognito_app_client_id)
        CfnOutput(self, "API Gateway Base URL: Extraction Service", value=extraction_service_stack.api_gw_base_url)

app = cdk.App()
root_stack = RootStack(app)

nag_suppressions = [
        {
            "id": "AwsSolutions-IAM5",
            "reason": "AWS managed policies are allowed which sometimes uses * in the resources like - AWSGlueServiceRole has aws-glue-* . AWS Managed IAM policies have been allowed to maintain secured access with the ease of operational maintenance - however for more granular control the custom IAM policies can be used instead of AWS managed policies",
        },
        {
            "id": "AwsSolutions-IAM4",
            "reason": "AWS Managed IAM policies have been allowed to maintain secured access with the ease of operational maintenance - however for more granular control the custom IAM policies can be used instead of AWS managed policies",
        },
        {
            'id': 'AwsSolutions-EC23',
            'reason': 'The Bastion hosts security group open to the public to allow end users access OpenSearch Dashboards via port forwarding through AWS Session Manager. Users can set up additional rules to restrict access to a specific list of IPs for better access control.'
        },
        {
            'id': 'AwsSolutions-L1',
            'reason': 'Python 3.10 lambda function is required to run langchain lib not compatiable with higher Python version.'
        },
        {
            'id': 'AwsSolutions-EC28',
            'reason': 'The EC2 instance provinsioned as a Bastion Host for admin user to access OpenSearch DB. HA is not required for this instance.'
        },
        {
            'id': 'AwsSolutions-EC29',
            'reason': 'The EC2 instance provinsioned as a Bastion Host for admin user to access OpenSearch DB. HA is not required for this instance.'
        },
        {
            'id': 'AwsSolutions-OS3',
            'reason': 'OpenSearch service is deployed to a VPC provisioned as part of the CDK package. Only Lambdas within the VPC could access the OpenSearch service, so there is no need to allowlist IP addresses.'
        },
        {
            'id': 'AwsSolutions-OS5',
            'reason': 'OpenSearch service is deployed to a VPC provisioned as part of the CDK package. Only Lambdas within the VPC could access the OpenSearch service, so it allows anaonymous access within the vpc.'
        },
        {
            'id': 'AwsSolutions-OS4',
            'reason': 'The default OpenSearch domain settings are configured for a development environment to save costs. This setup does not support high availability (HA), lacks master nodes, and does not include zone awareness. The production configuration in the cdk.json file supports HA. Enabling HA for OpenSearch is a decision left to the user.'
        },
        {
            'id': 'AwsSolutions-OS7',
            'reason': 'The default OpenSearch domain settings are configured for a development environment to save costs. This setup does not support high availability (HA), lacks master nodes, and does not include zone awareness. The production configuration in the cdk.json file supports HA. Enabling HA for OpenSearch is a decision left to the user.'
        },
        {
            'id': 'AwsSolutions-APIG2',
            'reason': 'API request validation is handled within the Lambda functions.'
        },
        {
            'id': 'AwsSolutions-APIG4',
            'reason': 'False Positive detection. All API Gateway methods are authorized using a Cognitio authrozier provisioned in the CDK.'
        },
        {
            'id': 'AwsSolutions-COG4',
            'reason': 'False Positive detection. All API Gateway methods are authorized using a Cognitio authrozier provisioned in the CDK.'
        },
        {
            'id': 'AwsSolutions-S1',
            'reason': 'The CloudFront access log bucket has logging disabled. It is up to the user to decide whether to enable the access log to the log bucket.'
        },
        {
            'id': 'AwsSolutions-CFR4',
            'reason': 'The internal admin web portal is deployed using the default CloudFront domain and certification. User can set up DNS to route the web portal through their managed domain and replace the certification to resolve this issue.'
        }
    ]

NagSuppressions.add_stack_suppressions(
    root_stack,
    nag_suppressions,
    apply_to_nested_stacks=True
)

cdk.Aspects.of(app).add(AwsSolutionsChecks())

app.synth()
