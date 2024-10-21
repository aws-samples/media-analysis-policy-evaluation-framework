# Media Analysis and Policy Evaluation Framework

## Table of Content

1. [Overview](#overview)
    - [Architecture Overview](#architecture-overview)
    - [Highlighted features](#highlighted-features)
    - [Cost](#cost)
2. [Prerequisites](#prerequisites)
    - [Install environment dependencies and set up authentication](#install-environment-dependencies-and-set-up-authentication)
    - [Service limits](#service-limits)
    - [Supported Regions](#supported-regions)
3. [Deployment Steps](#deployment-steps)
4. [Deployment Validation](#deployment-validation)
5. [Running the Guidance](#running-the-guidance)
6. [Cleanup](#cleanup)
7. [Known Issues](#known-issues)
8. [Notices](#notices)
9. [Authors](#authors)

## Overview

Organizations across media and entertainment, advertising, social media, education, and other sectors require efficient solutions to extract information from videos and apply flexible evaluations based on their policies. Generative artificial intelligence (AI) has unlocked fresh opportunities for these use cases. This solution uses AWS AI and generative AI services to provide a framework to streamline video extraction and evaluation processes.

This solution is designed for two personas: business users and builders. 
- Business users who seek to utilize a ready-made tool for media asset analysis and policy evaluation can take advantage of the built-in UI. They can upload videos, manage customized policy documents using Bedrock Knowledge Base, and apply flexible policy evaluation. 
- For builders in search of a modular solution for video extraction, user/face mapping, and LLMs analysis, they can deploy the backend micro-service independently and integrate it into their workflow.

This tool can be utilized for comprehensive video content analysis, encompassing but not limited to:
- Content Moderation
- Customized policy evaluation
- IAB classfication
- Video summarization
- Video scene detection

The solution is available as a [CDK](https://aws.amazon.com/cdk/) package, which you can deploy to your AWS account by following the [instruction](#deployment-steps).

### Architecture Overview

The solution can be deployed to your AWS account as a CDK package with a serverless architecture. It consists of three loosely coupled microservices:

- **Web UI**: This allows users to upload videos, extract metadata, and apply dynamic analysis in a self-serve manner. It is a static React application hosted on [AWS S3](https://aws.amazon.com/s3/) as a static website, with [Amazon CloudFront](https://aws.amazon.com/cloudfront/) for content distribution, [Amazon Cognito](https://aws.amazon.com/cognito/) user pool, and [Amazon Amplify](https://aws.amazon.com/amplify/) for authentication.
- **Extraction Service**: The core component of the solution that manages the video metadata extraction workflow. It supports concurrency management, high availability, and flexible configuration. The extracted data is accessible via S3 and RESTful APIs. It is built using [Amazon Step Functions](https://aws.amazon.com/step-functions/), [Amazon API Gateway](https://aws.amazon.com/api-gateway/), [AWS Lambda](https://aws.amazon.com/lambda/), [Amazon DynamoDB](https://aws.amazon.com/dynamodb/), [Amazon OpenSearch Service](https://aws.amazon.com/opensearch-service/), [Amazon SQS](https://aws.amazon.com/sqs/), [Amazon SNS](https://aws.amazon.com/sns/), Amazon S3, and [Amazon VPC](https://aws.amazon.com/vpc/).
- **Evaluation Service**: A lightweight component that helps users construct GenAI prompts and easily run evaluation tasks through the Web UI. It includes sample prompt templates for video content moderation, summarization, and IAB classification, demonstrating how to leverage Generative AI for flexible video analysis based on the Extraction Service output. This is a serverless application utilizing Amazon API Gateway, AWS Lambda, [Amazon Bedrock](https://aws.amazon.com/bedrock/), and Amazon DynamoDB.

![configureation UI](./assets/guidance-diagram.png)

### Highlighted features
The solution automatically extracts metadata from both the visual and audio aspects of a video. The metadata is accessible in two ways:
- As raw extraction files (in JSON and text file formats) stored in S3.
- Via RESTful APIs with pagination for accessing the extracted data.

The extraction service allows you to customize the extraction process, including:
- Sample frequency
- Smart sampling
- Which ML features are applied at the frame level
- Whether to enable audio transcription
- Whether to perform shot analysis. 

This flexibility gives users control over the workflow, enabling only the necessary features to optimize costs and processing times. Below is a screenshot of the extraction configuration page. The same settings can also be configured via the RESTful API.
![Extraction Configuration](./assets/extraction-config.png)

#### Video Extraction Data
- **Video Frames**

    Image frames are sampled from the video based on the provided sampling interval, with "smart sampling" enabled to remove adjacent similar image frames utilizing Amazon Bedrock [Titan](https://aws.amazon.com/bedrock/titan) Multimodal Embedding and Vector DB similarity search, optimizing costs and reducing processing time. The following metadata is generated at the frame level:
    - Timestamp: The exact time the frame was captured from the video.
    - Labels: Thousands of generic labels detected using [Amazon Rekognition](https://aws.amazon.com/rekognition/)’s [DetectLabels API](https://docs.aws.amazon.com/rekognition/latest/dg/labels-detect-labels-image.html).
    - Text: Text in images extracted using Amazon Rekognition’s [DetectText API](https://docs.aws.amazon.com/rekognition/latest/dg/text-detection.html).
    - Celebrity: Well known faces detected using Amazon Rekognition’s [DetectCelebrities API](https://docs.aws.amazon.com/rekognition/latest/dg/celebrities.html).
    - Content Moderation Labels: unsafe and inappropriate content classified using Amazon Rekognition’s [DetectModerationLabels API](https://docs.aws.amazon.com/rekognition/latest/dg/moderation.html).
    - Image Summary: Generic description of the image, generated using the Amazon Bedrock [Anthropic Claude](https://aws.amazon.com/bedrock/claude) V3 Haiku model.
    - Text embedding and multimodal embedding: Vectors generated using [Amazon Bedrock Titan](https://aws.amazon.com/bedrock/titan) Multimodal and text embedding models to support semantic search and image search.

- **Video Shots**

    A continuous sequence of frames captured by a single camera without interruption. The following metadata is available for video shots:
    - Shot Start and End Timestamps: The exact time range of the shot.
    - Shot Summary: A summary of the shot, generated based on the frame summaries and audio transcription using the Amazon Bedrock Anthropic Claude V3 Haiku model.

- **Audio Transcripts**
    - Subtitle Start and End Timestamps: The time range of each subtitle segment.
    - Audio Transcription: Generated using [Amazon Transcribe](https://aws.amazon.com/pm/transcribe).

### Customize the Extraction Service
The Extraction Service is the core component of the solution and can serve as a foundational building block for integration into existing workflows. It operates independently of the other microservices in the architecture. Its serverless design also makes it easy to extend and integrate with in-house trained or third-party ML models. For example, in the implementation diagram below, users can make minor modifications to the Lambda functions within the frame iteration subflow to incorporate additional ML models, enabling richer extraction results.

![Extraction Service](./assets/extraction-service-diagram.png)

### Cost

You are responsible for the cost of the AWS services used while running this Guidance. There are several factors can impact the monthly cost. 
- Amazon OpenSearch Service (OpenSearch) cluster settings: OpenSearch will incur a monthly cost. Choosing the 'Dev' option will deploy a cluster with a single data node. For production workloads, you can choose the 'Prod' setting to support a larger volume of searches.
- Enabling smart sampling: The solution utilizes Amazon Titan Multimodal embedding to deduplicate image frames sampled from the video. Enabling smart sampling typically reduces the number of sampled frames, thereby lowering extraction costs.
- Choose the AI/GenAI features for frame metadata extraction: Selecting fewer AI features (Amazon Rekognition and Amazon Bedrock Anthropic Claude V3 Haiku) in the video extraction configuration will reduce costs.
- Enabling audio transcription: The solution uses Amazon Transcribe to convert the audio of the video into text. You can disable audio transcription for videos that don't require audio extraction to reduce costs.

Below are a few sample cost estimations in USD for extracting 1,000 minutes of video per month in the us-east-1 region:
- **~$350** monthly: OpenSearch (Dev), enabled smart sampling (50% sample rate), enabled all the visual extraction features, enabled audio transcription.
- **~$280** monthly: OpenSearch (Dev), enabled smart sampling (50% sample rate), enabled visual extraction features: Label detection, moderation detection, text extraction, image caption, disabled audio transcription.

For production workloads, you can reach out to your AWS account team for a more detailed cost estimation.

## Prerequisites

- If you don't have the AWS account administrator access, ensure your [IAM](https://aws.amazon.com/iam/) role/user has permissions to create and manage the necessary resources and components for this solution.
- Please check the numbers of VPCs already launched in the account region where you plan to deploy the solution. The default quota for VPCs per region in the us-east-1 is 5. If the VPCs limit has already been reached in the region, you will need to increase the quota limit (+1) before deployment. You can manage the quota increase yourself using the AWS console by navigating to the ["Service Quotas" page](https://us-east-1.console.aws.amazon.com/servicequotas/home?region=us-east-1).
- In Amazon Bedrock, make sure you have access to the required models: 
    - Titan multimodal embedding V1
    - Titan text embedding V2
    - Anthropic Claude V3 Haiku and Sonnet
    - Anthropic Claude V3.5 Sonnet

    Refer to [this guide](https://catalog.workshops.aws/building-with-amazon-bedrock/en-US/prerequisites/bedrock-setup) for instructions on managing access to Bedrock models.

### Install environment dependencies and set up authentication

<details><summary>
:bulb: Skip if using CloudShell or AWS services that support bash commands from the same account (e.g., Cloud9). Required for self-managed environments like local desktops.
</summary>

- [ ] Install Node.js
https://nodejs.org/en/download/

- [ ] Install Python 3.8+
https://www.python.org/downloads/

- [ ] Install Git
https://github.com/git-guides/install-git

- [ ] Install Pip
```sh
python -m ensurepip --upgrade
```

- [ ] Install Python Virtual Environment
```sh
pip install virtualenv
```


- [ ] Setup the AWS CLI authentication
```sh
aws configure                                                                     
 ```                      
</details>

![Open CloudShell](./assets/cloudshell.png)

If your CloudShell instance has older dependency libraries like npm or pip, it may cause deployment errors. To resolve this, click 'Actions' and choose 'Delete AWS CloudShell Home Directory' to start a fresh instance.

### Service limits
The solution processes videos and extracts video frames concurrently. The number of videos and frames that can be processed in parallel depends on the related AI services quota in the deployed region. Some quotas can be increased upon request. Ensure that the following service quotas meet the requirements before increasing the extraction concurrency settings.
Amazon Rekognition, Amazon Bedrock, Amazon Transcribe

### Supported Regions
The solution requires AWS AI and Generative AI services, including Amazon Bedrock, Amazon Rekognition and Amazon Transcribe, which are available in certain regions. Please choose one of the below AWS regions to deploy the CDK package.

|||||
---------- | ---------- | ---------- | ---------- |
US | us-east-1 (N. Virginia) | us-west-2 (Oregon) ||

The solution requires access to Amazon Bedrock Foundation Models (FMs): Titan multimodal embedding, Titan text embedding, Anthropic Claude V3 models. If you are deploying the solution stack in other regions, such as Europe (Ireland), you can still try out the Amazon Bedrock FM models by choosing the model access in one of these regions: us-east-1, us-west-2 in the source/cdk.json file. Keep in mind that there will be additional Data Transfer cost across regions.

## Deployment Steps
1. Clone the source code from GitHub repo 

```
git clone git@github.com:aws-samples/media-analysis-policy-evaluation-framework.git
cd media-analysis-policy-evaluation-framework
```

2. Set up environment varaibles 

Set environment variables as input parameters for the CDK deployment package:

CDK_INPUT_USER_EMAILS: Email address(es) for login to the web portal. They will receive temporary passwords.
```
export CDK_INPUT_USER_EMAILS=<EMAILS_SPLIT_BY_COMMA>
```
Update the values with your target AWS account ID and the region where you intend to deploy the demo application.
```
export CDK_DEFAULT_ACCOUNT=<YOUR_ACCOUNT_ID>
export CDK_DEFAULT_REGION=<YOUR_TARGET_REGION> (e.x, us-east-1)
```
CDK_INPUT_OPENSEARCH_CONFIG: Configure the size of the Amazon OpenSearch cluster, accepting either "Dev" or "Prod" as values with a default value set to "Dev".
- Dev: suitable for development or testing environment. (No master node, 1 data node: m4.large.search)
- Prod: suitable for handling large volumes of video data. (3 master nodes: m4.large.search, 2 data nodes: m5.xlarge.search)
```
export CDK_INPUT_OPENSEARCH_CONFIG=<OPENSEARCH_CONFIG> ("Dev" or "Prod")
```

3. Run **deploy-cloudshell.sh** in CloudShell to deploy the application to your AWS account with the parameters defined in step 2.
```
cd deployment
bash ./deploy-cloudshell.sh
```

## Deployment Validation

Once the deployment completes, you can find the website URL in the bash console. You can also find it in the CloudFormation console by checking the output in stack **VideoAnalysisRootStack**.

![CloudFormation stack output](./assets/cloudformation-stack-output.png)

## Running the Guidance
An email with a username and temporary password will be sent to the email(s) you provided in deployment steps. Users can use this information to log in to the web portal.

## Cleanup

When you’re finished experimenting with this solution, clean up your resources by running the command from CloudShell:

```
cdk destroy
```

These commands deletes resources deploying through the solution. 
You can also go to the CloudFormation console, select the VideoAnalysisRootStack stack, and click the Delete button to remove all the resources.

## Known issues
For deployments in regions other than us-east-1, the web UI may not function properly for video uploads. This issue should resolve itself within an hour.

## Notices

*Customers are responsible for making their own independent assessment of the information in this Guidance. This Guidance: (a) is for informational purposes only, (b) represents AWS current product offerings and practices, which are subject to change without notice, and (c) does not create any commitments or assurances from AWS and its affiliates, suppliers or licensors. AWS products or services are provided “as is” without warranties, representations, or conditions of any kind, whether express or implied. AWS responsibilities and liabilities to its customers are controlled by AWS agreements, and this Guidance is not part of, nor does it modify, any agreement between AWS and its customers.*

## Authors

Lana Zhang (lanaz@amazon.com)
