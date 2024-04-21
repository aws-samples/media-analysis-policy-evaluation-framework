import React from 'react';
import './videoUpload.css'
import { FetchPost } from "../resources/data-provider";
import { Button, Box, Checkbox, Link, FileUpload, Select, Textarea, Wizard, Container, Header, SpaceBetween, Alert, Toggle, ProgressBar, ColumnLayout} from '@cloudscape-design/components';
import { getCurrentUser } from 'aws-amplify/auth';

class VideoUpload extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            status: null, // null, loading, loaded
            alert: null,
            uploadFiles: [],
            numChunks: null,
            uploadedChunks: 0,

            selectedVideoSampleMode: "even",
            selectedVideoSampleIntervalS: null,

            extractionSettingExpand: false,
            enableDetectText: true,
            enableDetectLabel: true,
            enableDetectModeration: true,
            enableDetectCelebrity: true,
            enableTranscription: true,
            enableDetectLogo: true,
            enableImageCaption: true,
            enableSmartSample: true,

            noEvaluation: false,
            evaluationSettingExpand: true,
            selectedEvalTemplate: null,
            selectedBedrockModel: null,
            selectedBedrockKb: null,
            promptsTemplate: null,

            activeStepIndex: 0,
            fileUploadedCounter: false,
            currentUploadingFileName: null,
        };
        this.item = null;
        this.llmParameters = null;
    }

    resetState = () => {
        this.setState({
            status: null, // null, loading, loaded
            alert: null,
            uploadFiles: [],
            numChunks: null,
            uploadedChunks: 0,

            selectedVideoSampleMode: "even",
            selectedVideoSampleIntervalS: {label: this.llmParameters.video_sample_interval[1].name, value:this.llmParameters.video_sample_interval[1].value},

            extractionSettingExpand: false,
            enableDetectText: true,
            enableDetectLabel: true,
            enableDetectModeration: true,
            enableDetectCelebrity: true,
            enableTranscription: true,
            enableDetectLogo: true,
            enableImageCaption: true,
            enableSmartSample: true,

            noEvaluation: false,
            evaluationSettingExpand: true,
            selectedEvalTemplate: null,
            selectedBedrockModel: {label: this.llmParameters.bedrock_model_ids[0].name, value: this.llmParameters.bedrock_model_ids[0].value},
            selectedBedrockKb: null,
            promptsTemplate: null,

            activeStepIndex: 0,
            fileUploadedCounter: false,
            currentUploadingFileName: null
        });
        this.uploadTimer = null;
    }

    async componentDidMount() {
        if (this.llmParameters === null) {
            fetch('./llm-eval-template.json')
            .then(response => response.json())
            .then(data => {
                this.llmParameters = data;
                this.setState({
                    selectedVideoSampleIntervalS: {label: data.video_sample_interval[1].name, value:data.video_sample_interval[1].value},
                    selectedBedrockModel: {label: data.bedrock_model_ids[0].name, value: data.bedrock_model_ids[0].value}
                });
            })
            .catch(error => {
                console.error('Error fetching llm template:', error);
            });
        }
    }


    handleNavigate = e => {
        if(e.detail.requestedStepIndex === 1) {
            if (this.state.uploadFiles.length === 0) {
                this.setState({alert: 'Please select a video file to continue.'});
                return;
            }
        }
        else if(e.detail.requestedStepIndex === 3) {
            if(!this.state.noEvaluation) {
                if (this.state.promptsTemplate === undefined || this.state.promptsTemplate === null || this.state.promptsTemplate.length === 0) {
                    this.setState({alert: "Choose a template or enter your prompt. Check 'Skip evaluation' to bypass LLMs policy assessment."});
                    return;
                }
                if(this.state.selectedBedrockModel === undefined || this.state.selectedBedrockModel === null || this.state.selectedBedrockModel.label === undefined || this.state.selectedBedrockModel.label === null) {
                    this.setState({alert: "Select a Bedrock LLMs model to evaluate."});
                    return;
                }
            }
        }
        this.setState({aler: null, activeStepIndex: e.detail.requestedStepIndex})
    }

    async handleSumbitTask () {
        for (let i = 0; i < this.state.uploadFiles.length; i++) {
            this.generatePresignedUrls(this.state.uploadFiles[i]);
        }
    }

    generatePresignedUrls (file) {
        // Wait if other file is uploading
        if (this.state.currentUploadingFileName !== null)
            setTimeout(() => {
                console.log(`Waiting`);
            }, 1000); 

        this.setState({currentUploadingFileName: file.name})
        //console.log(fileName);
        const fileSize = file.size;
        const numChunks = Math.ceil(fileSize / (5 * 1024 * 1024));
        this.setState({numChunks: numChunks});  

        this.setState({status: "generateurl"});
        FetchPost("/extraction/video/manage-s3-presigned-url", {"FileName": file.name, "NumParts": numChunks, "Action": "create"})
            .then((data) => {
                  //console.log(resp);
                  if (data.statusCode !== 200) {
                      this.setState( {status: null, alert: data.body});
                  }
                  else {
                      if (data.body !== null) {
                          return this.uploadFile({
                            taskId: data.body.TaskId,
                            uploadS3Url: data.body.UploadUrl,
                            uploadedS3Bucket: data.body.S3Bucket,
                            uploadedS3KeyVideo: data.body.S3Key,
                            status: null,
                            alert: null,
                            uploadId: data.body.UploadId,
                            uploadPartUrls: data.body.UploadPartUrls,
                            numChunks: numChunks
                        })
                      }
                  }
              })
              .catch((err) => {
                  this.setState( {status: null, alert: err.message});
              });  
    }

    async submitTask (urlResp) {
        //console.log(urlResp);
        var payload = {
            "TaskId": urlResp.taskId,
            "FileName": this.state.uploadFiles[0].name,
            "RequestBy": null,
            "Video": {
              "S3Object": {
                "Bucket": urlResp.uploadedS3Bucket,
                "Key": urlResp.uploadedS3KeyVideo,
              },
            },
            "PreProcessSetting": {
              "SampleMode": this.state.selectedVideoSampleMode,
              "SampleIntervalS": this.state.selectedVideoSampleIntervalS.value,
              "SmartSample": this.state.enableSmartSample,
            },
            "ExtractionSetting": {
              "Transcription": this.state.enableTranscription,
              "DetectLabel": this.state.enableDetectLabel,
              "DetectText": this.state.enableDetectText,
              "DetectCelebrity": this.state.enableDetectCelebrity,
              "DetectModeration": this.state.enableDetectModeration,
              "DetectLogo": this.state.enableDetectLogo,
              "ImageCaption": this.state.enableImageCaption,
              "CustomModerationArn": null,
            },
            "EvaluationSetting": {}
          }
        //console.log(payload)
        if (!this.state.noEvaluation) {
            payload["EvaluationSetting"] = {
              "PromptsTemplate": this.state.promptsTemplate,
              "KnowledgeBaseId": this.state.selectedBedrockKb !== null?this.state.selectedBedrockKb.value: null,
              "LLMsModelId": this.state.selectedBedrockModel !== null?this.state.selectedBedrockModel.value: null
            }
        }

        this.setState({status: "loading"});
        const { username } = getCurrentUser().then((username) => {
            payload["RequestBy"] = username.username;
            // Start task
            FetchPost('/extraction/video/start-task', payload)
                .then((data) => {
                    this.setState({currentUploadingFileName: null})
                    var resp = data.body;
                    if (data.statusCode !== 200) {
                        //console.log(data.body);
                        this.setState( {status: null, alert: data.body});
                    }
                    else {
                        if (this.state.fileUploadedCounter == this.state.uploadFiles.length) {
                            this.resetState(null);
                            this.props.onSubmit();
                        }
                    }
                })
                .catch((err) => {
                    this.setState({currentUploadingFileName: null})
                    //console.log(err.message);
                    this.setState( {status: null, alert: err.message});
                });                      
            }
        )

    }

    async uploadFile(urlResp) {
        this.setState({status: "uploading"});
        let file = this.state.uploadFiles[0];
        if (urlResp.uploadPartUrls === null || urlResp.uploadPartUrls.length === 0) return;
            //console.log(this.state);
            // Upload each part to the corresponding pre-signed URL
            const uploadPromises = [];
            let parts = [];
            for (let i = 0; i < urlResp.numChunks; i++) {
              const startByte = i * (5 * 1024 * 1024);
              const endByte = Math.min(startByte + (5 * 1024 * 1024), file.size);
              const chunk = file.slice(startByte, endByte);
        
              const formData = new FormData();
              formData.append('file', chunk);
        
              let retries = 0;
              const uploadPromise = await fetch(urlResp.uploadPartUrls[i], {
                method: 'PUT',
                headers: {'Content-Type': ''},
                body: chunk,
              }).then((response) => {
                if (response.ok) {
                    //console.log(response.headers.get('Etag'));
                    parts.push({'ETag': response.headers.get('Etag'), 'PartNumber': i + 1})
                    this.setState({uploadedChunks: this.state.uploadedChunks + 1})
                    //console.log("uploaded", i, parts);
                    //console.log(this.state);
                }
              });
              uploadPromises.push(uploadPromise);
            };

            await Promise.all(uploadPromises).then(() => {
                    this.setState({fileUploadedCounter: this.state.fileUploadedCounter + 1});
                    //console.log("all completed");
                }
            ).then((response) => {
                // Call complete endpoint
                let payload = {
                    "TaskId": urlResp.taskId,
                    "FileName": file.name, 
                    "MultipartUpload": parts, 
                    "UploadId": urlResp.uploadId, 
                    "Action": "complete"
                };
                FetchPost("/extraction/video/manage-s3-presigned-url", payload)
                .then((result) => {
                    if (result.statusCode !== 200) {
                        this.setState( {alert: result.body});
                    }
                    else {
                        this.setState( {alert: null});
                        this.submitTask(urlResp);
                    }   
                })
                .catch((err) => {
                    this.setState( {alert: err.message});
                })
            });
    }

    handelFileChange = (e) => {
        const supportedFormats = ['avi', 'mov', 'mp4'];
        const filteredFiles = [];
        const invalidFiles= [];

        for (let i = 0; i < e.detail.value.length; i++) {
            const fileName = e.detail.value[i].name;
            const fileExtension = fileName.split('.').pop().toLowerCase();
    
            if (supportedFormats.includes(fileExtension)) {
                filteredFiles.push(e.detail.value[i]);
            } else {
                invalidFiles.push(fileName);
            }
        }
        this.setState({
            uploadFiles: filteredFiles,
            alert: invalidFiles.length === 0?null: `File(s) "${invalidFiles.join(', ')}" not in supported format (avi, mov, mp4) and has been removed.`
        });
    }

    render() {
        return (
            <div className="videoupload">
                {this.state.alert !== null?
                <div><Alert statusIconAriaLabel="Warning" type="warning">{this.state.alert}</Alert><br/></div>
                :<div/>}
                <Wizard
                    i18nStrings={{
                        stepNumberLabel: stepNumber =>
                        `Step ${stepNumber}`,
                        collapsedStepsLabel: (stepNumber, stepsCount) =>
                        `Step ${stepNumber} of ${stepsCount}`,
                        skipToButtonLabel: (step, stepNumber) =>
                        `Skip to ${step.title}`,
                        navigationAriaLabel: "Steps",
                        cancelButton: "Cancel",
                        previousButton: "Previous",
                        nextButton: "Next",
                        submitButton: "Upload video and start analysis",
                        optional: "optional"
                    }}
                    onNavigate={this.handleNavigate}
                    onCancel={()=>{this.resetState();this.props.onCancel(null);}}
                    onSubmit={()=>this.handleSumbitTask()}
                    isLoadingNextStep={this.state.status !== null}
                    activeStepIndex={this.state.activeStepIndex}
                    steps={[
                        {
                            title: "Select a video file",
                            description:
                                "Upload a video file from your local disk. Supported format: .mp4, .mov, .avi",
                            content: (
                                <Container
                                    header={
                                        <Header variant="h2">
                                        Upload a video file
                                        </Header>
                                    }
                                >
                                <FileUpload
                                    onChange={this.handelFileChange}
                                    value={this.state.uploadFiles}
                                    i18nStrings={{
                                    uploadButtonText: e =>
                                        e ? "Choose files" : "Choose file",
                                    dropzoneText: e =>
                                        e
                                        ? "Drop files to upload"
                                        : "Drop file to upload",
                                    removeFileAriaLabel: e =>
                                        `Remove file ${e + 1}`,
                                    limitShowFewer: "Show fewer files",
                                    limitShowMore: "Show more files",
                                    errorIconAriaLabel: "Error"
                                    }}
                                    showFileLastModified
                                    showFileSize
                                    showFileThumbnail
                                    tokenLimit={3}
                                    multiple={false}
                                    constraintText="Supported video format: .mp4, .mov, .avi"
                                />
                                </Container>                                
                            )
                        },
                        {
                        title: "Extraction settings",
                        content: (
                            <Container
                            header={
                                <Header variant="h2">
                                Extraction settings
                                </Header>
                            }
                            >
                            <SpaceBetween direction="vertical" size="l">
                                <Container>
                                <Box variant="awsui-key-label">Select a sample </Box>
                                {this.state.selectedVideoSampleIntervalS !== null?
                                <Select 
                                        selectedOption={this.state.selectedVideoSampleIntervalS}
                                        onChange={({ detail }) => {
                                            this.setState({selectedVideoSampleIntervalS: detail.selectedOption})
                                        }}
                                        options={this.llmParameters.video_sample_interval.map(item => ({
                                            label: item.name, value: item.value
                                        }))}
                                        />:<div/>}
                                        <br/>
                                        <Toggle checked={this.state.enableSmartSample} onChange={(e)=>this.setState({enableSmartSample: e.detail.checked})}>
                                        Enable smart sampling (reduce processing time and costs by ignoring similar images)
                                        </Toggle>
                                </Container>
                                <Container>
                                <Box variant="awsui-key-label">Transcribe audio to text</Box><br/>
                                <Toggle checked={this.state.enableTranscription} onChange={(e)=>this.setState({enableTranscription: e.detail.checked})}>
                                    Transcribe audio (Amazon Transcribe)
                                </Toggle>
                                </Container>
                                <Container>
                                    <Box variant="awsui-key-label">Analysis image frames</Box><br/>
                                    <ColumnLayout columns={2}>
                                        <Checkbox checked={this.state.enableDetectLabel} onChange={(e)=>this.setState({enableDetectLabel: e.detail.checked})}>
                                            Detect Label (Amazon Rekognition) 
                                        </Checkbox>
                                        <Checkbox checked={this.state.enableDetectModeration} onChange={(e)=>this.setState({enableDetectModeration: e.detail.checked})}>
                                            Detect Moderation (Amazon Rekognition)
                                        </Checkbox>
                                        <Checkbox checked={this.state.enableDetectText} onChange={(e)=>this.setState({enableDetectText: e.detail.checked})}>
                                            Detect Text (Amazon Rekognition)
                                        </Checkbox>
                                        <Checkbox checked={this.state.enableDetectCelebrity} onChange={(e)=>this.setState({enableDetectCelebrity: e.detail.checked})}>
                                            Detect Celebrity (Amazon Rekognition)
                                        </Checkbox>
                                        {/* <Checkbox checked={this.state.enableDetectLogo} onChange={(e)=>this.setState({enableDetectLogo: e.detail.checked})}>
                                            Detect Logo (Amazon Titan Anthropic Claude V3 Sonnet)
                                        </Checkbox> */}
                                        <Checkbox checked={this.state.enableImageCaption} onChange={(e)=>this.setState({enableImageCaption: e.detail.checked})}>
                                            Image description (Amazon Titan Anthropic Claude V3 Haiku)
                                        </Checkbox>
                                    </ColumnLayout>
                                </Container>
                            </SpaceBetween>
                            </Container>
                        ),
                        },
                        // {
                        // title: "LLMs evaluation settings",
                        // content: (
                        //     <Container
                        //     header={
                        //         <Header variant="h2">
                        //         LLMs evaluation settings
                        //         </Header>
                        //     }
                        //     >
                        //         <Toggle 
                        //             checked={this.state.noEvaluation} 
                        //             onChange={(e) => {
                        //                 this.setState({noEvaluation: e.detail.checked});
                        //             }
                        //             }>
                        //             Skip evaluation
                        //         </Toggle>                

                        //             <br/>
                        //             Select a predefined policy template:
                        //             {this.state.selectedBedrockModel !== null?
                        //             <Select
                        //                 selectedOption={this.state.selectedEvalTemplate}
                        //                 onChange={({ detail }) =>
                        //                     {
                        //                         //console.log(detail.selectedOption.temp);
                        //                         this.setState({
                        //                             selectedEvalTemplate: detail.selectedOption,
                        //                             promptsTemplate: detail.selectedOption.temp,
                        //                             selectedBedrockModel: {label:detail.selectedOption.modelId, value: detail.selectedOption.modelId},
                        //                         })
                        //                         if (detail.kbId !== undefined && detail.kbId !== null && detail.kbId.length > 0) 
                        //                             this.setState({selectedBedrockKb: {label:detail.kbId}})
                        //                     }
                        //                 }
                        //                 options={this.llmParameters.templates.filter(item => item.type === "evaluation").map(item => ({
                        //                     label: item.name,
                        //                     //value: item.id,
                        //                     temp: item.prompts_template,
                        //                     modelId: item.bedrock_llm_model_id,
                        //                     kbId: item.bedrock_knowledge_base_id
                        //                 }))}
                        //                 />:<div/>}
                        //             <br/>
                        //             Edit the prompts template:
                        //             <Textarea rows={20}
                        //                 onChange={({ detail }) => {
                        //                     //console.log(detail);
                        //                     this.setState({promptsTemplate: detail.value});
                        //                 }
                        //                 }
                        //                 value={this.state.promptsTemplate}
                        //                 disableBrowserAutocorrect
                        //                 placeholder="LLMs prompts template with placeholders"
                        //                 />
                        //             <br/>
                        //             Select a Bedrock LLMs model for evaluation:
                        //             {this.llmParameters !== null?
                        //             <Select 
                        //                 selectedOption={this.state.selectedBedrockModel}
                        //                 onChange={({ detail }) => {
                        //                     this.setState({selectedBedrockModel: detail.selectedOption})
                        //                 }}
                        //                 options={this.llmParameters.bedrock_model_ids.map(item => ({
                        //                     label: item.name, value: item.value
                        //                 }))}
                        //                 />:<div/>}
                        //             <br/>
                        //             <div style={{display:"none"}}>
                        //             Choose a Bedrock Knowledge Base ID: 
                        //             (This is necessary for dynamically injecting policies managed in the Bedrock Knowledge Base and requires the use of the "##KB_POLICY##" placeholder in prompts template.)       
                        //             {this.llmParameters !== null?
                        //             <Select
                        //                 selectedOption={this.state.selectedBedrockKb}
                        //                 onChange={({ detail }) => this.setState({selectedBedrockKb: detail.selectedOption})}
                        //                 options={this.llmParameters.bedrock_knowledge_bases.map(item => ({
                        //                     label: item.name,
                        //                     value: item.value
                        //                 }))}
                        //                 />:<div/>}
                        //             </div>
                        //     </Container>
                        // ),
                        
                        // },
                        {
                            title: "Upload vidoes and start analysis",
                            info: <Link variant="info">Info</Link>,
                            description:
                                "Confirm the videos below and start analysis",
                            content: (
                                <Container
                                    header={
                                        <Header variant="h2">
                                        Upload a video file
                                        </Header>
                                    }
                                >
                                    {this.state.uploadFiles.map((file,i)=>{
                                        return <div key={file + i.toString()} className='uploadedfile'>
                                            <div className='filename'>{file.name}</div>
                                            <div className='attribute'>{(file.size / (1024 * 1024)).toFixed(2)} MB</div>
                                            {this.state.currentUploadingFileName === file.name &&
                                                <div>
                                                    <ProgressBar
                                                        value={this.state.numChunks && this.state.uploadedChunks?(this.state.uploadedChunks/this.state.numChunks)*100:0}
                                                        status={this.state.numChunks && this.state.uploadedChunks && this.state.uploadedChunks === this.state.numChunks? "success":"in-progress"}
                                                        label="Uploading file"
                                                    />
                                                    <br/>
                                                </div>
                                            }                                        
                                        </div>
                                    })}

                                    
                                </Container>
                            )
                        },
                    ]}
                />

            </div>
        );
    }
}

export default VideoUpload;