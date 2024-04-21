#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import CfnParameter as _cfnParameter
from aws_cdk import Stack,CfnOutput
from aws_cdk import aws_s3 as _s3
from aws_cdk import Duration
from aws_cdk import Fn, Token, CfnCondition
from aws_cdk import aws_opensearchservice as opensearch, aws_ec2 as ec2

import uuid, os, json
from extraction_service.stack.extraction_service_pre_stack import ExtractionServicePreStack
from extraction_service.stack.extraction_service_stack import ExtractionServiceStack
from evaluation_service.stack.evaluation_service_stack import EvaluationServiceStack
from policy_eval_frontend.stack.frontend_stack import FrontendStack
from extraction_service.stack.extraction_service_swagger_stack import ExtractionServiceSwaggerStack

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
        super().__init__(scope, id="ContentAnalysisRootStack", env=env, description="Content analysis stack. Beta",
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
        if env_key is None:
            env_key = "Dev"
        self.opensearch_config = self.node.try_get_context(env_key)["opensearch"]
        
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
            s3_bucket_name_extraction = extraction_service_pre_stack.s3_extraction_bucket_name
        )
        extraction_service_stack.node.add_dependency(extraction_service_pre_stack)

        # Evaluation service stack
        evaluation_service_stack = EvaluationServiceStack(self, "EvaluationServiceStack", description="Deploy evaluation service: API Gateway, Lambda",
            instance_hash_code=self.instance_hash,
            timeout = Duration.hours(1),
            cognito_user_pool_id=extraction_service_stack.cognito_user_pool_id
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

app.synth()