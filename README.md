# Media Analysis and Policy Evaluation Framework

Customers in Media & Entertainment, Advertising, and Social Media require an effective solution for extracting metadata from media assets such as video, audio, and images. They also need flexible analysis options, including summarization and policy evaluation. This solution serves as a generic framework allowing users to streamline the extraction and evaluation processes.

This solution is designed for two personas: business users and builders. 
- Business users who seek to utilize a ready-made tool for media asset analysis and policy evaluation can take advantage of the built-in UI. They can upload videos, manage customized policy documents using Bedrock Knowledge Base, and apply flexible policy evaluation. 
- For builders in search of a modular solution for video extraction, user/face mapping, and LLMs analysis, they can deploy the backend micro-service independently and integrate it into their workflow.

This tool can be utilized for comprehensive video content analysis, encompassing but not limited to:
- Content Moderation
- DEI detection
- Customized policy evaluation
- IAB classfication
- Video summarization

## Supported AWS regions
The solution requires AWS AI services, including Amazon Bedrock, Amazon Rekognition and Amazon Transcribe, which are available in certain regions. Please choose one of the below AWS regions to deploy the CDK package.

|||||
---------- | ---------- | ---------- | ---------- |
US | us-east-1 (N. Virginia) | ||

## Prerequisites

- If you don't have the AWS account administrator access, ensure your [IAM](https://aws.amazon.com/iam/) role/user has permissions to create and manage the necessary resources and components for this solution.
- In Amazon Bedrock, make sure you have access to the required models. Refer to [this instruction](https://catalog.workshops.aws/building-with-amazon-bedrock/en-US/prerequisites/bedrock-setup) for detail.

## Install environment dependencies and set up authentication

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

![Open CloudShell](static/cloudshell.png)

If your CloudShell instance has older dependency libraries like npm or pip, it may cause deployment errors. To resolve this, click 'Actions' and choose 'Delete AWS CloudShell Home Directory' to start a fresh instance.

### Deploy the CDK package using CloudShell
1. Clone the source code from GitHub repo 
```
git clone https://github.com/aws-samples/media-analysis-policy-evaluation-framework.git
cd media-analysis-policy-evaluation-framework
```

2. Set up environment variables 

Set environment variables as input parameters for the CDK deployment package:

CDK_INPUT_USER_EMAILS: Email address(es) for login to the web portal. They will receive temporary passwords.
```
export CDK_INPUT_USER_EMAILS=EMAILS_SPLIT_BY_COMMA
```
Update the values with your target AWS account ID and the region where you intend to deploy the demo application.
```
export CDK_DEFAULT_ACCOUNT=YOUR_ACCOUNT_ID
export CDK_DEFAULT_REGION=YOUR_TARGET_REGION (e.x, us-east-1)
```
CDK_INPUT_OPENSEARCH_CONFIG: Configure the size of the Amazon OpenSearch cluster, accepting either "Dev" or "Prod" as values.
- Dev: suitable for development or testing environment. (No master node, 1 data node: m5.large.search)
- Prod: suitable for handling large volumes of video data. (3 master nodes: m4.small.search, 2 data nodes: m5.large.search=2)
```
export CDK_INPUT_OPENSEARCH_CONFIG=OPENSEARCH_CONFIG ("Dev" or "Prod", default value: "Dev")
```


3. Run **deploy-cloudshell.sh** in CloudShell to deploy the application to your AWS account with the parameters defined in step 2.
```sh
bash deploy-cloudshell.sh
```

### Access the Web Portal
Once the deployment completes, you can find the website URL in the bash console. You can also find it in the CloudFormation console by checking the output in stack **AwsContentAnalysisRootStack**.

An email with a username and temporary password will be sent to the email(s) you provided in step 2. Users can use this information to log in to the web portal.

![CloudFormation stack output](static/cloudformation-stack-output.png)

### Access OpenSearch Dashboard
The solution deployed the OpenSearch service database into a private subnet. End users access the OpenSearch Dashboards via port forwarding in AWS Session Manager, eliminating the need to expose the SSH port to the internet.

![CloudFormation stack output](static/opensearch-vpc-cdk.png)

Run the following command to access OpenSearch Dashboards, after replacing <BastionHostId> and <OpenSearchDomainEndpoint> to the values output by cdk.
```sh
aws ssm start-session --target <BastionHostId> --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters '{"portNumber":["443"],"localPortNumber":["8157"], "host":["<OpenSearchDomainEndpoint>"]}'
```
After starting session, access https://localhost:8157/_dashboards in your browser. Warning may appear because the domain (*.[region].es.amazonaws.com) in the certificate is different from the domain (localhost) you access. Since this does not cause serious problems, continue accessing the site, and you will see OpenSearch Dashboards.

Refer to this instruction on how to install Amazon Session Manager on your local machine: [instruction](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)


## Architecture
The high-level workflow, as illustrated below, comprises a few major steps. 
- The user uploads media content (currently supporting videos). The application initiates pre-processing, extracting image frames from the video, and applies extraction for each image frame using Amazon Rekognition and Amazon Bedrock. 
- It extracts audio transcription using Amazon Transcribe. 
- It applies LLMs analysis based on the metadata extracted from the video. The LLMs analysis stage is flexible and offers a web UI for users to modify the prompts for better accuracy.
![moderator UI](static/workflow.png)

The solution embraces microservice design principles, with frontend and backend services decoupled, allowing each component to be deployed independently as a microservice without dependencies. This architecture enables flexible extension of the solution. For example, adding a new user/face tagging backend service would not impact the policy evaluation service.
![configureation UI](static/guidance-diagram.png)

## Metadata extraction
Extracting metadata from media assets like video and audio is a common requirement for enabling downstream analysis and search capabilities. This solution includes a core module that supports generic metadata extraction from media assets, encompassing both audio transcription and visual metadata extraction. The visual extraction feature adopts a flexible sampling configuration, allowing users to set the sample frequency, with more advanced sampling logic forthcoming. For each image frame, users can apply flexible extraction logic, such as Rekognition label detection, Rekognition moderation, Rekognition celebrity detection, Rekognition text extraction, Bedrock Titan multimodal embedding, and Bedrock Anthropic Claude V3 Sonnet image captioning, with the capability to extend support to additional video frame-level analysis. Audio transcription leverages Amazon Transcribe, providing full transcription and subtitles.

![Extraction Service Architecture](static/extraction-service-architecture.png)

## Custom policy evaluation

Customers need to evaluate their media assets against internal and external policies, which may include standard policies such as Trust & Safety, DEI, and industry-specific or company-specific policies. This solution introduces a flexible approach to managing policy evaluation using Bedrock LLMs. You can manage policy definitions via prompts engineering or by utilizing Bedrock Knowledge Base, a managed RAG (Retrieval Augmented Generation) solution. The demo UI includes a sandbox feature that allows users to flexibly adjust the metadata used for evaluation and review the evaluation results from LLMs.